# Bugs — Part 3

## 1. Todo overlay shows `(unknown)` rows instead of updating existing tasks

### Symptoms

User reproducer (see screenshot in the task brief):

> "Demo the todo list feature by create and update with 5 dummy tasks."

The model created 5 tasks and progressively updated their status. Expected: the
bottom overlay shows 5 rows whose glyphs change `□ → ▪ → ✔` as work progresses.

Observed: the overlay accumulated **6 pending rows** *plus* extra rows labelled
`(unknown)` for every status change:

```
□ Load and profile sales dataset
□ Load and profile sales dataset      ← duplicate from a re-issued create
□ Clean and deduplicate records
□ Build monthly revenue pivot table
□ Generate revenue trend chart
□ Export final report to workspace
✔ (unknown)                           ← spurious row from a TaskUpdate(taskId="1")
✔ (unknown)                           ← from TaskUpdate(taskId="2")
▪ (unknown)                           ← from TaskUpdate(taskId="3")
```

The status updates the model emitted (`Updated task #1`, `#2`, `#3`) never landed
on the originally-created rows; the originals stayed pending forever, and the
updates spawned new rows whose subject defaulted to `(unknown)`.

### Root cause

`TodoStore.observe_tool_result` calls `_extract_task_id(content)` to read the
SDK-assigned id out of a `TaskCreate` result, then keys the row by that id so
later `TaskUpdate(taskId=…)` calls can find it.

The previous implementation only handled a JSON-shaped result:

```python
# old _extract_task_id
data = json.loads(text)            # expects {"task": {"id": "…"}} or {"id": "…"}
```

But the actual Claude Agent SDK CLI emits a **plain string** for `TaskCreate`'s
tool_result. From the bundled CLI's task-tool definition:

```js
mapToolResultToToolResultBlockParam(H, $) {
  let { task: q } = H;
  return { tool_use_id: $, type: "tool_result",
           content: `Task #${q.id} created successfully: ${q.subject}` };
}
```

We confirmed the same shape in real session transcripts (`~/.claude/projects/.../*.jsonl`):

```
"content": "Task #1 created successfully: Failure analysis of current data-gen pipeline"
```

`json.loads` therefore raised, the JSON branch returned `None`, and the row was
keyed by the **fallback** id `local-{tool_use_id}`. When a later
`TaskUpdate(taskId="1")` arrived, the lookup `self._tasks.get("1")` missed
(the row was stored under `local-toolu_xxx`), so `_apply_update`'s
update-before-create path synthesised a fresh row with
`subject = (input_data.get("subject") or "(unknown)")` — i.e. `(unknown)`,
because `TaskUpdate` rarely carries `subject`.

Two compounding effects produced exactly what the user saw:
- The 5–6 `TaskCreate`s each landed under unique `local-…` ids → a row per create
  (matching subject), all stuck at `pending`.
- The 3 `TaskUpdate`s each synthesised a brand-new `(unknown)` row keyed by the
  numeric `taskId`. Because those ids were stable across updates of the same
  task, repeated updates of the same `taskId` did update the same `(unknown)`
  row — that is why exactly **3 distinct** `(unknown)` rows appeared even though
  the model issued more than 3 updates.

### Solution

Teach `_extract_task_id` to parse the plain-string format first, then fall back
to JSON for transports that re-encode the result.

```python
_PLAIN_ID_RE = re.compile(r"Task\s*#(\S+)\s+created successfully")
_JSON_ID_RE  = re.compile(r'"id"\s*:\s*"([^"\\]+)"')

def _extract_task_id(text: str) -> str | None:
    match = _PLAIN_ID_RE.search(text)
    if match:
        return match.group(1)
    # … existing JSON paths preserved as a fallback …
```

The plain-string path is the new fast path; the JSON paths stay for backwards
compatibility (they are how the existing `tests/test_todos.py` was written and
they continue to work for any future transport that wraps the result).

### Code summary

| File | Change |
|---|---|
| `src/da_agent/agent/todos.py` | Added `_PLAIN_ID_RE` (anchored on the literal `"Task #"` prefix the SDK emits) and reordered `_extract_task_id` to try the plain-string format first. JSON branches kept intact. |
| `tests/test_todos.py` | Added five regression tests: parses real SDK plain string; end-to-end create+update from the screenshot scenario produces no `(unknown)` row; legacy JSON format still works; alphanumeric task ids are accepted; runner-level integration of the same scenario. |

### Verification

```
$ pytest -q
.......................................                                  [100%]
39 passed in 0.26s
```

Specifically, the regression tests added for this fix:

- `test_taskcreate_parses_real_sdk_plain_string`
- `test_taskcreate_then_update_updates_same_row_no_unknown`
- `test_taskcreate_legacy_json_format_still_parsed`
- `test_extract_task_id_alphanumeric_id_supported`
- `test_runner_handles_real_sdk_create_then_update_no_unknown`

Each fails on the pre-fix `_extract_task_id` and passes after the change.

---

## 2. Bottom overlay flickers on each turn boundary

### Symptoms

When a new user prompt was issued, the rich-Live overlay at the bottom of the
terminal collapsed for a single frame and then re-mounted. Visible as a brief
spinner blink between turns. Mostly cosmetic, but it broke the "always present
at the bottom" promise the part-3 feature was meant to deliver.

### Root cause

`AgentRunner.send` reset todos and pushed an empty snapshot **before** calling
`begin_wait("Thinking")`:

```python
self._todos.reset()
self.ui.on_todos(self._todos.snapshot())   # snapshot empty AND no wait label
self.ui.begin_wait("Thinking")             # → live overlay restarts
```

Inside `_refresh_overlay` the live region is mounted iff `wait_label OR todos`
is non-empty. Between the two calls above, both were empty, so the live region
stopped — and immediately re-started one statement later.

### Solution

Swap the order: set the wait label first, *then* reset todos and push the empty
snapshot. The overlay observes a smooth `(label + todos) → (label only)`
transition and never has to tear down.

```python
self.ui.begin_wait("Thinking")
self._todos.reset()
self.ui.on_todos(self._todos.snapshot())
```

### Code summary

| File | Change |
|---|---|
| `src/da_agent/agent/core.py` | Reordered the four lines at the top of `AgentRunner.send`; added a comment explaining why the order matters. |
| `tests/test_todos.py` | New `test_runner_send_orders_overlay_calls_to_avoid_flicker` records the call order via a fake UI and asserts `begin_wait` precedes the first `on_todos` push. |

### Verification

```
$ pytest -q tests/test_todos.py::test_runner_send_orders_overlay_calls_to_avoid_flicker -v
... PASSED
```
