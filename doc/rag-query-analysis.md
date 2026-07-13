# RAG Query Analysis — What Gets Sent to the Vectorstore

Empirical analysis of the actual retrieval queries issued to the two Chroma vectorstores (`consulting_case_guide`, `profitability_guide`) during real interview runs, extracted from `src/main/artifacts/runs.sqlite`.

> Note: this replaces the earlier `interviewer-question-analysis.md`, which analyzed the **Interviewer's questions to the candidate** — a different thing from the RAG retrieval queries covered here. Both docs remain in `doc/` since they answer different questions ("how does the interviewer question the candidate?" vs "what does the system ask its own knowledge base?").

## 1. Data & method

- Source: `state_json` column of the `runs` table in `runs.sqlite`. Every run's final graph state includes a key `rag_query_log` — a list of dicts, one per retrieval call, with keys `node`, `source` (`case_guide` or `profitability_guide`), `query` (the literal string sent to the retriever), `top_k`, and `chunk_ids` (what came back).
- All 68 runs have a non-empty `rag_query_log`. Extracted **508 retrieval calls total**.
- The CSVs under `src/database/rag_evaluation/` (`retrieve_golden_set.csv`, `generation_golden_set_case_guide.csv`, `generation_golden_set_profitability.csv`, plus the two `*_chunks_dump.csv` files) are a **separate, hand-authored offline eval set** (33–65 rows each) used to benchmark retrieval/generation quality against known-good answers. They are not queries issued during live interview runs — don't conflate the two when writing up methodology.

## 2. Mechanism: how a query gets built

None of these are the raw candidate message, and none are LLM-rewritten queries. They're all **deterministic template strings**, assembled in plain Python, concatenating pieces of graph state:

- `src/main/studio/rag/case_guide_context.py:28-68` — `build_case_guide_query()`: joins `case_prompt` + a per-node `node_goal` string + `focus_areas` + the latest `Candidate:` transcript line.
- `src/main/studio/rag/profitability_guide_context.py:16-52` — `build_profitability_retrieval_query()`: joins an `evaluation_target` label + `case_prompt` + the last 8 transcript lines + the latest candidate recommendation + `focus_areas` + a static `PROFITABILITY_SOURCE_NAVIGATION_GUIDE` blurb describing what the textbook covers.

These are called from four agentic nodes (`judge_node`, `eval_case_performance_node`, `eval_dialog_quality_node`, `give_feedback_node`) and two baseline call sites (`baseline_node`, `baseline` case-performance step), each hitting `store.similarity_search(query, k=top_k)` in `src/main/studio/rag/rag_case_guide.py:113` / `rag_profitability_guide.py:124`.

**Important quirk**: the `baseline` node's *first* case-guide query (190 calls, all runs) is the **raw case prompt with no template wrapper at all** — just the literal scenario text, verbatim. Every other node/query type wraps the content in a "Case prompt / Current goal / Latest reasoning / Retrieve instruction" template. This is the one place the system queries the vectorstore with nothing but raw case text.

## 3. Call volume by node

| Graph | Node | Source | top_k | Calls | Unique query texts |
|---|---|---|---|---|---|
| baseline | `baseline` | case_guide | 4 | 190 | **1** (fixed — raw case prompt only) |
| baseline | `baseline_interviewer` | profitability_guide | 3 | 110 | 22 |
| baseline | `case_performance` | profitability_guide | 5 | 40 | 8 |
| agentic | `judge` | case_guide | 4 | 56 | 14 |
| agentic | `case_performance` | profitability_guide | 5 | 28 | 7 |
| agentic | `eval_case_performance` | case_guide | 4 | 28 | 7 |
| agentic | `eval_dialog_quality` | case_guide | 4 | 28 | 7 |
| agentic | `give_feedback` | case_guide | 4 | 28 | 7 |
| **Total** | | | | **508** | |

Same pattern as the interviewer-question analysis: baseline's queries barely vary run to run (1 fixed query dominates its case_guide calls; only 22 distinct variants across 110 profitability calls), while agentic's judge/eval/feedback nodes generate a fresh query nearly every turn because they always re-inject the *latest* candidate reasoning and (for the judge) the current round's `focus_areas`.

## 4. The written battery

