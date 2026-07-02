# Profitability Case Common Schema

This document extracts the shared structure across the repository's current profitability cases and turns it into an authoring template for new synthetic datasets.

Corpus reviewed:
- 10 Duke profitability cases
- 12 AGSM profitability cases
- Total: 22 profitability cases in `03-MVP/database/duke_cases` and `03-MVP/database/agsm_cases`

## What All Profitability Cases Have in Common

Across industries and difficulty levels, almost every profitability case follows the same logic:

1. A client reports declining profit, flat profit, margin pressure, or weak economics in a business that otherwise looks viable.
2. The candidate is expected to start with a profit tree or a revenue-cost structure.
3. The case then narrows to one primary driver rather than many equal causes.
4. The primary driver is supported by a small number of decisive facts, usually one or two exhibits or a compact data reveal.
5. The candidate must translate diagnosis into an action recommendation, not just identify the problem.
6. Strong performance requires both math and business judgment:
   - diagnose the driver correctly
   - quantify impact
   - discuss risks, implementation, and alternatives

In short, the shared pattern is:

`profit decline -> structured diagnosis -> targeted evidence -> quantified implication -> recommendation`

## Core Anatomy

### 1. Opening Business Situation

Every case begins with a short client setup that establishes:
- company type and industry
- geography or operating footprint
- what changed in profit, margin, or growth
- approximate time horizon of the problem
- why the client cares now

Typical opening tensions:
- profits down while revenue is up
- profits down while revenue is flat
- market share stable but margin falling
- one business line subsidizing another
- cost inflation the client does not fully understand
- a channel, customer, or product mix shift hiding inside the aggregate numbers

### 2. Expected Initial Framework

All cases implicitly want the candidate to begin with a structured profitability lens. The exact vocabulary changes, but the expected opening framework is usually one of:
- revenue vs. cost
- profit by product / customer / channel / geography
- fixed vs. variable cost
- price x volume on the revenue side
- unit economics or contribution margin

The important invariant is not the specific framework name. It is that the candidate segments the problem before solving it.

### 3. Hidden Driver

Each case is built around one dominant answer. Examples from the corpus include:
- cost inflation in a key input
- unfavorable product mix
- unfavorable channel or geography mix
- underutilized capacity
- price or margin compression
- labor cost escalation
- poor schedule or operating design
- structurally high cost position versus competitors

There may be secondary issues, but the case usually has one main economic story that explains most of the decline.

### 4. Progressive Evidence Reveal

The answer is almost never given upfront. The case releases evidence in stages:
- initial background facts
- financial breakdown
- exhibit or table
- follow-up prompt
- implementation or risk question

This staged reveal is essential because it lets the interviewer test whether the candidate:
- asks for the right information
- updates hypotheses logically
- extracts insight from imperfect data

### 5. Quantitative Inflection Point

Every profitability case contains at least one calculation that changes the conversation from hypothesis to conclusion. Common math formats:
- compare profit across segments
- compute contribution margin
- isolate the incremental impact of a mix shift
- evaluate a pricing or cost-change scenario
- test whether an action closes a target profit gap
- estimate unit economics after an operational change

The math is usually decision-oriented, not abstract.

### 6. Recommendation Under Constraints

The final step is always managerial. The candidate must recommend what to do, not just what is true.

Strong recommendations in the corpus usually include:
- the answer
- the economic reason
- major risks
- implementation considerations
- what to test next if uncertainty remains

## Common Block Pattern In The Repository

The repository currently expresses profitability cases as staged blocks inside `case_content`.

Most Duke cases use:
- `prompt`
- `guidance`
- `exhibit`
- `expected_analysis`
- `final_recommendation`

Most AGSM cases use:
- `prompt`
- `guidance`
- `expected_analysis`
- `data`
- `final_recommendation`

Even when block names differ, they map to the same logical stages:

| Logical stage | Common purpose | Current block types |
| --- | --- | --- |
| Opening | Introduce client and problem | `prompt` |
| Hidden interviewer notes | Expected framework, facts to reveal, desired insights | `guidance` |
| Evidence | Numbers, chart, table, or fact pattern | `exhibit`, `data` |
| Solution checkpoint | What the candidate should conclude from the evidence | `expected_analysis`, `guidance` |
| Closing | Ask for final synthesis and action | `final_recommendation` |

## Synthetic Authoring Template

Use this template when creating a new profitability case.

### A. Case Header

Define:
- company name
- industry
- geography
- business model
- exact profitability symptom
- time period

Example authoring prompt:

`A mid-market home insulation installer in Spain has grown revenue 20% in two years, but EBITDA margin has fallen from 14% to 6%.`

