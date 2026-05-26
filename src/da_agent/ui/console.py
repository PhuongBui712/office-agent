"""Console rendering with `rich`.

`ConsoleAgentUI` implements the full `AgentUI` protocol. Rendering uses rich; the
interactive bits (questions, plan approval) delegate to `ui.prompts` (prompt_toolkit).
The spinner is owned here and is paused before any interactive prompt so the two
libraries never fight over the terminal.
"""
from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.status import Status
from rich.text import Text

from ..agent.events import PlanDecision, QuestionRequest, QuestionResponse
from . import prompts as interactive

_RESULT_MAX_LINES = 14
_THINKING_MAX_CHARS = 600
_GREEN = "#3fb950"
_DIM = "grey62"


class ConsoleAgentUI:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self._status: Status | None = None

    # ------------------------------------------------------------------ #
    # waiting indicator
    # ------------------------------------------------------------------ #
    def begin_wait(self, label: str = "Working") -> None:
        self.end_wait()
        self._status = self.console.status(Text(f" {label}…", style=_DIM), spinner="dots")
        self._status.start()

    def end_wait(self) -> None:
        if self._status is not None:
            self._status.stop()
            self._status = None

    # ------------------------------------------------------------------ #
    # render
    # ------------------------------------------------------------------ #
    def on_user_prompt(self, text: str) -> None:
        self.end_wait()
        self.console.print()
        self.console.print(Text("› ", style="bold") + Text(text, style="bold white"))

    def on_thinking(self, text: str) -> None:
        self.end_wait()
        snippet = text.strip()
        if len(snippet) > _THINKING_MAX_CHARS:
            snippet = snippet[:_THINKING_MAX_CHARS].rstrip() + " …"
        self.console.print()
        self.console.print(Text("✻ Thinking", style=f"italic {_DIM}"))
        for line in snippet.splitlines():
            self.console.print(Text("  " + line, style=f"italic {_DIM}"))

    def on_text(self, text: str) -> None:
        self.end_wait()
        self.console.print()
        self.console.print(Text(text.strip()))

    def on_tool_use(self, name: str, tool_input: dict[str, Any], *, depth: int = 0) -> None:
        self.end_wait()
        pad = "  " * depth
        head = Text(f"{pad}● ", style=_GREEN) + Text(name, style="bold")
        arg = _format_args(name, tool_input)
        if arg:
            head += Text(f"({arg})", style=_DIM)
        self.console.print(head)

    def on_tool_result(self, summary: str, *, is_error: bool = False, depth: int = 0) -> None:
        self.end_wait()
        pad = "  " * depth
        lines = summary.rstrip().splitlines() or [""]
        shown, extra = lines[:_RESULT_MAX_LINES], len(lines) - _RESULT_MAX_LINES
        style = "red" if is_error else _DIM
        for i, line in enumerate(shown):
            prefix = f"{pad}  ⎿  " if i == 0 else f"{pad}     "
            self.console.print(Text(prefix, style=_DIM) + Text(line, style=style))
        if extra > 0:
            self.console.print(Text(f"{pad}     … +{extra} more lines", style=_DIM))

    def on_system(self, subtype: str, data: dict[str, Any]) -> None:
        if subtype == "init":
            model = data.get("model", "")
            note = f"session ready · {model}" if model else "session ready"
            self.console.print(Text(f"· {note}", style=_DIM))

    def on_result(self, *, turns: int, cost_usd: float | None, duration_s: float) -> None:
        self.end_wait()
        bits = [f"done in {duration_s:.1f}s", f"{turns} turn{'s' if turns != 1 else ''}"]
        if cost_usd:
            bits.append(f"${cost_usd:.4f}")
        self.console.print()
        self.console.print(Text("✶ " + " · ".join(bits), style=_DIM))

    def on_error(self, message: str) -> None:
        self.end_wait()
        self.console.print(Text(f"✗ {message}", style="bold red"))

    # ------------------------------------------------------------------ #
    # interaction
    # ------------------------------------------------------------------ #
    async def ask_question(self, request: QuestionRequest) -> QuestionResponse:
        self.end_wait()
        return await interactive.run_question_selector(request)

    async def approve_plan(self, plan: str) -> PlanDecision:
        self.end_wait()
        self._render_plan(plan)
        return await interactive.confirm_plan()

    def _render_plan(self, plan: str) -> None:
        self.console.print()
        self.console.print(Text("▌ Plan", style="bold"))
        for line in plan.strip().splitlines():
            self.console.print(Text("  " + line))


def _format_args(name: str, ti: dict[str, Any]) -> str:
    if not ti:
        return ""
    if name == "Bash":
        return _truncate(str(ti.get("command", "")), 90)
    if name in {"Read", "Write", "Edit", "NotebookEdit"}:
        return _truncate(str(ti.get("file_path", "")), 90)
    if name in {"Glob", "Grep"}:
        return _truncate(str(ti.get("pattern", "")), 90)
    if name == "Task":
        sub = ti.get("subagent_type", "")
        desc = ti.get("description", "")
        return _truncate(f"{sub}: {desc}".strip(": "), 90)
    if name == "TodoWrite":
        todos = ti.get("todos", [])
        return f"{len(todos)} item{'s' if len(todos) != 1 else ''}"
    if name == "Skill":
        return _truncate(str(ti.get("name", "")), 60)
    try:
        return _truncate(json.dumps(ti, ensure_ascii=False), 90)
    except (TypeError, ValueError):
        return _truncate(str(ti), 90)


def _truncate(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"
