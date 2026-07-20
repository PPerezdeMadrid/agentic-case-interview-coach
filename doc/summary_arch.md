# System Architecture Summary

## 1. Overview

The active program is a LangGraph-based evaluation workbench for consulting case interview simulations. It currently supports two executable graph variants:

1. `baseline`: one graph node acts as interviewer, evaluator, and feedback-writer in a single combined LLM call.
2. `agentic`: separate interviewer, judge, evaluation, and feedback nodes coordinate across several LLM calls.

The current MVP is not yet a live student-facing application. Instead, it runs controlled simulations with:

- a scenario JSON that defines the candidate profile and expected scores;
- a case JSON that contains prompt, visible data blocks, hidden guidance, and final recommendation;
- a shared rubric;
- an LLM-backed synthetic candidate node used to answer interview questions.

Beyond the baseline-vs-agentic comparison, the project has grown a second axis of experimentation: **retrieval quality and RAG ablation**. A golden-set-driven retrieval evaluator and a with/without-RAG scoring ablation now sit alongside the original run/trace/human-evaluation workbench, and a batch-experiment runner (`run_all_scenarios.py`) produces the repeated-run data both the "Experiment" and "RAG Evaluation" dashboard pages consume.


## 2. Active Runtime Structure

The active code lives under `src/main/`:

- `studio/`: LangGraph graphs, prompt orchestration, retrieval, loading, and persistence
- `studio/rag/`: dual RAG retrieval implementations plus golden-set/chunk-dump tooling
- `web/`: Flask dashboard for inspecting runs, traces, experiments, RAG evaluation, and human evaluations
- `artifacts/`: SQLite database of single runs, plus `batch_runs/` snapshots from the batch experiment runner
- `database/vectorstore/`: generated Chroma indices only (no source documents)
- `server_HPC/`: standalone FastAPI servers + SLURM launcher for self-hosting Mistral-Nemo/Llama-3.3-70B on the university GPU cluster; not imported by the active graphs, and corresponds to the commented-out GPU-hosted client block in `llm_server.py`

Supporting assets live under:

- `src/scenarios/synthetic-based/`: scenario definitions actually used by the loader
- `src/scenarios/casebook-based/`: casebook-derived scenario JSON, not referenced by any code path yet
- `src/synthetic-dataset/`: case content used by the active runtime
- `src/database/`: source PDFs, `rag_evaluation/` golden sets and chunk dumps, and a case-bank (`agsm_cases/`, `duke_cases/`, `harvard_cases/`, `casebooks.json`, `case_metadata.json`) that is likewise not wired into any code path yet
- `src/schemas/`: standalone JSON Schema files, not referenced by any Python code (superseded in practice by the Pydantic models in `state.py`)
- `doc/`: architecture and prompt documentation
- `archive/`: older prototypes and research material, not part of the active system

Directories described above as "not referenced by any code path" are planned-but-not-yet-integrated data layers, not dead code left over from a removed feature — they're kept for a future integration pass.


## 3. High-Level Execution Model

Both graph variants consume the same runtime bundle:

```mermaid
flowchart TD
    A[Scenario JSON] --> D[Loader]
    B[Case JSON] --> D
    C[Rubric JSON] --> D

    D --> E[Initial Graph State]

    E --> F1[Baseline Graph]
    E --> F2[Agentic Graph]

    F1 --> G[Persisted Run]
    F2 --> G

    G --> H[Flask Dashboard]
    G --> I[Human Evaluation]

    J[Batch Experiment Runner] --> F1
    J --> F2
    F1 --> K[Batch Run Directory]
    F2 --> K
    K --> L[Experiment Page]
    K --> M[RAG Ablation]
```

The loader resolves a scenario, loads the referenced case, adapts the shared rubric, and builds a runtime state consumed by the graph. `run_all_scenarios.py` drives either graph repeatedly across scenarios (with a configurable repeat count) and writes per-graph and combined JSONL/CSV plus a `summary.json` into a timestamped `src/main/artifacts/batch_runs/<batch>/` directory, which is what the Experiment page and `make rag-ablation` read from.


## 4. Shared State Model

Both graphs use the same typed state object (`AgenticGraphState`, `src/main/studio/state.py`). The main fields are:

