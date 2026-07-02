import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


STUDIO_DIR = Path(__file__).resolve().parents[1]
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

try:
    import agentic
    import persistence
except ModuleNotFoundError as exc:
    raise unittest.SkipTest(f"Studio test dependencies are not installed: {exc.name}") from exc


def make_runtime_case() -> dict:
    prompt_block = {
        "block_id": "prompt_1",
        "title": "Prompt",
        "content": "Our profits are down. What would you look at first?",
        "block_type": "prompt",
        "visible_to_candidate": True,
    }
    reveal_block = {
        "block_id": "data_1",
        "title": "Revenue trend",
        "content": "Revenue is flat year over year.",
        "block_type": "data",
        "visible_to_candidate": True,
    }
    hidden_guidance = {
        "block_id": "guide_1",
        "title": "Guidance",
        "content": "Push the candidate to separate revenue from cost drivers.",
        "block_type": "guidance",
        "visible_to_candidate": False,
    }
    final_recommendation = {
        "block_id": "rec_1",
        "title": "Recommendation",
        "content": "Recommend a cost-focused turnaround with store-level diagnostics.",
        "block_type": "final_recommendation",
        "visible_to_candidate": False,
    }
    blocks = [prompt_block, reveal_block, hidden_guidance, final_recommendation]
    return {
        "opening_block": prompt_block,
        "visible_blocks": [prompt_block, reveal_block],
        "hidden_blocks": [hidden_guidance, final_recommendation],
        "case_content": blocks,
        "blocks_by_type": {
            "prompt": [prompt_block],
            "guidance": [hidden_guidance],
            "data": [reveal_block],
            "final_recommendation": [final_recommendation],
        },
        "knowledge_sources": [],
        "profitability_knowledge_sources": [],
        "source_path": "tests/runtime_case.json",
    }


def make_runtime_bundle() -> dict:
    case_data = make_runtime_case()
    return {
        "scenario": {
            "scenario_id": "scenario_test",
            "case_id": "case_test",
            "candidate_profile": {
                "persona_instruction": {
                    "role": "Candidate",
                    "behaviour_description": "Structured but concise.",
                    "behavioural_rules": ["Answer directly."],
                    "case_specific_facts": ["The company is a retailer."],
                    "solution_roadmap": ["Clarify objective", "Split revenue and costs"],
                    "math_guidance": ["Show assumptions clearly."],
                },
                "expected_scores": {},
            },
            "source_path": "tests/scenario_test.json",
        },
        "case": case_data,
        "rubric": {
            "dimensions": [
                {
                    "dimension_id": "case_structure",
                    "description": "How well the candidate structures the case.",
                    "criteria": {"1": "Weak", "4": "Strong"},
                }
            ]
        },
    }


def make_state() -> dict:
    bundle = make_runtime_bundle()
    return {
        "scenario_ref": "scenario_test",
        "case_prompt": bundle["case"]["opening_block"]["content"],
        "candidate_profile": bundle["scenario"]["candidate_profile"],
        "turn_index": 0,
        "transcript": [],
        "case_guidance": agentic.extract_case_guidance(bundle["case"]),
        "case_data": bundle["case"],
        "enough_evidence": False,
        "focus_areas": [],
        "case_recommendation": agentic.extract_case_recommendation(bundle["case"]),
        "case_performance": {},
        "quality_dialog": {},
        "data_gathered": [],
        "thread_id": "thread_test",
        "rubric_data": bundle["rubric"],
        "judge_round": 0,
        "profitability_knowledge_base": {},
        "retrieved_profitability_context": [],
    }


