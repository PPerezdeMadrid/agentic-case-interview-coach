"""Judge golden-set evaluation dashboard data: reads the
`judge_golden_set_<name>_results.json` files that
`main/studio/node_eval/judge_eval/run_judge_golden_set.py` writes into
`src/database/node_eval/judge_eval/`.

Not recomputed on page load: each row costs one real judge LLM call. This only
reads whatever the last `run_judge_golden_set.py` run wrote for that golden set.
Rerun it (see `make judge-eval`) and reload this page to refresh -- same pattern
as `rag_ablation.py` for RAG ablation results.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parents[3]
JUDGE_EVAL_DIR = SRC_DIR / "database" / "node_eval" / "judge_eval"

_CACHE: dict[str, dict[str, Any]] = {}

# Matches --success/--warning/--danger in static/styles.css -- same tiers as
# the legend-dot--good/--fair/--poor convention used on the accuracy radar in
# experiment.html, reused here so "good/warn/bad" reads the same everywhere.
_TIER_COLOR = {
    "good": "#2d5a27",
    "warn": "#7a6520",
    "bad": "#7a2020",
    "none": "#4a5e47",
}


def _results_path(golden_set: str) -> Path:
    return JUDGE_EVAL_DIR / f"judge_golden_set_{golden_set}_results.json"


def _csv_path(golden_set: str) -> Path:
    return JUDGE_EVAL_DIR / f"judge_golden_set_{golden_set}.csv"


def _load_csv_metadata(golden_set: str) -> dict[str, dict[str, str]]:
    """Map conversation_id -> {category, judge_input}, read from the source
    golden-set CSV rather than duplicated into the (much smaller) results JSON
    cache."""
    path = _csv_path(golden_set)
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["conversation_id"]: {
                "category": row.get("category", ""),
                "judge_input": row.get("judge_input", ""),
            }
            for row in csv.DictReader(handle)
        }


def list_judge_golden_sets() -> list[str]:
    """Golden-set names (e.g. 'worldcup') that already have results computed,
    derived from whichever judge_golden_set_<name>_results.json files exist."""
    if not JUDGE_EVAL_DIR.exists():
        return []
    names = []
    for entry in JUDGE_EVAL_DIR.glob("judge_golden_set_*_results.json"):
        name = entry.stem.removeprefix("judge_golden_set_").removesuffix("_results")
        names.append(name)
    return sorted(names)


def load_judge_eval(golden_set: str, *, refresh: bool = False) -> dict[str, Any]:
    if not refresh and golden_set in _CACHE:
        return _CACHE[golden_set]

    path = _results_path(golden_set)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `make judge-eval GOLDEN_SET={golden_set}` "
            f"(or `python main/studio/node_eval/judge_eval/run_judge_golden_set.py` from src/) first."
        )

    payload = json.loads(path.read_text())
    csv_metadata = _load_csv_metadata(golden_set)
    records = sorted(
        (
            {
                **row,
                **csv_metadata.get(row["conversation_id"], {"category": "", "judge_input": ""}),
            }
            for row in payload.get("records", [])
        ),
        key=lambda row: row["conversation_id"],
    )
    result = {**payload, "records": records}
    _CACHE[golden_set] = result
    return result


def category_breakdown(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate per-conversation records into pass/fail counts by `category`,
    sorted worst-accuracy-first so systematic judge failures (see
    doc/evaluation/Dialog-evaluation.md) surface immediately instead of being
    buried in the per-conversation table."""
    stats: dict[str, dict[str, int]] = {}
    for row in records:
        category = row.get("category") or "(uncategorized)"
        bucket = stats.setdefault(category, {"total": 0, "correct": 0, "errors": 0})
        bucket["total"] += 1
        if row.get("error"):
            bucket["errors"] += 1
        elif row.get("correct"):
            bucket["correct"] += 1

    breakdown = []
    for category, bucket in stats.items():
        scored = bucket["total"] - bucket["errors"]
        wrong = scored - bucket["correct"]
        accuracy = (bucket["correct"] / scored) if scored else None
        if accuracy is None:
            tier = "none"
        elif accuracy >= 0.9:
            tier = "good"
        elif accuracy >= 0.5:
            tier = "warn"
        else:
            tier = "bad"
        breakdown.append(
            {
                "category": category,
                "total": bucket["total"],
                "correct": bucket["correct"],
                "wrong": wrong,
                "errors": bucket["errors"],
                "accuracy": accuracy,
                "tier": tier,
            }
        )

    breakdown.sort(key=lambda b: (b["accuracy"] if b["accuracy"] is not None else -1, b["category"]))
    for index, row in enumerate(breakdown, start=1):
        row["index"] = index
    return breakdown


def build_category_radar(categories: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Precompute SVG geometry for a per-category accuracy radar: one spoke per
    golden-set category, positioned worst-to-best around the circle (same order
    as the breakdown table) so failing categories cluster visually instead of
    scattering randomly. Spokes are numbered rather than labeled with the full
    (long, e.g. `FULL_COVERAGE_LONG_ITERATIVE_MANY_REDIRECTS`) category name --
    match the number to the breakdown table's `#` column or hover the vertex."""
    rows = [c for c in categories if c["accuracy"] is not None]
    if len(rows) < 3:
        return None

    n = len(rows)
    cx, cy, radius = 210.0, 210.0, 150.0
    start_angle = -math.pi / 2

    def point_at(angle: float, frac: float) -> dict[str, float]:
        return {
            "x": round(cx + radius * frac * math.cos(angle), 1),
            "y": round(cy + radius * frac * math.sin(angle), 1),
        }

    axes = []
    for i, row in enumerate(rows):
        angle = start_angle + i * (2 * math.pi / n)
        label_pos = point_at(angle, 1.1)
        anchor = "middle"
        if label_pos["x"] > cx + 10:
            anchor = "start"
        elif label_pos["x"] < cx - 10:
            anchor = "end"
        axes.append(
            {
                "index": row["index"],
                "category": row["category"],
                "accuracy": row["accuracy"],
                "spoke": point_at(angle, 1.0),
                "label_pos": label_pos,
                "anchor": anchor,
                "vertex": point_at(angle, max(row["accuracy"], 0.04)),
                "color": _TIER_COLOR[row["tier"]],
            }
        )

    rings = []
    for frac in (0.25, 0.5, 0.75, 1.0):
        points = " ".join(
            f"{point_at(start_angle + i * (2 * math.pi / n), frac)['x']},{point_at(start_angle + i * (2 * math.pi / n), frac)['y']}"
            for i in range(n)
        )
        rings.append({"frac": frac, "points": points})

    polygon_points = " ".join(f"{a['vertex']['x']},{a['vertex']['y']}" for a in axes)

    return {"cx": cx, "cy": cy, "radius": radius, "axes": axes, "rings": rings, "polygon_points": polygon_points}
