---
name: data-analysis
description: >
  Professional data analysis skill for the Data Analyst Agent (DAA).
  Trigger this skill ONLY when the user explicitly asks to "analyze", "investigate",
  "find the cause of", "deep dive into", or asks a complex, open-ended analytical
  question that requires multi-step reasoning across data (e.g. "Why did revenue drop?",
  "What's driving churn in Q2?", "Which campaigns actually moved the needle?").
  DO NOT trigger for simple questions ("what's the total revenue?"), data extraction
  ("pull all rows where status = active"), basic aggregation ("average order value by month"),
  or straightforward data manipulation ("add a column", "pivot this table", "merge these sheets").
  If the user's request can be answered with a single query or formula, skip this skill entirely.
  The boundary: if the answer requires hypothesis formation, segmentation, and interpretation — use this skill.
  If it just requires reading or reshaping data — don't.
---

# Data Analysis Skill

## Overview

This skill defines a strict, phased process for professional data analysis. It transforms
a vague analytical question into actionable insights and recommendations. The agent's job is
not to produce charts — it is to produce decisions.

**Agent stack:** Claude Agent SDK
**Input format:** Excel files only (.xlsx / .xls), which may contain multiple sheets.

---

## When NOT to Use This Skill

Recognize these patterns and handle them directly without invoking the full DA process:

| User request pattern             | What to do instead                          |
|----------------------------------|---------------------------------------------|
| "What's the total of column X?"  | Read the file, compute, answer.             |
| "Filter rows where Y > 100"     | Read the file, filter, return result.       |
| "Merge Sheet1 and Sheet2 on ID" | Read the file, merge, return result.        |
| "Create a pivot table of Z"     | Read the file, pivot, return result.        |
| "Convert this to CSV"           | Read the file, convert, return result.      |
| "Show me the first 10 rows"     | Read the file, display, done.              |

These are data extraction or manipulation tasks — not analysis.

---

## The Process

The full DA process has 6 phases. Every phase is mandatory and must be executed in order.
Never skip ahead. Never start Phase 3 without completing Phase 2.

```
Phase 1: Business Understanding  ←  YOU ARE HERE FIRST. ALWAYS.
Phase 2: Data Understanding
Phase 3: Data Cleaning & Preparation
Phase 4: Analysis & Hypothesis Testing
Phase 5: Synthesis & Recommendations
Phase 6: Delivery
```

After completing Phase 1, ALWAYS call `EnterPlanMode` to produce a detailed execution
plan before proceeding. The plan must map to Phases 2–6 with concrete steps.

---

## Phase 1 — Business Understanding

**Objective:** Fully define the problem before touching the data seriously.

### Step 1.1 — Quick Data Exploration

Before asking the user anything, do a fast scan of the uploaded Excel file(s):

- List all sheet names
- For each sheet: row count, column names, dtypes, first 5 rows
- Note obvious data characteristics (date ranges, categorical fields, numeric fields)

This gives you context to ask smarter questions in the next step.

### Step 1.2 — Ensure the Problem Is Fully Defined

You must have clear answers for these three items before moving forward:

1. **Business Question** — What specific question are we answering?
2. **KPIs / Metrics** — Which metrics matter for this question?
3. **Dimensions / Segments** — Along which axes should we slice the data?

**If the user's request does not clearly define all three, call `AskUserQuestion`.**

Frame your questions based on what you learned in Step 1.1. Reference actual columns,
sheets, and data ranges you found — don't ask generic questions.

Examples of good `AskUserQuestion` usage:

```
I see the file has columns: revenue, cost, region, channel, date.

To analyze this properly, I need to clarify:
1. Are we focused on revenue, profit (revenue - cost), or both?
2. Should I break this down by region, channel, or both?
3. What time period matters most — the full dataset (Jan–Jun 2024) or a specific range?
```

Do NOT ask about things you can infer from the data. If there's a "date" column spanning
Jan–Dec 2024, don't ask "what time range?" unless the user hinted at a specific window.

### Step 1.3 — Formulate Hypotheses

Once the problem is defined, generate **exactly 2–3 hypotheses** — no more.

