from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for

from dashboard_store import (
    CASE_PERFORMANCE_SECTION,
    DIALOG_QUALITY_SECTION,
    NOT_TESTED,
    ensure_dashboard_db,
    get_human_evaluation,
    list_trace_runs,
    list_runs,
    load_run,
    load_run_traces,
    save_human_evaluation,
)


ROOT_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(ROOT_DIR / "templates"),
    static_folder=str(ROOT_DIR / "static"),
)
app.config["SECRET_KEY"] = "main-human-eval"


def _wants_json() -> bool:
    if request.args.get("format") == "json":
        return True
    return request.accept_mimetypes.best == "application/json"


def _parse_numeric_field(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        abort(400, f"Invalid numeric value '{text}'.")


def _collect_dimension_payload(section_prefix: str, dimensions: list[str]) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}

    for dimension in dimensions:
        score_key = f"{section_prefix}__{dimension}__score"
        rationale_key = f"{section_prefix}__{dimension}__rationale"
        evidence_key = f"{section_prefix}__{dimension}__evidence"

        score = str(request.form.get(score_key, "")).strip()
        rationale = str(request.form.get(rationale_key, "")).strip()
        evidence = str(request.form.get(evidence_key, "")).strip()

        if score or rationale or evidence:
            payload[dimension] = {
                "score": score or NOT_TESTED,
                "rationale": rationale,
                "evidence": evidence,
            }

    return payload


def _collect_json_section(raw_section: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_section, dict):
        abort(400, "Section payload must be an object.")

    normalized: dict[str, dict[str, Any]] = {}
    for dimension, raw_entry in raw_section.items():
        if not isinstance(raw_entry, dict):
            abort(400, f"Dimension '{dimension}' must be an object.")
        score = str(raw_entry.get("score", "")).strip()
        normalized[dimension] = {
            "score": score or NOT_TESTED,
            "rationale": str(raw_entry.get("rationale", "")).strip(),
            "evidence": str(raw_entry.get("evidence", "")).strip(),
        }
    return normalized


@app.get("/")
def index():
    ensure_dashboard_db()
    runs = list_runs(limit=100)
    return render_template("index.html", runs=runs)


@app.get("/compare")
def compare_runs():
    ensure_dashboard_db()
    runs = list_runs(limit=100)
    run_a_id = str(request.args.get("run_a", "")).strip()
    run_b_id = str(request.args.get("run_b", "")).strip()

    try:
        run_a = load_run(run_a_id) if run_a_id else None
        run_b = load_run(run_b_id) if run_b_id else None
    except FileNotFoundError as exc:
        abort(404, str(exc))

    return render_template(
        "compare.html",
        runs=runs,
        run_a=run_a,
        run_b=run_b,
        run_a_id=run_a_id,
        run_b_id=run_b_id,
    )


@app.get("/traces")
def trace_index():
    ensure_dashboard_db()
    trace_runs = list_trace_runs(limit=100)
    return render_template("trace_index.html", trace_runs=trace_runs)


@app.get("/runs/<run_id>")
def get_run(run_id: str):
    try:
        run_payload = load_run(run_id)
    except FileNotFoundError as exc:
        abort(404, str(exc))

    if _wants_json():
        return jsonify(run_payload)

    return render_template("run_detail.html", run=run_payload)


@app.get("/runs/<run_id>/trace")
def get_run_trace(run_id: str):
    try:
        trace_payload = load_run_traces(run_id)
    except FileNotFoundError as exc:
        abort(404, str(exc))

    if _wants_json():
        return jsonify(trace_payload)

    return render_template("run_trace.html", trace=trace_payload)


@app.get("/runs/<run_id>/human-evaluation")
def human_evaluation_page(run_id: str):
    return redirect(url_for("get_run", run_id=run_id))


@app.post("/runs/<run_id>/human-evaluation")
def save_human_evaluation_page(run_id: str):
    run_payload = load_run(run_id)
    case_dimensions = sorted(
        row["dimension"] for row in run_payload["annotation_sections"][CASE_PERFORMANCE_SECTION]
    )
    dialog_dimensions = sorted(
        row["dimension"] for row in run_payload["annotation_sections"][DIALOG_QUALITY_SECTION]
    )

    case_section = _collect_dimension_payload(CASE_PERFORMANCE_SECTION, case_dimensions)
    dialog_section = _collect_dimension_payload(DIALOG_QUALITY_SECTION, dialog_dimensions)

    save_human_evaluation(
        run_id=run_id,
        evaluator_name=str(request.form.get("evaluator_name", "")).strip(),
        case_performance_human_json=case_section,
        dialog_quality_human_json=dialog_section,
        overall_human_score=_parse_numeric_field(request.form.get("overall_human_score")),
        notes=str(request.form.get("notes", "")).strip(),
    )
    flash("Human evaluation saved.", "success")
    return redirect(url_for("get_run", run_id=run_id))


@app.get("/api/runs/<run_id>/human-evaluation")
def get_human_evaluation_api(run_id: str):
    load_run(run_id)
    payload = get_human_evaluation(run_id)
    return jsonify(
        {
            "run_id": run_id,
            "human_evaluation": payload,
        }
    )


@app.post("/api/runs/<run_id>/human-evaluation")
def save_human_evaluation_api(run_id: str):
    payload = request.get_json(silent=True) or {}
    saved = save_human_evaluation(
        run_id=run_id,
        evaluator_name=str(payload.get("evaluator_name", "")).strip(),
        case_performance_human_json=_collect_json_section(
            payload.get("case_performance_human_json", {})
        ),
        dialog_quality_human_json=_collect_json_section(
            payload.get("dialog_quality_human_json", {})
        ),
        overall_human_score=_parse_numeric_field(payload.get("overall_human_score")),
        notes=str(payload.get("notes", "")).strip(),
    )
    return jsonify(saved)


@app.get("/api/runs/<run_id>/scores")
def get_run_scores_api(run_id: str):
    run_payload = load_run(run_id)
    return jsonify(
        {
            "expected_scores": run_payload["expected_scores"],
            "model_scores": run_payload["model_scores"],
            "human_scores": run_payload["human_scores"],
            "comparison_rows": run_payload["comparison_rows"],
            "metrics": run_payload["metrics"],
        }
    )


if __name__ == "__main__":
    ensure_dashboard_db()
    app.run(debug=True, port=int(os.environ.get("WORKBENCH_PORT", "5020")))
