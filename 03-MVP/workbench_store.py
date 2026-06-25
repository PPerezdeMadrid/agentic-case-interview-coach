from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "workbench_data"
RUNS_DIR = DATA_DIR / "runs"
DB_PATH = DATA_DIR / "workbench.sqlite3"


def initialize_store() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as connection:
        existing_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(runs)").fetchall()
        }
        if {"grade_label", "grade_value"} & existing_columns:
            connection.execute("DROP TABLE IF EXISTS runs")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                scenario_key TEXT NOT NULL,
                scenario_group TEXT NOT NULL,
                scenario_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                seed INTEGER,
                final_score INTEGER,
                expected_overall INTEGER,
                created_at TEXT NOT NULL,
                payload_path TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_created_at
            ON runs(created_at DESC)
            """
        )
        connection.commit()


def save_run(payload: dict[str, Any]) -> None:
    initialize_store()

    run_id = str(payload["run_id"])
    payload_path = RUNS_DIR / f"{run_id}.json"
    payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    scenario_snapshot = payload.get("scenario_snapshot", {})
    comparison = payload.get("comparison_result", {})
    run_metadata = payload.get("run_metadata", {})

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id,
                scenario_key,
                scenario_group,
                scenario_id,
                case_id,
                seed,
                final_score,
                expected_overall,
                created_at,
                payload_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                str(scenario_snapshot.get("scenario_key", "")),
                str(scenario_snapshot.get("scenario_group", "")),
                str(scenario_snapshot.get("scenario_id", "")),
                str(scenario_snapshot.get("case_id", "")),
                run_metadata.get("seed"),
                payload.get("actual_scores", {}).get("overall"),
                comparison.get("expected_overall"),
                str(run_metadata.get("created_at", "")),
                str(payload_path),
            ),
        )
        connection.commit()


def load_run(run_id: str) -> dict[str, Any]:
    initialize_store()

    with sqlite3.connect(DB_PATH) as connection:
        row = connection.execute(
            "SELECT payload_path FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()

    if row is None:
        raise FileNotFoundError(f"Run '{run_id}' not found.")

    payload_path = Path(row[0])
    if not payload_path.exists():
        raise FileNotFoundError(f"Run payload missing for '{run_id}'.")

    return json.loads(payload_path.read_text(encoding="utf-8"))


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    initialize_store()

    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                run_id,
                scenario_key,
                scenario_group,
                scenario_id,
                case_id,
                seed,
                final_score,
                expected_overall,
                created_at
            FROM runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]