One concrete, full-text example per node type, taken directly from the database. Each example is followed by a note on what part of the template varies between calls of that type.

### 4.1 `baseline` → case_guide (190 calls, 1 unique text)

```
Your client is Solventus Energy, a Spanish renewable energy company. Over the past two years, EBITDA has fallen 34% even though total revenue has grown 18%. The company operates three business units: onshore wind generation, residential electricity retail, and large-scale battery storage construction. The CEO has asked you to identify what is driving the profit decline and recommend a path forward.
```
**Varies with**: nothing but the scenario itself — this is the raw `case_prompt`, no template. Same query is issued for every turn of the same scenario, so the retrieved case-guide chunks never change across a baseline interview.

### 4.2 `baseline_interviewer` → profitability_guide (110 calls, 22 unique)

```
Consulting profitability case methodology grounded in managerial accounting.
Evaluation target: baseline_interviewer
Case prompt: Your client is Solventus Energy, a Spanish renewable energy company. Over the past two years, EBITDA has fallen 34% even though total revenue has grown 18%. The company operates three business units: onshore wind generation, residential electricity retail, and large-scale battery storage construction. The CEO has asked you to identify what is driving the profit decline and recommend a path forward.
Recent transcript:
Interviewer: Your client is Solventus Energy... [full opening]
Candidate: To understand the EBITDA decline, we should analyze each business unit separately. Wind generation has a strong 41% EBITDA margin and is operationally healthy... We need more details on how revenue growth was distributed across these units.
Latest candidate recommendation: Candidate: To understand the EBITDA decline... [repeats the transcript excerpt above]
Source coverage: The profitability source is a managerial accounting textbook. It covers cost behavior, contribution margin, cost-volume-profit analysis, break-even logic, segmented income reporting, budgeting, flexible budgets, variance analysis, performance evaluation, relevant costs, and differential decision making such as add/drop, make/buy, and outsourcing. Use this source to retrieve accounting logic, definitions, formulas, analytical lenses, common mistakes, and worked reasoning patterns that help evaluate a profitability case.
Write the retrieval intent for this exact situation using the source coverage above. Retrieve only the parts of the textbook that are most useful for the current case, reasoning step, or evaluation need.
```
**Varies with**: `Recent transcript` (grows turn by turn) and `Latest candidate recommendation` (the most recent `Candidate:` line). The `Source coverage` boilerplate is always identical.

### 4.3 `case_performance` → profitability_guide, both graphs (40 baseline + 28 agentic calls)

Same template family as 4.2, but fired once at the end of the run with the *full* transcript instead of a growing one. Example (agentic, CF Baluarte Levante):

```
Consulting profitability case methodology grounded in managerial accounting.
Evaluation target: case_performance
Case prompt: Your client is CF Baluarte Levante, a mid-sized Spanish football club...
Recent transcript:
Interviewer: What evidence supports prioritizing wage reduction over other potential levers like enhancing matchday revenues or renegotiating sponsorship deals?
Interviewer: Can you break down CF Baluarte Levante's major cost components beyond wages, and explain why wage reduction should be prioritized over these?
Candidate: To prioritize wage reduction, we need to understand CF Baluarte Levante's major cost components beyond wages... [full reasoning, restates 52% broadcasting-revenue drop, EUR100M→EUR65M]
Interviewer: How do operational costs and player development expenses compare to wages in terms of their impact on CF Baluarte Levante's profitability?
Candidate: [repeats similar reasoning]
Interviewer: Can you break down the major cost components beyond wages, such as operational costs and player development expenses, to see how they compare in terms of impact on profitability?
Latest candidate recommendation: Candidate: [same reasoning excerpt]
Source coverage: [identical boilerplate as above]
Write the retrieval intent for this exact situation using the source coverage above. Retrieve only the parts of the textbook that are most useful for the current case, reasoning step, or evaluation need.
```

### 4.4 `judge` → case_guide (56 calls, 14 unique) — round 1

