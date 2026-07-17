from __future__ import annotations

import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from dashboard_store import to_numeric_score

WEB_DIR = Path(__file__).resolve().parent
MAIN_DIR = WEB_DIR.parent
BATCH_RUNS_DIR = MAIN_DIR / "artifacts" / "batch_runs"

SECTION_LABELS = {
    "case_performance": "Case Performance (Eval Case Performance)",
    "quality_dialog": "Dialog Quality (Eval Dialog Quality)",
}

# Maps SECTION_LABELS keys (as produced by the judge / stored in combined_results.jsonl)
# to the section keys used inside a scenario JSON's candidate_profile.expected_scores.
EXPECTED_SCORE_SECTION_MAP = {
    "case_performance": "rubric",
    "quality_dialog": "case_interaction_quality",
}

TRANSCRIPT_PREFIXES = {
    "Interviewer reveal: ": ("reveal", "Interviewer reveal"),
    "Interviewer: ": ("interviewer", "Interviewer"),
    "Candidate: ": ("candidate", "Candidate"),
    "Judge: ": ("judge", "Judge"),
    "Eval Case Performance: ": ("judge", "Judge · Case Performance Eval"),
    "Eval Dialog Quality: ": ("judge", "Judge · Dialog Quality Eval"),
    "Give Feedback: ": ("judge", "Judge · Final Feedback"),
}

REPETITION_KEYWORDS = ("repeat", "repetit", "same question", "same phrase", "loop")


def _mean(values: list[float]) -> float | None:
    values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _rate(count: int, total: int) -> float | None:
    if total == 0:
        return None
    return round((count / total) * 100, 1)