- `scenario_ref`
- `case_prompt`
- `candidate_profile`
- `transcript`
- `turn_index`
- `case_guidance`
- `case_data`
- `case_recommendation`
- `focus_areas`
- `enough_evidence`
- `judge_round`
- `case_performance`
- `quality_dialog`
- `data_gathered`
- `retrieved_profitability_context`
- `candidate_reasoning` / `interviewer_reasoning`: last free-text reasoning captured from each role, used for guide-retrieval query building
- `rag_query_log`: append-only log of retrieval calls (query, source, hit count) across the run, using a custom reducer so the two parallel eval nodes don't clobber each other's entries
- `llm_usage`: append-only per-call token accounting, same append reducer pattern as `rag_query_log`
- `run_id` / `trace_step_index`: identifiers used by the tracing/persistence layer
- `thread_id`, `rubric_data`

The transcript is the main shared evidence structure. It stores interviewer turns, candidate turns, evaluation markers, and the final feedback line.


## 5. Input Assets

### 5.1 Scenarios

Synthetic scenarios live in `src/scenarios/synthetic-based/`. A scenario primarily provides:

- `scenario_id`
- `case_id`
- candidate persona instructions
- expected rubric scores for later comparison

### 5.2 Cases

Case JSON files live in `src/synthetic-dataset/`. They are adapted into:

- `opening_block`
- `visible_blocks`
- `hidden_blocks`
- `blocks_by_type`

This allows the interviewer to reveal only candidate-visible data while still keeping hidden guidance and the expected recommendation available for evaluation.

### 5.3 Rubric

The runtime uses one shared rubric file from `src/scenarios/rubric/rubric.json`. It is adapted into a stable list of dimensions with criteria and score scale metadata. (A separate, capitalized `src/database/Rubric/rubric.json` also exists but is not read by any code — the loader only reads the lowercase path above.)


## 6. Baseline Graph

The baseline graph is compiled from `src/main/studio/baseline.py`.

```mermaid
flowchart TD
    Start --> LoadScenario
    LoadScenario --> BaselineNode
    BaselineNode -->|needs more evidence| Candidate
    Candidate --> BaselineNode
    BaselineNode -->|enough evidence| PersistRun
    PersistRun --> End
```

The baseline flow works as follows:

1. Load scenario and case assets.
2. Run a single, traced baseline interviewer/evaluator node (`baseline_node`), which — inline, on each turn — decides whether to consult the case guide (deliberately simple/query-less lookup) and the profitability guide (LLM-scouted, query-driven) before producing its next move.
3. Alternate with the (also traced) synthetic candidate node until the node decides it has enough evidence, or until `MAX_BASELINE_TURNS` is reached.
4. On the final forced turn, produce case-performance scoring, dialog-quality scoring, and final feedback in the same combined LLM call (`parse_baseline_output`, action ∈ `{question, reveal, evaluate}`).
5. Persist the final run.

In this architecture, the same logical agent handles interviewing, stopping, retrieval, evaluation, and final feedback — there is no separate persistent-retrieval node or standalone eval/feedback node. This single-node design is also what the RAG ablation tooling patches around when producing a "without RAG" baseline arm.


## 7. Agentic Graph

The agentic graph is compiled from `src/main/studio/agentic.py`.

```mermaid
flowchart TD
    Start --> LoadScenario
    LoadScenario --> Interviewer
    Interviewer -->|continue interview| Candidate
    Candidate --> Interviewer
    Interviewer -->|ready for review| Judge
    Judge -->|more evidence needed| Interviewer
    Judge -->|enough evidence| EvalCasePerformance
    Judge -->|enough evidence| EvalDialogQuality
    EvalCasePerformance --> GiveFeedback
    EvalDialogQuality --> GiveFeedback
    GiveFeedback --> PersistRun
    PersistRun --> End
```

The agentic flow separates responsibilities:

- `interviewer_node`: asks the next question or reveals candidate-visible data
- `candidate_node`: produces the synthetic candidate response and updates `data_gathered`
- `judge_node`: decides whether enough evidence exists and, if not, writes `focus_areas` (routing function `route_after_judge_agentic_02`)
- `eval_case_performance_node`: scores case-solving performance
- `eval_dialog_quality_node`: scores communication quality
- `give_feedback_node`: writes final coaching feedback

`eval_case_performance` and `eval_dialog_quality` run as genuinely parallel branches of the same LangGraph superstep (both fan out from `judge` and fan back into `give_feedback`). This is why `rag_query_log` and `llm_usage` use append-only reducers in the shared state — without them, concurrent writes from the two eval nodes would clobber each other.