```
Case prompt: Your client is CF Baluarte Levante, a mid-sized Spanish football club. After being promoted to La Liga in 2019, the club took on significant debt to fund player signings and was relegated back to Segunda Division in 2023. Since relegation, profitability has deteriorated sharply. The majority owner, a US private equity fund, wants to understand why and what levers are available to improve performance within the next 18 months.
Current goal: Decide what evidence is still missing before evaluating the candidate.
Latest candidate reasoning: The specific data indicating that reducing the wage bill is more critical includes the significant drop in broadcasting revenue by approximately 52%, which was a major component of their La Liga income, now reduced from EUR100M to EUR65M annually... making wage reduction a crucial lever for aligning costs with current revenue levels.
Retrieve methodology, evaluation criteria, common mistakes, and examples of strong candidate behaviour that are most relevant to this exact situation.
```

### 4.5 `judge` → case_guide, round 2 (once `focus_areas` exist from round 1)

```
Case prompt: Your client is CF Baluarte Levante...
Current goal: Decide what evidence is still missing before evaluating the candidate.
Judge focus areas or coaching targets: test whether the candidate can break profit into revenue and cost drivers; push for a sharper recommendation with risks and next steps; check whether the candidate prioritises the biggest cost bucket
Latest candidate reasoning: To prioritize wage reduction, we need to understand CF Baluarte Levante's major cost components beyond wages...
Retrieve methodology, evaluation criteria, common mistakes, and examples of strong candidate behaviour that are most relevant to this exact situation.
```
**Varies with**: `Current goal` is fixed per node type; `Judge focus areas` only appears from round 2 onward (round 1 has no prior judge output yet); `Latest candidate reasoning` always reflects the newest turn.

### 4.6 `eval_case_performance` / `eval_dialog_quality` / `give_feedback` → case_guide (28 calls each, 7 unique each)

Same template as judge, with `Current goal` swapped per node:
- `eval_case_performance`: *"Evaluate the quality of the candidate's case-solving approach."*
- `eval_dialog_quality`: *"Evaluate the quality of the candidate's communication and interaction."*
- `give_feedback`: *"Generate actionable coaching feedback for the candidate."*

```
Case prompt: Your client is CF Baluarte Levante...
Current goal: Evaluate the quality of the candidate's case-solving approach.
Latest candidate reasoning: To prioritize wage reduction, we need to understand CF Baluarte Levante's major cost components beyond wages...
Retrieve methodology, evaluation criteria, common mistakes, and examples of strong candidate behaviour that are most relevant to this exact situation.
```
These three post-hoc nodes fire once per run each, always with the *final* candidate reasoning — so within a single run they issue near-identical queries to each other (same `Latest candidate reasoning`, different `Current goal` line), which is why chunk_ids retrieved across these three often overlap heavily.

## 5. Takeaways

1. **Query construction is templated, not LLM-generated, in both graphs.** The variation between calls comes entirely from which state fields (transcript tail, focus_areas, evaluation target label) get spliced into a fixed skeleton — there's no query-rewriting model in the loop anywhere in this pipeline.
2. **Baseline's case_guide retrieval never adapts within a run**: the same raw case prompt is queried on every turn (190 calls → 1 unique text), so the case-guide chunks returned to the baseline node are frozen at whatever the opening prompt happens to retrieve. Its profitability_guide queries do adapt (22 unique / 110 calls) because that template folds in the growing transcript.
3. **Agentic's judge-driven queries change the retrieval target as the interview progresses** — once `focus_areas` exist (round 2+), the query text itself asks the case guide for material relevant to *"push for a sharper recommendation with risks and next steps"* rather than just the opening case facts. This is a second-order effect of the same judge → interviewer feedback loop documented in `interviewer-question-analysis.md` §3, now shaping *retrieval* instead of just the next question.
4. **The three post-run eval/feedback nodes (`eval_case_performance`, `eval_dialog_quality`, `give_feedback`) issue near-duplicate case_guide queries** — same case prompt and same final candidate reasoning, differing only in one line (`Current goal`). Worth checking whether their retrieved chunk sets are similar enough that a single shared retrieval call could serve all three, if retrieval cost/latency across these three nodes ever becomes a concern.
5. **Coverage gap carries over from the question analysis**: all of this is drawn from Case 1 (Solventus) and a small Case 2 (CF Baluarte, 3 runs) sample; Case 3 (Verdex) has no runs yet, so the "1 unique / 190 calls" baseline finding in particular should be re-checked once more scenarios exist, in case it's an artifact of this specific case's short case prompt rather than a general property of the `baseline` node.
