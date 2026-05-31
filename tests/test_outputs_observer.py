"""Pure-unit tests for OutputsObserver (spec §8.2).

Phase C 2026-05-31 (Golden Rule 4 broken per user approval): the observer
only emits `standalone` detections under the per-session layout

    outputs/<session_id>/<out_id>/<filename>

The `kb_version` and `attachment_version` branches are DEPRECATED — they
remain in code for type stability but `_classify` returns None for any path
under `kb_dir` or `attachments_dir`. KB-bound and attachment-bound writes are
now routed through the standalone layout via `_resolve_output_target`.
"""

from __future__ import annotations

import pytest

from da_agent.outputs import OutputDetection, OutputsObserver

# Fixed sid used by every test that constructs an observer. We keep it
# constant so assertions can hard-code the expected session-scoped path.
SID = "sess_test_abc"


@pytest.fixture
def dirs(tmp_path):
    outputs_dir = tmp_path / "outputs"
    kb_dir = tmp_path / "kb"
    attachments_dir = tmp_path / "attachments"
    outputs_dir.mkdir()
    (outputs_dir / SID).mkdir()
    kb_dir.mkdir()
    attachments_dir.mkdir()
    return outputs_dir, kb_dir, attachments_dir


@pytest.fixture
def make_observer(dirs):
    outputs_dir, kb_dir, attachments_dir = dirs

    def _make():
        events: list[OutputDetection] = []
        obs = OutputsObserver(
            outputs_dir, SID, kb_dir, attachments_dir, on_detect=events.append
        )
        return obs, events

    return _make


def test_write_under_outputs_dir_with_out_prefix_fires(dirs, make_observer):
    outputs_dir, _, _ = dirs
    obs, events = make_observer()

    file_path = outputs_dir / SID / "out_abc" / "report.xlsx"
    obs.observe_tool_use("u1", "Write", {"file_path": str(file_path)})
    obs.observe_tool_result("u1", "ok", False)

    assert len(events) == 1
    det = events[0]
    assert det.kind == "standalone"
    assert det.output_id == "out_abc"
    assert det.filename == "report.xlsx"


def test_tool_result_with_is_error_does_not_fire(dirs, make_observer):
    outputs_dir, _, _ = dirs
    obs, events = make_observer()

    obs.observe_tool_use(
        "u1", "Write", {"file_path": str(outputs_dir / SID / "out_abc" / "x.xlsx")}
    )
    obs.observe_tool_result("u1", "permission denied", True)

    assert events == []


def test_bash_redirect_outside_known_roots_does_not_fire(dirs, make_observer):
    obs, events = make_observer()

    obs.observe_tool_use("u1", "Bash", {"command": "echo hi > /tmp/x.txt"})
    obs.observe_tool_result("u1", "", False)

    assert events == []


def test_bash_redirect_under_session_outputs_fires_standalone(dirs, make_observer):
    """A `>` redirect into outputs/<sid>/<out_*>/ classifies as standalone."""
    outputs_dir, _, _ = dirs
    obs, events = make_observer()

    target = outputs_dir / SID / "out_xyz" / "report.xlsx"
    obs.observe_tool_use(
        "u1",
        "Bash",
        {"command": f"python script.py --output {target}"},
    )
    obs.observe_tool_result("u1", "", False)

    assert len(events) == 1
    det = events[0]
    assert det.kind == "standalone"
    assert det.output_id == "out_xyz"
    assert det.filename == "report.xlsx"


def test_kb_version_now_returns_none_deprecated(dirs, make_observer):
    """DEPRECATED 2026-05-31: KB-bound writes no longer emit detections.

    Phase C routes them through the standalone layout instead, so the
    observer must return None for any path under `kb_dir`.
    """
    _, kb_dir, _ = dirs
    obs, events = make_observer()

    target = kb_dir / "kb_xyz" / "versions" / "v_curr.xlsx"
    obs.observe_tool_use(
        "u1",
        "Bash",
        {"command": f"python script.py --output {target}"},
    )
    obs.observe_tool_result("u1", "", False)

    assert events == []


def test_write_under_outputs_dir_without_out_prefix_does_not_fire(dirs, make_observer):
    outputs_dir, _, _ = dirs
    obs, events = make_observer()

    file_path = outputs_dir / SID / "some_random_dir" / "file.xlsx"
    obs.observe_tool_use("u1", "Write", {"file_path": str(file_path)})
    obs.observe_tool_result("u1", "", False)

    assert events == []


