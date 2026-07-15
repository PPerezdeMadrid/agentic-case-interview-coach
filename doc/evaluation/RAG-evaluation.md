# RAG Evaluation Framework

## 1. Retrieval Evaluation

**Objective:** Assess the quality and relevance of chunks retrieved from the vector store in response to user queries.

### Metrics

The retrieval component is evaluated using the following key performance indicators:

- **Precision@K**: The percentage of retrieved chunks that are relevant to the query. Measures the accuracy of returned results.
  
- **Recall@K**: The percentage of all relevant chunks in the vector store that were successfully retrieved. Measures completeness of relevant results.
  
- **Hit Rate**: The percentage of queries for which at least one relevant chunk was retrieved (Hit Rate ≥ 1). Indicates the system's ability to find *any* relevant information.
  
- **Mean Reciprocal Rank (MRR)**: The average position of the first relevant chunk across all queries. Lower values indicate that relevant content is ranked higher in the retrieval results.

### Golden Dataset

A golden evaluation dataset must be created with the filename: **`retrieve_golden_set.csv`**

**Required Columns:**
- `query_id`: Unique identifier for each query
- `query`: The user question or search query
- `answer`: The expected/ground truth answer
- `source_chunk_ids`: Comma-separated list of chunk IDs that contain the relevant information (enables precise evaluation of what was retrieved)


## 2. RAG Ablation Evaluation

**Objective:** Measure how much RAG actually changes the judge's grading, rather than scoring generation quality against a golden set in isolation.

Instead of grading a standalone "query -> expected answer" pair (there is no such ground truth for interview transcripts), this evaluation takes one experiment batch (produced by `make experiment` / `make run-all`, see `doc/evaluation/Dialog-evaluation.md`) and replays its stored transcripts through the same judge nodes that already scored them -- `eval_case_performance` and `eval_dialog_quality` -- with every RAG retrieval call disabled. The scouting call that decides *whether* to consult a source still runs; only the content it would retrieve is removed, mirroring "the source is unavailable" rather than "the model never knew a source existed."

### What's compared

For each dimension in `case_performance` (Eval Case Performance) and `quality_dialog` (Eval Dialog Quality):

- **With-RAG score**: the score already stored in the batch from the original run.
- **Without-RAG score**: the score recomputed on the exact same transcript with retrieval disabled.
- **Delta**: without-RAG score minus with-RAG score, aggregated as mean delta (keeps direction) and mean |delta| (ignores direction) per dimension, plus how many comparable records actually landed on a different score.

### Running it

```
make rag-ablation BATCH=<batch_dir_name> [LIMIT=<n>]
```

This writes `rag_ablation_results.json` / `.csv` into that batch's own directory under `src/main/artifacts/batch_runs/<batch_dir_name>/`. The workbench's **RAG Evaluation** page (RAG Ablation section) reads that cached file (it does not recompute live, since each ablated record costs a real judge call) -- rerun the command and reload the page to refresh.


## 3. Aggregation & Visualization

**Objective:** Provide comprehensive visibility into overall system performance and performance breakdown by category and source.

### Dashboard Requirements

A dedicated page must be created in the evaluation workbench displaying:

- **Overall Metrics**: Aggregated performance across all evaluation dimensions
- **Category Breakdown**: Performance metrics segmented by semantic category (e.g., cost_concepts, frameworks, budgeting)
- **Source Breakdown**: Performance metrics grouped by source document (PDF files), allowing identification of strengths and weaknesses by document

This enables rapid identification of performance gaps and areas requiring improvement.


## Evaluation Dataset Specification

All evaluation datasets must include the following standardized structure:

### Required Columns

- `query_id`: Unique identifier for each query (e.g., "QUERY_001")
- `query`: The input question or search prompt
- `answer`: The expected ground truth answer
- `category`: Semantic classification tag for the query (see category lists below)

### Category System

Categories enable fine-grained analysis of system performance across different knowledge domains.

#### Case Guide Categories

These categories are derived from the Consulting Case Guide:

- **frameworks**: Structured problem-solving approaches (Porter's Five Forces, 3Cs, 4Ps, MECE principle)
- **pyramid_principle**: Communication structure leading with conclusion followed by supporting logic and data
- **profitability_tree**: Breaking down profit into revenue and cost drivers; financial decomposition
- **market_sizing**: Estimating market size with limited data; building assumptions and logic
- **break_even**: Break-even calculations and interpretation in business context
- **hypothesis_testing**: Forming, testing, and validating hypotheses throughout the case
- **recommendation**: Developing clear, actionable recommendations grounded in case analysis
- **business_judgment**: Trade-offs, prioritization, and judgment calls in competitive/market context

#### Profitability Categories

These categories are derived from the Principles of Managerial Accounting:

- **cost_concepts**: Understanding different cost classifications (direct, indirect, fixed, variable, mixed costs) and their behavior
- **cost_costing**: Job-order and process costing systems; how costs flow through inventory accounts
- **cvp_analysis**: Cost-Volume-Profit analysis including contribution margin, break-even calculations, and profit targeting
- **budgeting**: Master budget preparation, sales budget, production budget, flexible budgeting, and budget variance analysis
- **variance_analysis**: Standard costs and variance calculations (materials, labor, overhead variances)
- **performance_evaluation**: Responsibility centers, ROI, residual income, and decentralized performance metrics
- **differential_analysis**: Relevant cost analysis for decision-making (make/buy, add/drop segment, special orders)
- **capital_budgeting**: Time value of money, payback period, NPV, IRR, and capital investment decisions


## Implementation Workflow

1. **Create Golden Datasets**: Prepare the retrieval golden-set CSVs (`generation_golden_set_case_guide.csv`, `generation_golden_set_profitability.csv`) with all required columns and categories
2. **Configure Metrics**: Set up evaluation pipelines for each dimension following the specifications above
3. **Run Evaluations**: Retrieval eval recomputes live from the workbench page; for RAG ablation, run `make rag-ablation BATCH=<batch_dir_name>` against an existing experiment batch
4. **Visualize Results**: Display metrics on the workbench's single RAG Evaluation page (retrieval quality segmented by category/source; RAG ablation segmented by dimension)
5. **Iterate & Improve**: Use insights from evaluation results to refine the RAG system