class AgenticGraphTests(unittest.TestCase):
    def test_build_initial_interview_state_populates_runtime_fields(self) -> None:
        bundle = make_runtime_bundle()

        with patch.object(agentic, "load_selected_simulation_bundle", return_value=bundle):
            state = agentic.build_initial_interview_state(scenario_ref="scenario_test", seed=7)

        self.assertEqual(state["scenario_ref"], "scenario_test")
        self.assertEqual(state["case_prompt"], bundle["case"]["opening_block"]["content"])
        self.assertEqual(state["turn_index"], 0)
        self.assertEqual(state["transcript"], [])
        self.assertEqual(state["judge_round"], 0)
        self.assertIn("case_structure", agentic.format_rubric(state["rubric_data"]))

    def test_interviewer_first_turn_uses_case_prompt_without_llm(self) -> None:
        state = make_state()

        with patch.object(agentic.llm_server, "invoke") as invoke:
            update = agentic.interviewer_node(state)

        invoke.assert_not_called()
        self.assertEqual(update["turn_index"], 1)
        self.assertFalse(update["enough_evidence"])
        self.assertEqual(
            update["transcript"],
            ["Interviewer: Our profits are down. What would you look at first?"],
        )

    def test_candidate_node_ignores_hidden_transcript_and_falls_back_to_plain_text(self) -> None:
        state = make_state()
        state["transcript"] = [
            "Interviewer: Start with the objective.",
            "Interviewer reveal: Revenue is flat year over year.",
            "Judge: internal note that should stay hidden.",
        ]

        observed_prompt = {}

        def fake_invoke(messages):
            observed_prompt["content"] = messages[0].content
            return SimpleNamespace(content="<think>scratchpad</think>I'd split revenue and costs first.")

        with patch.object(agentic.llm_server, "invoke", side_effect=fake_invoke):
            update = agentic.candidate_node(state)

        self.assertIn("Interviewer: Start with the objective.", observed_prompt["content"])
        self.assertIn("Interviewer reveal: Revenue is flat year over year.", observed_prompt["content"])
        self.assertNotIn("Judge: internal note", observed_prompt["content"])
        self.assertEqual(
            update["transcript"][-1],
            "Candidate: I'd split revenue and costs first.",
        )
        self.assertEqual(update["data_gathered"], [])

    def test_judge_forces_evaluation_when_max_rounds_is_reached(self) -> None:
        state = make_state()
        state["judge_round"] = agentic.MAX_JUDGE_ROUNDS - 1
        state["focus_areas"] = ["structure"]

        with patch.object(
            agentic.llm_server,
            "invoke",
            return_value=SimpleNamespace(
                content=json.dumps(
                    {
                        "enough_evidence": False,
                        "focus_areas": ["structure", "communication"],
                    }
                )
            ),
        ):
            update = agentic.judge_node(state)

        self.assertEqual(update["judge_round"], agentic.MAX_JUDGE_ROUNDS)
        self.assertTrue(update["enough_evidence"])
        self.assertIsNone(update["focus_areas"])

    def test_graph_runs_end_to_end_and_persists_feedback(self) -> None:
        state = make_state()
        llm_responses = [
            SimpleNamespace(
                content=json.dumps(
                    {
                        "answer": "I would split the problem into revenue and costs.",
                        "data_gathered": ["Revenue is flat year over year."],
                    }
                )
            ),
            SimpleNamespace(
                content=json.dumps(
                    {
                        "action": "reveal",
                        "content": "placeholder",
                        "block_id": "data_1",
                        "ready_for_judge": True,
                    }
                )
            ),
            SimpleNamespace(
                content=json.dumps(
                    {
                        "enough_evidence": True,
                        "focus_areas": [],
                    }
                )
            ),
            SimpleNamespace(
                content=json.dumps(
                    {
                        field: {"score": 3, "rationale": "Reasonable evidence."}
                        for field in agentic.CASE_PERFORMANCE_FIELDS
                    }
                )
            ),
            SimpleNamespace(
                content=json.dumps(
                    {
                        field: {"score": 4, "rationale": "Clear and grounded."}
                        for field in agentic.QUALITY_DIALOG_FIELDS
                    }
                )
            ),
            SimpleNamespace(content="Clear structure. Push harder on cost drill-downs next time."),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir)
            db_path = artifacts_dir / "runs.sqlite"

            with patch.object(agentic.llm_server, "invoke", side_effect=llm_responses):
                with patch.object(persistence, "ARTIFACTS_DIR", artifacts_dir):
                    with patch.object(persistence, "RUNS_DB_PATH", db_path):
                        result = agentic.graph.invoke(
                            state,
                            config=agentic.build_graph_config("thread_integration"),
                        )

            self.assertIn(
                "Interviewer reveal: Revenue is flat year over year.",
                result["transcript"],
            )
            self.assertEqual(result["data_gathered"], ["Revenue is flat year over year."])
            self.assertIn(
                "Give Feedback: Clear structure. Push harder on cost drill-downs next time.",
                result["transcript"],
            )
            self.assertEqual(
                result["retrieved_profitability_context"],
                [],
            )

            with sqlite3.connect(db_path) as connection:
                row = connection.execute(
                    "SELECT thread_id, final_feedback, transcript_json FROM runs"
                ).fetchone()

            self.assertIsNotNone(row)
            self.assertEqual(row[0], "thread_test")
            self.assertEqual(
                row[1],
                "Clear structure. Push harder on cost drill-downs next time.",
            )
            self.assertIn("Give Feedback", row[2])


if __name__ == "__main__":
    unittest.main()