def list_batches() -> list[dict[str, Any]]:
    if not BATCH_RUNS_DIR.exists():
        return []

    batches = []
    for entry in sorted(BATCH_RUNS_DIR.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        summary_path = entry / "summary.json"
        jsonl_path = entry / "combined_results.jsonl"
        if not summary_path.exists() or not jsonl_path.exists():
            continue
        try:
            summary = json.loads(summary_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        batches.append(
            {
                "dir_name": entry.name,
                "batch_id": summary.get("batch_id", entry.name),
                "created_at": summary.get("created_at", ""),
                "scenario_count": summary.get("scenario_count"),
                "repeat_count": summary.get("repeat_count"),
                "graphs": summary.get("graphs", {}),
            }
        )
    return batches


def load_batch(dir_name: str) -> dict[str, Any]:
    batch_dir = BATCH_RUNS_DIR / dir_name
    summary_path = batch_dir / "summary.json"
    jsonl_path = batch_dir / "combined_results.jsonl"
    if not summary_path.exists() or not jsonl_path.exists():
        raise FileNotFoundError(f"Batch '{dir_name}' not found.")

    summary = json.loads(summary_path.read_text())
    records: list[dict[str, Any]] = []
    with jsonl_path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    return {"dir_name": dir_name, "summary": summary, "records": records}


def parse_transcript(transcript: list[str]) -> list[dict[str, Any]]:
    seen_candidate_lines: set[str] = set()
    messages: list[dict[str, Any]] = []

    for line in transcript:
        role, label, content = "system", "System", line
        for prefix, (prefix_role, prefix_label) in TRANSCRIPT_PREFIXES.items():
            if line.startswith(prefix):
                role, label, content = prefix_role, prefix_label, line[len(prefix) :]
                break

        is_repeat = False
        if role == "candidate":
            is_repeat = content in seen_candidate_lines
            seen_candidate_lines.add(content)

        messages.append({"role": role, "label": label, "content": content, "is_repeat": is_repeat})

    return messages


def count_candidate_repeats(transcript: list[str]) -> int:
    lines = [line[len("Candidate: ") :] for line in transcript if line.startswith("Candidate: ")]
    if not lines:
        return 0
    return len(lines) - len(set(lines))


def _mentions_repetition(text: str) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in REPETITION_KEYWORDS)


def _candidate_only_text(transcript: list[str]) -> str:
    return "\n".join(line for line in transcript if line.startswith("Candidate: "))


def iter_dimension_scores(record: dict[str, Any]):
    for section_key, label in SECTION_LABELS.items():
        section = record.get(section_key) or {}
        if not isinstance(section, dict):
            continue
        for dimension, entry in section.items():
            score = entry.get("score") if isinstance(entry, dict) else entry
            rationale = entry.get("rationale", "") if isinstance(entry, dict) else ""
            yield section_key, label, dimension, score, rationale


def compute_graph_metrics(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_graph: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_graph[record.get("graph_name", "unknown")].append(record)

    by_scenario_graph: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = (record.get("graph_name", "unknown"), record.get("scenario_ref", ""))
        by_scenario_graph[key].append(record)

    identical_repeat_scenarios: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for (graph_name, _scenario_ref), rows in by_scenario_graph.items():
        if len(rows) < 2:
            continue
        candidate_texts = {_candidate_only_text(row.get("transcript") or []) for row in rows}
        identical_repeat_scenarios[graph_name][1] += 1
        if len(candidate_texts) == 1:
            identical_repeat_scenarios[graph_name][0] += 1

    metrics = []
    for graph_name, rows in sorted(by_graph.items()):
        n_runs = len(rows)
        errors = sum(1 for row in rows if row.get("status") != "ok")
        turn_indices = [row.get("turn_index") for row in rows]
        judge_rounds = [row.get("judge_round") for row in rows]
        message_counts = [len(row.get("transcript") or []) for row in rows]
        repeat_counts = [count_candidate_repeats(row.get("transcript") or []) for row in rows]
        degenerate_runs = sum(1 for count in repeat_counts if count > 0)
        feedback_mentions = sum(1 for row in rows if _mentions_repetition(row.get("final_feedback", "")))
        identical_hits, identical_total = identical_repeat_scenarios.get(graph_name, [0, 0])

        prompt_tokens = [row.get("total_prompt_tokens") for row in rows]
        completion_tokens = [row.get("total_completion_tokens") for row in rows]
        total_tokens = [row.get("total_tokens") for row in rows]
        llm_call_counts = [row.get("llm_call_count") for row in rows]

        metrics.append(
            {
                "graph_name": graph_name,
                "n_runs": n_runs,
                "errors": errors,
                "error_rate": _rate(errors, n_runs),
                "avg_turn_index": _mean(turn_indices),
                "avg_judge_round": _mean(judge_rounds),
                "avg_message_count": _mean(message_counts),
                "avg_candidate_repeats": _mean(repeat_counts),
                "degenerate_run_rate": _rate(degenerate_runs, n_runs),
                "identical_candidate_scenario_rate": _rate(identical_hits, identical_total),
                "feedback_mentions_repetition_rate": _rate(feedback_mentions, n_runs),
                "avg_llm_calls": _mean(llm_call_counts),
                "avg_prompt_tokens": _mean(prompt_tokens),
                "avg_completion_tokens": _mean(completion_tokens),
                "avg_total_tokens": _mean(total_tokens),
                "sum_total_tokens": sum(v for v in total_tokens if v is not None),
            }
        )

    return metrics


# Rubric dimensions are scored 1-4, so the widest possible miss is 3 points.
MAX_SCORE_SPAN = 3.0
BIAS_EPSILON = 0.15
RADAR_PALETTE = ["#2d5a27", "#a8622a", "#3a5a78", "#7a3d78", "#8a7a1f"]


def _severity(mae: float | None) -> str:
    if mae is None:
        return "empty"
    if mae <= 0.4:
        return "good"
    if mae <= 1.0:
        return "fair"
    return "poor"


def _rmse(errors: list[float]) -> float | None:
    """Root-mean-square error, same 1-4 point scale as MAE but more sensitive to a few large misses."""
    if not errors:
        return None
    return round(math.sqrt(sum(err * err for err in errors) / len(errors)), 2)


def _bias_label(signed_bias: float | None) -> str:
    if signed_bias is None:
        return ""
    if signed_bias > BIAS_EPSILON:
        return "over"
    if signed_bias < -BIAS_EPSILON:
        return "under"
    return "match"


def compute_accuracy_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compare each graph's judge scores against the scenario's own author-defined
    expected score (candidate_profile.expected_scores), pooled across every
    repeat in the batch. This is what answers "which graph scores accurately"
    and "who wins".
    """
    graph_names = sorted({record.get("graph_name", "unknown") for record in records})

    all_keys: set[tuple[str, str, str]] = set()
    pairs: dict[tuple[str, str, str], dict[str, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))

    for record in records:
        graph_name = record.get("graph_name", "unknown")
        reference = load_reference_scores(record.get("scenario_ref", ""))
        for section_key, label, dimension, score, _rationale in iter_dimension_scores(record):
            key = (section_key, label, dimension)
            all_keys.add(key)
            actual = to_numeric_score(score)
            expected_entry = reference.get(section_key, {}).get(dimension, {})
            expected = to_numeric_score(expected_entry.get("score")) if isinstance(expected_entry, dict) else None
            if actual is None or expected is None:
                continue
            pairs[key][graph_name].append((actual, expected))

    rows = []
    graph_pooled_errors: dict[str, list[float]] = defaultdict(list)
    graph_dim_wins: dict[str, int] = defaultdict(int)

    for section_key, label, dimension in sorted(all_keys):
        key = (section_key, label, dimension)
        by_graph = pairs.get(key, {})
        row_graphs: dict[str, Any] = {}

        for graph_name in graph_names:
            observations = by_graph.get(graph_name, [])
            if not observations:
                row_graphs[graph_name] = {
                    "n_compared": 0,
                    "mae": None,
                    "rmse": None,
                    "signed_bias": None,
                    "exact_match_rate": None,
                    "accuracy_pct": None,
                    "severity": "empty",
                    "bias": "",
                    "is_winner": False,
                }
                continue

            abs_errors = [abs(a - e) for a, e in observations]
            signed_errors = [a - e for a, e in observations]
            mae = _mean(abs_errors)
            exact = sum(1 for err in abs_errors if err == 0)
            accuracy_pct = round(max(0.0, min(100.0, 100 * (1 - mae / MAX_SCORE_SPAN))), 1) if mae is not None else None

            row_graphs[graph_name] = {
                "n_compared": len(observations),
                "mae": mae,
                "rmse": _rmse(abs_errors),
                "signed_bias": _mean(signed_errors),
                "exact_match_rate": _rate(exact, len(observations)),
                "accuracy_pct": accuracy_pct,
                "severity": _severity(mae),
                "bias": _bias_label(_mean(signed_errors)),
                "is_winner": False,
            }
            graph_pooled_errors[graph_name].extend(abs_errors)

        candidates = [(g, row_graphs[g]["mae"]) for g in graph_names if row_graphs[g]["mae"] is not None]
        if candidates:
            best_mae = min(mae for _, mae in candidates)
            winners = [g for g, mae in candidates if mae == best_mae]
            if len(winners) == 1:
                row_graphs[winners[0]]["is_winner"] = True
                graph_dim_wins[winners[0]] += 1

        rows.append({"section": section_key, "section_label": label, "dimension": dimension, "graphs": row_graphs})

    summary = []
    for graph_name in graph_names:
        errors = graph_pooled_errors.get(graph_name, [])
        overall_mae = _mean(errors)
        summary.append(
            {
                "graph_name": graph_name,
                "dims_won": graph_dim_wins.get(graph_name, 0),
                "overall_mae": overall_mae,
                "overall_rmse": _rmse(errors),
                "n_compared": len(errors),
                "accuracy_pct": round(max(0.0, min(100.0, 100 * (1 - overall_mae / MAX_SCORE_SPAN))), 1)
                if overall_mae is not None
                else None,
            }
        )

    overall_winner = None
    ranked = sorted(
        (s for s in summary if s["overall_mae"] is not None),
        key=lambda s: (-s["dims_won"], s["overall_mae"]),
    )
    if ranked:
        overall_winner = ranked[0]["graph_name"]

    return {
        "rows": rows,
        "summary": summary,
        "graph_names": graph_names,
        "total_dims": len(rows),
        "overall_winner": overall_winner,
    }


def build_radar_chart(accuracy_rows: list[dict[str, Any]], graph_names: list[str]) -> dict[str, Any] | None:
    """Precompute SVG polygon geometry for an accuracy radar chart (one axis per rubric dimension)."""
    rows = [row for row in accuracy_rows if any(row["graphs"].get(g, {}).get("n_compared") for g in graph_names)]
    if not rows or not graph_names:
        return None

    n = len(rows)
    cx, cy, radius = 200.0, 200.0, 150.0
    start_angle = -math.pi / 2

    def point_at(angle: float, frac: float) -> dict[str, float]:
        return {
            "x": round(cx + radius * frac * math.cos(angle), 1),
            "y": round(cy + radius * frac * math.sin(angle), 1),
        }

    axes = []
    for i, row in enumerate(rows):
        angle = start_angle + i * (2 * math.pi / n)
        label_pos = point_at(angle, 1.16)
        anchor = "middle"
        if label_pos["x"] > cx + 10:
            anchor = "start"
        elif label_pos["x"] < cx - 10:
            anchor = "end"
        axes.append(
            {
                "label": row["dimension"],
                "angle": angle,
                "spoke": point_at(angle, 1.0),
                "label_pos": label_pos,
                "anchor": anchor,
            }
        )

    rings = []
    for frac in (0.25, 0.5, 0.75, 1.0):
        points = " ".join(f"{point_at(axis['angle'], frac)['x']},{point_at(axis['angle'], frac)['y']}" for axis in axes)
        rings.append({"frac": frac, "points": points})

    series = []
    for idx, graph_name in enumerate(graph_names):
        points = []
        for i, row in enumerate(rows):
            cell = row["graphs"].get(graph_name, {})
            frac = (cell.get("accuracy_pct") or 0) / 100
            point = point_at(axes[i]["angle"], frac)
            points.append(f"{point['x']},{point['y']}")
        series.append(
            {
                "graph_name": graph_name,
                "color": RADAR_PALETTE[idx % len(RADAR_PALETTE)],
                "points": " ".join(points),
            }
        )

    return {"cx": cx, "cy": cy, "radius": radius, "axes": axes, "rings": rings, "series": series}


def list_scenarios(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for record in records:
        scenario_ref = record.get("scenario_ref") or ""
        slug = Path(scenario_ref).stem if scenario_ref else record.get("thread_id", "unknown")
        if slug not in seen:
            seen[slug] = {"slug": slug, "scenario_ref": scenario_ref, "graph_names": set(), "n_runs": 0}
        seen[slug]["graph_names"].add(record.get("graph_name", "unknown"))
        seen[slug]["n_runs"] += 1

    scenarios = []
    for slug, info in sorted(seen.items()):
        scenarios.append(
            {
                "slug": slug,
                "scenario_ref": info["scenario_ref"],
                "graph_names": sorted(info["graph_names"]),
                "n_runs": info["n_runs"],
            }
        )
    return scenarios


def _extract_case_prompt(transcript: list[str]) -> str:
    for line in transcript:
        if line.startswith("Interviewer: "):
            return line[len("Interviewer: ") :]
    return ""


@lru_cache(maxsize=None)
def _load_scenario_json(scenario_ref: str) -> dict[str, Any]:
    if not scenario_ref:
        return {}
    path = Path(scenario_ref)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def load_reference_scores(scenario_ref: str) -> dict[str, dict[str, Any]]:
    """Load the scenario's own (author-defined) expected scores, keyed like SECTION_LABELS."""
    scenario = _load_scenario_json(scenario_ref)
    candidate_profile = scenario.get("candidate_profile", {}) if isinstance(scenario, dict) else {}
    expected_scores = candidate_profile.get("expected_scores", {}) if isinstance(candidate_profile, dict) else {}

    sections: dict[str, dict[str, Any]] = {}
    for section_key, expected_section_key in EXPECTED_SCORE_SECTION_MAP.items():
        raw_section = expected_scores.get(expected_section_key, {}) if isinstance(expected_scores, dict) else {}
        section: dict[str, Any] = {}
        if isinstance(raw_section, dict):
            for dimension, details in raw_section.items():
                if isinstance(details, dict):
                    section[dimension] = {
                        "score": details.get("expected", ""),
                        "rationale": str(details.get("rationale", "")).strip(),
                    }
        sections[section_key] = section
    return sections


def load_scenario_detail(records: list[dict[str, Any]], slug: str) -> dict[str, Any]:
    matched = [record for record in records if Path(record.get("scenario_ref") or "").stem == slug]
    if not matched:
        raise FileNotFoundError(f"Scenario '{slug}' not found in this batch.")

    by_graph: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in matched:
        by_graph[record.get("graph_name", "unknown")].append(record)

    reference_scores = load_reference_scores(matched[0].get("scenario_ref", ""))

    case_prompt = ""
    graph_sections = []
    for graph_name in sorted(by_graph):
        rows = sorted(by_graph[graph_name], key=lambda row: row.get("repeat_index") or 0)
        repeats = []
        candidate_texts = []
        feedback_texts = []

        for row in rows:
            transcript = row.get("transcript") or []
            if not case_prompt:
                case_prompt = _extract_case_prompt(transcript)
            messages = parse_transcript(transcript)
            candidate_texts.append(_candidate_only_text(transcript))
            final_feedback = row.get("final_feedback", "")
            feedback_texts.append(final_feedback)

            repeats.append(
                {
                    "repeat_index": row.get("repeat_index"),
                    "thread_id": row.get("thread_id"),
                    "messages": messages,
                    "final_feedback": final_feedback,
                    "message_count": len(transcript),
                    "candidate_repeat_count": count_candidate_repeats(transcript),
                    "turn_index": row.get("turn_index"),
                    "judge_round": row.get("judge_round"),
                    "enough_evidence": row.get("enough_evidence"),
                    "focus_areas": row.get("focus_areas") or [],
                    "llm_call_count": row.get("llm_call_count"),
                    "total_prompt_tokens": row.get("total_prompt_tokens"),
                    "total_completion_tokens": row.get("total_completion_tokens"),
                    "total_tokens": row.get("total_tokens"),
                    "dimension_scores": [
                        {"section_label": label, "dimension": dimension, "score": score, "rationale": rationale}
                        for _section_key, label, dimension, score, rationale in iter_dimension_scores(row)
                    ],
                }
            )

        graph_sections.append(
            {
                "graph_name": graph_name,
                "repeats": repeats,
                "identical_candidate_across_repeats": len(set(candidate_texts)) == 1 if candidate_texts else False,
                "identical_feedback_across_repeats": len(set(feedback_texts)) == 1 if feedback_texts else False,
                "reference_scores": [
                    {
                        "section_label": label,
                        "dimension": dimension,
                        "score": reference_scores.get(section_key, {}).get(dimension, {}).get("score", ""),
                        "rationale": reference_scores.get(section_key, {}).get(dimension, {}).get("rationale", ""),
                    }
                    for section_key, label, dimension, _score, _rationale in iter_dimension_scores(rows[0])
                ],
            }
        )

    return {
        "slug": slug,
        "scenario_ref": matched[0].get("scenario_ref", ""),
        "case_prompt": case_prompt,
        "graphs": graph_sections,
    }


def build_overview(dir_name: str) -> dict[str, Any]:
    batch = load_batch(dir_name)
    records = batch["records"]
    accuracy = compute_accuracy_stats(records)
    return {
        "dir_name": dir_name,
        "summary": batch["summary"],
        "graph_metrics": compute_graph_metrics(records),
        "scenarios": list_scenarios(records),
        "accuracy": accuracy,
        "radar": build_radar_chart(accuracy["rows"], accuracy["graph_names"]),
    }
