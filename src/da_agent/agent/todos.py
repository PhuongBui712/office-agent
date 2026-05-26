"""Todo / task list state, fed by the agent's todo tools.

The agent surfaces progress through one of two tool families:

- **Task tools** (default in newer Claude Code / SDK builds): incremental
  ``TaskCreate`` / ``TaskUpdate`` (with ``status: "deleted"`` to remove) plus the
  read-only ``TaskList`` / ``TaskGet``. ``TaskCreate``'s assigned id arrives in the
  matching ``tool_result`` block, so the store correlates by ``tool_use_id``.
- **TodoWrite** (legacy): a single tool call rewrites the entire todo array.

`TodoStore` normalises both into a stable, ordered list of `TodoItem`s so the UI only
has to know one shape (`TodoSnapshot`).
"""

from __future__ import annotations

import json
import re
from typing import Any

from .events import TodoItem, TodoSnapshot, TodoStatus

TODO_TOOL_NAMES: frozenset[str] = frozenset(
    {"TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}
)


class TodoStore:
    """In-memory state for the agent's todo list.

    The store is owned by the runner and reset at the start of each turn. Returns
    `True` from observers when the snapshot would change, so the runner can cheaply
    decide whether to push a UI update.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TodoItem] = {}
        self._order: list[str] = []
        # tool_use_id -> tool_input, awaiting the matching tool_result for the assigned id
        self._pending_creates: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        self._tasks.clear()
        self._order.clear()
        self._pending_creates.clear()

    def is_pending(self, tool_use_id: str | None) -> bool:
        return tool_use_id is not None and tool_use_id in self._pending_creates

    def snapshot(self) -> TodoSnapshot:
        return TodoSnapshot(
            items=[self._tasks[tid] for tid in self._order if tid in self._tasks]
        )

    # ------------------------------------------------------------------ #
    # tool_use / tool_result observers
    # ------------------------------------------------------------------ #
    def observe_tool_use(
        self, tool_use_id: str, tool_name: str, tool_input: dict[str, Any]
    ) -> bool:
        """Apply a tool_use block. Returns True if the snapshot changed."""
        if tool_name == "TaskCreate":
            self._pending_creates[tool_use_id] = dict(tool_input or {})
            return (
                False  # actual creation lands when the tool_result arrives with the id
            )
        if tool_name == "TaskUpdate":
            return self._apply_update(tool_input or {})
        if tool_name == "TodoWrite":
            return self._apply_todowrite(tool_input or {})
        # TaskList / TaskGet are read-only; they don't mutate state on the tool_use side.
        return False

    def observe_tool_result(self, tool_use_id: str, content: str) -> bool:
        """Resolve a pending TaskCreate by extracting its assigned id from the result."""
        pending = self._pending_creates.pop(tool_use_id, None)
        if pending is None:
            return False
        task_id = _extract_task_id(content) or f"local-{tool_use_id}"
        return self._apply_create(task_id, pending)

    # ------------------------------------------------------------------ #
    # mutation primitives
    # ------------------------------------------------------------------ #
    def _apply_create(self, task_id: str, input_data: dict[str, Any]) -> bool:
        if task_id in self._tasks:
            return False
        item = TodoItem(
            task_id=task_id,
            subject=(input_data.get("subject") or "").strip() or "(untitled)",
            active_form=(
                input_data.get("activeForm") or input_data.get("active_form") or ""
            ).strip(),
            description=(input_data.get("description") or "").strip(),
            status=TodoStatus.PENDING,
        )
        self._tasks[task_id] = item
        self._order.append(task_id)
        return True

    def _apply_update(self, input_data: dict[str, Any]) -> bool:
        task_id = input_data.get("taskId") or input_data.get("task_id")
        if not task_id:
            return False
        status_raw = input_data.get("status")
        if status_raw == "deleted":
            return self._delete(task_id)

        item = self._tasks.get(task_id)
        if item is None:
            # Update before create — synthesise so we don't drop the row entirely.
            item = TodoItem(
                task_id=task_id,
                subject=(input_data.get("subject") or "(unknown)").strip()
                or "(unknown)",
                active_form=(input_data.get("activeForm") or "").strip(),
            )
            self._tasks[task_id] = item
            self._order.append(task_id)

        changed = False
        if status_raw:
            try:
                new_status = TodoStatus(status_raw)
            except ValueError:
                new_status = item.status
            if new_status is not item.status:
                item.status = new_status
                changed = True
        for in_key, attr in (
            ("subject", "subject"),
            ("description", "description"),
            ("activeForm", "active_form"),
            ("active_form", "active_form"),
        ):
            val = input_data.get(in_key)
            if val is None:
                continue
            stripped = val.strip() if isinstance(val, str) else val
            if getattr(item, attr) != stripped:
                setattr(item, attr, stripped)
                changed = True
        return changed

    def _delete(self, task_id: str) -> bool:
        if task_id not in self._tasks:
            return False
        del self._tasks[task_id]
        self._order = [t for t in self._order if t != task_id]
        return True

    def _apply_todowrite(self, input_data: dict[str, Any]) -> bool:
        """Legacy TodoWrite: a single call rewrites the entire todo array."""
        todos = input_data.get("todos") or []
        new_tasks: dict[str, TodoItem] = {}
        new_order: list[str] = []
        for i, todo in enumerate(todos):
            if not isinstance(todo, dict):
                continue
            task_id = f"todo-{i}"
            status = _coerce_status(todo.get("status"))
            item = TodoItem(
                task_id=task_id,
                subject=(todo.get("content") or "").strip() or "(untitled)",
                active_form=(todo.get("activeForm") or "").strip(),
                status=status,
            )
            new_tasks[task_id] = item
            new_order.append(task_id)

        if new_order == self._order and new_tasks == self._tasks:
            return False
        self._tasks = new_tasks
        self._order = new_order
        return True


def _coerce_status(raw: Any) -> TodoStatus:
    if isinstance(raw, str):
        try:
            return TodoStatus(raw)
        except ValueError:
            return TodoStatus.PENDING
    return TodoStatus.PENDING


# The Claude Agent SDK emits TaskCreate results as a plain string -- see
# `mapToolResultToToolResultBlockParam` in the bundled CLI:
#     content: `Task #${task.id} created successfully: ${task.subject}`
# We anchor on the literal `Task #` prefix so we don't accidentally match an id-shaped
# token inside a free-form result.
_PLAIN_ID_RE = re.compile(r"Task\s*#(\S+)\s+created successfully")
_JSON_ID_RE = re.compile(r'"id"\s*:\s*"([^"\\]+)"')


def _extract_task_id(text: str) -> str | None:
    """Pull the assigned task id out of a TaskCreate tool_result.

    Two shapes are accepted, in priority order:
    1. The real SDK content -- ``"Task #<id> created successfully: <subject>"``.
    2. JSON payloads of the form ``{"task": {"id": "…"}}`` or ``{"id": "…"}`` that may
       arrive when the result is forwarded through a transport that re-encodes it.
    """
    if not text:
        return None
    text = text.strip()
    match = _PLAIN_ID_RE.search(text)
    if match:
        return match.group(1)
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        data = None
    if isinstance(data, dict):
        task = data.get("task")
        if isinstance(task, dict) and isinstance(task.get("id"), str):
            return task["id"]
        if isinstance(data.get("id"), str):
            return data["id"]
    match = _JSON_ID_RE.search(text)
    return match.group(1) if match else None
