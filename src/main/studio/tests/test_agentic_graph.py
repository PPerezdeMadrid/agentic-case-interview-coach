import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


STUDIO_DIR = Path(__file__).resolve().parents[1]
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

try:
    import agentic
    import baseline
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
    def test_initial_state(self) -> None:
        # Checks that the initial graph state is populated from the runtime bundle.
        bundle = make_runtime_bundle()

        with patch.object(agentic, "load_selected_simulation_bundle", return_value=bundle):
            state = agentic.build_initial_interview_state(scenario_ref="scenario_test", seed=7)

        self.assertEqual(state["scenario_ref"], "scenario_test")
        self.assertEqual(state["case_prompt"], bundle["case"]["opening_block"]["content"])
        self.assertEqual(state["turn_index"], 0)
        self.assertEqual(state["transcript"], [])
        self.assertEqual(state["judge_round"], 0)
        self.assertIn("case_structure", agentic.format_rubric(state["rubric_data"]))

    def test_interviewer_first_turn(self) -> None:
        # Checks that the first interviewer turn uses the case prompt without calling the LLM.
        state = make_state()
        mock_llm = Mock()

        with patch.object(agentic, "llm_server", mock_llm):
            update = agentic.interviewer_node(state)

        mock_llm.invoke.assert_not_called()
        self.assertEqual(update["turn_index"], 1)
        self.assertFalse(update["enough_evidence"])
        self.assertEqual(
            update["transcript"],
            ["Interviewer: Our profits are down. What would you look at first?"],
        )

    def test_candidate_visible_transcript(self) -> None:
        # Checks that the candidate only sees public transcript lines and supports plain-text fallback.
        state = make_state()
        mock_llm = Mock()
        state["transcript"] = [
            "Interviewer: Start with the objective.",
            "Interviewer reveal: Revenue is flat year over year.",
            "Judge: internal note that should stay hidden.",
        ]

        observed_prompt = {}

        def fake_invoke(messages):
            observed_prompt["content"] = messages[0].content
            return SimpleNamespace(content="<think>scratchpad</think>I'd split revenue and costs first.")

        mock_llm.invoke.side_effect = fake_invoke
        with patch.object(agentic, "llm_server", mock_llm):
            update = agentic.candidate_node(state)

        self.assertIn("Interviewer: Start with the objective.", observed_prompt["content"])
        self.assertIn("Interviewer reveal: Revenue is flat year over year.", observed_prompt["content"])
        self.assertNotIn("Judge: internal note", observed_prompt["content"])
        self.assertEqual(
            update["transcript"][-1],
            "Candidate: I'd split revenue and costs first.",
        )
        self.assertEqual(update["data_gathered"], [])

    def test_interviewer_focus_areas(self) -> None:
        # Checks that judge focus areas are injected into the interviewer prompt as direct instructions.
        state = make_state()
        mock_llm = Mock()
        state["turn_index"] = 1
        state["transcript"] = ["Interviewer: Our profits are down. What would you look at first?"]
        state["focus_areas"] = [
            "test whether the candidate can break profit into revenue and cost drivers",
            "push for a sharper recommendation with risks and next steps",
        ]

        observed_prompt = {}

        def fake_invoke(messages):
            observed_prompt["content"] = messages[0].content
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "action": "question",
                        "content": "How would you prioritise between revenue and cost drivers first?",
                        "block_id": "",
                        "ready_for_judge": False,
                    }
                )
            )

        mock_llm.invoke.side_effect = fake_invoke
        with patch.object(agentic, "llm_server", mock_llm):
            update = agentic.interviewer_node(state)

        self.assertIn("Current judge focus areas to act on directly:", observed_prompt["content"])
        self.assertIn("- test whether the candidate can break profit into revenue and cost drivers", observed_prompt["content"])
        self.assertIn("- push for a sharper recommendation with risks and next steps", observed_prompt["content"])
        self.assertEqual(
            update["transcript"][-1],
            "Interviewer: How would you prioritise between revenue and cost drivers first?",
        )

    def test_judge_max_rounds(self) -> None:
        # Checks that the judge forces evaluation after the maximum number of rounds.
        state = make_state()
        mock_llm = Mock()
        state["judge_round"] = agentic.MAX_JUDGE_ROUNDS - 1
        state["focus_areas"] = ["structure"]

        with patch.object(
            agentic,
            "retrieve_case_guide_context",
            return_value=[{"content": "Start with a clean issue tree."}],
        ):
            mock_llm.invoke.return_value = SimpleNamespace(
                content=json.dumps(
                    {
                        "enough_evidence": False,
                        "focus_areas": ["structure", "communication"],
                    }
                )
            )
            with patch.object(agentic, "llm_server", mock_llm):
                update = agentic.judge_node(state)

        self.assertEqual(update["judge_round"], agentic.MAX_JUDGE_ROUNDS)
        self.assertTrue(update["enough_evidence"])
        self.assertIsNone(update["focus_areas"])

    def test_case_guide_context_without_prompt(self) -> None:
        # Checks that case-guide retrieval can rebuild the query when case_prompt is missing.
        state = {"scenario_ref": "scenario_test"}

        with patch.object(agentic, "load_selected_simulation_bundle", return_value=make_runtime_bundle()):
            with patch.object(
                agentic,
                "retrieve_case_guide_context",
                return_value=[{"content": "Clarify the objective first."}],
            ) as retrieve:
                context = agentic.get_case_guide_context(state, "judge")

        retrieve.assert_called_once()
        retrieval_query = retrieve.call_args.args[0]
        self.assertIn("Case prompt: Our profits are down. What would you look at first?", retrieval_query)
        self.assertIn("Current goal: Decide what evidence is still missing before evaluating the candidate.", retrieval_query)
        self.assertEqual(context, ["Clarify the objective first."])

    def test_profitability_query_includes_source_navigation_guide(self) -> None:
        retrieval_query = agentic.build_profitability_retrieval_query(
            "Profits are down in one region. Should we close stores or renegotiate labor costs?",
            [
                "Candidate: I would split the issue into revenue, fixed costs, and variable costs.",
                "Candidate: Then I would compare segment margin by store and region.",
            ],
            evaluation_target="case_performance",
            focus_areas=["test whether the candidate isolates the loss-making segment"],
        )

        self.assertIn("Source coverage:", retrieval_query)
        self.assertIn("cost-volume-profit analysis", retrieval_query)
        self.assertIn("segmented income reporting", retrieval_query)
        self.assertIn("variance analysis", retrieval_query)
        self.assertIn("Write the retrieval intent for this exact situation", retrieval_query)

    def test_graph_end_to_end(self) -> None:
        # Checks the full graph run, including final feedback and SQLite persistence.
        state = make_state()
        mock_llm = Mock()
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

            with patch.object(
                agentic,
                "retrieve_case_guide_context",
                return_value=[],
            ):
                mock_llm.invoke.side_effect = llm_responses
                with patch.object(agentic, "llm_server", mock_llm):
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
                trace_rows = connection.execute(
                    """
                    SELECT node_name, step_index, changed_fields_json
                    FROM agent_state_traces
                    ORDER BY step_index
                    """
                ).fetchall()

            self.assertIsNotNone(row)
            self.assertEqual(row[0], "thread_test")
            self.assertEqual(
                row[1],
                "Clear structure. Push harder on cost drill-downs next time.",
            )
            self.assertIn("Give Feedback", row[2])
            self.assertGreaterEqual(len(trace_rows), 2)
            self.assertEqual(trace_rows[0][0], "interviewer")
            self.assertIn('"turn_index"', trace_rows[0][2])
            self.assertTrue(any(trace_row[0] == "judge" for trace_row in trace_rows))


