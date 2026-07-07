from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SRC_DIR = Path(__file__).resolve().parent
STUDIO_DIR = SRC_DIR / "main" / "studio"

if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

import agentic  # noqa: E402
import baseline  # noqa: E402
import loader  # noqa: E402
import persistence  # noqa: E402


@dataclass(frozen=True)
class GraphRuntime:
    name: str
    module: Any
    state_builder_name: str


GRAPH_RUNTIMES: dict[str, GraphRuntime] = {
    "baseline": GraphRuntime(
        name="baseline",
        module=baseline,
        state_builder_name="build_initial_baseline_state",
    ),
    "agentic": GraphRuntime(
        name="agentic",
        module=agentic,
        state_builder_name="build_initial_interview_state",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the baseline and/or agentic graphs across every synthetic scenario "
            "and export the final feedback for comparison."
        )
    )
    parser.add_argument(
        "--graph",
        choices=("baseline", "agentic", "both"),
        default="both",
        help="Which graph to execute. Default: both.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of scenarios to run per graph. Default: 0 (all).",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help=(
            "Optional scenario reference or path. Repeat to run a subset. "
            "If omitted, all synthetic scenarios are executed."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional output directory. Default: src/main/artifacts/batch_runs/<timestamp>/",
    )
    parser.add_argument(
        "--label",
        default="",
        help="Optional label added to the output folder name.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Optional seed passed into initial state builders. Default: 0.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=4,
        help="How many times to run each selected scenario. Default: 4.",
    )
    return parser.parse_args()


def list_scenario_paths(selected_refs: list[str]) -> list[Path]:
    if selected_refs:
        return [Path(loader._find_scenario_path(ref)).resolve() for ref in selected_refs]
    return [path.resolve() for path in loader._list_scenario_paths()]


def make_output_dir(raw_output_dir: str, label: str) -> Path:
    if raw_output_dir:
        output_dir = Path(raw_output_dir).resolve()
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = f"_{label.strip()}" if label.strip() else ""
        output_dir = persistence.ARTIFACTS_DIR / "batch_runs" / f"{timestamp}{suffix}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def extract_final_feedback(transcript: list[str]) -> str:
    for line in reversed(transcript):
        if isinstance(line, str) and line.startswith("Give Feedback: "):
            return line.removeprefix("Give Feedback: ").strip()
    return ""


def flatten_scores(payload: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    if not isinstance(payload, dict):
        return flattened

    for field_name, field_payload in payload.items():
        if not isinstance(field_payload, dict):
            continue
        flattened[f"{field_name}_score"] = field_payload.get("score", "")
        flattened[f"{field_name}_rationale"] = field_payload.get("rationale", "")
    return flattened


def build_record(
    graph_name: str,
    thread_id: str,
    scenario_ref: str,
    result: dict[str, Any] | None,
    *,
    repeat_index: int = 1,
    repeat_count: int = 1,
    error: str = "",
) -> dict[str, Any]:
    transcript = result.get("transcript", []) if isinstance(result, dict) else []
    record: dict[str, Any] = {
        "graph_name": graph_name,
        "thread_id": thread_id,
        "scenario_ref": scenario_ref,
        "repeat_index": repeat_index,
        "repeat_count": repeat_count,
        "status": "error" if error else "ok",
        "error": error,
        "turn_index": result.get("turn_index", "") if isinstance(result, dict) else "",
        "judge_round": result.get("judge_round", "") if isinstance(result, dict) else "",
        "enough_evidence": result.get("enough_evidence", "") if isinstance(result, dict) else "",
        "final_feedback": extract_final_feedback(transcript),
        "transcript": transcript,
        "focus_areas": result.get("focus_areas", []) if isinstance(result, dict) else [],
        "case_performance": result.get("case_performance", {}) if isinstance(result, dict) else {},
        "quality_dialog": result.get("quality_dialog", {}) if isinstance(result, dict) else {},
    }
    record.update(flatten_scores(record["case_performance"]))
    record.update(flatten_scores(record["quality_dialog"]))
    return record


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    for record in records:
        for key in record.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            normalized = {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (list, dict))
                else value
                for key, value in record.items()
            }
            writer.writerow(normalized)


def run_graph_for_scenario(
    runtime: GraphRuntime,
    scenario_path: Path,
    seed: int,
    batch_id: str,
    index: int,
    repeat_index: int,
    repeat_count: int,
) -> dict[str, Any]:
    scenario_ref = str(scenario_path)
    scenario_id = scenario_path.stem
    thread_id = f"{runtime.name}_{scenario_id}_{index:03d}_r{repeat_index:02d}_{batch_id}"

    state_builder = getattr(runtime.module, runtime.state_builder_name)
    state = state_builder(scenario_ref=scenario_ref, seed=seed)
    config = runtime.module.build_graph_config(thread_id)
    result = runtime.module.graph.invoke(state, config=config)
    return build_record(
        runtime.name,
        thread_id,
        scenario_ref,
        result,
        repeat_index=repeat_index,
        repeat_count=repeat_count,
    )


def run_batch(
    runtimes: list[GraphRuntime],
    scenario_paths: list[Path],
    output_dir: Path,
    seed: int,
    repeat_count: int,
) -> dict[str, Any]:
    batch_id = output_dir.name
    combined_records: list[dict[str, Any]] = []
    total_runs_per_graph = len(scenario_paths) * repeat_count
    summary: dict[str, Any] = {
        "batch_id": batch_id,
        "output_dir": str(output_dir),
        "runs_db_path": str(persistence.ensure_runs_db()),
        "scenario_count": len(scenario_paths),
        "repeat_count": repeat_count,
        "total_runs_per_graph": total_runs_per_graph,
        "scenarios": [str(path) for path in scenario_paths],
        "graphs": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    for runtime in runtimes:
        graph_records: list[dict[str, Any]] = []
        ok_count = 0
        error_count = 0

        run_index = 0
        for index, scenario_path in enumerate(scenario_paths, start=1):
            for repeat_index in range(1, repeat_count + 1):
                run_index += 1
                print(
                    (
                        f"[{runtime.name}] {run_index}/{total_runs_per_graph} "
                        f"{scenario_path.stem} (repeat {repeat_index}/{repeat_count})"
                    ),
                    flush=True,
                )
                try:
                    record = run_graph_for_scenario(
                        runtime,
                        scenario_path,
                        seed,
                        batch_id,
                        index,
                        repeat_index,
                        repeat_count,
                    )
                    ok_count += 1
                except Exception as exc:
                    error_count += 1
                    record = build_record(
                        runtime.name,
                        thread_id=(
                            f"{runtime.name}_{scenario_path.stem}_{index:03d}"
                            f"_r{repeat_index:02d}_{batch_id}"
                        ),
                        scenario_ref=str(scenario_path),
                        result=None,
                        repeat_index=repeat_index,
                        repeat_count=repeat_count,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                graph_records.append(record)
                combined_records.append(record)

        jsonl_path = output_dir / f"{runtime.name}_results.jsonl"
        csv_path = output_dir / f"{runtime.name}_results.csv"
        write_jsonl(jsonl_path, graph_records)
        write_csv(csv_path, graph_records)

        summary["graphs"][runtime.name] = {
            "records": len(graph_records),
            "ok": ok_count,
            "errors": error_count,
            "jsonl_path": str(jsonl_path),
            "csv_path": str(csv_path),
        }

    combined_jsonl = output_dir / "combined_results.jsonl"
    combined_csv = output_dir / "combined_results.csv"
    write_jsonl(combined_jsonl, combined_records)
    write_csv(combined_csv, combined_records)

    summary["combined_jsonl_path"] = str(combined_jsonl)
    summary["combined_csv_path"] = str(combined_csv)
    summary_path = output_dir / "summary.json"
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def resolve_runtimes(graph_selection: str) -> list[GraphRuntime]:
    if graph_selection == "both":
        return [GRAPH_RUNTIMES["baseline"], GRAPH_RUNTIMES["agentic"]]
    return [GRAPH_RUNTIMES[graph_selection]]


def main() -> int:
    args = parse_args()
    runtimes = resolve_runtimes(args.graph)
    scenario_paths = list_scenario_paths(args.scenario)

    if args.limit > 0:
        scenario_paths = scenario_paths[: args.limit]

    if not scenario_paths:
        raise SystemExit("No scenarios found to run.")

    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1.")

    output_dir = make_output_dir(args.output_dir, args.label)
    summary = run_batch(runtimes, scenario_paths, output_dir, args.seed, args.repeat)

    print("", flush=True)
    print(f"Batch finished: {summary['batch_id']}", flush=True)
    print(f"Output directory: {summary['output_dir']}", flush=True)
    print(f"Runs database: {summary['runs_db_path']}", flush=True)
    for graph_name, graph_summary in summary["graphs"].items():
        print(
            f"{graph_name}: ok={graph_summary['ok']} errors={graph_summary['errors']} "
            f"jsonl={graph_summary['jsonl_path']}",
            flush=True,
        )
    print(f"Combined CSV: {summary['combined_csv_path']}", flush=True)
    print(f"Summary JSON: {summary['summary_path']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
