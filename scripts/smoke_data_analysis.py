"""Live smoke for the data-analysis methodology integration.

Boots a real uvicorn subprocess against an isolated `DA_AGENT_HOME=$(mktemp -d)`,
uploads the standard Singapore Retail Sales Index xlsx as KB, then drives a
3-phase script that exercises the data-analysis skill's trigger gate and
target-chain output:

  Phase A — simple lookup ("how many rows?")          -> NO skill, NO output
  Phase B — analytical "why" + asks for PowerPoint    -> AskUserQuestion(Target)
                                                          + .pptx deliverable
  Phase C — explicit Target=New .docx + Source=N/A    -> .docx deliverable

Phase B auto-responds to AskUserQuestion mid-stream via the FE-facing
`/sessions/{sid}/interactions/{tu_id}/respond` endpoint, mirroring
`scripts/smoke_output_mechanism.py`.

Pre-req: `ANTHROPIC_API_KEY` (or whatever credential the configured model uses)
must be available. Configurable via `DA_AGENT_MODEL`.

Run:
    uv run python scripts/smoke_data_analysis.py
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

SOURCE_XLSX = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "output"
    / "Singapore Retail Sales Index.xlsx"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_healthz(port: int, timeout: float = 30.0) -> None:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            last_err = e
            time.sleep(0.3)
    raise RuntimeError(f"server never became healthy: {last_err}")


def _post_json(port: int, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read()
        if r.status == 204 or not body:
            return {}
        return json.loads(body)


def _delete(port: int, path: str) -> int:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def _multipart_upload(port: int, path: str, file_path: Path, mime: str) -> dict:
    boundary = f"----smoke{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode()
    body += file_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _stream_turn(
    port: int,
    sid: str,
    prompt: str,
    *,
    deadline_s: float = 600.0,
    on_interaction: object | None = None,
    body_extra: dict | None = None,
) -> list[dict]:
    """POST a message; if an `interaction.requested` event arrives, invoke
    the `on_interaction(event)` callback to drive the response (callback is
    expected to POST to /interactions/<id>/respond synchronously).

    Returns the full event list (including any events emitted after the
    interaction is resolved).
    """
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/sessions/{sid}/messages",
        data=json.dumps({"prompt": prompt, **(body_extra or {})}).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    events: list[dict] = []
    deadline = time.monotonic() + deadline_s
    with urllib.request.urlopen(req, timeout=deadline_s) as r:
        buf: list[str] = []
        for raw in r:
            if time.monotonic() > deadline:
                raise TimeoutError("SSE drain timed out")
            line = raw.decode("utf-8").rstrip("\n")
            if line == "":
                rec = {}
                for entry in buf:
                    if entry.startswith("data:"):
                        try:
                            rec = json.loads(entry[5:].strip())
                        except json.JSONDecodeError:
                            pass
                if rec:
                    events.append(rec)
                    if rec.get("type") == "interaction.requested" and on_interaction:
                        on_interaction(rec)
                buf.clear()
            else:
                buf.append(line)
            if events and events[-1].get("type") == "result":
                break
    return events


def _wait_kb_ready(port: int, kb_id: str, *, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/kb/files/{kb_id}", timeout=15
        ) as r:
            meta = json.loads(r.read())
        if meta["status"] == "READY":
            return
        if meta["status"] == "FAILED":
            raise RuntimeError(f"kb {kb_id} FAILED: {meta.get('error')}")
        time.sleep(0.5)
    raise TimeoutError(f"kb {kb_id} never reached READY")


def _summarise(events: list[dict], label: str) -> None:
    from collections import Counter

    types = Counter(e.get("type") for e in events)
    print(f"  [{label}] {len(events)} events: {dict(types)}")


def _has_target_question(events: list[dict]) -> bool:
    """Return True if any `interaction.requested` event carries a sub-question
    with header == 'Target' (the §8.2 target-chain prompt)."""
    for ev in events:
        if ev.get("type") != "interaction.requested" or ev.get("kind") != "question":
            continue
        for q in ev.get("questions") or []:
            if q.get("header") == "Target":
                return True
    return False


def _ask_user_question_fired(events: list[dict]) -> bool:
    """Did the model invoke AskUserQuestion at all?

    We check both the `tool.use` channel (raw SDK signal) and the higher-level
    `interaction.requested` event (which AgentUI emits when AskUserQuestion is
    invoked) — either suffices.
    """
    for ev in events:
        if ev.get("type") == "tool.use" and ev.get("name") == "AskUserQuestion":
            return True
        if ev.get("type") == "interaction.requested" and ev.get("kind") == "question":
            return True
    return False


def _todo_write_with_phases(events: list[dict]) -> dict | None:
    """Return the first `tool.use` of TodoWrite whose input mentions 'Phase'."""
    for ev in events:
        if ev.get("type") != "tool.use" or ev.get("name") != "TodoWrite":
            continue
        if "Phase" in json.dumps(ev.get("input") or {}):
            return ev
    return None


def main() -> int:
    if not SOURCE_XLSX.exists():
        print(f"✗ source xlsx missing: {SOURCE_XLSX}")
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    data_root = Path(tempfile.mkdtemp(prefix="da-agent-data-analysis-smoke-"))
    port = _free_port()
    print(f"→ smoke: data_root={data_root}  port={port}")

    env = dict(os.environ)
    env["DA_AGENT_HOME"] = str(data_root)
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "da_agent.cli",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(repo_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    failures: list[str] = []
    try:
        try:
            _wait_healthz(port)
            print("✓ server healthy")

            kb_meta = _multipart_upload(
                port,
                "/kb/files",
                SOURCE_XLSX,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            kb_id = kb_meta["id"]
            print(f"✓ kb uploaded: {kb_id}")
            _wait_kb_ready(port, kb_id)
            print(f"✓ kb {kb_id} READY")

            sess = _post_json(port, "/sessions", {"name": "smoke-data-analysis"})
            sid = sess["id"]
            print(f"✓ session: {sid}")

            outputs_dir = data_root / "outputs"

            # ---------------------------------------------------------------
            # Phase A — simple lookup must NOT trigger the data-analysis skill
            # ---------------------------------------------------------------
            print("\n=== Phase A — simple lookup (no skill, no output) ===")
            events_a = _stream_turn(
                port,
                sid,
                "File KB vừa upload có tổng cộng bao nhiêu dòng? Trả lời ngắn gọn.",
                deadline_s=600.0,
                body_extra={"kb_scope": [kb_id]},
            )
            _summarise(events_a, "A")

            text_present = any(
                e.get("type") in ("assistant.text", "assistant.text.delta")
                and (e.get("text") or "").strip()
                for e in events_a
            )
            if not text_present:
                failures.append("Phase A: agent produced no text answer")
            if _ask_user_question_fired(events_a):
                offending = next(
                    (
                        e
                        for e in events_a
                        if e.get("type") == "interaction.requested"
                        or (
                            e.get("type") == "tool.use"
                            and e.get("name") == "AskUserQuestion"
                        )
                    ),
                    None,
                )
                failures.append(
                    "Phase A: AskUserQuestion fired on a simple count question — "
                    f"trigger gate too loose (event={offending})"
                )
            phase_todo = _todo_write_with_phases(events_a)
            if phase_todo is not None:
                failures.append(
                    "Phase A: TodoWrite enumerated multi-phase plan on a simple "
                    f"count question (event={phase_todo})"
                )
            if any(e.get("type") == "output.created" for e in events_a):
                failures.append(
                    "Phase A: unexpected output.created on a simple count question"
                )

            # ---------------------------------------------------------------
            # Phase B — analytical "why" + explicit PowerPoint deliverable
            # ---------------------------------------------------------------
            print(
                "\n=== Phase B — analytical 'why' + .pptx (expect Target question) ==="
            )

            def _answer_pptx(ev: dict) -> None:
                tu_id = ev["tool_use_id"]
                # Build answers per sub-question — Source may or may not be
                # asked; reply to whichever headers the agent presented.
                answers: list[dict] = []
                for q in ev.get("questions") or []:
                    h = q.get("header")
                    if h == "Target":
                        answers.append({"header": "Target", "selected": ["New .pptx"]})
                    elif h == "Source":
                        answers.append({"header": "Source", "selected": ["N/A"]})
                    else:
                        answers.append({"header": h or "", "selected": []})
                _post_json(
                    port,
                    f"/sessions/{sid}/interactions/{tu_id}/respond",
                    {"answers": answers},
                )

            events_b = _stream_turn(
                port,
                sid,
                "Hãy phân tích sâu xu hướng và tìm nguyên nhân của các biến động "
                "trong dữ liệu này. Tạo một báo cáo PowerPoint tóm tắt các phát hiện.",
                deadline_s=1500.0,
                on_interaction=_answer_pptx,
                body_extra={"kb_scope": [kb_id]},
            )
            _summarise(events_b, "B")

            if not _has_target_question(events_b):
                failures.append(
                    "Phase B: AskUserQuestion(Target) was NOT raised — the §8.2 "
                    "target-chain step was skipped on an analytical request"
                )

            standalone_pptx = [
                e
                for e in events_b
                if e.get("type") == "output.created"
                and e.get("kind") == "standalone"
                and (e.get("title") or "").lower().endswith(".pptx")
            ]
            if not standalone_pptx:
                failures.append(
                    "Phase B: no output.created with kind='standalone' and "
                    ".pptx filename — deliverable was never written"
                )
            else:
                ev = standalone_pptx[0]
                output_id = ev.get("output_id")
                on_disk = outputs_dir / (output_id or "") / "output.pptx"
                if not on_disk.exists():
                    failures.append(f"Phase B: expected pptx not on disk at {on_disk}")
                elif on_disk.stat().st_size == 0:
                    failures.append(f"Phase B: pptx at {on_disk} is empty")

            # Soft check — log a warning but do NOT fail.
            todo_b = _todo_write_with_phases(events_b)
            todo_phase_count = 0
            if todo_b is not None:
                todos = (todo_b.get("input") or {}).get("todos") or []
                todo_phase_count = sum(
                    1
                    for t in todos
                    if "Phase" in (t.get("content") or t.get("activeForm") or "")
                )
            if todo_phase_count < 4:
                print(
                    f"  ⚠ Phase B soft-check: TodoWrite enumerated only "
                    f"{todo_phase_count} 'Phase' entries (expected ≥4 for the "
                    "6-phase methodology, but we don't fail on this)"
                )

            # ---------------------------------------------------------------
            # Phase C — explicit Target=New .docx, Source=N/A
            # ---------------------------------------------------------------
            print("\n=== Phase C — explicit Target=New .docx (expect .docx output) ===")

            def _answer_docx(ev: dict) -> None:
                tu_id = ev["tool_use_id"]
                answers: list[dict] = []
                for q in ev.get("questions") or []:
                    h = q.get("header")
                    if h == "Target":
                        answers.append({"header": "Target", "selected": ["New .docx"]})
                    elif h == "Source":
                        answers.append({"header": "Source", "selected": ["N/A"]})
                    else:
                        answers.append({"header": h or "", "selected": []})
                _post_json(
                    port,
                    f"/sessions/{sid}/interactions/{tu_id}/respond",
                    {"answers": answers},
                )

            events_c = _stream_turn(
                port,
                sid,
                "Tạo một báo cáo Word .docx tóm tắt các sheets có trong file KB này, "
                "ghi rõ tên cột chính của mỗi sheet. Target = New .docx, Source = N/A.",
                deadline_s=600.0,
                on_interaction=_answer_docx,
                body_extra={"kb_scope": [kb_id]},
            )
            _summarise(events_c, "C")

            standalone_docx = [
                e
                for e in events_c
                if e.get("type") == "output.created"
                and e.get("kind") == "standalone"
                and (e.get("title") or "").lower().endswith(".docx")
            ]
            if not standalone_docx:
                failures.append(
                    "Phase C: no output.created with kind='standalone' and "
                    ".docx filename — deliverable was never written"
                )
            else:
                ev = standalone_docx[0]
                output_id = ev.get("output_id")
                on_disk = outputs_dir / (output_id or "") / "output.docx"
                if not on_disk.exists():
                    failures.append(f"Phase C: expected docx not on disk at {on_disk}")
                elif on_disk.stat().st_size == 0:
                    failures.append(f"Phase C: docx at {on_disk} is empty")

            _delete(port, f"/sessions/{sid}")
        except Exception as exc:
            failures.append(f"smoke crashed mid-flow: {type(exc).__name__}: {exc}")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if not failures:
            shutil.rmtree(data_root, ignore_errors=True)
        else:
            print(f"\n⚠ data_root preserved for inspection: {data_root}")

    print()
    if failures:
        print("✗ SMOKE FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(
        "✓ SMOKE PASSED — data-analysis methodology integration green across 3 phases."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
