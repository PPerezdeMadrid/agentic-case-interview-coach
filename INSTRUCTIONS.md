# Instructions: How To Use This System

This document walks through every command available in this repository: setup, running interview batches, starting the workbench, and running the node-level evaluation suites. For a description of what the project *is*, see [README.md](README.md); this file is about how to *operate* it.

All commands below are run from the `src/` directory unless stated otherwise:

```bash
cd src
```


## 1. Setup

### 1.1 Local (venv) setup — default

```bash
make setup
```

(`make setup` is an alias for `make setup-local`.) This:

- creates `.venv/` if it doesn't already exist
- installs `requirements.txt`
- installs the LangGraph CLI (`langgraph-cli[inmem]`)
- writes `RUNNER := local` to `src/.make.runner.mk`, so later `make` targets use this venv by default

### 1.2 HPC (conda) setup

```bash
make setup-hpc
```

This:

- creates a conda environment named `coach` (Python 3.11) if it doesn't exist
- installs `requirements.txt` and the LangGraph CLI into it
- writes `RUNNER := hpc` to `src/.make.runner.mk`, so later `make` targets (`make test`, `make run-all`, `make workbench`, ...) run inside the conda env automatically

You can switch back to local by re-running `make setup-local`. The active runner is whatever was set last — check `src/.make.runner.mk` if you're unsure which one is active.

### 1.3 Environment variables

The runtime loads a repository-level `.env` file automatically.

The `baseline` and `agentic` graphs both call OpenRouter for their LLM roles — this is the config that matters for actually running interviews:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL_INTERVIEWER=qwen/qwen3-14b
OPENROUTER_MODEL_CANDIDATE=mistralai/mistral-small-24b-instruct-2501
OPENROUTER_MODEL_JUDGE=meta-llama/llama-3.3-70b-instruct
OPENROUTER_MODEL_FEEDBACK=openai/gpt-4o-mini
CANDIDATE_TEMPERATURE=0.5
INTERVIEWER_TEMPERATURE=0.6
JUDGE_TEMPERATURE=0.0
FEEDBACK_TEMPERATURE=0.0
WORKBENCH_PORT=5020
```

`LMSTUDIO_*` variables are also read by [llm_server.py](main/studio/llm_server.py), but no active graph role is wired to them by default — they only back the connectivity test (`tests.test_api_connection`) and are available as a manual local fallback:

```bash
LMSTUDIO_BASE_URL=http://localhost:8081/v1
LMSTUDIO_MODEL=deepseek-r1-distill-llama-8b
LMSTUDIO_API_KEY=lm-studio
LMSTUDIO_TEMPERATURE=0.14
```

`LMSTUDIO_BASE_URL` can be given with or without the trailing `/v1`; the runtime normalizes it. Any OpenAI-compatible endpoint (local LM Studio, remote vLLM, OpenRouter, ...) works as long as it exposes a chat-completions API. See [.env](.env) for the values currently configured in this checkout.


## 2. Running Interview Batches

The batch runner is [run_all_scenarios.py](src/run_all_scenarios.py). It simulates interviews across scenarios using the `baseline` and/or `agentic` graph, then writes both a persisted SQLite record and a batch export folder.

### 2.1 Direct Python invocation

```bash
python3 run_all_scenarios.py [OPTIONS]
```

| Flag | Type | Default | Meaning |
|---|---|---|---|
| `--graph` | `baseline`\|`agentic`\|`both` | `both` | Which runtime graph(s) to execute |
| `--limit` | int | `0` (all) | Max number of scenarios to run per graph |
| `--scenario` | str (repeatable) | none | Run only this scenario (repeat the flag for more than one). Overrides `--case` if both given |
| `--case` | str | none | Run every scenario belonging to this case id (e.g. `01-energy-company`), ignored if `--scenario` is set |
| `--repeat` | int | `4` | How many times to repeat each selected scenario |
| `--seed` | int | `0` | Deterministic seed passed to the initial state builders |
| `--output-dir` | path | `main/artifacts/batch_runs/<timestamp>/` | Custom output directory |
| `--label` | str | none | Suffix appended to the generated batch folder name |

Examples:

```bash
# Quick smoke test: both graphs, 3 scenarios only
python3 run_all_scenarios.py --graph both --limit 3

# Only the baseline graph, all scenarios
python3 run_all_scenarios.py --graph baseline

# Only the agentic graph
python3 run_all_scenarios.py --graph agentic

# A specific subset of scenarios
python3 run_all_scenarios.py --graph both \
  --scenario scenario_01_01 \
  --scenario scenario_01_02