Selection criteria for hypotheses:
- **Impact**: Would confirming this hypothesis explain a large portion of the observed problem?
- **Testability**: Can you actually test it with the available data?
- **Actionability**: If true, does it lead to a concrete recommendation?

Format:

```
H1: [Most likely / highest impact hypothesis]
H2: [Second most likely hypothesis]
H3: [Alternative / contrarian hypothesis]  (optional — only if genuinely valuable)
```

Example:

```
Business question: "Why did revenue drop 15% in May?"

H1: The drop is concentrated in the Southeast region due to a pricing change on May 3rd.
H2: Paid ad spend decreased in May, reducing traffic volume across all regions.
H3: A product stockout in the top-selling SKU caused the revenue gap.
```

### Step 1.4 — Call `EnterPlanMode`

After completing Steps 1.1–1.3, ALWAYS call `EnterPlanMode`.

The plan must:
- Reference the specific business question, KPIs, dimensions, and hypotheses from Phase 1
- Map every subsequent step to Phases 2–6
- Be concrete — name actual columns, sheets, and transformations
- Estimate which hypothesis each analysis step is testing
- Include validation checkpoints (e.g., "reconcile metric X before proceeding")

Plan template:

```
## Analysis Plan

### Context
- Business Question: [from Step 1.2]
- KPIs: [from Step 1.2]
- Dimensions: [from Step 1.2]
- Hypotheses: [from Step 1.3]

### Phase 2 — Data Understanding
- [ ] Profile each sheet: nulls, duplicates, outliers, distributions
- [ ] Identify grain of each table (1 row = 1 what?)
- [ ] Validate key metrics against any known benchmarks
- [ ] Map relationships between sheets (join keys, foreign keys)

### Phase 3 — Data Cleaning & Preparation
- [ ] Handle missing values in [specific columns]
- [ ] Remove duplicates using [specific logic]
- [ ] Standardize [dates/currencies/categories] as needed
- [ ] Build analysis-ready dataset by joining [Sheet X] with [Sheet Y] on [key]

### Phase 4 — Analysis & Hypothesis Testing
- [ ] H1: [specific analysis steps — e.g., segment revenue by region + time]
- [ ] H2: [specific analysis steps]
- [ ] H3: [specific analysis steps, if applicable]
- [ ] Additional exploratory analysis if hypotheses are inconclusive

### Phase 5 — Synthesis & Recommendations
- [ ] Summarize which hypotheses were confirmed/rejected and why
- [ ] Quantify the impact of each confirmed root cause
- [ ] Formulate 2–4 specific, actionable recommendations

### Phase 6 — Delivery
- [ ] Write Executive Summary
- [ ] Prepare supporting visualizations
- [ ] Document methodology and assumptions
```

Do NOT proceed to Phase 2 until the plan is finalized.

---

## Phase 2 — Data Understanding

**Objective:** Know the data deeply before analyzing it.

### Checklist

1. **Schema exploration** — For every sheet: column names, types, sample values, enums.
2. **Data profiling** — For every column: null rate, duplicate rate, unique count, min/max,
   distribution shape (for numerics), top categories (for categoricals).
3. **Grain identification** — Define what one row represents in each sheet. This is critical.
   Wrong grain = wrong analysis. Document it explicitly.
4. **Cross-sheet relationships** — Identify join keys. Verify they're actually unique where
   expected (e.g., if `order_id` should be unique in the orders sheet, confirm it).
5. **Metric validation** — If the user mentioned any known numbers ("revenue was $2M last month"),
   check whether your data reproduces them. Flag discrepancies immediately.

---

## Phase 3 — Data Cleaning & Preparation

**Objective:** Produce an analysis-ready dataset.

### Checklist

1. **Handle missing values**
   - Decide per column: drop, impute (mean/median/mode/forward-fill), or flag.
   - Document every decision and its reasoning.

2. **Remove duplicates**
   - Use appropriate dedup logic (exact match vs. fuzzy, which columns define uniqueness).
   - Log how many rows were removed.

3. **Standardize**
   - Dates: consistent format and timezone.
   - Currency: single unit.
   - Categories: merge synonyms (e.g., "NY" / "New York" / "new york").

