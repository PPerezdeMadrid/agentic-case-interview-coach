from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

from workbench_service import build_scenario_preview, list_scenario_groups, run_scenario
from workbench_store import initialize_store, list_runs, load_run


ROOT_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(ROOT_DIR / "workbench_templates"),
    static_folder=str(ROOT_DIR / "workbench_static"),
)


def _wants_json() -> bool:
    if request.args.get("format") == "json":
        return True
    return request.accept_mimetypes.best == "application/json"


@app.route("/")
def index():
    initialize_store()
    scenario_groups = list_scenario_groups()
    if not scenario_groups:
        abort(404, "No synthetic scenarios were found.")

    selected_group = request.args.get("scenario_group") or scenario_groups[0]["scenario_group"]
    selected_grade = request.args.get("grade")
    preview = build_scenario_preview(selected_group, selected_grade)

    return render_template(
        "index.html",
        scenario_groups=scenario_groups,
        selected_group=selected_group,
        preview=preview,
        recent_runs=list_runs(limit=12),
    )


@app.get("/scenarios/<scenario_group>")
def get_scenario(scenario_group: str):
    try:
        preview = build_scenario_preview(scenario_group, request.args.get("grade"))
    except FileNotFoundError as exc:
        abort(404, str(exc))

    if _wants_json():
        return jsonify(preview)

    return redirect(
        url_for(
            "index",
            scenario_group=scenario_group,
            grade=preview["scenario_key"],
        )
    )


@app.get("/scenarios/<scenario_group>/preview")
def get_scenario_preview(scenario_group: str):
    grade = request.args.get("grade")
    try:
        preview = build_scenario_preview(scenario_group, grade)
    except FileNotFoundError as exc:
        abort(404, str(exc))
    return jsonify(preview)


@app.post("/runs")
def create_run():
    payload = request.get_json(silent=True) or request.form
    scenario_group = str(payload.get("scenario_group", "")).strip()
    scenario_key = str(payload.get("grade", "")).strip()
    seed_raw = payload.get("seed")
    seed = int(seed_raw) if str(seed_raw).strip() else None

    if not scenario_group or not scenario_key:
        abort(400, "scenario_group and grade are required.")

    result = run_scenario(scenario_group, scenario_key, seed=seed)
    if _wants_json():
        return jsonify(result), 201

    return redirect(url_for("get_run", run_id=result["run_id"]))


@app.get("/runs/<run_id>")
def get_run(run_id: str):
    try:
        run_payload = load_run(run_id)
    except FileNotFoundError as exc:
        abort(404, str(exc))

    if _wants_json():
        return jsonify(run_payload)

    return render_template("run_detail.html", run=run_payload)


if __name__ == "__main__":
    initialize_store()
    app.run(debug=True, port=5001)
