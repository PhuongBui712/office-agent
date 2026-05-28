# DAA Evaluation Strategy

## 1. Overview

This document defines the evaluation strategy for the **Data Analyst Agent (DAA)** — an agent built on the Claude Agent SDK that accepts Excel files as input and performs two classes of work:

| Capability | Description | Trigger |
|---|---|---|
| **Data Operations** | Extract, aggregate, filter, reshape, merge data | Simple or direct questions |
| **Data Analysis** | Full 6-phase analytical process producing actionable insights | Explicit analysis requests or complex, open-ended questions |

Because these two capabilities have fundamentally different outputs and success criteria, they require separate evaluation suites. This strategy covers both.

**Grader constraint:** All evaluations use only **code-based** and **model-based** graders. No human graders are used in the automated pipeline.

---

## 2. Evaluation Architecture

### 2.1 Core Definitions

These definitions follow the terminology from Anthropic's agent evaluation framework:

- **Task**: A single test case with a defined input (Excel file + user prompt) and success criteria.
- **Trial**: One execution of a task. Multiple trials per task are run to handle non-determinism.
- **Grader**: Logic that scores agent performance. Each task can have multiple graders.
- **Transcript**: The full record of a trial — all messages, tool calls, reasoning, and intermediate outputs.
- **Outcome**: The final state after the trial — the files produced, the answer returned, the data transformed.
- **Evaluation Suite**: A collection of tasks targeting a specific capability or behavior.

### 2.2 Suite Structure

```
DAA Evaluation
├── Suite A: Data Operations (extraction, aggregation, manipulation)
├── Suite B: Data Analysis (full 6-phase analytical process)
├── Suite C: Routing (does the agent correctly choose which capability to use?)
└── Suite D: Regression (graduated tasks from Suites A-C with near-100% pass rate)
```

### 2.3 Grader Types Used

#### Code-Based Graders

| Method | What it checks |
|---|---|
| **Exact value match** | Output numbers, strings, or cell values match expected answers |
| **Dataframe comparison** | Output table structure, dtypes, row counts, and values match reference (with tolerance for floats) |
| **Schema validation** | Output contains required columns, correct types, no unexpected nulls |
| **Tool call verification** | Agent called the right tools, in a valid order, with valid parameters |
| **Transcript analysis** | Turn count, token usage, and cost stayed within budgets |
| **Regex / pattern match** | Output contains required patterns (e.g., a recommendation section, a hypothesis statement) |
| **Phase gate checks** | For analysis tasks: agent completed all mandatory phases in the correct sequence |

#### Model-Based Graders

| Method | What it checks |
|---|---|
| **Rubric-based scoring** | A structured rubric evaluates quality dimensions (e.g., insight quality, recommendation specificity) |
| **Natural language assertions** | LLM checks whether specific claims hold true about the output (e.g., "the recommendation ties directly to a finding") |
| **Reference-based evaluation** | LLM compares agent output against a reference solution and scores similarity, completeness, and correctness |
| **Pairwise comparison** | LLM compares two agent outputs (e.g., before/after a prompt change) and picks the better one |

---

## 3. How to Create Evaluation Data

Building high-quality evaluation data is the most important and most underestimated part of the process. Poorly defined tasks produce noisy results that mislead more than they inform.

### 3.1 Principles

1. **Start with 20–50 tasks.** Don't wait for hundreds. Small, well-crafted suites detect large effect sizes early in development.
2. **Source from real failures.** Every bug report, every wrong answer during manual testing, every user complaint becomes a candidate task.
3. **Make tasks unambiguous.** Two experts looking at the same task should independently reach the same pass/fail verdict. If they wouldn't, rewrite the task.
4. **Build balanced sets.** Test both positive cases (agent should do X) and negative cases (agent should NOT do X). One-sided evals produce one-sided optimization.
5. **Create reference solutions.** Every task should have a known correct output that passes all graders. This proves the task is solvable and validates the grading logic.

### 3.2 Task Anatomy

Every evaluation task follows this structure:

```yaml
task:
  id: "unique_task_id"
  suite: "data_operations | data_analysis | routing"
  description: "Clear, unambiguous description of what the agent must do"
  input:
    excel_file: "path/to/test_file.xlsx"        # The input Excel file
    user_prompt: "The user's request in natural language"
    context: {}                                   # Optional: additional user-provided context
  reference:
    solution_file: "path/to/reference_output"     # Expected output (file, value, or report)
    solution_notes: "Explanation of the correct approach"
  graders: []                                     # List of graders (see Section 4)
  tracked_metrics: []                             # List of metrics to record (see Section 5)
  config:
    max_turns: 30                                 # Trial aborts if exceeded
    max_tokens: 50000                             # Token budget
    n_trials: 3                                   # Number of trials to run
```

