# Batch Scenario Runner

This folder contains the main runtime plus a batch runner for executing all synthetic scenarios with the `baseline` graph, the `agentic` graph, or both.

## Run all scenarios

From `src/`:

```bash
python3 run_all_scenarios.py --graph both
```

This runs every synthetic scenario through both graphs and writes:

- one persisted run per scenario into `main/artifacts/runs.sqlite`
- one batch snapshot into `main/artifacts/batch_runs/<timestamp>/`

## Useful variants

Run only baseline:

```bash
python3 run_all_scenarios.py --graph baseline
```

Run only agentic:

```bash
python3 run_all_scenarios.py --graph agentic
```

Run only a subset:

```bash
python3 run_all_scenarios.py --graph both --limit 5
```

Run specific scenarios:

```bash
python3 run_all_scenarios.py --graph both --scenario scenario_01_01 --scenario scenario_01_02
```

Add a custom label to the output folder:

```bash
python3 run_all_scenarios.py --graph both --label server_run_1
```

## Makefile shortcuts

From `src/`:

```bash
make run-all
make run-all-baseline
make run-all-agentic
```

They are thin wrappers around the Python commands above.

## Output files

Each batch creates:

- `baseline_results.jsonl`
- `baseline_results.csv`
- `agentic_results.jsonl`
- `agentic_results.csv`
- `combined_results.jsonl`
- `combined_results.csv`
- `summary.json`

`final_feedback` is included in the exported records so baseline and agentic outputs can be compared directly.
