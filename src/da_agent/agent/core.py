"""AgentRunner — owns the SDK session and translates its message stream into UI calls.

This is the reusable core. It knows nothing about rich or prompt_toolkit; it only talks
to an `AgentUI`. A web backend would construct an `AgentRunner` with a websocket-backed
UI and get the same behavior.
"""

from __future__ import annotations

import os
import time
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from ..config import Settings
from ..ui.base import AgentUI
from .events import PlanDecision, QuestionRequest, QuestionResponse
from .permissions import make_can_use_tool
from .prompts import build_system_prompt
from .subagents import build_subagents
from .todos import TodoStore, TODO_TOOL_NAMES

# Tool calls we drive via dedicated interactive UI (built-ins from the CLI). They never
# render as ordinary tool steps -- the matching UI surface (selector / plan approval /
# todo overlay) renders them instead.
_INTERACTIVE_TOOLS = {"AskUserQuestion", "ExitPlanMode"} | TODO_TOOL_NAMES

_BASE_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "TodoWrite",
    "NotebookEdit",
    "Task",
    "ExitPlanMode",
    "AskUserQuestion",
]


class AgentRunner:
    def __init__(self, ui: AgentUI, settings: Settings | None = None):
        self.ui = ui
        self.settings = settings or Settings()
        self.settings.ensure_dirs()
        self._client: ClaudeSDKClient | None = None
        self._first_block = True
        self._todos = TodoStore()

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    async def __aenter__(self) -> "AgentRunner":
        self._client = ClaudeSDKClient(options=self._build_options())
        await self._client.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    def _build_options(self) -> ClaudeAgentOptions:
        s = self.settings
        can_use_tool = make_can_use_tool(
            ask_plan=self._ask_plan,
            on_approved=self._on_plan_approved,
            ask_question=self._ask_question,
        )
        env = dict(os.environ)
        # Keep SDK session JSONL under the tool's own data dir.
        env["CLAUDE_CONFIG_DIR"] = str(s.sessions_dir)
        # Keep the legacy TodoWrite tool path active for backwards compatibility, but the
        # runner accepts both that and the newer Task* tool family transparently.
        env.setdefault("CLAUDE_CODE_ENABLE_TASKS", "1")

        return ClaudeAgentOptions(
            cwd=str(s.project_root),
            setting_sources=["project"],  # discover .claude/skills
            skills=["xlsx"],  # enable only the spreadsheet skill
            system_prompt=build_system_prompt(s),
            agents=build_subagents(),
            allowed_tools=_BASE_TOOLS,
            can_use_tool=can_use_tool,
            permission_mode="plan" if s.plan_first else "default",
            model=s.model,
            max_turns=s.max_turns,
            add_dirs=[str(s.kb_dir), str(s.workspace_dir)],
            env=env,
            include_partial_messages=False,
        )

    # ------------------------------------------------------------------ #
    # one conversational turn
    # ------------------------------------------------------------------ #
    async def send(self, prompt: str, *, echo_prompt: bool = True) -> None:
        assert self._client is not None, "AgentRunner not connected"
        if echo_prompt:
            self.ui.on_user_prompt(prompt)
        self._first_block = True
        started = time.monotonic()
        # begin_wait BEFORE the empty todos snapshot so the bottom-anchored overlay
        # transitions through "label only" rather than collapsing and re-mounting --
        # otherwise the live region briefly stops between turns and the spinner flickers.
        self.ui.begin_wait("Thinking")
        self._todos.reset()
        self.ui.on_todos(self._todos.snapshot())
        try:
            await self._client.query(prompt)
            async for message in self._client.receive_response():
                self._render(message, started)
        finally:
            self.ui.end_wait()

    # ------------------------------------------------------------------ #
    # rendering
    # ------------------------------------------------------------------ #
    def _render(self, message: Any, started: float) -> None:
        if isinstance(message, SystemMessage):
            self.ui.on_system(message.subtype, message.data or {})
        elif isinstance(message, AssistantMessage):
            depth = 1 if message.parent_tool_use_id else 0
            for block in message.content:
                self._render_block(block, depth)
        elif isinstance(message, UserMessage):
            depth = 1 if getattr(message, "parent_tool_use_id", None) else 0
            content = message.content if isinstance(message.content, list) else []
            for block in content:
                if isinstance(block, ToolResultBlock):
                    self._render_tool_result(block, depth)
        elif isinstance(message, ResultMessage):
            self.ui.on_result(
                turns=message.num_turns,
                cost_usd=message.total_cost_usd,
                duration_s=time.monotonic() - started,
            )

    def _render_block(self, block: Any, depth: int) -> None:
        if isinstance(block, ThinkingBlock):
            if self.settings.show_thinking and block.thinking.strip():
                self.ui.on_thinking(block.thinking)
        elif isinstance(block, TextBlock):
            if block.text.strip():
                self.ui.on_text(block.text)
        elif isinstance(block, ToolUseBlock):
            if block.name in TODO_TOOL_NAMES:
                self._absorb_todo_tool_use(block)
                return
            if block.name in _INTERACTIVE_TOOLS:
                return  # handled by dedicated interactive UI
            self.ui.on_tool_use(block.name, block.input or {}, depth=depth)
            # A tool is about to run -> show the waiting indicator again.
            self.ui.begin_wait(f"Running {block.name}")

    def _render_tool_result(self, block: ToolResultBlock, depth: int) -> None:
        if self._todos.is_pending(block.tool_use_id):
            self._absorb_todo_tool_result(block)
            return
        summary = _stringify_tool_result(block.content)
        self.ui.on_tool_result(summary, is_error=bool(block.is_error), depth=depth)

    # ------------------------------------------------------------------ #
    # todo plumbing
    # ------------------------------------------------------------------ #
    def _absorb_todo_tool_use(self, block: ToolUseBlock) -> None:
        if self._todos.observe_tool_use(block.id, block.name, block.input or {}):
            self.ui.on_todos(self._todos.snapshot())

    def _absorb_todo_tool_result(self, block: ToolResultBlock) -> None:
        text = _stringify_tool_result(block.content)
        if self._todos.observe_tool_result(block.tool_use_id, text):
            self.ui.on_todos(self._todos.snapshot())

    # ------------------------------------------------------------------ #
    # interaction hooks (called from permission callback)
    # ------------------------------------------------------------------ #
    async def _ask_plan(self, plan: str) -> PlanDecision:
        return await self.ui.approve_plan(plan)

    async def _ask_question(self, request: QuestionRequest) -> QuestionResponse:
        return await self.ui.ask_question(request)

    async def _on_plan_approved(self) -> None:
        # Plan accepted: stop gating every subsequent edit; steps remain visible.
        if self._client is not None:
            await self._client.set_permission_mode("acceptEdits")

    async def set_plan_mode(self) -> None:
        """Re-enter plan mode so the next turn produces a plan for approval."""
        if self._client is not None:
            await self._client.set_permission_mode("plan")


def _stringify_tool_result(content: Any) -> str:
    """Tool result content may be a str or a list of content blocks/dicts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            parts.append(item.get("text", "") or "")
        else:
            parts.append(getattr(item, "text", str(item)))
    return "\n".join(p for p in parts if p)