class BaselineGraphTests(unittest.TestCase):
    def test_baseline_prompt_context(self) -> None:
        # Checks that the baseline interviewer prompt includes retrieved guide context.
        state = make_state()
        mock_llm = Mock()
        state["turn_index"] = 1
        state["transcript"] = ["Interviewer: Our profits are down. What would you look at first?"]
        state["case_guide_context"] = [
            "Start by clarifying the objective and metric.",
            "Split the problem into revenue and cost drivers.",
        ]

        observed_prompt = {}

        def fake_invoke(messages):
            observed_prompt["content"] = messages[0].content
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "action": "question",
                        "content": "What has happened to costs over time?",
                        "block_id": "",
                        "ready_for_evaluation": False,
                    }
                )
            )

        mock_llm.invoke.side_effect = fake_invoke
        with patch.object(baseline, "llm_server", mock_llm):
            update = baseline.baseline_node(state)

        self.assertIn("Consulting Case Interview Guide excerpts:", observed_prompt["content"])
        self.assertIn("Start by clarifying the objective and metric.", observed_prompt["content"])
        self.assertEqual(
            update["transcript"][-1],
            "Interviewer: What has happened to costs over time?",
        )

    def test_baseline_retrieve_context(self) -> None:
        # Checks that retrieved guide chunks are stored as baseline case_guide_context.
        state = make_state()

        with patch.object(
            baseline,
            "retrieve_case_guide_context",
            return_value=[
                {"content": "Probe the objective before branching."},
                {"content": "Check revenue versus cost drivers."},
            ],
        ):
            update = baseline.retrieve_case_guide_node(state)

        self.assertEqual(
            update["case_guide_context"],
            [
                "Probe the objective before branching.",
                "Check revenue versus cost drivers.",
            ],
        )

    def test_baseline_context_without_prompt(self) -> None:
        # Checks that baseline retrieval can rebuild the query when case_prompt is missing.
        state = {"scenario_ref": "scenario_test"}

        with patch.object(baseline, "load_selected_simulation_bundle", return_value=make_runtime_bundle()):
            with patch.object(
                baseline,
                "retrieve_case_guide_context",
                return_value=[{"content": "Split revenue from cost drivers."}],
            ) as retrieve:
                update = baseline.retrieve_case_guide_node(state)

        retrieve.assert_called_once_with(
            "Our profits are down. What would you look at first?",
            top_k=4,
        )
        self.assertEqual(update["case_guide_context"], ["Split revenue from cost drivers."])


if __name__ == "__main__":
    unittest.main()