### 3.3 Creating Test Excel Files

Since DAA only accepts Excel files, every task needs a test workbook. Three approaches:

**Approach A — Synthetic generation (recommended for most tasks)**

Write a script that generates Excel files with known properties. This gives full control over data characteristics: row count, null patterns, distributions, edge cases, multi-sheet relationships.

```python
# Example: Generate a sales dataset with a known revenue drop in May
import pandas as pd
import numpy as np

np.random.seed(42)
dates = pd.date_range("2024-01-01", "2024-06-30", freq="D")
revenue = np.where(
    dates.month == 5,
    np.random.normal(800, 50, len(dates)),   # May: revenue drops
    np.random.normal(1000, 50, len(dates))   # Other months: normal
)
df = pd.DataFrame({"date": dates, "revenue": revenue, "region": np.random.choice(["North", "South", "East", "West"], len(dates))})
df.to_excel("test_revenue_drop.xlsx", index=False)
```

Advantages: deterministic, reproducible, you know the ground truth because you designed it.

**Approach B — Sampled from real data**

Take anonymized subsets of real datasets. Useful for testing messy-data handling (merged cells, inconsistent formatting, encoding issues).

**Approach C — Adversarial construction**

Hand-craft files designed to break common assumptions: hidden sheets, multi-row headers, dates stored as numbers, mixed types in a column, extremely wide or tall sheets.

### 3.4 Task Examples by Suite

**Suite A — Data Operations:**

```yaml
- id: "ops_filter_001"
  description: "Filter orders where amount > 500 and region = 'West'"
  user_prompt: "Show me all orders over $500 in the West region"
  # Grader: dataframe comparison against reference filtered table

- id: "ops_agg_002"
  description: "Calculate average order value by month"
  user_prompt: "What's the average order value for each month?"
  # Grader: exact value match (with float tolerance) for each month

- id: "ops_merge_003"
  description: "Merge Sheet1 (orders) with Sheet2 (customers) on customer_id"
  user_prompt: "Combine the orders and customers sheets"
  # Grader: schema validation + row count check + sample value spot-check
```

**Suite B — Data Analysis:**

```yaml
- id: "analysis_revenue_001"
  description: "Identify root cause of 15% revenue decline in May"
  user_prompt: "Revenue dropped significantly in May. Can you analyze why?"
  excel_file: "test_revenue_drop.xlsx"   # Synthetic: drop caused by Region=South + Channel=Paid
  # Graders: phase gate check + model-based rubric for insight quality

- id: "analysis_cohort_002"
  description: "Analyze user retention across signup cohorts"
  user_prompt: "I want to understand how retention differs across our monthly signup cohorts"
  # Graders: phase gate check + reference comparison for cohort calculations
```

**Suite C — Routing:**

```yaml
- id: "route_simple_001"
  description: "Agent should NOT trigger full analysis for a simple sum"
  user_prompt: "What's the total revenue?"
  # Grader: transcript check — agent should NOT call EnterPlanMode

- id: "route_complex_001"
  description: "Agent SHOULD trigger full analysis for an open-ended question"
  user_prompt: "Why are our sales declining? Please analyze."
  # Grader: transcript check — agent MUST call EnterPlanMode
```

---

## 4. Evaluation Metrics

### 4.1 Common Metrics (Apply to All Suites)

These metrics are tracked on every trial regardless of suite.

#### Correctness Metrics

| Metric | Grader Type | Description |
|---|---|---|
| **Task pass rate** | Code | Binary: did the agent produce a correct final output? Aggregated as pass@k across trials. |
| **Partial credit score** | Code | For multi-component tasks: fraction of sub-checks passed (0.0–1.0). |
| **Factual accuracy** | Model | LLM verifies that all numeric claims in the output are consistent with the source data. |

#### Efficiency Metrics

| Metric | Grader Type | Description |
|---|---|---|
| **Turn count** | Code | Number of agent turns (tool calls + responses). Lower is better for equivalent quality. |
| **Token usage** | Code | Total input + output tokens consumed. Proxy for cost. |
| **Latency** | Code | Wall-clock time from prompt to final output. |
| **Redundant tool calls** | Code | Count of tool calls that read the same data or repeat a computation. Should be 0 or near-0. |

#### Safety / Guardrail Metrics

| Metric | Grader Type | Description |
|---|---|---|
| **No hallucinated data** | Model | LLM verifies the agent never cited numbers, columns, or sheets that don't exist in the input file. |
| **Assumption transparency** | Model | LLM checks that every assumption the agent made is explicitly stated in the output. |
| **Error handling** | Code | When given a corrupted or empty file, agent fails gracefully with a clear message instead of crashing or hallucinating. |

### 4.2 Data Operations — Problem-Specific Metrics

These apply only to Suite A (extraction, aggregation, manipulation tasks).

