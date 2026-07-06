# Agentic Runtime

This `src/` workspace contains the active implementation of the dissertation prototype: a case interview simulator with two runnable graphs, persisted run artifacts, and a small web workbench for inspection and human evaluation.

The main comparison in this folder is:

- `baseline`: a simpler interview loop with fixed evaluation flow
- `agentic`: a more adaptive graph with interviewer decisions, judge checkpoints, and retrieval-backed feedback

## What Is In Scope

- LangGraph-based interview runtimes in `main/studio/`
- Batch scenario execution in `run_all_scenarios.py`
- Persisted run storage in `main/artifacts/runs.sqlite`
- Batch export snapshots in `main/artifacts/batch_runs/`
- A Flask workbench in `main/web/` for browsing runs and adding human scores

## Folder Layout

```text
src/
├── main/
│   ├── studio/             # active LangGraph runtimes and shared runtime utilities
│   ├── web/                # run dashboard and human-evaluation UI
│   ├── artifacts/          # generated SQLite DB and batch exports
│   └── GPU-server.md       # optional remote GPU / vLLM setup notes
├── scenarios/
│   ├── synthetic-based/    # active synthetic scenarios used by the runtime
│   ├── casebook-based/     # additional scenario assets
│   └── rubric/             # shared rubric JSON
├── synthetic-dataset/      # case content used by the active runtime
├── database/               # broader structured case library
├── schemas/                # JSON schemas for runs and scenarios
├── run_all_scenarios.py    # batch runner
└── Makefile                # convenience commands
```

## Runtime Architecture

Both graphs load the same simulation bundle:

1. A synthetic scenario from `scenarios/synthetic-based/`
2. Its referenced case from `synthetic-dataset/`
3. The shared rubric from `scenarios/rubric/rubric.json`

The runtime then simulates a consulting case interview between model-driven roles:

- `Interviewer`: asks the opening prompt, follow-up questions, and optional reveals
- `Candidate`: answers according to the synthetic candidate profile
- `Judge`: evaluates progress and identifies focus areas
- `Feedback`: produces final coaching feedback

The `agentic` graph adds adaptive interviewer behavior and staged judge intervention. The `baseline` graph is kept as a simpler comparison point.

## Requirements

- Python 3.10+
- A chat-completions-compatible LLM endpoint
- Installed Python dependencies for `main/studio/` and `main/web/`

Install the main runtime dependencies from `src/main/studio/requirements.txt`. The web app uses Flask, so make sure it is available in the same environment if you want to run the dashboard.

## Environment Variables

The runtime loads `.env` automatically if present at the repository root.

Supported variables:

```bash
LMSTUDIO_BASE_URL=http://localhost:8081/v1
LMSTUDIO_MODEL=deepseek-r1-distill-llama-8b
LMSTUDIO_API_KEY=lm-studio
LMSTUDIO_TEMPERATURE=0.14
WORKBENCH_PORT=5020
```

Notes:

- `LMSTUDIO_BASE_URL` can be given with or without `/v1`; the runtime normalizes it.
- Any OpenAI-compatible local or remote server should work if it exposes the expected chat API.
- For remote GPU deployment notes, see `main/GPU-server.md`.

## Quick Start

From `src/`:

```bash
python3 run_all_scenarios.py --graph both --limit 3
```

This runs a small batch through both graphs and writes:

- one persisted run per scenario into `main/artifacts/runs.sqlite`
- one batch snapshot into `main/artifacts/batch_runs/<timestamp>/`

## Run Batch Experiments

Run both graphs:

```bash
python3 run_all_scenarios.py --graph both
```

Run only the baseline:

```bash
python3 run_all_scenarios.py --graph baseline
```

Run only the agentic graph:

```bash
python3 run_all_scenarios.py --graph agentic
```

Run a subset:

```bash
python3 run_all_scenarios.py --graph both --limit 5
```

Run specific scenarios:

```bash
python3 run_all_scenarios.py --graph both \
  --scenario scenario_01_01 \
  --scenario scenario_01_02
```

Write outputs to a custom folder:

```bash
python3 run_all_scenarios.py --graph both --output-dir /tmp/agentic-batch
```

Add a label to the generated batch folder:

```bash
python3 run_all_scenarios.py --graph both --label retrieval_ablation
```

Use a deterministic scenario picker seed:

```bash
python3 run_all_scenarios.py --graph agentic --seed 7
```

## Makefile Shortcuts

From `src/`:

```bash
make run-all
make run-all-baseline
make run-all-agentic
make test
make workbench
make langgraph
```

These targets are thin wrappers around the Python runtime and local development servers.

## Output Files

Each batch may generate the following files, depending on the selected graph:

- `baseline_results.jsonl`
- `baseline_results.csv`
- `agentic_results.jsonl`
- `agentic_results.csv`
- `combined_results.jsonl`
- `combined_results.csv`
- `summary.json`

Each exported record includes:

- graph name
- scenario reference
- transcript
- final feedback
- case performance scores and rationales
- dialog quality scores and rationales
- error status if a run failed

## Workbench

The web app reads persisted runs from `main/artifacts/runs.sqlite` and lets you:

- browse recent runs
- compare two runs side by side
- inspect transcript, expected scores, model scores, and derived metrics
- add human evaluation notes and scores

Start it from `src/`:

```bash
make workbench
```

Then open:

```text
http://localhost:5020
```

If needed, change the port:

```bash
WORKBENCH_PORT=5050 make workbench
```

## LangGraph Dev Server

If you want to inspect or iterate on the graph in LangGraph Studio-compatible mode:

```bash
make langgraph
```

This starts the development server from `main/studio/`.

## Testing

Run the studio and workbench test suites from `src/`:

```bash
make test
```

This executes:

- `main/studio/tests/`
- `main/web/tests/`

## Key Files

- `run_all_scenarios.py`: batch runner for baseline and agentic comparison
- `main/studio/agentic.py`: adaptive graph runtime
- `main/studio/baseline.py`: simpler comparison graph
- `main/studio/loader.py`: resolves scenarios, cases, and rubric assets
- `main/studio/persistence.py`: persists run outputs to SQLite
- `main/web/app.py`: dashboard and human-evaluation app

## Related Documentation

- `../README.md`: repository-level overview
- `../doc/scenario-case-rubric-integration-plan.md`: data-layer integration design
- `../doc/RAG.md`: retrieval design notes
- `../RAG_GUIDE_PDF.md`: case-guide PDF RAG implementation and refactor notes
- `main/GPU-server.md`: optional vLLM/HPC deployment setup