The interviewer uses judge-generated `focus_areas` as direct instructions for the next follow-up question. This is the key behavioural difference from the baseline graph.


## 8. Synthetic Candidate Role

The current system simulates the candidate with an LLM node rather than a human user. The candidate node:

- sees only public transcript lines;
- does not see judge notes or hidden guidance;
- follows the scenario persona;
- updates a running `data_gathered` list of factual case information learned so far.

This design keeps experiments reproducible and allows architecture comparison before building a full interactive front end.


## 9. Retrieval Architecture

The active retrieval layer is split into two independent paths, each with a persistent Chroma vector store built from a source PDF in `src/database/` and persisted under `src/main/database/vectorstore/`. Both graphs import a stable "context" bridge module rather than the raw retrieval module, so tests can patch retrieval without touching the underlying vector store.

### 9.1 Case Guide RAG

Implemented in `src/main/studio/rag/rag_case_guide.py`, fronted by `case_guide_context.py`.

- indexes `src/database/ConsultingCaseGuide-PPML.pdf` into `src/main/database/vectorstore/consulting_case_guide/` (`FastEmbedEmbeddings`, `BAAI/bge-small-en-v1.5`);
- builds query text from graph state, node goal, focus areas, and latest interviewer/candidate reasoning;
- the baseline graph uses a deliberately simpler, query-less retrieval path (`get_baseline_case_guide_context`) for this source, so the agentic-vs-baseline comparison also implicitly compares scouted vs. unscouted case-guide retrieval.

### 9.2 Profitability Guide RAG

Implemented in `src/main/studio/rag/rag_profitability_guide.py`, fronted by `profitability_guide_context.py`.

- indexes `Principles-of-Managerial-Accounting-profitability.pdf` into `src/main/database/vectorstore/profitability_guide/`, plus a hand-written navigation guide (`src/database/profitability_source_navigation.json`) that gets folded into the scouting prompt;
- performs an LLM-scouted retrieval decision (`ProfitabilityRagScoutingDecision`) in both baseline and agentic graphs — the model explicitly decides whether to consult this source before querying it;
- is used mainly for case-performance evaluation.

The retrieval split exists because case-specific methodology and general consulting/accounting guidance play different roles in the prompts, and because the two sources warranted different retrieval-decision strategies (query-less vs. LLM-scouted) to compare.

### 9.3 Retrieval Evaluation Tooling

`src/main/studio/rag/` also holds evaluation/authoring tooling, run manually (no `make` target):

- `dump_vectorstore_chunks.py`: dumps every chunk of both vector stores to CSV for manual golden-set authoring.
- `build_retrieve_golden_set_chunk_ids.py`: backfills ground-truth `source_chunk_ids` onto a golden set by embedding each row, similarity-searching the relevant store, then re-ranking by lexical word-overlap against the expected answer (embedding similarity alone favored section-heading chunks over the true match).

See §11 for how this tooling feeds retrieval-quality metrics and RAG ablation.


## 10. LLM Layer

All active graph nodes use per-role LLM clients defined in `src/main/studio/llm_server.py` and assigned in `src/main/studio/node.py`. Six `ChatOpenAI` clients are defined; not all are wired into an active role:

| Client | Provider / default model | Wired to |
|---|---|---|
| `lmstudio_llm_server` | Local LM Studio (`LMSTUDIO_MODEL`) | interviewer, candidate, feedback (agentic + baseline) |
| `judge_llm_server` | OpenRouter, `meta-llama/llama-3.1-70b-instruct` | judge (agentic); all four roles (baseline) |
| `interviewer_llm_server` | OpenRouter, `qwen/qwen-2.5-32b-instruct` | defined, currently unused (agentic interviewer runs on LM Studio instead — see below) |
| `candidate_llm_server` | OpenRouter, `mistralai/mixtral-8x7b-instruct` | defined, currently unused (agentic candidate runs on LM Studio instead) |
| `openai_llm_server` | OpenAI, `gpt-5.4-nano` | not wired to any graph role; pinged only by the API-connection smoke test |

