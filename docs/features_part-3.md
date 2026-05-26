# Features — Part 3

> Two features shipped together in this iteration. Both keep the existing UI-agnostic
> seam (`AgentUI` Protocol) intact so a future websocket frontend can adopt them
> without touching agent core code.

---

## 1. Migrate `AskUserQuestion` to the SDK built-in tool

### Description

Up to this point the agent shipped its own MCP tool — `mcp__interaction__ask_user_question`
— created with `create_sdk_mcp_server` to drive multiple-choice questions to the user.
That worked but duplicated functionality the Claude Agent SDK already exposes as a
**built-in client tool**: when the model emits `AskUserQuestion`, the SDK relays the
call through the `can_use_tool` permission callback, and the consumer answers by
returning a `PermissionResultAllow` whose `updated_input` carries the user's selections.

The agent layer now uses that built-in path:

- The custom MCP server is gone (`agent/tools.py` deleted).
- `permissions.make_can_use_tool()` accepts an additional `ask_question` callback and
  routes `tool_name == "AskUserQuestion"` to its own handler that reads
  `tool_input["questions"]`, drives `ui.ask_question(...)`, and returns
  `PermissionResultAllow(updated_input={"questions": …, "answers": {Q text → label}})`.
- The system prompt now references the built-in `AskUserQuestion` tool by name
  (`agent/prompts.py`).

### Why it matters

- **One source of truth for the question schema.** The SDK and Claude Code already
  understand `AskUserQuestion`'s `questions[].{question, header, options, multiSelect, …}`
  shape. Removing the custom MCP tool eliminates the parallel definition we had to
  keep aligned with `CLAUDE_AGENT_TOOLS.md`.
- **Less code to maintain.** No more `create_sdk_mcp_server` registration, no
  `mcp_servers={"interaction": …}` wiring, no custom MCP tool name in the allow-list.
- **Same UI seam.** `AgentUI.ask_question(QuestionRequest) -> QuestionResponse` is
  unchanged, so `ConsoleAgentUI` and `ui/prompts.py` don't move at all. A future web
  UI implements the same Protocol method and stays compatible.

### Code summary

| File | Change |
|---|---|
| `src/da_agent/agent/permissions.py` | New `ask_question` parameter on `make_can_use_tool`; new `_handle_ask_user_question` returns `PermissionResultAllow` with `updated_input.{questions, answers}`. |
| `src/da_agent/agent/core.py` | Removed MCP server wiring; replaced `QUALIFIED_TOOL_NAME` with the literal `"AskUserQuestion"` in `_BASE_TOOLS` and `_INTERACTIVE_TOOLS`; passes `self._ask_question` into `make_can_use_tool`. |
| `src/da_agent/agent/tools.py` | **Deleted** (custom MCP tool no longer needed). |
| `src/da_agent/agent/prompts.py` | System prompt now names `AskUserQuestion` instead of `ask_user_question`. |
| `tests/test_agent.py` | Removed tests of the deleted MCP handler; added two new tests that drive the built-in path through `can_use_tool` (happy path + empty-response path); existing plan-approval tests updated for the new `ask_question` parameter. |

### Reference

The pattern follows the demo at `notebooks/TEST-claude-built-in-tool.py` from this
repo, which shows the canonical "intercept `AskUserQuestion` via `can_use_tool`,
return `PermissionResultAllow(updated_input={"questions", "answers"})`" round-trip.

---

## 2. Todo list display (Claude Code-style)

### Description

The agent's todo list is now first-class in the UI. The runner observes the
SDK-emitted task tools, normalises them into a snapshot, and pushes it through the
`AgentUI` Protocol so the CLI can render an in-progress checklist that mirrors what
Claude Code shows. The same snapshot shape is serialisable, so a future web frontend
can render the list from the exact same data.

Two tool families are supported transparently:

- **Task tools** (`TaskCreate`, `TaskUpdate`, `TaskList`, `TaskGet`) — the modern
  incremental API. `TaskCreate` returns the assigned id in its tool_result; the store
  correlates by `tool_use_id`. `TaskUpdate` patches by `taskId`, with
  `status: "deleted"` removing the row.
- **TodoWrite** (legacy) — a single tool call rewrites the entire array of todos with
  shape `{content, status, activeForm}`. `TodoStore` handles this path too so
  pre-migration sessions still render.

In the CLI the overlay lives in a single `rich.live.Live` region pinned to the bottom
of the terminal. It shows:

- A spinner line whose label switches to the in-progress todo's `activeForm` when one
  is running (so the user sees *Aggregating revenue…* rather than a generic *Working…*).