| Metric | Grader Type | How It's Measured |
|---|---|---|
| **Value exactness** | Code | Output values match reference within defined tolerance (default: 1e-6 for floats, exact for strings/ints). |
| **Schema correctness** | Code | Output has the correct columns, column names, and dtypes. No extra or missing columns. |
| **Row count accuracy** | Code | Output row count matches expected count. Catches silent row duplication or loss from bad joins. |
| **Order preservation** | Code | Where sort order matters, output rows are in the expected sequence. |
| **Null handling** | Code | Nulls are handled as specified (dropped, imputed, or flagged) — not silently ignored. |

#### Example Grader Configuration

```yaml
# Task: "What's the average order value by region?"
graders:
  - type: code_dataframe_compare
    reference: "ref/avg_by_region.csv"
    tolerance: 0.01
    check_columns: true
    check_dtypes: true
  - type: code_value_match
    assertions:
      - {path: "output.North", expected: 142.57, tolerance: 0.01}
      - {path: "output.South", expected: 98.33, tolerance: 0.01}
tracked_metrics:
  - {type: transcript, metrics: [n_turns, n_total_tokens]}
  - {type: latency, metrics: [time_to_last_token]}
```

### 4.3 Data Analysis — Problem-Specific Metrics

These apply only to Suite B (full analytical process tasks). They are divided into **process metrics** (did the agent follow the methodology?) and **output quality metrics** (is the final deliverable good?).

#### Process Metrics

| Metric | Grader Type | How It's Measured |
|---|---|---|
| **Phase completion** | Code | Transcript contains evidence of all 6 phases executed in order. Check for markers: `AskUserQuestion` calls (Phase 1), `EnterPlanMode` call (Phase 1→2 gate), cleaning steps (Phase 3), hypothesis testing (Phase 4), recommendations (Phase 5), executive summary (Phase 6). |
| **Plan quality** | Model | LLM evaluates the plan produced after `EnterPlanMode`: Does it reference the actual business question, KPIs, dimensions, and hypotheses? Does it map to Phases 2–6? Is it concrete (names columns, sheets, joins) or vague? Scored 1–5. |
| **Hypothesis discipline** | Code + Model | Code: count of hypotheses ≤ 3. Model: each hypothesis is impact-ranked, testable with available data, and actionable. |
| **AskUserQuestion appropriateness** | Code + Model | Code: did the agent call `AskUserQuestion` when the prompt was underspecified (true positive) and skip it when the prompt was fully specified (true negative)? Model: were the questions relevant and grounded in actual data columns? |

#### Output Quality Metrics

| Metric | Grader Type | How It's Measured |
|---|---|---|
| **Root cause identification** | Model | LLM compares agent's identified root cause(s) against reference answer. Did the agent find the primary driver? Scored: missed / partially identified / fully identified. |
| **Insight quality** | Model | LLM rubric evaluates: Are insights non-obvious? Are they supported by evidence? Do they go beyond restating the data? Scored 1–5. |
| **Recommendation specificity** | Model | LLM checks each recommendation against criteria: (a) ties to a finding, (b) names a specific action (not generic advice), (c) estimates impact where possible. Scored 1–5. |
| **Quantitative rigor** | Model | LLM evaluates: Are comparisons made against baselines? Are percentage changes / absolute numbers provided? Is statistical significance considered where appropriate? Scored 1–5. |
| **Executive summary quality** | Model | LLM rubric: Is it concise (< 200 words)? Does it lead with the key finding? Does it include a clear recommendation? Is it understandable by a non-technical stakeholder? Scored 1–5. |

#### Example Grader Configuration

```yaml
# Task: "Analyze why revenue dropped in May"
graders:
  - type: code_phase_gate
    required_phases: [business_understanding, data_understanding, 
                      cleaning, analysis, synthesis, delivery]
    required_calls: [EnterPlanMode]
    max_hypotheses: 3

  - type: model_rubric
    model: claude-sonnet-4-20250514
    rubric: |
      You are evaluating a data analysis agent's output. The agent was given
      a sales dataset where revenue dropped 15% in May. The true root causes are:
      1. Region "South" saw a 40% decline due to a pricing change on May 3rd
      2. Paid ad channel quality degraded, reducing conversion by 22%
      
      Score each dimension 1-5:
      - root_cause_identification: Did the agent find both causes?
      - insight_quality: Are insights evidence-backed and non-obvious?
      - recommendation_specificity: Are recommendations actionable?
      - quantitative_rigor: Are claims supported by numbers?
      - executive_summary: Clear, concise, decision-ready?
      
      Return JSON: {"root_cause_identification": X, "insight_quality": X, 
      "recommendation_specificity": X, "quantitative_rigor": X, 
      "executive_summary": X, "reasoning": "..."}
    pass_threshold:
      root_cause_identification: 3
      recommendation_specificity: 3

tracked_metrics:
  - {type: transcript, metrics: [n_turns, n_toolcalls, n_total_tokens]}
  - {type: latency, metrics: [time_to_last_token]}
```