def test_duplicate_tool_result_fires_only_once(dirs, make_observer):
    outputs_dir, _, _ = dirs
    obs, events = make_observer()

    file_path = outputs_dir / SID / "out_abc" / "report.xlsx"
    obs.observe_tool_use("u1", "Write", {"file_path": str(file_path)})
    obs.observe_tool_result("u1", "", False)
    obs.observe_tool_result("u1", "", False)  # second time -> no-op

    assert len(events) == 1


def test_legacy_numbered_kb_version_does_not_fire(dirs, make_observer):
    """The old `v<N>.xlsx` layout under kb_dir is no longer accepted (Phase C)."""
    _, kb_dir, _ = dirs
    obs, events = make_observer()

    for legacy in ("v3.xlsx", "v0.5.xlsx", "v_now.xlsx"):
        target = kb_dir / "kb_xyz" / "versions" / legacy
        obs.observe_tool_use(f"u-{legacy}", "Write", {"file_path": str(target)})
        obs.observe_tool_result(f"u-{legacy}", "", False)

    assert events == []


def test_attachment_version_now_returns_none_deprecated(dirs, make_observer):
    """DEPRECATED 2026-05-31: attachment-bound writes no longer emit detections.

    Phase C routes them through the standalone layout, so any path under
    `attachments_dir` must yield None from `_classify`.
    """
    _, _, attachments_dir = dirs
    obs, events = make_observer()

    target = attachments_dir / "sess_001" / "att_001" / "versions" / "v_curr.xlsx"
    obs.observe_tool_use("u1", "Write", {"file_path": str(target)})
    obs.observe_tool_result("u1", "", False)

    assert events == []


def test_attachment_version_prev_now_returns_none_deprecated(dirs, make_observer):
    """DEPRECATED 2026-05-31: same as v_curr — v_prev attachment writes no longer emit."""
    _, _, attachments_dir = dirs
    obs, events = make_observer()

    target = attachments_dir / "sess_001" / "att_001" / "versions" / "v_prev.csv"
    obs.observe_tool_use("u1", "Write", {"file_path": str(target)})
    obs.observe_tool_result("u1", "", False)

    assert events == []


def test_attachment_unknown_extension_does_not_fire(dirs, make_observer):
    _, _, attachments_dir = dirs
    obs, events = make_observer()

    target = attachments_dir / "sess_001" / "att_001" / "versions" / "v_curr.json"
    obs.observe_tool_use("u1", "Write", {"file_path": str(target)})
    obs.observe_tool_result("u1", "", False)

    assert events == []


def test_attachment_missing_att_prefix_does_not_fire(dirs, make_observer):
    _, _, attachments_dir = dirs
    obs, events = make_observer()

    # Notice "abc" instead of "att_..." in the attachment id slot.
    target = attachments_dir / "sess_001" / "abc" / "versions" / "v_curr.xlsx"
    obs.observe_tool_use("u1", "Write", {"file_path": str(target)})
    obs.observe_tool_result("u1", "", False)

    assert events == []


def test_reset_clears_pending_state(dirs, make_observer):
    outputs_dir, _, _ = dirs
    obs, events = make_observer()

    obs.observe_tool_use(
        "u1", "Write", {"file_path": str(outputs_dir / SID / "out_abc" / "x.xlsx")}
    )
    obs.reset()
    obs.observe_tool_result("u1", "", False)

    assert events == []


def test_non_write_non_bash_tool_is_ignored(dirs, make_observer):
    outputs_dir, _, _ = dirs
    obs, events = make_observer()

    obs.observe_tool_use(
        "u1",
        "Read",
        {"file_path": str(outputs_dir / SID / "out_abc" / "x.xlsx")},
    )
    obs.observe_tool_result("u1", "ok", False)

    assert events == []


def test_kb_version_xlsm_returns_none_deprecated(dirs, make_observer):
    """DEPRECATED 2026-05-31: KB writes no longer emit, regardless of extension."""
    _, kb_dir, _ = dirs
    obs, events = make_observer()

    target = kb_dir / "kb_macro" / "versions" / "v_curr.xlsm"
    obs.observe_tool_use("u1", "Write", {"file_path": str(target)})
    obs.observe_tool_result("u1", "", False)

    assert events == []