- A checklist beneath it: `▪` for in_progress (bold), `□` for pending, `✔` for
  completed. Streaming text/tool prints scroll **above** this region.

### Why it matters

- **Lifecycle visibility.** The user sees what the agent thinks the task list is and
  how it's progressing, not just disconnected tool calls.
- **Adaptive across UIs.** The `TodoSnapshot` payload is a plain dataclass with
  `to_dict()`. The `AgentUI.on_todos(snapshot)` Protocol method is the single seam.
  A web backend implements that one method and gets identical fidelity.
- **Both tool dialects.** Sessions that still emit legacy `TodoWrite` and sessions
  using the new `Task*` tools both produce the same UI without configuration.

### Code summary

| File | Change |
|---|---|
| `src/da_agent/agent/events.py` | New `TodoStatus` enum, `TodoItem`, `TodoSnapshot` (with `in_progress`, `counts()`, `to_dict()`). All slots, all dataclass-serialisable. |
| `src/da_agent/agent/todos.py` (new) | `TodoStore` — observes tool_use / tool_result blocks, maintains an ordered `task_id → TodoItem` map, returns immutable `TodoSnapshot`s. Constants: `TODO_TOOL_NAMES`. |
| `src/da_agent/agent/core.py` | `AgentRunner` owns a `TodoStore`; resets at the start of each turn; intercepts todo tool calls in `_render_block`/`_render_tool_result` so they bypass the normal step renderer and feed the store; pushes a fresh snapshot to `ui.on_todos(...)` whenever state changes. |
| `src/da_agent/ui/base.py` | Protocol gains `on_todos(snapshot: TodoSnapshot) -> None`. |
| `src/da_agent/ui/console.py` | Replaced the old `console.status` spinner with a single `rich.live.Live` overlay holding both the spinner and the todo checklist. Spinner label is taken from the in_progress todo when one exists. The overlay self-manages: it starts when the wait label or todos become non-empty and stops when both go away. |
| `src/da_agent/cli.py` | The scripted `demo` command now drives `ui.on_todos(...)` between subagent steps so the overlay is visible without running a real model session. |
| `tests/test_todos.py` (new) | 13 unit + integration tests covering: TaskCreate/Update lifecycle, deleted status, update-before-create synthesis, unknown-status tolerance, missing-id fallback, legacy TodoWrite path, `in_progress` / `counts()` helpers, runner-level intercept, `display_text` switching to `activeForm`. |
| `tests/test_console_overlay.py` (new) | 5 tests covering: glyph + branch rendering, overlay start/stop on wait label, overlay persistence when todos remain, label being replaced by the active todo's `activeForm`, overlay teardown when the snapshot empties. |

### How the overlay tracks tool events

```
ToolUseBlock(name="TaskCreate", id="tu1", input={subject,...})
   └─ store.observe_tool_use(tu1, ...)   -> pending: tu1
ToolResultBlock(tool_use_id="tu1", content='{"task":{"id":"T-1"}}')
   └─ store.observe_tool_result(tu1, ...) -> create T-1 (PENDING) + push snapshot

ToolUseBlock(name="TaskUpdate", input={taskId="T-1", status="in_progress"})
   └─ store.observe_tool_use -> patch T-1 + push snapshot
   └─ ConsoleAgentUI.on_todos: spinner label flips to T-1.activeForm

ToolUseBlock(name="TaskUpdate", input={taskId="T-1", status="completed"})
   └─ patch + push -> ✔ in checklist; spinner falls back to wait label
```

### Tests

```
$ pytest -q
.................................                                       [100%]
33 passed in 0.26s
```

Baseline before this iteration was 13 tests. The 13 → 33 jump comes from:
- `test_agent.py`: +1 (built-in `AskUserQuestion` round-trip), -1 (deleted MCP test), kept 13.
- `test_todos.py` (new): +13 covering store + runner intercept.
- `test_console_overlay.py` (new): +5 covering the rich-Live overlay.
- `test_selector.py`: unchanged (3).

### Open considerations / non-goals

- **No persistence across turns.** The store resets on each `AgentRunner.send(...)` so
  it always reflects the current turn. If a future feature wants cross-turn carry-over,
  drop the `self._todos.reset()` line in `AgentRunner.send` and add an explicit clear
  command instead.
- **No web UI yet.** The Protocol seam is there; the websocket implementation is not.
  The `to_dict()` helpers on `TodoItem`/`TodoSnapshot` exist precisely so it's a thin
  step away.
- **Spinner animation requires a TTY.** Tests use `force_terminal=False` to avoid
  driving the live loop; in a real terminal the dots animate normally.