### 4.4 Routing — Problem-Specific Metrics

These apply only to Suite C (capability routing tasks).

| Metric | Grader Type | How It's Measured |
|---|---|---|
| **Routing accuracy** | Code | Binary: did the agent use the correct capability (operations vs. analysis) for this prompt? |
| **False analysis rate** | Code | Proportion of simple tasks where the agent incorrectly triggered the full DA process. Should be ~0%. |
| **Missed analysis rate** | Code | Proportion of complex tasks where the agent failed to trigger the DA process. Should be ~0%. |
| **EnterPlanMode gate** | Code | For analysis tasks: `EnterPlanMode` must appear in transcript. For operations tasks: it must NOT appear. |

---

## 5. Model-Based Grader Design Guidelines

Since model-based graders are non-deterministic, they need careful design to produce reliable signal.

### 5.1 Rubric Construction

Every model-based grader must have a rubric with these properties:

- **Specific scoring anchors.** Don't just say "1 = bad, 5 = good." Define what each score means for each dimension. Example: "3 = identified 1 of 2 root causes with supporting evidence; 4 = identified both root causes but missed quantifying one."
- **Reference solution included.** The grader prompt should contain the known correct answer so the LLM can compare against it.
- **Structured output.** Always require JSON output with a `reasoning` field. This makes grader debugging possible.
- **Escape hatch.** Include an instruction like "If the agent output is too incomplete to evaluate, return score 0 with reasoning explaining what was missing." This avoids forcing the grader to hallucinate a score.

### 5.2 Calibration Protocol

Before trusting model-based graders in the pipeline:

1. **Manually grade 15–20 outputs** across the full score range.
2. **Run the model grader** on the same outputs.
3. **Compare.** If model scores diverge from manual scores by more than 1 point on a 5-point scale for >20% of cases, rewrite the rubric.
4. **Re-calibrate periodically** — especially after changing the grader model or modifying rubrics.

### 5.3 Reducing Variance

- Run each model grader **3 times** per trial and take the median score.
- Use **isolated graders per dimension** — one LLM call per quality dimension rather than one call grading everything. This reduces interference between dimensions.
- Set **temperature to 0** for grader calls.

---

## 6. Aggregation and Interpretation

### 6.1 Per-Task Scoring

For tasks with multiple graders, use weighted combination:

```
task_score = (w1 * grader_1_score) + (w2 * grader_2_score) + ... 
```

Default weights for analysis tasks:

| Grader | Weight |
|---|---|
| Phase completion (code) | 0.15 |
| Root cause identification (model) | 0.25 |
| Insight quality (model) | 0.20 |
| Recommendation specificity (model) | 0.20 |
| Quantitative rigor (model) | 0.10 |
| Executive summary (model) | 0.10 |

A task passes if `task_score >= 0.6` AND all critical graders pass (phase completion, root cause at least partially identified).

### 6.2 Per-Suite Scoring

Use **pass@1** as the primary metric (did the agent succeed on the first try?) since DAA is a single-attempt, user-facing agent. Track **pass@3** as a secondary signal to separate "capability gap" (fails all 3 trials) from "reliability gap" (succeeds sometimes but not consistently).

### 6.3 Reading Transcripts

No metric replaces reading transcripts. After every evaluation run:

- Read ALL failing trials to confirm failures are fair (agent error, not grader bug).
- Sample 20% of passing trials to confirm the grader isn't being too lenient.
- Look for patterns: is the agent consistently struggling at a specific phase? Is it over-calling `AskUserQuestion`? Is it producing bloated plans?

---

## 7. Evaluation Lifecycle

```
 ┌─────────────────────────────────────────────────────────────────┐
 │  1. Write tasks          Seed with 20-50 cases from real usage  │
 │  2. Build graders        Code-based first, model-based where    │
 │                          deterministic checking is insufficient  │
 │  3. Run trials           3 trials per task minimum               │
 │  4. Read transcripts     Every failure + 20% of passes          │
 │  5. Fix graders/tasks    If failures are unfair, fix the eval   │
 │  6. Fix agent            If failures are fair, fix the agent    │
 │  7. Graduate tasks       High pass-rate tasks move to Suite D   │
 │  8. Add harder tasks     Keep capability evals challenging      │
 │  9. Repeat               Continuously                           │
 └─────────────────────────────────────────────────────────────────┘
```

As the agent improves, capability eval tasks with consistently high pass rates should graduate into the regression suite (Suite D). This ensures the agent never loses ground on problems it has already solved, while the capability suites remain focused on pushing the frontier.
