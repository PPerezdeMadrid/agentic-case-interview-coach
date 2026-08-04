import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


STUDIO_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = STUDIO_DIR.parents[1]
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    import rag_ablation_eval
except ModuleNotFoundError as exc:
    raise unittest.SkipTest(f"Studio test dependencies are not installed: {exc.name}") from exc


class RagAblationEvalTests(unittest.TestCase):
    def test_transcript_before_eval_drops_post_eval_lines(self) -> None:
        record = {
            "transcript": [
                "Interviewer: Walk me through your approach.",
                "Candidate: I would split revenue and cost.",
                "Eval Case Performance: structured case-performance assessment completed.",
                "Eval Dialog Quality: structured interaction-quality assessment completed.",
                "Give Feedback: Nice structure.",
            ]
        }

        self.assertEqual(
            rag_ablation_eval._transcript_before_eval(record),
            [
                "Interviewer: Walk me through your approach.",
                "Candidate: I would split revenue and cost.",
            ],
        )


class RagAblationCheckpointTests(unittest.TestCase):
    def _make_record(self, thread_id: str) -> dict:
        score_entry = {"score": 3, "rationale": "placeholder"}
        return {
            "status": "ok",
            "thread_id": thread_id,
            "graph_name": "agentic",
            "scenario_ref": "scenario_01_01.json",
            "repeat_index": 1,
            "transcript": ["Interviewer: Hi.", "Candidate: Hi."],
            "case_performance": {field: score_entry for field in rag_ablation_eval.CASE_PERFORMANCE_FIELDS},
            "quality_dialog": {field: score_entry for field in rag_ablation_eval.QUALITY_DIALOG_FIELDS},
        }

    def _write_batch(self, batch_dir: Path, records: list[dict]) -> None:
        batch_dir.mkdir(parents=True, exist_ok=True)
        (batch_dir / "summary.json").write_text(json.dumps({"batch_id": batch_dir.name}))
        with (batch_dir / "combined_results.jsonl").open("w") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")

    def test_load_checkpoint_missing_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(rag_ablation_eval._load_checkpoint(Path(tmp)), {})

    def test_checkpoint_roundtrip_skips_corrupt_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batch_dir = Path(tmp)
            rag_ablation_eval._append_checkpoint(batch_dir, {"thread_id": "t1", "value": 1})
            with rag_ablation_eval._checkpoint_path(batch_dir).open("a") as handle:
                handle.write("{not valid json\n")
            rag_ablation_eval._append_checkpoint(batch_dir, {"thread_id": "t2", "value": 2})

            done = rag_ablation_eval._load_checkpoint(batch_dir)
            self.assertEqual(set(done), {"t1", "t2"})
            self.assertEqual(done["t2"]["value"], 2)

    def test_run_ablation_resumes_from_checkpoint(self) -> None:
        record1, record2 = self._make_record("t1"), self._make_record("t2")
        without_case_performance = {field: {"score": 2, "rationale": "no-rag"} for field in rag_ablation_eval.CASE_PERFORMANCE_FIELDS}
        without_quality_dialog = {field: {"score": 2, "rationale": "no-rag"} for field in rag_ablation_eval.QUALITY_DIALOG_FIELDS}

        with tempfile.TemporaryDirectory() as tmp:
            batches_root = Path(tmp)
            dir_name = "fake_batch"
            batch_dir = batches_root / dir_name
            self._write_batch(batch_dir, [record1, record2])

            # Pre-seed the checkpoint as if a prior run had already scored t1 before crashing.
            checkpoint_entry = {
                "thread_id": "t1",
                "graph_name": "agentic",
                "scenario_ref": record1["scenario_ref"],
                "repeat_index": 1,
                "case_performance": [
                    rag_ablation_eval._compare_field(field, record1["case_performance"], without_case_performance)
                    for field in rag_ablation_eval.CASE_PERFORMANCE_FIELDS
                ],
                "quality_dialog": [
                    rag_ablation_eval._compare_field(field, record1["quality_dialog"], without_quality_dialog)
                    for field in rag_ablation_eval.QUALITY_DIALOG_FIELDS
                ],
            }
            rag_ablation_eval._append_checkpoint(batch_dir, checkpoint_entry)

            with (
                patch.object(rag_ablation_eval, "BATCH_RUNS_DIR", batches_root),
                patch.object(rag_ablation_eval, "_rebuild_state", return_value={}) as mock_rebuild,
                patch.object(
                    rag_ablation_eval,
                    "_evaluate_without_rag",
                    return_value=(without_case_performance, without_quality_dialog, []),
                ) as mock_evaluate,
            ):
                output = rag_ablation_eval.run_ablation(dir_name)

            # Only the pending record (t2) should have triggered real work.
            self.assertEqual(mock_evaluate.call_count, 1)
            self.assertEqual(mock_rebuild.call_count, 1)
            self.assertEqual(mock_rebuild.call_args[0][1]["thread_id"], "t2")

            # Output preserves the batch's original order and includes both records.
            self.assertEqual(output["n_records"], 2)
            self.assertEqual([r["thread_id"] for r in output["records"]], ["t1", "t2"])

            # A successful full run cleans up the checkpoint.
            self.assertFalse(rag_ablation_eval._checkpoint_path(batch_dir).exists())
            self.assertTrue((batch_dir / "rag_ablation_results.json").exists())

    def test_run_ablation_restart_ignores_checkpoint(self) -> None:
        record1 = self._make_record("t1")
        without_case_performance = {field: {"score": 2, "rationale": "no-rag"} for field in rag_ablation_eval.CASE_PERFORMANCE_FIELDS}
        without_quality_dialog = {field: {"score": 2, "rationale": "no-rag"} for field in rag_ablation_eval.QUALITY_DIALOG_FIELDS}

        with tempfile.TemporaryDirectory() as tmp:
            batches_root = Path(tmp)
            dir_name = "fake_batch"
            batch_dir = batches_root / dir_name
            self._write_batch(batch_dir, [record1])
            rag_ablation_eval._append_checkpoint(batch_dir, {"thread_id": "t1", "case_performance": [], "quality_dialog": []})

            with (
                patch.object(rag_ablation_eval, "BATCH_RUNS_DIR", batches_root),
                patch.object(rag_ablation_eval, "_rebuild_state", return_value={}),
                patch.object(
                    rag_ablation_eval,
                    "_evaluate_without_rag",
                    return_value=(without_case_performance, without_quality_dialog, []),
                ) as mock_evaluate,
            ):
                rag_ablation_eval.run_ablation(dir_name, restart=True)

            # --restart forces t1 to be re-scored even though a checkpoint already had it.
            self.assertEqual(mock_evaluate.call_count, 1)

    def test_print_status_reports_partial_progress_and_mae(self) -> None:
        record1, record2 = self._make_record("t1"), self._make_record("t2")
        without_case_performance = {
            field: {"score": 2, "rationale": "no-rag"} for field in rag_ablation_eval.CASE_PERFORMANCE_FIELDS
        }
        without_quality_dialog = {
            field: {"score": 2, "rationale": "no-rag"} for field in rag_ablation_eval.QUALITY_DIALOG_FIELDS
        }

        with tempfile.TemporaryDirectory() as tmp:
            batches_root = Path(tmp)
            dir_name = "fake_batch"
            batch_dir = batches_root / dir_name
            self._write_batch(batch_dir, [record1, record2])

            # Only t1 has been checkpointed so far -- t2's run is still "in flight".
            checkpoint_entry = {
                "thread_id": "t1",
                "graph_name": "agentic",
                "scenario_ref": record1["scenario_ref"],
                "repeat_index": 1,
                "checkpointed_at": "2026-08-01T10:00:00+00:00",
                "case_performance": [
                    rag_ablation_eval._compare_field(field, record1["case_performance"], without_case_performance)
                    for field in rag_ablation_eval.CASE_PERFORMANCE_FIELDS
                ],
                "quality_dialog": [
                    rag_ablation_eval._compare_field(field, record1["quality_dialog"], without_quality_dialog)
                    for field in rag_ablation_eval.QUALITY_DIALOG_FIELDS
                ],
            }
            rag_ablation_eval._append_checkpoint(batch_dir, checkpoint_entry)

            with patch.object(rag_ablation_eval, "BATCH_RUNS_DIR", batches_root):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    rag_ablation_eval.print_status(dir_name)

            output = buffer.getvalue()
            self.assertIn("1/2 records scored (50.0%)", output)
            self.assertIn("MAE", output)
            # Every score was 3 (with-RAG) vs 2 (without-RAG) -> |delta| == 1.0 for every dimension.
            self.assertIn("1.000", output)

    def test_print_status_reads_final_results_once_completed(self) -> None:
        record1 = self._make_record("t1")

        with tempfile.TemporaryDirectory() as tmp:
            batches_root = Path(tmp)
            dir_name = "fake_batch"
            batch_dir = batches_root / dir_name
            self._write_batch(batch_dir, [record1])
            # No checkpoint left -- a completed run cleans it up, per run_ablation.
            (batch_dir / "rag_ablation_results.json").write_text(
                json.dumps({"records": [{"thread_id": "t1", "graph_name": "agentic", "case_performance": [], "quality_dialog": []}]})
            )

            with patch.object(rag_ablation_eval, "BATCH_RUNS_DIR", batches_root):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    rag_ablation_eval.print_status(dir_name)

            self.assertIn("already completed -- 1/1 records", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
