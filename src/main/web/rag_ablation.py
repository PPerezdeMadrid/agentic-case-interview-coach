"""Reads `rag_ablation_results.json` written by `rag_ablation_eval.py` per batch.

Not recomputed here -- each record costs a real judge call, so rerun
`make rag-ablation BATCH=<dir_name>` to refresh.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WEB_DIR = Path(__file__).resolve().parent
MAIN_DIR = WEB_DIR.parent
BATCH_RUNS_DIR = MAIN_DIR / "artifacts" / "batch_runs"

SECTION_LABELS = {
    "case_performance": "Case Performance (Eval Case Performance)",
    "quality_dialog": "Dialog Quality (Eval Dialog Quality)",
}

_CACHE: dict[str, dict[str, Any]] = {}


def _results_path(dir_name: str) -> Path:
    return BATCH_RUNS_DIR / dir_name / "rag_ablation_results.json"


def list_ablation_batches() -> list[str]:
    """Batch dir names (newest first) that already have ablation results computed."""
    if not BATCH_RUNS_DIR.exists():
        return []
    return sorted(
        (entry.name for entry in BATCH_RUNS_DIR.iterdir() if _results_path(entry.name).exists()),
        reverse=True,
    )


def _flatten_detail_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        for section_key, section_label in SECTION_LABELS.items():
            for row in record.get(section_key, []):
                rows.append(
                    {
                        "thread_id": record.get("thread_id", ""),
                        "graph_name": record.get("graph_name", ""),
                        "scenario_ref": record.get("scenario_ref", ""),
                        "repeat_index": record.get("repeat_index"),
                        "section_label": section_label,
                        **row,
                    }
                )
    rows.sort(key=lambda row: abs(row["delta"]) if row.get("delta") is not None else -1, reverse=True)
    return rows


def load_ablation(dir_name: str, *, refresh: bool = False) -> dict[str, Any]:
    if not refresh and dir_name in _CACHE:
        return _CACHE[dir_name]

    path = _results_path(dir_name)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `make rag-ablation BATCH={dir_name}` "
            f"(or `python rag_ablation_eval.py --batch {dir_name}` from src/) first."
        )

    payload = json.loads(path.read_text())
    records = payload.get("records", [])
    aggregate_by_dimension = [
        {**row, "section_label": SECTION_LABELS.get(row["section"], row["section"])}
        for row in payload.get("aggregate_by_dimension", [])
    ]
    result = {
        **payload,
        "dir_name": dir_name,
        "aggregate_by_dimension": aggregate_by_dimension,
        "detail_rows": _flatten_detail_rows(records),
    }
    _CACHE[dir_name] = result
    return result
