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
        # Checks that the candidate sees only public transcript lines, replayed as
        # real conversation turns (not flattened into the system prompt), and
        # supports plain-text fallback.
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
        self.assertEqual(messages[0].content, agentic.node_module.CANDIDATE_SYSTEM_PROMPT)
        contents = [message.content for message in messages]
        self.assertIn("Start with the objective.", contents)
        self.assertIn("[revealed fact] Revenue is flat year over year.", contents)
        self.assertFalse(any("Judge: internal note" in content for content in contents))
        self.assertEqual(
            update["transcript"][-1],
            "Candidate: I'd split revenue and costs first.",
        )
        self.assertEqual(update["data_gathered"], [])

    def test_interviewer_focus_areas(self) -> None:
        # Checks that judge focus areas are injected into the interviewer prompt as direct instructions.
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

    def test_judge_max_rounds(self) -> None:
        # Checks that the judge forces evaluation after the maximum number of rounds.
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

    def test_judge_resets_turn_budget_when_more_evidence_is_needed(self) -> None:
        # Checks that judge coaching reopens the interviewer->candidate loop.
        state = make_state()
        state["turn_index"] = agentic.node_module.MAX_INTERVIEWER_TURNS_BEFORE_JUDGE
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
        self.assertEqual(
            agentic.route_after_judge_agentic_02(update),
            "interviewer",
        )

    def test_interviewer_retries_invalid_json_before_controlled_fallback(self) -> None:
        # Checks that the interviewer retries JSON repair instead of immediately using a generic fallback.
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
        # Checks that judge_node itself decides -- with its own prompt/persona and its
        # own judge_llm, in a single node -- whether it needs an excerpt from the case
        # guide, rather than routing through a separate/generic RAG-query node. A
        # non-empty decision should drive retrieval; the query used should be exactly
        # what judge wrote, not a raw situation dump.
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
        # Checks that retrieval is genuinely conditional: when judge's own scouting
        # decision leaves case_guide_query empty, no retrieval call is made at all.
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
        # Checks that eval_case_performance_node -- in its own single scouting call,
        # with its own CASE_EVAL_SYSTEM_PROMPT -- decides what (if anything) it needs
        # from each of the two sources it has access to, grounded in a short
        # description of each source rather than a generic query-writer prompt.
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
        # Checks the full graph run, including final feedback and SQLite persistence.
        state = make_state()
        mock_llm = Mock()
        mock_llm.bind.return_value = mock_llm
        # Every role (candidate/judge/interviewer/feedback) is patched to the same mock_llm
        # below. `eval_case_performance` and `eval_dialog_quality` run as parallel branches
        # of the same graph superstep (see route_after_judge_agentic_02, which fans out to
        # both), so their calls to this shared mock race each other. A plain ordered
        # `side_effect` list is not safe under that race: whichever branch's thread happens
        # to call first "steals" the next list item meant for the other branch, making the
        # test flaky. Routing by the distinguishing text of each prompt instead makes the
        # response independent of call order/thread interleaving.
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
            if "You are evaluating consulting case performance" in combined:
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
            if "You are evaluating interview interaction quality" in combined:
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
        # Checks that the baseline interviewer prompt includes retrieved guide context.
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
            "get_baseline_case_guide_context",
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
        # Checks that the baseline interviewer retrieves guide snippets directly during prompt construction.
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
            "get_baseline_case_guide_context",
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

    def test_baseline_context_without_prompt(self) -> None:
        # Checks that the shared baseline guide helper can rebuild the query when case_prompt is missing.
        state = {"scenario_ref": "scenario_test"}

        with patch.object(
            case_guide_context,
            "load_selected_simulation_bundle",
            return_value=make_runtime_bundle(),
        ):
            with patch.object(
                case_guide_context,
                "retrieve_case_guide_context",
                return_value=[{"content": "Split revenue from cost drivers.", "chunk_id": "guide::chunk_9"}],
            ) as retrieve:
                context, log_entry = baseline.get_baseline_case_guide_context(state)

        retrieve.assert_called_once_with(
            "Our profits are down. What would you look at first?",
            top_k=4,
        )
        self.assertEqual(
            context,
            [f"[{case_guide_context.CASE_GUIDE_CITATION_LABEL}, p.?] Split revenue from cost drivers."],
        )
        self.assertEqual(log_entry["chunk_ids"], ["guide::chunk_9"])


if __name__ == "__main__":
    unittest.main()
