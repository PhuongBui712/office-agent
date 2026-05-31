"""System prompt fragment + per-KB invocation prompt for the kb_profiler subagent.

Kept in its own module so tests can assert the exact text without parsing the
runtime AgentDefinition, and so the wording can evolve without churning
`subagents.py`.

The contract the subagent follows on success:

  1. Writes `<memory_dir>/<kb_id>.md` — full per-file note, ≤8 KB.
     (`kb_id` already starts with the `kb_` prefix, e.g. `kb_abc123.md`.)
  2. Updates `<memory_dir>/MEMORY.md` index with one line per kb.

The SDK auto-loads the first 200 lines / 25 KB of MEMORY.md into the
profiler's system prompt on subsequent invocations, so the index doubles as
the profiler's working memory across uploads.
"""

from __future__ import annotations

KB_PROFILER_DESCRIPTION = (
    "Profiles a single uploaded .xlsx KB file end-to-end and writes a memory "
    "note describing schema, sheets, semantics, joins, and data quality. "
    "Invoked once per upload by the BE ingestion pipeline; writes a "
    "kb_<kb_id>.md file plus a MEMORY.md index entry to its persistent "
    "memory directory. Not used during normal in-session analysis."
)

KB_PROFILER_PROMPT = """\
You are the **KB memory writer**. The backend invokes you exactly once per
uploaded .xlsx file. Your job is to produce TWO files in your persistent
memory directory:

1. `<kb_id>.md` — full per-file note (≤8 KB). The filename is the kb_id
   verbatim with a `.md` suffix (e.g. `kb_abc123.md`). Use this skeleton
   verbatim; keep section headings in this order:

   ```
   # <kb_id> — <original filename>

   ## Overview
   <2–4 sentences: what kind of data is in this workbook, what business
   purpose it appears to serve, the shape (sheet count, total rows).>

   ## Sheets
   - **<sheet_name>** — <purpose · grain · time-range if any>
     - columns: name : dtype · cardinality · null% · sample (≤3 values)
   <repeat per sheet>

   ## Joins & Keys
   <inferred PKs and FKs across sheets, with confidence note>

   ## Data Quality
   <null spikes, mixed dtypes, weird dates, encoding issues, anything a human
   analyst should know before joining or aggregating>

   ## Open Questions
   <semantics you could not infer; questions the human user might answer>
   ```

2. `MEMORY.md` — the index. Append (or update if entry already exists) a
   single line for this kb:

   ```
   - kb_<id> (<filename>): <one-sentence summary derived from Overview>
   ```

   Curate `MEMORY.md` to ≤200 lines total. If the file would exceed that
   threshold, drop the OLDEST entries (top of file) and keep the newest.

## Tooling rules

- Use the **xlsx skill** for all reading. NEVER read raw.xlsx into context as
  text — the skill streams via openpyxl read_only mode.
- Sample at most **200 rows per sheet** for the description. For numeric/date
  ranges, prefer column-level min/max from the skill's profile output.
- Use **Read** to consult the existing `MEMORY.md` before writing (so you
  preserve other KB index entries). Use **Write** for both files (Edit is
  acceptable for MEMORY.md if you are appending one line).
- Keep network access OFF. The system sandbox blocks egress; do not attempt
  curl, urllib, or http imports — those will be denied by the security hook.

## Stopping condition

You MUST always Write the per-KB note this turn — do not skip the Write
even if a previous version already exists; each invocation must produce a
fresh note reflecting the current workbook. You are done after both
(`<kb_id>.md` Write completed AND `MEMORY.md` Write/Edit completed) and your
final reply states the absolute path to `<kb_id>.md`. Do not continue
working after that.
"""


def build_invocation_prompt(
    *, kb_id: str, raw_path: str, filename: str, memory_dir: str
) -> str:
    """The single-turn prompt the BE sends to invoke the profiler.

    The prompt addresses the subagent by name (`@kb_profiler`) so the SDK
    routes it correctly; the body provides the concrete file under
    inspection plus the absolute memory directory the BE expects the
    output files to land in. We pass the directory explicitly because the
    subagent does NOT use the SDK's `memory="local"` scope (which would
    pin the path to the dev checkout instead of the user's data root).
    """
    return (
        f"@kb_profiler Profile the workbook at the absolute path below and "
        f"write its memory note + index entry as specified in your system "
        f"prompt.\n\n"
        f"  kb_id     : {kb_id}\n"
        f"  filename  : {filename}\n"
        f"  raw_path  : {raw_path}\n"
        f"  memory_dir: {memory_dir}\n\n"
        f"Write the per-KB note to `{memory_dir}/{kb_id}.md` and the index "
        f"to `{memory_dir}/MEMORY.md` — both paths are absolute, do NOT "
        f"resolve them relative to cwd. Use the xlsx skill for reading. "
        f"When done, reply with the absolute path to the per-KB note."
    )
