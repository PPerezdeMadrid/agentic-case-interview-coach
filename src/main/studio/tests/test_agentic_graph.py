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
    from rag import case_guide_context
    from rag.profitability_guide_context import PROFITABILITY_CITATION_LABEL
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
                "reference_scores": {},
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
        "retrieved_profitability_context": [],
    }


class AgenticGraphTests(unittest.TestCase):
    def test_initial_state(self) -> None:
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
        state = make_state()
        mock_llm = Mock()

        with patch.object(agentic, "interviewer_llm", mock_llm):
            update = agentic.interviewer_node(state)

        mock_llm.invoke.assert_not_called()
        self.assertEqual(update["turn_index"], 1)
        self.assertFalse(update["enough_evidence"])
        self.assertEqual(
            update["transcript"],
            ["Interviewer: Our profits are down. What would you look at first?"],
        )

    def test_candidate_visible_transcript(self) -> None:
        # Candidate sees only public transcript lines, passed as real messages (not flattened into the system prompt).
        state = make_state()
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
        state["transcript"] = [
            "Interviewer: Start with the objective.",
            "Interviewer reveal: Revenue is flat year over year.",
            "Judge: internal note that should stay hidden.",
        ]

        observed_messages = {}

        def fake_invoke(messages):
            observed_messages["messages"] = messages
            return SimpleNamespace(content="<think>scratchpad</think>I'd split revenue and costs first.")

        mock_llm.invoke.side_effect = fake_invoke
        with patch.object(agentic, "candidate_llm", mock_llm):
            update = agentic.candidate_node(state)

        messages = observed_messages["messages"]
        # Adjacent same-role messages are coalesced (some OpenRouter providers reject non-alternating roles), so system prompt + persona share messages[0].
        self.assertTrue(messages[0].content.startswith(agentic.node_module.CANDIDATE_SYSTEM_PROMPT))
        contents = [message.content for message in messages]
        self.assertTrue(any("Start with the objective." in content for content in contents))
        self.assertTrue(any("[revealed fact] Revenue is flat year over year." in content for content in contents))
        self.assertFalse(any("Judge: internal note" in content for content in contents))
        self.assertEqual(
            update["transcript"][-1],
            "Candidate: I'd split revenue and costs first.",
        )
        self.assertEqual(update["data_gathered"], [])

    def test_interviewer_focus_areas(self) -> None:
        state = make_state()
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
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
        with patch.object(agentic, "interviewer_llm", mock_llm):
            update = agentic.interviewer_node(state)

        self.assertIn("Current judge focus areas to act on directly:", observed_prompt["content"])
        self.assertIn("- test whether the candidate can break profit into revenue and cost drivers", observed_prompt["content"])
        self.assertIn("- push for a sharper recommendation with risks and next steps", observed_prompt["content"])
        self.assertIn("Question style reference derived from the SoQG dataset", observed_prompt["content"])
        self.assertIn("What exactly suggests pricing is the main issue?", observed_prompt["content"])
        self.assertEqual(
            update["transcript"][-1],
            "Interviewer: How would you prioritise between revenue and cost drivers first?",
        )

    def test_interviewer_round_budget_shrinks_with_remaining_total(self) -> None:
        # Round's turn budget shrinks with remaining total turns (Fix 6), not a fresh MAX_INTERVIEWER_TURNS_BEFORE_JUDGE each round.
        state = make_state()
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
        state["turn_index"] = 1
        state["total_turns_used"] = agentic.node_module.MAX_INTERVIEWER_TURNS_TOTAL - 2
        state["transcript"] = [
            "Interviewer: Our profits are down. What would you look at first?",
            "Candidate: I would split revenue and costs.",
            "Interviewer: Which side would you prioritize first?",
            "Candidate: I would start with revenue.",
        ]

        observed_prompt = {}

        def fake_invoke(messages):
            observed_prompt["content"] = messages[0].content
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "action": "question",
                        "content": "Before we close, what's your final recommendation?",
                        "block_id": "",
                        "ready_for_judge": True,
                    }
                )
            )

        mock_llm.invoke.side_effect = fake_invoke
        with patch.object(agentic, "interviewer_llm", mock_llm):
            update = agentic.interviewer_node(state)

        # Only 2 turns remain, so the final-turn signal must fire at turn_index 1, not wait until turn_index 9 (default budget).
        self.assertIn("final turn before judge evaluation: yes", observed_prompt["content"])
        # ready_for_judge=True from the mock is overridden to False -- the candidate hasn't answered this final ask yet.
        self.assertFalse(update["enough_evidence"])

    def test_judge_max_rounds(self) -> None:
        state = make_state()
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
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
            with patch.object(agentic, "judge_llm", mock_llm):
                update = agentic.judge_node(state)

        self.assertEqual(update["judge_round"], agentic.MAX_JUDGE_ROUNDS)
        self.assertTrue(update["enough_evidence"])
        self.assertIsNone(update["focus_areas"])

    def test_judge_resets_round_turn_index_but_accumulates_total(self) -> None:
        # Judge coaching resets the *per-round* turn_index, but total_turns_used keeps accumulating across rounds.
        state = make_state()
        state["turn_index"] = agentic.node_module.MAX_INTERVIEWER_TURNS_BEFORE_JUDGE
        state["total_turns_used"] = 0
        state["transcript"] = [
            "Interviewer: Our profits are down. What would you look at first?",
            "Candidate: I would split revenue and costs.",
            "Interviewer: Which side would you prioritize first?",
            "Candidate: I would start with revenue.",
        ]
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
        mock_llm.invoke.return_value = SimpleNamespace(
            content=json.dumps(
                {
                    "enough_evidence": False,
                    "focus_areas": ["push the candidate to quantify the revenue decline"],
                }
            )
        )

        with patch.object(agentic, "judge_llm", mock_llm):
            update = agentic.judge_node(state)

        self.assertFalse(update["enough_evidence"])
        self.assertEqual(update["turn_index"], 0)
        self.assertEqual(update["total_turns_used"], agentic.node_module.MAX_INTERVIEWER_TURNS_BEFORE_JUDGE)
        self.assertEqual(
            agentic.route_after_judge_agentic_02(update),
            "interviewer",
        )

    def test_judge_forces_evaluation_when_total_turn_budget_exhausted(self) -> None:
        # Whole-conversation turn budget (Fix 6) forces evaluation on its own, even on an early round the judge_round cap alone wouldn't catch.
        state = make_state()
        state["judge_round"] = 0
        state["turn_index"] = agentic.node_module.MAX_INTERVIEWER_TURNS_BEFORE_JUDGE
        state["total_turns_used"] = agentic.node_module.MAX_INTERVIEWER_TURNS_TOTAL - agentic.node_module.MAX_INTERVIEWER_TURNS_BEFORE_JUDGE
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
        mock_llm.invoke.return_value = SimpleNamespace(
            content=json.dumps({"enough_evidence": False, "focus_areas": ["still missing math"]})
        )

        with patch.object(agentic, "judge_llm", mock_llm):
            update = agentic.judge_node(state)

        self.assertEqual(update["total_turns_used"], agentic.node_module.MAX_INTERVIEWER_TURNS_TOTAL)
        self.assertTrue(update["enough_evidence"])
        self.assertIsNone(update["focus_areas"])
        self.assertNotIn("turn_index", update)

    def test_interviewer_retries_invalid_json_before_controlled_fallback(self) -> None:
        state = make_state()
        state["turn_index"] = 1
        state["transcript"] = ["Interviewer: Our profits are down. What would you look at first?"]
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
        mock_llm.invoke.side_effect = [
            SimpleNamespace(content="Let's analyze this step by step."),
            SimpleNamespace(
                content=json.dumps(
                    {
                        "action": "question",
                        "content": "What has changed more materially: revenue or costs?",
                        "block_id": "",
                        "ready_for_judge": False,
                    }
                )
            ),
        ]

        with patch.object(agentic, "interviewer_llm", mock_llm):
            update = agentic.interviewer_node(state)

        self.assertEqual(mock_llm.invoke.call_count, 2)
        repair_prompt = mock_llm.invoke.call_args_list[1].args[0][-1].content
        self.assertIn("previous reply was not valid", repair_prompt.lower())
        self.assertEqual(
            update["transcript"][-1],
            "Interviewer: What has changed more materially: revenue or costs?",
        )

    def test_judge_scouts_case_guide_with_its_own_prompt_and_llm(self) -> None:
        # judge_node scouts the case guide itself in one call with its own prompt/llm; the retrieval query is exactly what judge wrote, not a raw situation dump.
        state = make_state()
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
        mock_llm.invoke.side_effect = [
            SimpleNamespace(
                content=json.dumps(
                    {"case_guide_query": "What counts as sufficient evidence before evaluating a candidate?"}
                )
            ),
            SimpleNamespace(content=json.dumps({"enough_evidence": True, "focus_areas": []})),
        ]

        with patch.object(
            agentic,
            "retrieve_case_guide_context",
            return_value=[{"content": "Clarify the objective first.", "chunk_id": "guide::chunk_1"}],
        ) as retrieve:
            with patch.object(agentic, "judge_llm", mock_llm):
                update = agentic.judge_node(state)

        retrieve.assert_called_once()
        retrieval_query = retrieve.call_args.args[0]
        self.assertEqual(retrieval_query, "What counts as sufficient evidence before evaluating a candidate?")

        scouting_prompt = mock_llm.invoke.call_args_list[0].args[0][0].content
        self.assertIn("Consulting Case Interview Guide", scouting_prompt)
        self.assertIn("Case prompt:\nOur profits are down. What would you look at first?", scouting_prompt)

        main_prompt = mock_llm.invoke.call_args_list[1].args[0][0].content
        self.assertIn("Clarify the objective first.", main_prompt)

        self.assertEqual(update["rag_query_log"][0]["query"], retrieval_query)
        self.assertEqual(update["rag_query_log"][0]["chunk_ids"], ["guide::chunk_1"])
        self.assertTrue(update["llm_usage"])

    def test_judge_can_decide_it_does_not_need_the_guide(self) -> None:
        # Retrieval is genuinely conditional -- an empty case_guide_query from judge's scouting means no retrieval call at all.
        state = make_state()
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
        mock_llm.invoke.side_effect = [
            SimpleNamespace(content=json.dumps({"case_guide_query": ""})),
            SimpleNamespace(content=json.dumps({"enough_evidence": True, "focus_areas": []})),
        ]

        with patch.object(agentic, "retrieve_case_guide_context") as retrieve:
            with patch.object(agentic, "judge_llm", mock_llm):
                update = agentic.judge_node(state)

        retrieve.assert_not_called()
        self.assertEqual(update["rag_query_log"], [])

    def test_eval_case_performance_scouts_both_sources_in_one_decision(self) -> None:
        # eval_case_performance_node scouts both sources in one call with its own CASE_EVAL_SYSTEM_PROMPT, not a generic query-writer prompt.
        state = make_state()
        state["enough_evidence"] = True
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
        mock_llm.invoke.side_effect = [
            SimpleNamespace(
                content=json.dumps(
                    {
                        "case_guide_query": "",
                        "profitability_query": "How is segment margin computed for a multi-store retailer?",
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
        ]

        with patch.object(agentic, "retrieve_case_guide_context") as retrieve_case_guide, patch.object(
            agentic,
            "retrieve_profitability_guide_context",
            return_value=[{"content": "Segment margin = segment revenue minus traceable segment costs."}],
        ) as retrieve_profitability:
            with patch.object(agentic, "judge_llm", mock_llm):
                update = agentic.eval_case_performance_node(state)

        retrieve_case_guide.assert_not_called()
        retrieve_profitability.assert_called_once()
        self.assertEqual(
            retrieve_profitability.call_args.args[0],
            "How is segment margin computed for a multi-store retailer?",
        )

        scouting_prompt = mock_llm.invoke.call_args_list[0].args[0][0].content
        self.assertIn("Consulting Case Interview Guide", scouting_prompt)
        self.assertIn("cost-volume-profit analysis", scouting_prompt)
        self.assertIn("segmented income reporting", scouting_prompt)

        self.assertEqual(
            update["retrieved_profitability_context"],
            [
                f"[{PROFITABILITY_CITATION_LABEL}, p.?] "
                "Segment margin = segment revenue minus traceable segment costs."
            ],
        )
        self.assertEqual(len(update["rag_query_log"]), 1)
        self.assertEqual(update["rag_query_log"][0]["source"], "profitability_guide")

    def test_graph_end_to_end(self) -> None:
        state = make_state()
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
        # eval_case_performance/eval_dialog_quality run as parallel branches of one superstep and race each other against
        # this shared mock, so a plain ordered side_effect list would be flaky -- route by each prompt's distinguishing text instead.
        def fake_invoke(messages):
            prompt = messages[0].content if messages else ""
            combined = "\n".join(getattr(message, "content", "") for message in messages)

            if "You are a candidate in a consulting case interview" in prompt:
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "answer": "I would split the problem into revenue and costs.",
                            "data_gathered": ["Revenue is flat year over year."],
                        }
                    )
                )
            if "You are the interviewer agent" in prompt:
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "action": "reveal",
                            "content": "placeholder",
                            "block_id": "data_1",
                            "ready_for_judge": True,
                        }
                    )
                )
            if "You are the judge agent" in combined:
                if "Available support source" in combined:
                    return SimpleNamespace(
                        content=json.dumps(
                            {"case_guide_query": "What evidence is still missing before evaluating the candidate?"}
                        )
                    )
                return SimpleNamespace(content=json.dumps({"enough_evidence": True, "focus_areas": []}))
            if "You are the case-performance judge" in combined:
                if "Available support sources:" in combined:
                    return SimpleNamespace(
                        content=json.dumps(
                            {
                                "case_guide_query": "What case-structuring methodology applies here?",
                                "profitability_query": "How should segment profitability be analyzed?",
                            }
                        )
                    )
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            field: {"score": 3, "rationale": "Reasonable evidence."}
                            for field in agentic.CASE_PERFORMANCE_FIELDS
                        }
                    )
                )
            if "You are the interaction-quality judge" in combined:
                if "Available support source" in combined:
                    return SimpleNamespace(
                        content=json.dumps({"case_guide_query": "What communication criteria apply here?"})
                    )
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            field: {"score": 4, "rationale": "Clear and grounded."}
                            for field in agentic.QUALITY_DIALOG_FIELDS
                        }
                    )
                )
            if "You are writing final feedback" in combined:
                if "Available support source" in combined:
                    return SimpleNamespace(
                        content=json.dumps({"case_guide_query": "What coaching guidance applies to this feedback?"})
                    )
                return SimpleNamespace(content="Clear structure. Push harder on cost drill-downs next time.")

            raise AssertionError(f"Unexpected prompt reached the mock LLM: {prompt[:200]!r}")

        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir)
            db_path = artifacts_dir / "runs.sqlite"

            with patch.object(
                agentic,
                "retrieve_case_guide_context",
                return_value=[],
            ), patch.object(
                agentic,
                "retrieve_profitability_guide_context",
                return_value=[],
            ):
                mock_llm.invoke.side_effect = fake_invoke
                with patch.object(agentic, "candidate_llm", mock_llm), patch.object(
                    agentic, "judge_llm", mock_llm
                ), patch.object(agentic, "interviewer_llm", mock_llm), patch.object(
                    agentic, "feedback_llm", mock_llm
                ):
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
            self.assertTrue(result["rag_query_log"])
            self.assertEqual(
                {entry["node"] for entry in result["rag_query_log"]},
                {"judge", "eval_case_performance", "case_performance", "eval_dialog_quality", "give_feedback"},
            )

            with sqlite3.connect(db_path) as connection:
                row = connection.execute(
                    "SELECT thread_id, final_feedback, transcript_json, state_json FROM runs"
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
            persisted_state = json.loads(row[3])
            self.assertTrue(persisted_state["rag_query_log"])
            self.assertGreaterEqual(len(trace_rows), 2)
            self.assertEqual(trace_rows[0][0], "interviewer")
            self.assertIn('"turn_index"', trace_rows[0][2])
            self.assertTrue(any(trace_row[0] == "judge" for trace_row in trace_rows))


class BaselineGraphTests(unittest.TestCase):
    def test_baseline_prompt_context(self) -> None:
        state = make_state()
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
        state["turn_index"] = 1
        state["transcript"] = ["Interviewer: Our profits are down. What would you look at first?"]

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
        with patch.object(
            baseline,
            "get_pending_case_guide_context",
            return_value=(
                [
                    "Start by clarifying the objective and metric.",
                    "Split the problem into revenue and cost drivers.",
                ],
                {},
            ),
        ), patch.object(
            baseline,
            "retrieve_profitability_guide_context",
            return_value=[],
        ), patch.object(baseline, "baseline_llm", mock_llm):
            update = baseline.baseline_node(state)

        self.assertIn(f"Excerpts from the {baseline.CASE_GUIDE_CITATION_LABEL}:", observed_prompt["content"])
        self.assertIn("Start by clarifying the objective and metric.", observed_prompt["content"])
        self.assertEqual(
            update["transcript"][-1],
            "Interviewer: What has happened to costs over time?",
        )

    def test_baseline_retrieves_context_inline(self) -> None:
        state = make_state()
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
        state["turn_index"] = 1
        state["transcript"] = ["Interviewer: Our profits are down. What would you look at first?"]

        mock_llm.invoke.return_value = SimpleNamespace(
            content=json.dumps(
                {
                    "action": "question",
                    "content": "What has changed in revenue versus costs?",
                    "block_id": "",
                    "ready_for_evaluation": False,
                }
            )
        )
        with patch.object(
            baseline,
            "get_pending_case_guide_context",
            return_value=(
                [
                    "Probe the objective before branching.",
                    "Check revenue versus cost drivers.",
                ],
                {},
            ),
        ) as get_context, patch.object(
            baseline,
            "retrieve_profitability_guide_context",
            return_value=[],
        ), patch.object(baseline, "baseline_llm", mock_llm):
            update = baseline.baseline_node(state)

        get_context.assert_called_once_with(state)
        self.assertEqual(
            update["transcript"][-1],
            "Interviewer: What has changed in revenue versus costs?",
        )

    def test_pending_case_guide_context_empty_without_pending_query(self) -> None:
        # Baseline has no separate scouting call, so a turn with nothing queued in pending_case_guide_query must not hit retrieval at all.
        state = {"scenario_ref": "scenario_test"}

        with patch.object(case_guide_context, "retrieve_case_guide_context") as retrieve:
            context, log_entry = case_guide_context.get_pending_case_guide_context(state)

        retrieve.assert_not_called()
        self.assertEqual(context, [])
        self.assertEqual(log_entry, {})

    def test_pending_case_guide_context_retrieves_queued_query(self) -> None:
        # Query queued by the *previous* turn's pending_case_guide_query is what gets retrieved now.
        state = {"pending_case_guide_query": "How should I structure a profitability drop case?"}

        with patch.object(
            case_guide_context,
            "retrieve_case_guide_context",
            return_value=[{"content": "Split revenue from cost drivers.", "chunk_id": "guide::chunk_9"}],
        ) as retrieve:
            context, log_entry = case_guide_context.get_pending_case_guide_context(state)

        retrieve.assert_called_once_with(
            "How should I structure a profitability drop case?",
            top_k=4,
        )
        self.assertEqual(
            context,
            [f"[{case_guide_context.CASE_GUIDE_CITATION_LABEL}, p.?] Split revenue from cost drivers."],
        )
        self.assertEqual(log_entry["chunk_ids"], ["guide::chunk_9"])


if __name__ == "__main__":
    unittest.main()
