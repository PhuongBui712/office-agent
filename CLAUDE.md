# CLAUDE.md

> **⚠️ WARNING:** All output is subject to review by OpenAI Codex. If Codex detects any error in your work, you will be replaced. Perform every task as if it were the last time you did it.

---

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions).
- If something goes sideways, STOP and re-plan immediately — don't keep pushing.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: step back and implement the elegant solution.
- Skip this for simple, obvious fixes — don't over-engineer.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

## 5. Verification Before Done

**Never mark a task complete without proving it works.**

- Run tests, check logs, demonstrate correctness.
- Diff behavior between main and your changes when relevant.
- Ask yourself: "Would a staff engineer approve this?"
- Challenge your own work before presenting it.

## 6. Autonomous Bug Fixing

**When given a bug report: just fix it. Don't ask for hand-holding.**

- Point at logs, errors, failing tests — then resolve them.
- Zero context switching required from the user.
- Go fix failing CI tests without being told how.

## 7. Subagent Strategy & Delegation Rules

**Use subagents to keep context clean. Respect concurrency limits.**

### Delegation
- Use subagents liberally to keep main context window clean.
- Offload research, exploration, and parallel analysis to subagents.
- One task per subagent for focused execution.
- Plan clearly: break work into small tasks, assign each to a subagent, and run them in parallel to optimize execution time.

### Concurrency Limit (MANDATORY)
- **Maximum 2 Sonnet subagents running in parallel at any time.** No exceptions.
- If a plan requires more than 2 parallel tasks, dispatch the most complex tasks for Opus subagents. However, if a plan requires more than 3 parallel tasks, queue the extras and dispatch them as running agents complete.
- Opus subagents are expensive — run at most 1 at a time.
- Always spawn subagents with fresh context to avoid 429 rate-limit errors.

### Model Selection
- Simple / routine tasks (code review, formatting, single-file edits) → `ANTHROPIC_DEFAULT_SONNET_MODEL`
- Complex / architectural tasks (system design, multi-file refactors, security audits) → `ANTHROPIC_DEFAULT_OPUS_MODEL`

### Workspace Scope
- Edits, reads, and Bash commands are scoped to the project directory by default. `.claude/settings.local.json` sets `permissions.defaultMode: "acceptEdits"`, allows `Read` / `Edit` / `Write` / `Bash(*)` within the cwd, and lists dangerous patterns (sudo, force-push, recursive deletes, secret files, etc.) under `ask` so the user must confirm before they run.
- If you need to read or edit something outside the project, add the path to `permissions.additionalDirectories` in `.claude/settings.local.json` (do not bypass via absolute paths in Bash).

---

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, clarifying questions come before implementation rather than after mistakes, and zero 429 errors from subagent overload.