In the **agentic** graph, `node.py` currently assigns `interviewer_llm = feedback_llm_server` and `candidate_llm = feedback_llm_server` — i.e. interviewer and candidate both run on the local LM Studio endpoint, and only `judge_llm` uses OpenRouter (Llama-3.1-70B). This is a narrower split than the original per-role-on-OpenRouter design (a source-comment in `node.py` still describes the old wiring and is stale); the intent, per the most recent commit touching this ("Improved candidate's profile"), was to move candidate/interviewer back onto the local model. The **baseline** graph is unaffected by this and still runs all four roles on `judge_llm_server` (OpenRouter Llama-3.1-70B) with zero local dependency.

Relevant env vars: `LMSTUDIO_BASE_URL`/`LMSTUDIO_MODEL`/`LMSTUDIO_API_KEY`/`LMSTUDIO_TEMPERATURE`, `OPENROUTER_BASE_URL`/`OPENROUTER_API_KEY`/`OPENROUTER_MODEL_{INTERVIEWER,CANDIDATE,JUDGE}`/`{INTERVIEWER,CANDIDATE,JUDGE}_TEMPERATURE`, `OPENAI_*`. A commented-out block in `llm_server.py` (`candidate_llm_server_gpu`, `judge_llm_server_gpu`) targets the self-hosted endpoints exposed by `src/main/server_HPC/server.py` (`localhost:18401`/`18402`) — kept in case the project reverts to self-hosted inference on the university HPC GPU cluster.


## 11. RAG Evaluation and Ablation

Two independent evaluation mechanisms sit behind the workbench's single "RAG Evaluation" page — no "RAG Triad" (context-relevance/faithfulness/answer-relevance) evaluator was ever implemented; that idea was dropped from the design diagram in favor of the two below.

### 11.1 Retrieval-Quality Metrics

Computed live (recomputed on each page load) by `src/main/web/retrieval_eval.py` against **generation golden sets** — `src/database/rag_evaluation/generation_golden_set_case_guide.csv` and `generation_golden_set_profitability.csv`. Each row carries a query, an expected answer, a category tag, and exact ground-truth `source_chunk_ids`. Metrics: Precision@K, Recall@K, Hit Rate, and Mean Reciprocal Rank, broken down overall and by category/source document.

A second CSV, `retrieve_golden_set.csv`, was an earlier attempt at a golden set keyed by document/page rather than chunk id; it turned out unusable for the profitability PDF (the source uses the textbook's own printed pagination, offset from the PDF's actual page index) and is not what retrieval metrics are computed against today — it's superseded by the generation golden sets above, with `build_retrieve_golden_set_chunk_ids.py` (§9.3) used to backfill chunk ids onto it for a one-off match-quality report rather than for live scoring.

### 11.2 RAG Ablation