# Every scenario belonging to one case, repeated 10 times each
python3 run_all_scenarios.py --graph agentic --case 01-energy-company --repeat 10

# Custom output location and a label for the run
python3 run_all_scenarios.py --graph both --output-dir /tmp/agentic-batch --label retrieval_ablation

# Deterministic scenario selection
python3 run_all_scenarios.py --graph agentic --seed 7
```

Available case ids (see `src/synthetic-dataset/`): `01-energy-company`, `02-football-team`, `03-agriculture-company`, `04-worldcup-test`.

### 2.2 Makefile shortcuts

```bash
make run-all                                   # both graphs, all scenarios [N=<repeat>] [LABEL=...]
make run-all-baseline                          # baseline only            [N=<repeat>] [LABEL=...]
make run-all-agentic                           # agentic only             [N=<repeat>] [LABEL=...]
make experiment CASE=<case_id> N=<repeat> [GRAPH=agentic|baseline|both] [LABEL=...]
```

`make experiment` is a thin wrapper around `run_all_scenarios.py --case ... --repeat ...`. `CASE` is required (the command exits with a usage message if omitted); `N` defaults to `4`, `GRAPH` defaults to `agentic`.

```bash
make experiment CASE=01-energy-company N=10 GRAPH=baseline LABEL=retrieval_ablation
```

### 2.3 Output

Each batch writes:

- one persisted run per scenario into `main/artifacts/runs.sqlite`
- a batch snapshot folder under `main/artifacts/batch_runs/<timestamp>[_label]/`, containing (depending on `--graph`):
  - `baseline_results.jsonl` / `baseline_results.csv`
  - `agentic_results.jsonl` / `agentic_results.csv`
  - `combined_results.jsonl` / `combined_results.csv`
  - `summary.json`

Each record includes: graph name, scenario reference, full transcript, final feedback, case-performance scores + rationales, dialog-quality scores + rationales, and error status if the run failed.


## 3. The Workbench (Web UI)

The workbench is a local Flask app for browsing persisted runs and adding human evaluation.

```bash
make workbench      # or: make app (alias)
```

Equivalent direct call:

```bash
cd main/web && WORKBENCH_PORT=5020 python3 app.py
```

Default URL:

```text
http://localhost:5020
```

To use a different port:

```bash
WORKBENCH_PORT=5050 make workbench
```

What it lets you do:

- browse recent runs
- compare two runs side by side
- inspect transcript, expected scores, model scores, and derived metrics
- add human evaluation notes and scores
- (per the Makefile help) view node-eval results under **Agents > Judge** and **Agents > Interviewer**, including the agentic-vs-baseline comparison


## 4. LangGraph Dev Server

To inspect or iterate on the graph definitions in LangGraph Studio-compatible mode:

```bash
make langgraph
```

Equivalent direct call:

```bash
cd main/studio && langgraph dev --no-browser
```


## 5. Tests

```bash
make test
```

Runs, from `src/`:

- `main/studio/tests/` (`python3 -m unittest discover -s tests`)
- `main/web/tests/` (`python3 -m unittest discover -s tests`)


## 6. Node-Level Evaluation Suites

These target individual graph nodes (judge, interviewer, baseline) against hand-labeled "golden set" CSVs, rather than running a full interview batch. Results are written as JSON next to the CSVs and are also readable from the workbench's **Agents** pages.

### 6.1 Judge eval

Runs a judge golden-set CSV against the real judge LLM and scores `enough_evidence` accuracy.

```bash
make judge-eval [GOLDEN_SET=worldcup] [LIMIT=<n>]
```

Equivalent direct call:

```bash
python3 main/studio/node_eval/judge_eval/run_judge_golden_set.py \
  --csv database/node_eval/judge_eval/judge_golden_set_worldcup.csv \
  [--limit N]
```

### 6.2 Interviewer eval

Runs an interviewer golden-set CSV against the real interviewer LLM and grades move accuracy.

```bash
make interviewer-eval [INTERVIEWER_GOLDEN_SET=evidence_handling] [LIMIT=<n>]
```

Available golden sets (`database/node_eval/interviewer_eval/`): `evidence_handling` (default), `socratic_function`, `guardrail`, `turn_control`.

Equivalent direct call:

```bash
python3 main/studio/node_eval/interviewer_eval/run_interviewer_golden_set.py \
  --csv database/node_eval/interviewer_eval/interviewer_golden_set_evidence_handling.csv \
  [--limit N]