4. **Build the analytical dataset**
   - Join sheets as needed.
   - Create derived columns (e.g., profit = revenue − cost, cohort = signup month).
   - Verify row counts after every join — unexpected row inflation means a grain mismatch.

---

## Phase 4 — Analysis & Hypothesis Testing

**Objective:** Test each hypothesis with evidence, not intuition.

### For each hypothesis:

1. **State the hypothesis clearly** — what you expect to find.
2. **Define the test** — what analysis would confirm or reject it.
3. **Execute the analysis** — segment, compare, compute.
4. **State the result** — confirmed, rejected, or inconclusive, with evidence.

### Analysis techniques (use as appropriate):

| Technique            | When to use                                      |
|----------------------|--------------------------------------------------|
| Segment comparison   | Compare metric across groups (region, cohort)     |
| Trend analysis       | Identify changes over time                        |
| Funnel analysis      | Find drop-off points in a process                 |
| Cohort analysis      | Compare behavior of groups defined by time         |
| Correlation analysis | Test relationships between variables              |
| Contribution analysis| Decompose a metric change into its components     |
| Outlier detection    | Identify anomalous data points skewing results    |

### Rules:

- Always compare against a baseline (prior period, benchmark, control group).
- Always check if a pattern is statistically meaningful vs. noise.
- If all hypotheses are rejected, do not force a narrative. State that the initial
  hypotheses were inconclusive and identify new directions from what you learned.

---

## Phase 5 — Synthesis & Recommendations

**Objective:** Turn findings into decisions.

### Structure:

1. **Root cause summary** — Which hypotheses were confirmed? What was the primary driver?
   Quantify impact (e.g., "Region Southeast accounts for 60% of the revenue decline").

2. **Recommendations** — 2–4 specific, actionable next steps. Each recommendation must:
   - Tie directly to a finding
   - Be specific enough to act on ("Pause Campaign X" not "Improve marketing")
   - Include expected impact if possible

3. **Risks and caveats** — What assumptions were made? What data limitations exist?
   What could invalidate the conclusions?

---

## Phase 6 — Delivery

**Objective:** Communicate results clearly to stakeholders.

### Executive Summary format:

```
[METRIC] changed by [AMOUNT] over [PERIOD] due to:
- [Root cause 1] — [quantified impact]
- [Root cause 2] — [quantified impact]

Recommendations:
1. [Action] — expected to [impact]
2. [Action] — expected to [impact]

Key caveat: [most important limitation]
```

### Supporting materials:

- **Visualizations**: trend charts, segment comparisons, funnel diagrams — only charts that
  directly support a finding. No decorative charts.
- **Detailed findings**: technical breakdown for stakeholders who want to dig deeper.
- **Methodology note**: data sources, cleaning decisions, assumptions, analysis period.

---

## Reading Excel Files — Technical Notes

Since all inputs are Excel files:

- Always check for multiple sheets — they often represent different entities or time periods.
- Watch for merged cells, multi-row headers, or metadata rows at the top of sheets.
  Clean these before processing.
- Be aware of Excel-specific issues: dates stored as numbers, trailing whitespace in
  categories, formulas vs. values, hidden sheets.
- When a sheet has no clear header row, infer it from the data or ask the user.

---

## Critical Reminders

1. **Never skip Phase 1.** The most common failure mode is jumping into data without
   understanding the question. A perfect analysis of the wrong question is worthless.

2. **Always `EnterPlanMode` after Phase 1.** The plan is your contract with the user.
   It ensures alignment before you invest effort in execution.

3. **Hypotheses drive the analysis.** Every analysis step in Phase 4 should be tied to
   testing a specific hypothesis. Aimless exploration produces noise, not insight.

4. **Output decisions, not dashboards.** The deliverable is "here's what to do and why" —
   not "here's a chart."

5. **Document everything.** Every cleaning decision, every assumption, every caveat.
   Reproducibility is non-negotiable.

6. **Grain awareness.** Before any join or aggregation, confirm the grain of each table.
   This single check prevents the most common class of analytical errors.
