# Agentic Case Interview Coach

This repository contains the active dissertation MVP for AI-supported consulting case interview practice.

The current system compares two LangGraph runtimes:

- `baseline`: a simpler interview loop with fixed evaluation flow
- `agentic`: a more adaptive graph with interviewer decisions, judge checkpoints, retrieval, and final coaching feedback

Both runtimes simulate a case interview from structured scenario data, persist run artifacts, and can be reviewed in a small local workbench.

## What The MVP Does Today

- Runs synthetic consulting case interviews end to end
- Uses separate model roles for interviewer, candidate, judge, and feedback
- Evaluates runs against a structured rubric
- Adds retrieval-backed methodology context from case-guide and profitability knowledge sources
- Persists run outputs to SQLite for later inspection
- Exposes a local Flask workbench to browse runs and add human evaluation

## Active Project Layout

```text
src/
├── main/
│   ├── studio/        # LangGraph runtimes, prompts, retrieval, persistence, tests
│   ├── web/           # local workbench for run inspection and human scoring
│   ├── artifacts/     # generated SQLite DB and batch exports
│   ├── database/      # structured case data used by the active MVP
│   └── GPU-server.md  # optional remote serving notes
├── scenarios/         # scenario configs and shared rubric assets
├── synthetic-dataset/ # synthetic case content used by the runtime
├── schemas/           # shared JSON schemas
└── run_all_scenarios.py
```

Other top-level folders:

- `archive/`: legacy experiments and research material
- `doc/`: supporting documentation and diagrams

## Runtime Notes

- `src/main/studio/baseline.py` uses the LM Studio compatible server by default.
- `src/main/studio/agentic.py` delegates most nodes to `src/main/studio/node.py`.
- The interviewer JSON decision step in `node.py` uses `openai_llm_server`.
- Environment variables for both providers are loaded from the repository `.env` when present.

## Quick Start

Install the Python dependencies used by `src/main/studio/` and `src/main/web/`, then from `src/` run:

```bash
python3 run_all_scenarios.py --graph both --limit 3
```

This writes persisted runs to `src/main/artifacts/runs.sqlite` and batch exports to `src/main/artifacts/batch_runs/`.

To inspect runs locally:

```bash
cd src
make workbench
```

## Documentation

- `src/README.md`: detailed runtime, batch, workbench, and test instructions
- `src/main/GPU-server.md`: optional remote model serving setup
