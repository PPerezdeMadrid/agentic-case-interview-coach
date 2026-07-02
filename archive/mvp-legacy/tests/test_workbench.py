from __future__ import annotations

import unittest

import workbench_service
from workbench_service import build_scenario_preview, run_scenario


class _FakeLLM:
    def __init__(self) -> None:
        self.temperature = 0.14
        self.model = "fake-local-model"
        self.model_name = "fake-local-model"
        self._judge_round = 0


class _FakeAgenticModule:
    def __init__(self) -> None:
        self.llm_server = _FakeLLM()

    @staticmethod
    def build_initial_interview_state(scenario_ref=None, seed=None):  # noqa: ANN001
        return {
            "scenario_ref": scenario_ref,
            "seed": seed,
            "transcript": [],
            "candidate_transcript": [],
            "turn_index": 0,
            "judge_round": 0,
            "last_judge_turn_index": 0,
            "latest_question": "",
            "latest_answer": "",
            "latest_feedback": "",
            "interviewer_decision": "ask_candidate",
            "interviewer_action": "question",
            "judge_decision": "continue",
            "focus_area": "",
            "interviewer_guidance": "",
            "enough_evidence": False,
            "judge_reason": "",
            "final_score": 0,
        }

    @staticmethod
    def interviewer_node(state):  # noqa: ANN001
        if state.get("turn_index", 0) == 0:
            content = "How would you break down the profit decline?"
            return {
                "latest_question": content,
                "interviewer_decision": "ask_candidate",
                "interviewer_action": "question",
                "transcript": state["transcript"] + [f"Interviewer: {content}"],
                "candidate_transcript": state["candidate_transcript"] + [f"Interviewer: {content}"],
            }
        return {
            "latest_question": "What would you recommend to the CEO?",
            "interviewer_decision": "judge",
            "interviewer_action": "question",
            "transcript": state["transcript"] + ["Interviewer: What would you recommend to the CEO?"],
            "candidate_transcript": state["candidate_transcript"] + ["Interviewer: What would you recommend to the CEO?"],
        }

    @staticmethod
    def candidate_node(state):  # noqa: ANN001
        answer = (
            "I would split the problem by business unit and ask for margin trends."
            if state.get("turn_index", 0) == 0
            else "I would protect wind, fix or exit retail, and review battery storage independently."
        )
        return {
            "turn_index": state.get("turn_index", 0) + 1,
            "latest_answer": answer,
            "transcript": state["transcript"] + [f"Candidate: {answer}"],
            "candidate_transcript": state["candidate_transcript"] + [f"Candidate: {answer}"],
        }

    @staticmethod
    def judge_node(state):  # noqa: ANN001
        return {
            "judge_round": state.get("judge_round", 0) + 1,
            "last_judge_turn_index": state.get("turn_index", 0),
            "latest_feedback": "Clear recommendation overall. Score 4/5.",
            "judge_decision": "score",
            "focus_area": "none",
            "interviewer_guidance": "",
            "enough_evidence": True,
            "judge_reason": "Enough evidence.",
            "final_score": 4,
            "transcript": state["transcript"] + ["Judge: Clear recommendation overall. Score 4/5."],
        }

    @staticmethod
    def route_after_interviewer(state):  # noqa: ANN001
        return "judge" if state.get("interviewer_decision") == "judge" else "candidate"

    @staticmethod
    def route_after_judge(state):  # noqa: ANN001
        return "end" if state.get("judge_decision") == "score" else "interviewer"


class WorkbenchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_agentic = workbench_service._AGENTIC_MVP
        workbench_service._AGENTIC_MVP = _FakeAgenticModule()

    def tearDown(self) -> None:
        workbench_service._AGENTIC_MVP = self.original_agentic

    def test_preview_contains_grade_metadata(self) -> None:
        preview = build_scenario_preview("scenario_01", "scenario_01_01")
        self.assertEqual(preview["scenario_group"], "scenario_01")
        self.assertEqual(preview["scenario_key"], "scenario_01_01")
        self.assertIsInstance(preview["expected_overall"], int)
        self.assertGreaterEqual(preview["expected_overall"], 1)
        self.assertLessEqual(preview["expected_overall"], 4)
        self.assertTrue(preview["expected_scores"]["rubric"])

    def test_run_contains_trace_and_snapshot(self) -> None:
        result = run_scenario("scenario_01", "scenario_01_01", seed=7)
        self.assertEqual(result["scenario_snapshot"]["scenario_key"], "scenario_01_01")
        self.assertGreaterEqual(len(result["node_trace"]), 4)
        self.assertEqual(result["node_trace"][0]["node_name"], "interviewer")
        self.assertIn("alignment", result["comparison_result"])


if __name__ == "__main__":
    unittest.main()
