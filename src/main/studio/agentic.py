from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

import node as node_module
from loader import load_selected_simulation_bundle
from llm_server import openai_llm_server
from persistence import make_persist_run_node, make_trace_node
from rag import case_guide_context as case_guide_context_module
from rag.case_guide_context import retrieve_case_guide_context
from rag.profitability_guide_context import (
    build_profitability_retrieval_query,
    retrieve_profitability_guide_context,
)
from state import AgenticGraphState
from utils import (
    extract_case_guidance,
    extract_case_recommendation,
    format_rubric,
)


class GraphConfig(TypedDict, total=False):
    thread_id: str


def _sync_node_dependencies() -> None:
    """Keep extracted node implementations aligned with this module's public patch points."""
    node_module.llm_server = llm_server
    node_module.openai_llm_server = openai_llm_server
    node_module.load_selected_simulation_bundle = load_selected_simulation_bundle
    node_module.retrieve_case_guide_context = retrieve_case_guide_context
    node_module.retrieve_profitability_guide_context = retrieve_profitability_guide_context
    case_guide_context_module.load_selected_simulation_bundle = load_selected_simulation_bundle


def build_initial_interview_state(
    case_name: str | None = None,
    seed: int | None = None,
    scenario_ref: str | None = None,
) -> AgenticGraphState:
    _sync_node_dependencies()
    return node_module.build_initial_interview_state(
        case_name=case_name,
        seed=seed,
        scenario_ref=scenario_ref,
    )


def load_scenario_node(
    state: AgenticGraphState,
    config=None,
) -> AgenticGraphState:
    _sync_node_dependencies()
    return node_module.load_scenario_node(state, config)


def interviewer_node(state: AgenticGraphState) -> AgenticGraphState:
    _sync_node_dependencies()
    return node_module.interviewer_node(state)


def candidate_node(state: AgenticGraphState) -> AgenticGraphState:
    _sync_node_dependencies()
    return node_module.candidate_node(state)


def judge_node(state: AgenticGraphState) -> AgenticGraphState:
    _sync_node_dependencies()
    return node_module.judge_node(state)


def eval_case_performance_node(state: AgenticGraphState) -> AgenticGraphState:
    _sync_node_dependencies()
    return node_module.eval_case_performance_node(state)


def eval_dialog_quality_node(state: AgenticGraphState) -> AgenticGraphState:
    _sync_node_dependencies()
    return node_module.eval_dialog_quality_node(state)


def give_feedback_node(state: AgenticGraphState) -> AgenticGraphState:
    _sync_node_dependencies()
    return node_module.give_feedback_node(state)


def get_case_guide_context(
    state: AgenticGraphState, node_name: str, *, top_k: int = 4
) -> tuple[list[str], dict]:
    _sync_node_dependencies()
    return node_module.get_case_guide_context(state, node_name, top_k=top_k)


def resolve_case_guide_query(state: AgenticGraphState) -> str:
    _sync_node_dependencies()
    return node_module.resolve_case_guide_query(state)


def route_after_interviewer(state: AgenticGraphState):
    return node_module.route_after_interviewer(state)


def route_after_judge_agentic_02(state: AgenticGraphState):
    return node_module.route_after_judge_agentic_02(state)


def build_graph_config(thread_id: str | None = None) -> dict:
    """Build the LangGraph config payload for a thread id."""
    return {
        "configurable": {
            "thread_id": thread_id or DEFAULT_THREAD_ID,
        }
    }


llm_server = node_module.llm_server
DEFAULT_THREAD_ID = node_module.DEFAULT_THREAD_ID
MAX_JUDGE_ROUNDS = node_module.MAX_JUDGE_ROUNDS
CASE_PERFORMANCE_FIELDS = node_module.CASE_PERFORMANCE_FIELDS
QUALITY_DIALOG_FIELDS = node_module.QUALITY_DIALOG_FIELDS
format_focus_areas_for_prompt = node_module.format_focus_areas_for_prompt
get_candidate_visible_transcript = node_module.get_candidate_visible_transcript


_sync_node_dependencies()

builder = StateGraph(AgenticGraphState, config_schema=GraphConfig)
builder.add_node("load_scenario", load_scenario_node)
builder.add_node("interviewer", make_trace_node("agentic", "interviewer", "interviewer", interviewer_node))
builder.add_node("candidate", candidate_node)
builder.add_node("judge", make_trace_node("agentic", "judge", "judge", judge_node))
builder.add_node("eval_case_performance", eval_case_performance_node)
builder.add_node("eval_dialog_quality", eval_dialog_quality_node)
builder.add_node("give_feedback", give_feedback_node)
builder.add_node("persist_run", make_persist_run_node("agentic"))

builder.add_edge(START, "load_scenario")
builder.add_edge("load_scenario", "interviewer")
builder.add_conditional_edges(
    "interviewer",
    route_after_interviewer,
    {
        "candidate": "candidate",
        "judge": "judge",
    },
)
builder.add_edge("candidate", "interviewer")
builder.add_conditional_edges(
    "judge",
    route_after_judge_agentic_02,
    {
        "interviewer": "interviewer",
        "eval_case_performance": "eval_case_performance",
        "eval_dialog_quality": "eval_dialog_quality",
    },
)
builder.add_edge(["eval_case_performance", "eval_dialog_quality"], "give_feedback")
builder.add_edge("give_feedback", "persist_run")
builder.add_edge("persist_run", END)

graph = builder.compile()
