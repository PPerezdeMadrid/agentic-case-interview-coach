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
    list_runs,
    load_run,
    load_run_traces,
    save_human_evaluation,
)
from experiment_store import (
    build_overview,
    list_batches,
    load_batch,
    load_scenario_detail,
)
from judge_eval import build_category_radar, category_breakdown, list_judge_golden_sets, load_judge_eval
from rag_ablation import list_ablation_batches, load_ablation
from retrieval_eval import DEFAULT_TOP_K, evaluate_retrieval


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


@app.get("/experiment")
def experiment_index():
    batches = list_batches()
    if not batches:
        return render_template("experiment.html", batches=[], batch=None, overview=None)

    requested_dir = str(request.args.get("batch", "")).strip()
    dir_name = requested_dir if any(b["dir_name"] == requested_dir for b in batches) else batches[0]["dir_name"]

    try:
        overview = build_overview(dir_name)
    except FileNotFoundError:
        abort(404, f"Batch '{dir_name}' not found.")

    return render_template("experiment.html", batches=batches, batch=dir_name, overview=overview)


@app.get("/experiment/<dir_name>/<slug>")
def experiment_scenario(dir_name: str, slug: str):
    try:
        batch = load_batch(dir_name)
    except FileNotFoundError:
        abort(404, f"Batch '{dir_name}' not found.")

    try:
        scenario = load_scenario_detail(batch["records"], slug)
    except FileNotFoundError:
        abort(404, f"Scenario '{slug}' not found in batch '{dir_name}'.")

    return render_template("experiment_scenario.html", dir_name=dir_name, scenario=scenario)


@app.get("/rag-evaluation")
def rag_evaluation_index():
    try:
        top_k = int(str(request.args.get("k", DEFAULT_TOP_K)).strip())
    except ValueError:
        top_k = DEFAULT_TOP_K
    retrieval_refresh = request.args.get("refresh") == "1"

    retrieval_result = None
    retrieval_error = None
    try:
        retrieval_result = evaluate_retrieval(top_k=top_k, refresh=retrieval_refresh)
    except FileNotFoundError as exc:
        retrieval_error = str(exc)

    ablation_batches = list_ablation_batches()
    ablation_batch = None
    ablation_result = None
    ablation_error = None
    if ablation_batches:
        requested_batch = str(request.args.get("batch", "")).strip()
        ablation_batch = requested_batch if requested_batch in ablation_batches else ablation_batches[0]
        ablation_refresh = request.args.get("ablation_refresh") == "1"
        try:
            ablation_result = load_ablation(ablation_batch, refresh=ablation_refresh)
        except FileNotFoundError as exc:
            ablation_error = str(exc)

    if _wants_json():
        return jsonify({"retrieval": retrieval_result, "ablation": ablation_result})

    return render_template(
        "rag_evaluation.html",
        top_k=top_k,
        retrieval_result=retrieval_result,
        retrieval_error=retrieval_error,
        ablation_batches=ablation_batches,
        ablation_batch=ablation_batch,
        ablation_result=ablation_result,
        ablation_error=ablation_error,
    )


@app.get("/agents")
def agents_index():
    return render_template("agents.html")


@app.get("/agents/judge")
def agents_judge():
    golden_sets = list_judge_golden_sets()
    golden_set = None
    result = None
    error = None
    categories = None
    radar = None
    if golden_sets:
        requested = str(request.args.get("golden_set", "")).strip()
        golden_set = requested if requested in golden_sets else golden_sets[0]
        refresh = request.args.get("refresh") == "1"
        try:
            result = load_judge_eval(golden_set, refresh=refresh)
            categories = category_breakdown(result["records"])
            radar = build_category_radar(categories)
        except FileNotFoundError as exc:
            error = str(exc)

    if _wants_json():
        return jsonify({**result, "category_breakdown": categories} if result else result)

    return render_template(
        "agents_judge.html",
        golden_sets=golden_sets,
        golden_set=golden_set,
        result=result,
        error=error,
        categories=categories,
        radar=radar,
    )


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
