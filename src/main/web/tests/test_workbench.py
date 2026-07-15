import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


WEB_DIR = Path(__file__).resolve().parents[1]
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

try:
    import app as workbench_app
    import dashboard_store
except ModuleNotFoundError as exc:
    raise unittest.SkipTest(f"Workbench test dependencies are not installed: {exc.name}") from exc


def create_runs_table(db_path: Path) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                graph_name TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                scenario_ref TEXT,
                case_prompt TEXT,
                turn_index INTEGER,
                judge_round INTEGER,
                enough_evidence INTEGER NOT NULL,
                focus_areas_json TEXT NOT NULL,
                transcript_json TEXT NOT NULL,
                case_performance_json TEXT NOT NULL,
                quality_dialog_json TEXT NOT NULL,
                final_feedback TEXT,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE agent_state_traces (
                trace_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                graph_name TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                node_name TEXT NOT NULL,
                actor TEXT NOT NULL,
                scenario_ref TEXT,
                turn_index_before INTEGER,
                turn_index_after INTEGER,
                judge_round_before INTEGER,
                judge_round_after INTEGER,
                enough_evidence_before INTEGER,
                enough_evidence_after INTEGER,
                focus_areas_before_json TEXT NOT NULL,
                focus_areas_after_json TEXT NOT NULL,
                changed_fields_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def insert_sample_run(db_path: Path, run_id: str = "run_001") -> None:
    state = {
        "candidate_profile": {
            "expected_scores": {
                dashboard_store.CASE_PERFORMANCE_SECTION: {
                    "case_structure": {
                        "expected": 4,
                        "rationale": "The candidate should structure the problem clearly.",
                    }
                },
                dashboard_store.DIALOG_QUALITY_SECTION: {
                    "clarity_and_concision": {
                        "expected": 3,
                        "rationale": "Communication should stay concise.",
                    }
                },
            }
        }
    }
    transcript = [
        "Interviewer: Our profits are falling.",
        "Candidate: I would split revenue and costs.",
        "Give Feedback: Good structure overall.",
    ]
    case_performance = {
        "case_structure": {
            "score": 3,
            "rationale": "Reasonable structure.",
        }
    }
    quality_dialog = {
        "clarity_and_concision": {
            "score": 4,
            "rationale": "Clear communication.",
        }
    }

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO runs (
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                "agentic",
                "thread_001",
                "scenario_test",
                "Our profits are falling.",
                4,
                1,
                1,
                json.dumps(["structure"]),
                json.dumps(transcript),
                json.dumps(case_performance),
                json.dumps(quality_dialog),
                "Good structure overall.",
                json.dumps(state),
                "2026-07-02T10:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO agent_state_traces (
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trace_001",
                run_id,
                "agentic",
                "thread_001",
                1,
                "interviewer",
                "interviewer",
                "scenario_test",
                0,
                1,
                0,
                0,
                0,
                0,
                json.dumps([]),
                json.dumps(["structure"]),
                json.dumps(
                    {
                        "transcript": {
                            "before": [],
                            "after": ["Interviewer: Our profits are falling."],
                        },
                        "turn_index": {
                            "before": 0,
                            "after": 1,
                        },
                        "focus_areas": {
                            "before": [],
                            "after": ["structure"],
                        },
                    }
                ),
                "2026-07-02T10:00:01+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO agent_state_traces (
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trace_002",
                run_id,
                "agentic",
                "thread_001",
                2,
                "candidate",
                "candidate",
                "scenario_test",
                1,
                2,
                0,
                0,
                0,
                1,
                json.dumps(["structure"]),
                json.dumps(["structure"]),
                json.dumps(
                    {
                        "transcript": {
                            "before": ["Interviewer: Our profits are falling."],
                            "after": [
                                "Interviewer: Our profits are falling.",
                                "Candidate: I would split revenue and costs.",
                            ],
                        },
                        "enough_evidence": {
                            "before": False,
                            "after": True,
                        },
                    }
                ),
                "2026-07-02T10:00:02+00:00",
            ),
        )


