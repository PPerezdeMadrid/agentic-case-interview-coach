from __future__ import annotations

from loader import load_selected_simulation_bundle
from rag.rag_case_guide import retrieve_case_guide_context as _retrieve_case_guide_context
from state import AgenticGraphState
from utils import extract_case_prompt, normalize_string_list

DEFAULT_TOP_K = 4


def format_case_guide_snippets(case_guide_context: list[str]) -> str:
    """Format retrieved guide snippets for prompt injection"""
    if not case_guide_context:
        return "None."
    return "\n".join(f"- {snippet}" for snippet in case_guide_context)


def resolve_case_guide_query(state: AgenticGraphState) -> str:
    """Resolve the base case-guide query from the current scenario"""
    case_prompt = str(state.get("case_prompt", "")).strip()
    if case_prompt:
        return case_prompt

    bundle = load_selected_simulation_bundle(scenario_ref=state.get("scenario_ref"))
    return str(extract_case_prompt(bundle["case"])).strip()


def build_case_guide_query(state: AgenticGraphState, case_prompt: str, node_name: str) -> str:
    """Build a simple natural-language retrieval query for the consulting guide"""
    transcript = state.get("transcript", [])
    latest_candidate_turn = next(
        (
            line.removeprefix("Candidate: ").strip()
            for line in reversed(transcript)
            if line.startswith("Candidate:")
        ),
        "",
    )
    focus_areas = normalize_string_list(state.get("focus_areas", []))

    # each node will ask for sth different
    node_goal_by_name = {
        "judge": "Decide what evidence is still missing before evaluating the candidate.",
        "eval_case_performance": "Evaluate the quality of the candidate's case-solving approach.",
        "eval_dialog_quality": "Evaluate the quality of the candidate's communication and interaction.",
        "give_feedback": "Generate actionable coaching feedback for the candidate.",
    }
    node_goal = node_goal_by_name.get(node_name, "Retrieve the most useful consulting-case methodology.")

    return "\n".join(
        part
        for part in [
            f"Case prompt: {case_prompt}" if case_prompt else "",
            f"Current goal: {node_goal}",
            (
                "Judge focus areas or coaching targets: "
                + "; ".join(focus_areas)
                if focus_areas
                else ""
            ),
            f"Latest candidate reasoning: {latest_candidate_turn}" if latest_candidate_turn else "",
            (
                "Retrieve methodology, evaluation criteria, common mistakes, and examples of strong candidate behaviour "
                "that are most relevant to this exact situation."
            ),
        ]
        if part
    )


def retrieve_case_guide_context(query: str, *, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """Bridge from graph modules into the guide PDF retriever"""
    return _retrieve_case_guide_context(query, top_k=top_k)


def get_case_guide_context(
    state: AgenticGraphState,
    node_name: str,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> list[str]:
    """Retrieve guide snippets tailored to a specific graph node"""
    case_prompt = resolve_case_guide_query(state)
    query = build_case_guide_query(state, case_prompt, node_name)
    if not query.strip():
        return []

    case_guide_chunks = retrieve_case_guide_context(query, top_k=top_k)
    return [
        str(chunk.get("content", "")).strip()
        for chunk in case_guide_chunks
        if str(chunk.get("content", "")).strip()
    ]


def get_baseline_case_guide_context(
    state: AgenticGraphState,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> tuple[list[str], dict]:
    """Retrieve guide snippets for the baseline graph with a simple prompt query.

    Returns (snippets, rag_query_log_entry) so callers can persist the retrieval
    query and retrieved chunk ids alongside the rest of the graph state.
    """
    query = resolve_case_guide_query(state) or "consulting case interview methodology"
    case_guide_chunks = retrieve_case_guide_context(query, top_k=top_k)
    snippets = [
        str(chunk.get("content", "")).strip()
        for chunk in case_guide_chunks
        if str(chunk.get("content", "")).strip()
    ]
    log_entry = {
        "node": "baseline",
        "source": "case_guide",
        "query": query,
        "top_k": top_k,
        "chunk_ids": [chunk.get("chunk_id") for chunk in case_guide_chunks],
    }
    return snippets, log_entry