### B. Narrative Tension

Add 2 to 4 lines that make the case interview-worthy:
- a recent expansion
- a change in costs
- a segment mix shift
- a new competitor
- an operational bottleneck
- a leadership constraint or strategic preference

This should create ambiguity without making the case messy.

### C. Core Economic Question

State the single question the case is really about:
- Which segment is destroying profit?
- Is the issue revenue, cost, or mix?
- Should the client change pricing, footprint, capacity, or product mix?
- Can one intervention restore target profit?

If you cannot write this in one sentence, the case is too diffuse.

### D. Candidate-Visible Opening Prompt

The first prompt should contain only enough information to trigger a good framework:
- who the client is
- what profit problem exists
- what the client wants

Do not include the root cause yet.

### E. Interviewer-Only Hidden Logic

Write down:
- expected opening framework
- facts the interviewer can reveal if asked
- the true dominant driver
- common traps or weak paths

This is what makes the case evaluable.

### F. Quantitative Reveal

Include one decisive numerical block. Good options:
- segment P&L
- price-volume-cost table
- product mix comparison
- utilization and capacity data
- before/after margin comparison
- customer or channel profitability view

Design rule:
- one exhibit should be enough to move a strong candidate materially closer to the answer

### G. Insight Checkpoint

After the math, define the exact conclusion the candidate should reach. This should be written explicitly for the interviewer or judge:
- what changed
- why it matters economically
- why alternative explanations are weaker

### H. Decision Prompt

Ask the candidate to choose an action:
- proceed or not
- prioritize segment A or B
- change price or keep price
- cut cost here or shift mix there

The best profitability cases force a tradeoff, not a generic brainstorm.

### I. Final Recommendation Standard

A complete final answer should include:
- recommendation
- supporting numbers
- 1 to 3 key risks
- next steps or implementation considerations

## Minimum Data Requirements For A Good Synthetic Case

To feel like the current corpus, a new case should usually have:
- 1 clear client objective
- 1 dominant root cause
- 1 to 3 supporting data reveals
- 1 core calculation
- 1 decision with constraints

If a case has many unrelated root causes, many exhibits, or no decisive calculation, it will feel less like the current profitability set.

## Reusable Root-Cause Menu

Most current profitability cases can be generated from a small set of root-cause patterns:
- adverse mix shift by product, channel, customer, or geography
- input cost inflation
- labor cost increase
- utilization or capacity mismatch
- structurally weak cost position
- pricing pressure without matching cost improvement
- margin dilution from a new segment
- operational design problems that make revenue look healthy but economics poor

This is the best menu to reuse for synthetic generation because it matches the source corpus closely.

## Recommended JSON-or-Markdown Content Skeleton

Whether you store the synthetic case as markdown or later convert it to JSON, keep this content order:

1. Case overview
2. Candidate opening prompt
3. Hidden interviewer guidance
4. Reveal 1: base facts
5. Reveal 2: quantitative exhibit or data
6. Expected insight
7. Optional follow-up calculation or creativity prompt
8. Final recommendation prompt
9. Hidden ideal answer

## Quality Checklist

Before accepting a new synthetic profitability case, verify:
- the profit problem is explicit
- the case can be opened with a standard profitability structure
- one primary economic driver explains most of the issue
- the numbers are sufficient to diagnose that driver
- the math changes the recommendation, not just the detail
- the final question requires action, not summary only
- risks and implementation tradeoffs are real
- the case is solvable in an interview without excessive industry knowledge

## Short Fill-In Template

```md
# [Case Title]

## Context
[Company], a [industry] player in [geography], has seen [profit symptom] over [time period]. The client wants to [objective].

## Narrative Tension
- [Recent change or strategic tension]
- [Constraint]
- [Why this is not obvious]

## Candidate Prompt
[Opening prompt shown to the candidate]

## Hidden Interviewer Guidance
- Expected framework: [profit tree / segment profitability / price-volume-cost]
- True primary driver: [single dominant driver]
- Facts to reveal if asked: [3-6 bullets]
- Common weak path: [typical mistake]

## Quantitative Reveal
[Table, exhibit, or concise numeric data]

## Expected Insight
[What a strong candidate should conclude]

## Decision Prompt
[What action should the client take and why?]

## Ideal Recommendation
- Recommendation: [action]
- Why: [economic logic]
- Risks: [1-3]
- Next steps: [pilot / validate / implement]
```

## Bottom Line

If you want new synthetic profitability datasets to match the existing corpus, optimize for this formula:

`simple opening + one dominant hidden driver + one decisive quantitative reveal + action-oriented recommendation`

That is the stable common schema across the current profitability cases in this repository.