```

### 6.3 Baseline eval

Runs the same fixtures as `interviewer-eval` (plus a `worldcup` set) against the baseline graph's fused interviewer/judge/grader node, so it can be compared head-to-head with the agentic interviewer and judge.

```bash
make baseline-eval [BASELINE_GOLDEN_SET=evidence_handling] [LIMIT=<n>]
```

Available golden sets (`database/node_eval/baseline_eval/`): `evidence_handling` (default), `socratic_function`, `guardrail`, `turn_control`, plus `worldcup` (baseline's `ready_for_evaluation` call graded on the judge golden set, built via `node_eval/baseline_eval/build_baseline_worldcup_golden_set.py`).

Equivalent direct call:

```bash
python3 main/studio/node_eval/baseline_eval/run_baseline_golden_set.py \
  --csv database/node_eval/baseline_eval/baseline_golden_set_evidence_handling.csv \
  [--limit N]
```

### 6.4 RAG ablation eval

Replays a batch's already-stored transcripts through the judge eval nodes with retrieval (RAG) disabled, then compares `eval_case` / `eval_dialog` scores against that same batch's original (with-RAG) scores — isolating what the retrieval layer contributes.

```bash
make rag-ablation BATCH=<batch_dir_name> [LIMIT=<n>]
```

`BATCH` is required and must name a folder that already exists under `main/artifacts/batch_runs/` (i.e. run a batch first with `run_all_scenarios.py` / `make run-all`, then ablate it).

Equivalent direct call:

```bash
python3 rag_ablation_eval.py --batch <batch_dir_name> [--limit N]
```


## 7. Command Reference (cheat sheet)

```bash
# --- setup ---
make setup                 # venv setup (default runner)
make setup-hpc              # conda setup on HPC (persists as default runner)

# --- run interviews ---
make run-all                                    # both graphs, all scenarios
make run-all-baseline                           # baseline only
make run-all-agentic                            # agentic only
make experiment CASE=<case_id> N=<repeat>       # one case, N repeats
python3 run_all_scenarios.py --graph both --limit 3

# --- inspect ---
make workbench                                  # http://localhost:5020
make langgraph                                  # LangGraph Studio dev server

# --- test & evaluate ---
make test                                       # unit tests (studio + web)
make judge-eval [GOLDEN_SET=worldcup]
make interviewer-eval [INTERVIEWER_GOLDEN_SET=evidence_handling]
make baseline-eval [BASELINE_GOLDEN_SET=evidence_handling]
make rag-ablation BATCH=<batch_dir_name>

# --- help ---
make help                                       # prints this same target list
```

Run `make help` at any time from `src/` to see the authoritative, up-to-date list of targets — this document mirrors it but the Makefile is the source of truth.


## 8. HPC / Remote GPU Notes

Self-hosting the LLM roles on a Slurm cluster is set up but **not wired into the runtime** — `llm_server.py` calls OpenRouter for all four roles (see [Section 1.3](#13-environment-variables)); the GPU-hosted client definitions are present only as a commented-out block. Using either setup below means starting the Slurm job yourself and manually pointing the relevant `OPENROUTER_MODEL_*`/base-URL wiring at the resulting `http://127.0.0.1:<port>/v1` endpoint.

There are two independent HPC setups in the repo:

- [src/server.bash](src/server.bash) / [src/experiment.bash](src/experiment.bash) — self-contained Slurm jobs that `vllm serve` the models directly, run `run_all_scenarios.py` against them, then tear the servers down. `server.bash` serves Mistral-Nemo as candidate + Llama-3.3-70B as judge (`--graph both --repeat 3`); `experiment.bash` is a Mistral-only variant (`--repeat 1`).
- [src/server_HPC/](src/server_HPC/) — a FastAPI-based alternative ([server.py](src/server_HPC/server.py) + [server.bash](src/server_HPC/server.bash)) that only starts and holds the model servers open (no scenario run baked in); pairs with [src/server_HPC/test_servers.py](src/server_HPC/test_servers.py) to smoke-test the endpoints once up. It currently serves Mistral-Small-24B as candidate (port 18403) + Llama-3.3-70B as judge (port 18402); Mistral-Nemo is still available via `python server.py --model mistral` (port 18401) but is not launched by `server.bash` by default. See [src/server_HPC/GPU-server.md](src/server_HPC/GPU-server.md) for model download paths and monitoring commands.


## Related Documentation

- [README.md](README.md) — project overview, architecture, stack
- [src/README.md](src/README.md) — detailed runtime and development guide
- [doc/summary_arch.md](doc/summary_arch.md) — architecture summary
- [doc/RAG.md](doc/RAG.md) — retrieval design notes
- [doc/evaluation/](doc/evaluation/) — evaluation methodology notes