Implemented in `src/rag_ablation_eval.py`, surfaced by `src/main/web/rag_ablation.py`. Rather than grading retrieval in isolation (there's no ground truth for a full interview transcript), this replays an existing experiment batch's stored transcripts through the same `eval_case_performance`/`eval_dialog_quality` nodes a second time with retrieval content forced empty (the scouting decision of *whether* to consult a source still runs; only the retrieved content is suppressed), then diffs the resulting scores against the original with-RAG scores per dimension (mean delta and mean absolute delta).

Run via `make rag-ablation BATCH=<batch_dir_name> [LIMIT=<n>]`; results are cached to `rag_ablation_results.{json,csv}` inside that batch's directory and read (not recomputed) by the dashboard, since each ablated record costs a real judge call. **Known gap:** the ablation script's baseline-graph branch calls `baseline.evaluate_case_performance`/`baseline.evaluate_dialog_quality`, functions that no longer exist now that baseline uses one combined `baseline_node` — running the ablation against a batch containing baseline-graph records currently raises an `AttributeError`.


## 12. Persistence and Observability

Run persistence is implemented in `src/main/studio/persistence.py` and stored in `src/main/artifacts/runs.sqlite`.

There are two main tables:

1. `runs`: final graph outputs and serialized state
2. `agent_state_traces`: step-level state transitions for traced nodes

Both graphs trace their interviewer-equivalent and judge-equivalent nodes: agentic traces `interviewer` and `judge`; baseline traces `baseline` and `candidate`. Each trace captures:

- node name
- actor
- step index
- scenario reference
- before/after values for key state fields
- a computed summary of changed fields

Separately, `src/run_all_scenarios.py` (the batch experiment runner) writes flat per-run records — including flattened scores and summarized LLM token usage — to timestamped directories under `src/main/artifacts/batch_runs/`, independent of the SQLite store. This is what feeds the Experiment page and RAG ablation, and lets a scenario be repeated N times per graph (default 4) to see run-to-run variance rather than inspecting a single run.


## 13. Dashboard and Human Evaluation

The Flask app in `src/main/web/app.py` provides a lightweight workbench over the SQLite database and the batch-run directories.

Main views:

- `/`: run list (also surfaces per-run trace counts and a link into `/compare`)
- `/compare`: side-by-side run comparison
- `/experiment`: batch picker with aggregate per-graph metrics (error rate, avg turn index/judge rounds, score histograms, token/LLM-call averages) across a repeated-run batch
- `/experiment/<dir_name>/<slug>`: per-scenario drill-down across repeats within a batch, joined against the scenario's own expected scores
- `/rag-evaluation`: retrieval-quality metrics (live) and RAG ablation results (cached per batch), on one page
- `/runs/<run_id>`: final run detail
- `/runs/<run_id>/trace`: step-by-step trace detail

The dashboard also supports human evaluation storage through a `human_evaluations` table, plus a small JSON API (`/api/runs/<run_id>/human-evaluation`, `/api/runs/<run_id>/scores`) and a `?format=json` toggle on most HTML routes. Human evaluators can score rubric dimensions and dialog-quality dimensions, add rationales and evidence, and compare:

- expected scores from the scenario
- model scores from the graph
- human scores entered in the dashboard

The store layer computes comparison rows and error metrics such as exact match rate, off-by-one rate, and mean absolute error.


## 14. Evaluation Outputs

The active program produces three main evaluation outputs:

1. `case_performance`: structured scoring for case-solving dimensions
2. `quality_dialog`: structured scoring for communication and interaction dimensions
3. final written feedback appended to the transcript

The current case-performance fields are:

- `case_opening`
- `case_structure`
- `case_math_answer`
- `case_creative_answer`
- `final_recommendation`
- `overall_structure`
- `overall_problem_solving`
- `overall_communication`

The current dialog-quality fields are:

- `clarity_and_concision`
- `responsiveness_and_adaptation`
- `groundedness`
- `confidence_calibration`
- `multi_turn_coherence`


## 15. What Is Active vs Experimental

Active MVP:

- `src/main/studio/` (including `studio/rag/`)
- `src/main/web/`
- `src/run_all_scenarios.py`, `src/rag_ablation_eval.py`
- `src/scenarios/synthetic-based/`, `src/scenarios/rubric/`
- `src/synthetic-dataset/`
- `src/database/` (source PDFs, `rag_evaluation/` golden sets)

Present but not yet integrated into any code path (planned data layers, not legacy):

- `src/scenarios/casebook-based/`
- `src/database/{agsm,duke,harvard}_cases/`, `casebooks.json`, `case_metadata.json`, `Rubric/rubric.json`
- `src/schemas/`

Experimental but separate:

- `src/main/server_HPC/`: standalone FastAPI + SLURM launcher for self-hosting Mistral-Nemo/Llama-3.3-70B on the university GPU cluster; not imported by either graph today, but is the infrastructure behind the commented-out GPU-hosted client block in `llm_server.py`

Not part of the active architecture:

- `archive/`: legacy prototypes and research artifacts


## 16. Current Architectural Position

The current program is best understood as an evaluation and experimentation platform rather than a finished tutoring product.

Its real architectural strengths today are:

- direct baseline vs agentic comparison on the same scenario assets, now extended with repeated-run batch experiments to see variance rather than single-run snapshots;
- explicit shared state in LangGraph, including append-only reducers so parallel evaluation nodes can log retrieval/token usage safely;
- dual retrieval grounding with two different retrieval-decision strategies (query-less vs. LLM-scouted), plus dedicated retrieval-quality and RAG-ablation evaluation to quantify what retrieval is actually contributing;
- persisted runs and state traces;
- human-in-the-loop evaluation through the dashboard.

Its main current limitations: the "candidate" is still simulated, not a real user; the agentic graph's interviewer/candidate wiring has drifted from OpenRouter back onto the local LM Studio model in a way the surrounding code comments no longer reflect (see §10); and the RAG ablation tool has a known gap on baseline-graph batches (see §11.2). The system is therefore strongest for controlled research and architecture/retrieval comparison, and is not yet a deployed end-user interview coach with a live conversational UI.