class DashboardStoreTests(unittest.TestCase):
    def test_calculate_error_metrics_ignores_non_numeric_pairs(self) -> None:
        rows = [
            {"expected_score": 4, "model_score": 3, "human_score": 4},
            {"expected_score": 3, "model_score": "not_tested", "human_score": 2},
            {"expected_score": "", "model_score": 2, "human_score": None},
        ]

        metrics = dashboard_store.calculate_error_metrics(rows)

        self.assertEqual(metrics["model_vs_human_mae"], 1.0)
        self.assertEqual(metrics["exact_match_rate"], 0.0)
        self.assertEqual(metrics["off_by_one_rate"], 100.0)
        self.assertEqual(metrics["overestimation_count"], 0)
        self.assertEqual(metrics["underestimation_count"], 1)
        self.assertEqual(metrics["expected_vs_human_mae"], 0.5)
        self.assertEqual(metrics["comparable_dimensions"], 1)
        self.assertEqual(metrics["expected_human_comparable_dimensions"], 2)

    def test_calculate_error_metrics_exact_match_rate_is_100_for_all_matches(self) -> None:
        rows = [
            {"expected_score": 4, "model_score": 4, "human_score": 4},
            {"expected_score": 3, "model_score": 3, "human_score": 3},
        ]

        metrics = dashboard_store.calculate_error_metrics(rows)

        self.assertEqual(metrics["exact_match_rate"], 100.0)
        self.assertEqual(metrics["off_by_one_rate"], 100.0)
        self.assertEqual(metrics["model_vs_human_mae"], 0.0)
        self.assertEqual(metrics["comparable_dimensions"], 2)

    def test_calculate_error_metrics_exact_match_rate_is_50_for_mixed_results(self) -> None:
        rows = [
            {"expected_score": 4, "model_score": 4, "human_score": 4},
            {"expected_score": 3, "model_score": 2, "human_score": 3},
        ]

        metrics = dashboard_store.calculate_error_metrics(rows)

        self.assertEqual(metrics["exact_match_rate"], 50.0)
        self.assertEqual(metrics["off_by_one_rate"], 100.0)
        self.assertEqual(metrics["model_vs_human_mae"], 0.5)
        self.assertEqual(metrics["comparable_dimensions"], 2)

    def test_calculate_error_metrics_exact_match_rate_ignores_missing_pairs(self) -> None:
        rows = [
            {"expected_score": 4, "model_score": 4, "human_score": 4},
            {"expected_score": 3, "model_score": "", "human_score": 3},
            {"expected_score": 2, "model_score": 2, "human_score": None},
        ]

        metrics = dashboard_store.calculate_error_metrics(rows)

        self.assertEqual(metrics["exact_match_rate"], 100.0)
        self.assertEqual(metrics["comparable_dimensions"], 1)

    def test_calculate_error_metrics_exact_match_rate_is_none_without_comparable_pairs(self) -> None:
        rows = [
            {"expected_score": 4, "model_score": "", "human_score": 4},
            {"expected_score": 3, "model_score": "not_tested", "human_score": None},
        ]

        metrics = dashboard_store.calculate_error_metrics(rows)

        self.assertIsNone(metrics["exact_match_rate"])
        self.assertEqual(metrics["comparable_dimensions"], 0)

    def test_load_run_builds_expected_model_and_human_scores(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "runs.sqlite"
            create_runs_table(db_path)
            insert_sample_run(db_path)

            with patch.object(dashboard_store, "RUNS_DB_PATH", db_path):
                dashboard_store.ensure_dashboard_db()
                dashboard_store.save_human_evaluation(
                    run_id="run_001",
                    evaluator_name="Paloma",
                    case_performance_human_json={
                        "case_structure": {
                            "score": 4,
                            "rationale": "Strong issue tree.",
                            "evidence": "Candidate split revenue and costs.",
                        }
                    },
                    dialog_quality_human_json={
                        "clarity_and_concision": {
                            "score": 3,
                            "rationale": "Clear enough.",
                            "evidence": "Direct answer.",
                        }
                    },
                    overall_human_score=3.5,
                    notes="Solid attempt.",
                )
                payload = dashboard_store.load_run("run_001")

        self.assertEqual(payload["run_id"], "run_001")
        self.assertEqual(payload["expected_scores"]["rubric"]["case_structure"]["score"], 4)
        self.assertEqual(payload["model_scores"]["rubric"]["case_structure"]["score"], 3)
        self.assertEqual(payload["human_scores"]["rubric"]["case_structure"]["score"], 4)
        self.assertEqual(payload["metrics"]["model_vs_human_mae"], 1.0)
        self.assertEqual(payload["metrics"]["exact_match_rate"], 0.0)
        self.assertEqual(len(payload["annotation_sections"]["rubric"]), 1)
        self.assertEqual(payload["annotation_sections"]["rubric"][0]["dimension"], "case_structure")

    def test_load_run_traces_builds_timeline_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "runs.sqlite"
            create_runs_table(db_path)
            insert_sample_run(db_path)

            with patch.object(dashboard_store, "RUNS_DB_PATH", db_path):
                trace_payload = dashboard_store.load_run_traces("run_001")

        self.assertEqual(trace_payload["run"]["run_id"], "run_001")
        self.assertEqual(trace_payload["summary"]["trace_count"], 2)
        self.assertEqual(trace_payload["summary"]["actor_count"], 2)
        self.assertIn("transcript", trace_payload["summary"]["changed_field_names"])
        self.assertEqual(trace_payload["traces"][0]["transcript_updates"][0]["role"], "interviewer")
        self.assertEqual(
            trace_payload["traces"][1]["transcript_updates"][0]["content"],
            "I would split revenue and costs.",
        )


class WorkbenchAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "runs.sqlite"
        create_runs_table(self.db_path)
        insert_sample_run(self.db_path)

        self.dashboard_db_patch = patch.object(dashboard_store, "RUNS_DB_PATH", self.db_path)
        self.dashboard_db_patch.start()
        workbench_app.app.config["TESTING"] = True
        self.client = workbench_app.app.test_client()

    def tearDown(self) -> None:
        self.dashboard_db_patch.stop()
        self.temp_dir.cleanup()

    def test_get_run_json_returns_run_payload(self) -> None:
        response = self.client.get("/runs/run_001?format=json")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["run_id"], "run_001")
        self.assertEqual(payload["graph_name"], "agentic")
        self.assertIn("comparison_rows", payload)

    def test_human_evaluation_api_round_trip_updates_scores(self) -> None:
        response = self.client.post(
            "/api/runs/run_001/human-evaluation",
            json={
                "evaluator_name": "Paloma",
                "case_performance_human_json": {
                    "case_structure": {
                        "score": 4,
                        "rationale": "Strong structure.",
                        "evidence": "Clear split.",
                    }
                },
                "dialog_quality_human_json": {
                    "clarity_and_concision": {
                        "score": 3,
                        "rationale": "Concise enough.",
                        "evidence": "Short answer.",
                    }
                },
                "overall_human_score": 3.5,
                "notes": "Useful benchmark.",
            },
        )

        self.assertEqual(response.status_code, 200)
        saved = response.get_json()
        self.assertEqual(saved["run_id"], "run_001")
        self.assertEqual(saved["evaluator_name"], "Paloma")

        evaluation_response = self.client.get("/api/runs/run_001/human-evaluation")
        self.assertEqual(evaluation_response.status_code, 200)
        evaluation_payload = evaluation_response.get_json()
        self.assertEqual(
            evaluation_payload["human_evaluation"]["case_performance_human"]["case_structure"]["score"],
            "4",
        )

        scores_response = self.client.get("/api/runs/run_001/scores")
        self.assertEqual(scores_response.status_code, 200)
        scores_payload = scores_response.get_json()
        self.assertEqual(scores_payload["human_scores"]["rubric"]["case_structure"]["score"], "4")
        self.assertEqual(scores_payload["metrics"]["model_vs_human_mae"], 1.0)

    def test_human_evaluation_api_returns_wrapper_when_missing(self) -> None:
        response = self.client.get("/api/runs/run_001/human-evaluation")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["run_id"], "run_001")
        self.assertIsNone(payload["human_evaluation"])

    def test_runs_page_includes_trace_summary(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("run_001", body)
        self.assertIn("Open trace (2)", body)

    def test_get_run_trace_json_returns_trace_payload(self) -> None:
        response = self.client.get("/runs/run_001/trace?format=json")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["run"]["run_id"], "run_001")
        self.assertEqual(payload["summary"]["trace_count"], 2)
        self.assertEqual(payload["traces"][0]["step_index"], 1)

    def test_human_evaluation_api_rejects_invalid_section_shape(self) -> None:
        response = self.client.post(
            "/api/runs/run_001/human-evaluation",
            json={
                "case_performance_human_json": {
                    "case_structure": "invalid"
                },
                "dialog_quality_human_json": {},
            },
        )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
