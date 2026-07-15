from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


WEB_DIR = Path(__file__).resolve().parent
MAIN_DIR = WEB_DIR.parent
RUNS_DB_PATH = MAIN_DIR / "artifacts" / "runs.sqlite"

CASE_PERFORMANCE_SECTION = "rubric"
DIALOG_QUALITY_SECTION = "case_interaction_quality"
NOT_TESTED = "not_tested"


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(RUNS_DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def ensure_dashboard_db() -> Path:
    RUNS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS human_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                evaluator_name TEXT,
                case_performance_human_json TEXT,
                dialog_quality_human_json TEXT,
                overall_human_score REAL,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_human_evaluations_run_id
            ON human_evaluations(run_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_human_evaluations_updated_at
            ON human_evaluations(updated_at DESC)
            """
        )

    return RUNS_DB_PATH


def _normalize_dimension_entry(raw_entry: Any) -> dict[str, Any]:
    if isinstance(raw_entry, dict):
        score = raw_entry.get("score", "")
        rationale = raw_entry.get("rationale", "")
        evidence = raw_entry.get("evidence", "")
    else:
        score = raw_entry
        rationale = ""
        evidence = ""

    return {
        "score": score if score not in {None, ""} else "",
        "rationale": str(rationale or "").strip(),
        "evidence": str(evidence or "").strip(),
    }


def _extract_expected_scores(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidate_profile = state.get("candidate_profile", {})
    expected_scores = candidate_profile.get("expected_scores", {})

    sections: dict[str, dict[str, Any]] = {
        CASE_PERFORMANCE_SECTION: {},
        DIALOG_QUALITY_SECTION: {},
    }
    for section_name in sections:
        raw_section = expected_scores.get(section_name, {})
        if not isinstance(raw_section, dict):
            continue
        for dimension, details in raw_section.items():
            if not isinstance(details, dict):
                continue
            sections[section_name][dimension] = {
                "score": details.get("expected", ""),
                "rationale": str(details.get("rationale", "")).strip(),
            }
    return sections


def _extract_model_scores(run_row: sqlite3.Row) -> dict[str, dict[str, Any]]:
    return {
        CASE_PERFORMANCE_SECTION: _json_loads(run_row["case_performance_json"], {}),
        DIALOG_QUALITY_SECTION: _json_loads(run_row["quality_dialog_json"], {}),
    }


def _extract_human_sections(evaluation_row: sqlite3.Row | None) -> dict[str, dict[str, Any]]:
    if evaluation_row is None:
        return {
            CASE_PERFORMANCE_SECTION: {},
            DIALOG_QUALITY_SECTION: {},
        }

    return {
        CASE_PERFORMANCE_SECTION: _json_loads(
            evaluation_row["case_performance_human_json"],
            {},
        ),
        DIALOG_QUALITY_SECTION: _json_loads(
            evaluation_row["dialog_quality_human_json"],
            {},
        ),
    }


def _score_sort_key(value: Any) -> tuple[int, str]:
    return (0, str(value))


def _summarize_changed_field(name: str, change: dict[str, Any]) -> dict[str, Any]:
    before_value = change.get("before")
    after_value = change.get("after")
    summary = ""

    if name == "transcript" and isinstance(before_value, list) and isinstance(after_value, list):
        appended = after_value[len(before_value) :] if after_value[: len(before_value)] == before_value else []
        if appended:
            summary = f"+{len(appended)} transcript line(s)"
        else:
            summary = "transcript updated"
    elif isinstance(before_value, list) and isinstance(after_value, list):
        delta = len(after_value) - len(before_value)
        if delta > 0:
            summary = f"+{delta} item(s)"
        elif delta < 0:
            summary = f"{delta} item(s)"
        else:
            summary = "list updated"
    elif isinstance(before_value, dict) and isinstance(after_value, dict):
        added_keys = sorted(set(after_value) - set(before_value))
        removed_keys = sorted(set(before_value) - set(after_value))
        changed_keys = sorted(
            key for key in set(before_value) & set(after_value) if before_value.get(key) != after_value.get(key)
        )
        parts = []
        if added_keys:
            parts.append(f"+{len(added_keys)} key(s)")
        if removed_keys:
            parts.append(f"-{len(removed_keys)} key(s)")
        if changed_keys:
            parts.append(f"~{len(changed_keys)} key(s)")
        summary = ", ".join(parts) or "object updated"
    else:
        summary = f"{before_value!r} -> {after_value!r}"

    return {
        "field": name,
        "summary": summary,
        "before": before_value,
        "after": after_value,
    }


def _extract_trace_transcript_updates(changed_fields: dict[str, Any]) -> list[dict[str, str]]:
    transcript_change = changed_fields.get("transcript")
    if not isinstance(transcript_change, dict):
        return []

    before_value = transcript_change.get("before")
    after_value = transcript_change.get("after")
    if not isinstance(before_value, list) or not isinstance(after_value, list):
        return []

    appended = after_value[len(before_value) :] if after_value[: len(before_value)] == before_value else after_value
    updates: list[dict[str, str]] = []
    for line in appended:
        if not isinstance(line, str):
            continue
        role = "system"
        if ": " in line:
            prefix, content = line.split(": ", 1)
            role = prefix.strip().lower().replace(" ", "_")
        else:
            content = line
        updates.append({"role": role, "content": content.strip()})
    return updates


def to_numeric_score(value: Any) -> float | None:
    """
    Convert a score to float/int if possible.
    Return None for missing, not_tested, N/A, or non-numeric values.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower()
    if text in {"", NOT_TESTED, "n/a", "na", "none", "null", "missing"}:
        return None

    try:
        return float(text)
    except ValueError:
        return None


def score_status(error: float | None) -> str:
    """
    Return exact match, off by 1, different, or not applicable.
    """
    if error is None:
        return "not applicable"
    if error == 0:
        return "exact match"
    if error == 1:
        return "off by 1"
    return "different"


def _pair_status(left_score: Any, right_score: Any) -> str:
    if left_score in {"", None} or right_score in {"", None}:
        return "missing"
    if str(left_score).strip().lower() == NOT_TESTED or str(right_score).strip().lower() == NOT_TESTED:
        return "not tested"
    error = _absolute_error(left_score, right_score)
    if error is None:
        return "missing"
    if error == 0:
        return "exact match"
    if error == 1:
        return "off by 1"
    return "different"


def _absolute_error(left_score: Any, right_score: Any) -> float | None:
    left_numeric = to_numeric_score(left_score)
    right_numeric = to_numeric_score(right_score)
    if left_numeric is None or right_numeric is None:
        return None
    return abs(left_numeric - right_numeric)


def calculate_error_metrics(comparison_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Given rows containing expected_score, model_score and human_score,
    calculate MAE, exact match rate, off-by-one rate, overestimation count,
    underestimation count, signed error, and expected-vs-human MAE.
    """
    model_abs_errors: list[float] = []
    expected_abs_errors: list[float] = []
    signed_errors: list[float] = []
    exact_match_count = 0
    off_by_one_count = 0
    overestimation_count = 0
    underestimation_count = 0

    for row in comparison_rows:
        model_score = to_numeric_score(row.get("model_score"))
        human_score = to_numeric_score(row.get("human_score"))
        expected_score = to_numeric_score(row.get("expected_score"))

        if model_score is not None and human_score is not None:
            absolute_error = abs(model_score - human_score)
            signed_error = model_score - human_score
            model_abs_errors.append(absolute_error)
            signed_errors.append(signed_error)
            if absolute_error == 0:
                exact_match_count += 1
            if absolute_error <= 1:
                off_by_one_count += 1
            if signed_error > 0:
                overestimation_count += 1
            if signed_error < 0:
                underestimation_count += 1

        if expected_score is not None and human_score is not None:
            expected_abs_errors.append(abs(expected_score - human_score))

    comparable_dimensions = len(model_abs_errors)
    expected_human_comparable_dimensions = len(expected_abs_errors)

    def _mean(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 3)

    def _rate(count: int, total: int) -> float | None:
        if total == 0:
            return None
        return round((count / total) * 100, 1)

    return {
        "model_vs_human_mae": _mean(model_abs_errors),
        "exact_match_rate": _rate(exact_match_count, comparable_dimensions),
        "off_by_one_rate": _rate(off_by_one_count, comparable_dimensions),
        "overestimation_count": overestimation_count,
        "underestimation_count": underestimation_count,
        "signed_error": _mean(signed_errors),
        "expected_vs_human_mae": _mean(expected_abs_errors),
        "comparable_dimensions": comparable_dimensions,
        "expected_human_comparable_dimensions": expected_human_comparable_dimensions,
    }


def build_three_way_score_comparison(
    expected_scores: dict[str, dict[str, Any]],
    model_scores: dict[str, dict[str, Any]],
    human_scores: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    comparison_rows: list[dict[str, Any]] = []

    for section_name, label in (
        (CASE_PERFORMANCE_SECTION, "Case Performance"),
        (DIALOG_QUALITY_SECTION, "Dialog Quality"),
    ):
        expected_section = expected_scores.get(section_name, {})
        model_section = model_scores.get(section_name, {})
        human_section = human_scores.get(section_name, {})
        dimensions = sorted(
            set(expected_section) | set(model_section) | set(human_section),
            key=_score_sort_key,
        )

        for dimension in dimensions:
            expected_entry = expected_section.get(dimension, {})
            model_entry = _normalize_dimension_entry(model_section.get(dimension, {}))
            human_entry = _normalize_dimension_entry(human_section.get(dimension, {}))
            expected_score = expected_entry.get("score", "")
            model_score = model_entry.get("score", "")
            human_score = human_entry.get("score", "")
            model_human_error = _absolute_error(model_score, human_score)
            expected_human_error = _absolute_error(expected_score, human_score)

            comparison_rows.append(
                {
                    "section": section_name,
                    "section_label": label,
                    "dimension": dimension,
                    "expected_score": expected_score,
                    "expected_rationale": expected_entry.get("rationale", ""),
                    "model_score": model_score,
                    "model_rationale": model_entry.get("rationale", ""),
                    "human_score": human_score,
                    "human_rationale": human_entry.get("rationale", ""),
                    "human_evidence": human_entry.get("evidence", ""),
                    "model_human_absolute_error": model_human_error,
                    "expected_human_absolute_error": expected_human_error,
                    "expected_model_status": _pair_status(expected_score, model_score),
                    "model_human_status": score_status(model_human_error),
                    "expected_human_status": score_status(expected_human_error),
                }
            )

    return comparison_rows


def build_annotation_sections(comparison_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """
    Group every comparison row by section so a human can score each dimension,
    whether or not the golden set already provides a reference score.
    """
    sections: dict[str, list[dict[str, Any]]] = {
        CASE_PERFORMANCE_SECTION: [],
        DIALOG_QUALITY_SECTION: [],
    }

    for row in comparison_rows:
        section_name = str(row.get("section", "")).strip()
        if section_name in sections:
            sections[section_name].append(row)

    return sections


def get_human_evaluation(run_id: str) -> dict[str, Any] | None:
    ensure_dashboard_db()

    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                run_id,
                evaluator_name,
                case_performance_human_json,
                dialog_quality_human_json,
                overall_human_score,
                notes,
                created_at,
                updated_at
            FROM human_evaluations
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "evaluator_name": row["evaluator_name"] or "",
        "case_performance_human": _json_loads(row["case_performance_human_json"], {}),
        "dialog_quality_human": _json_loads(row["dialog_quality_human_json"], {}),
        "overall_human_score": row["overall_human_score"],
        "notes": row["notes"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def save_human_evaluation(
    run_id: str,
    evaluator_name: str,
    case_performance_human_json: dict[str, Any],
    dialog_quality_human_json: dict[str, Any],
    overall_human_score: float | None,
    notes: str,
) -> dict[str, Any]:
    ensure_dashboard_db()

    payload = (
        evaluator_name.strip(),
        _json_dumps(case_performance_human_json),
        _json_dumps(dialog_quality_human_json),
        overall_human_score,
        notes.strip(),
        run_id,
    )

    with get_db_connection() as connection:
        run_exists = connection.execute(
            "SELECT 1 FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if run_exists is None:
            raise FileNotFoundError(f"Run '{run_id}' not found.")

        existing = connection.execute(
            "SELECT id FROM human_evaluations WHERE run_id = ?",
            (run_id,),
        ).fetchone()

        if existing is None:
            connection.execute(
                """
                INSERT INTO human_evaluations (
                    run_id,
                    evaluator_name,
                    case_performance_human_json,
                    dialog_quality_human_json,
                    overall_human_score,
                    notes
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, *payload[:-1]),
            )
        else:
            connection.execute(
                """
                UPDATE human_evaluations
                SET
                    evaluator_name = ?,
                    case_performance_human_json = ?,
                    dialog_quality_human_json = ?,
                    overall_human_score = ?,
                    notes = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ?
                """,
                payload,
            )

    saved = get_human_evaluation(run_id)
    if saved is None:
        raise RuntimeError(f"Human evaluation for run '{run_id}' was not saved.")
    return saved


def _build_run_payload(run_row: sqlite3.Row) -> dict[str, Any]:
    state = _json_loads(run_row["state_json"], {})
    transcript = _json_loads(run_row["transcript_json"], [])
    human_evaluation = get_human_evaluation(run_row["run_id"])
    human_sections = {
        CASE_PERFORMANCE_SECTION: {},
        DIALOG_QUALITY_SECTION: {},
    }
    if human_evaluation is not None:
        human_sections = {
            CASE_PERFORMANCE_SECTION: human_evaluation["case_performance_human"],
            DIALOG_QUALITY_SECTION: human_evaluation["dialog_quality_human"],
        }

    expected_scores = _extract_expected_scores(state)
    model_scores = _extract_model_scores(run_row)
    comparison_rows = build_three_way_score_comparison(
        expected_scores=expected_scores,
        model_scores=model_scores,
        human_scores=human_sections,
    )
    annotation_sections = build_annotation_sections(comparison_rows)
    metrics = calculate_error_metrics(comparison_rows)

    return {
        "run_id": run_row["run_id"],
        "graph_name": run_row["graph_name"],
        "thread_id": run_row["thread_id"],
        "scenario_ref": run_row["scenario_ref"] or "",
        "case_prompt": run_row["case_prompt"] or "",
        "turn_index": run_row["turn_index"],
        "judge_round": run_row["judge_round"],
        "enough_evidence": bool(run_row["enough_evidence"]),
        "focus_areas": _json_loads(run_row["focus_areas_json"], []),
        "transcript": transcript,
        "final_feedback": run_row["final_feedback"] or "",
        "state": state,
        "expected_scores": expected_scores,
        "model_scores": model_scores,
        "human_evaluation": human_evaluation,
        "human_scores": human_sections,
        "comparison_rows": comparison_rows,
        "annotation_sections": annotation_sections,
        "metrics": metrics,
        "created_at": run_row["created_at"],
    }


def load_run_traces(run_id: str) -> dict[str, Any]:
    run_payload = load_run(run_id)

    with get_db_connection() as connection:
        if not _table_exists(connection, "agent_state_traces"):
            return {
                "run": run_payload,
                "summary": {
                    "trace_count": 0,
                    "actor_count": 0,
                    "node_count": 0,
                    "changed_field_names": [],
                    "has_trace_table": False,
                },
                "traces": [],
            }

        rows = connection.execute(
            """
            SELECT
                trace_id,
                run_id,
                graph_name,
                thread_id,
                step_index,
                node_name,
                actor,
                scenario_ref,
                turn_index_before,
                turn_index_after,
                judge_round_before,
                judge_round_after,
                enough_evidence_before,
                enough_evidence_after,
                focus_areas_before_json,
                focus_areas_after_json,
                changed_fields_json,
                created_at
            FROM agent_state_traces
            WHERE run_id = ?
            ORDER BY step_index ASC, created_at ASC
            """,
            (run_id,),
        ).fetchall()

    traces: list[dict[str, Any]] = []
    actors: set[str] = set()
    nodes: set[str] = set()
    changed_field_names: set[str] = set()

    for row in rows:
        changed_fields = _json_loads(row["changed_fields_json"], {})
        field_changes = []
        if isinstance(changed_fields, dict):
            for field_name, change in sorted(changed_fields.items()):
                if not isinstance(change, dict):
                    continue
                changed_field_names.add(field_name)
                field_changes.append(_summarize_changed_field(field_name, change))

        transcript_updates = _extract_trace_transcript_updates(changed_fields if isinstance(changed_fields, dict) else {})
        actors.add(str(row["actor"]))
        nodes.add(str(row["node_name"]))

        traces.append(
            {
                "trace_id": row["trace_id"],
                "step_index": row["step_index"],
                "node_name": row["node_name"],
                "actor": row["actor"],
                "scenario_ref": row["scenario_ref"] or "",
                "turn_index_before": row["turn_index_before"],
                "turn_index_after": row["turn_index_after"],
                "judge_round_before": row["judge_round_before"],
                "judge_round_after": row["judge_round_after"],
                "enough_evidence_before": bool(row["enough_evidence_before"]),
                "enough_evidence_after": bool(row["enough_evidence_after"]),
                "focus_areas_before": _json_loads(row["focus_areas_before_json"], []),
                "focus_areas_after": _json_loads(row["focus_areas_after_json"], []),
                "changed_fields": changed_fields,
                "field_changes": field_changes,
                "changed_field_names": [item["field"] for item in field_changes],
                "transcript_updates": transcript_updates,
                "created_at": row["created_at"],
            }
        )

    return {
        "run": run_payload,
        "summary": {
            "trace_count": len(traces),
            "actor_count": len(actors),
            "node_count": len(nodes),
            "changed_field_names": sorted(changed_field_names),
            "has_trace_table": True,
        },
        "traces": traces,
    }


def list_runs(limit: int = 100) -> list[dict[str, Any]]:
    ensure_dashboard_db()

    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                run_id,
                graph_name,
                thread_id,
                scenario_ref,
                turn_index,
                judge_round,
                enough_evidence,
                case_prompt,
                final_feedback,
                created_at,
                state_json,
                transcript_json,
                focus_areas_json,
                case_performance_json,
                quality_dialog_json
            FROM runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        trace_counts: dict[str, dict[str, Any]] = {}
        if _table_exists(connection, "agent_state_traces"):
            trace_rows = connection.execute(
                """
                SELECT
                    run_id,
                    COUNT(trace_id) AS trace_count,
                    MAX(step_index) AS max_step_index,
                    MAX(created_at) AS last_trace_at
                FROM agent_state_traces
                GROUP BY run_id
                """
            ).fetchall()
            trace_counts = {
                row["run_id"]: {
                    "trace_count": int(row["trace_count"] or 0),
                    "max_step_index": int(row["max_step_index"] or 0),
                    "last_trace_at": row["last_trace_at"] or "",
                }
                for row in trace_rows
            }

    items = []
    for row in rows:
        payload = _build_run_payload(row)
        trace_info = trace_counts.get(
            payload["run_id"],
            {"trace_count": 0, "max_step_index": 0, "last_trace_at": ""},
        )
        items.append(
            {
                "run_id": payload["run_id"],
                "graph_name": payload["graph_name"],
                "scenario_ref": payload["scenario_ref"],
                "created_at": payload["created_at"],
                "case_prompt": payload["case_prompt"],
                "metrics": payload["metrics"],
                "has_human_evaluation": payload["human_evaluation"] is not None,
                "trace_count": trace_info["trace_count"],
                "max_step_index": trace_info["max_step_index"],
                "last_trace_at": trace_info["last_trace_at"],
                "has_traces": trace_info["trace_count"] > 0,
            }
        )
    return items


def load_run(run_id: str) -> dict[str, Any]:
    ensure_dashboard_db()

    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT
                run_id,
                graph_name,
                thread_id,
                scenario_ref,
                case_prompt,
                turn_index,
                judge_round,
                enough_evidence,
                focus_areas_json,
                transcript_json,
                case_performance_json,
                quality_dialog_json,
                final_feedback,
                state_json,
                created_at
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

    if row is None:
        raise FileNotFoundError(f"Run '{run_id}' not found.")

    return _build_run_payload(row)
