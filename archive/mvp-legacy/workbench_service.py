from __future__ import annotations

import copy
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from workbench_store import save_run


ROOT_DIR = Path(__file__).resolve().parent
STUDIO_DIR = ROOT_DIR / "src" / "main02" / "studio"
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))


SCENARIO_DIR = ROOT_DIR / "scenarios" / "synthetic-based"
_AGENTIC_MVP = None
_LOADER = None


def _get_loader():
    global _LOADER
    if _LOADER is None:
        import loader as loader_module  # type: ignore

        _LOADER = loader_module
    return _LOADER


def _get_agentic_mvp():
    global _AGENTIC_MVP
    if _AGENTIC_MVP is None:
        import agentic as agentic_mvp_module  # type: ignore

        _AGENTIC_MVP = agentic_mvp_module
    return _AGENTIC_MVP


@dataclass(frozen=True)
class ScenarioVariant:
    scenario_group: str
    scenario_key: str
    scenario_id: str
    case_id: str
    variant_title: str
    primary_issues: tuple[str, ...]
    source_path: Path


def _list_scenario_paths() -> list[Path]:
    return sorted(
        path
        for path in SCENARIO_DIR.glob("scenario_*.json")
        if path.is_file() and "template" not in path.name
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _scenario_group_from_stem(stem: str) -> str:
    parts = stem.split("_")
    return "_".join(parts[:2]) if len(parts) >= 2 else stem


def _flatten_expected_scores(raw_scenario: dict[str, Any]) -> dict[str, Any]:
    candidate_profile = raw_scenario.get("candidate_profile", {})
    expected_scores = candidate_profile.get("expected_scores", {})

    flat: dict[str, Any] = {}
    for section_name in ("rubric", "case_interaction_quality"):
        section = expected_scores.get(section_name, {})
        if not isinstance(section, dict):
            continue
        for dimension, details in section.items():
            if isinstance(details, dict):
                flat[dimension] = details.get("expected", "not_tested")
    return flat


def _numeric_expected_values(raw_scenario: dict[str, Any]) -> list[float]:
    values = []
    for value in _flatten_expected_scores(raw_scenario).values():
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def _extract_primary_issues(raw_scenario: dict[str, Any]) -> list[str]:
    issues = []
    for dimension, value in _flatten_expected_scores(raw_scenario).items():
        if isinstance(value, (int, float)) and value <= 2:
            issues.append(dimension)
    return issues


def _variant_title(raw_scenario: dict[str, Any], scenario_key: str) -> str:
    issues = _extract_primary_issues(raw_scenario)
    variant_suffix = scenario_key.split("_")[-1]
    if issues:
        return f"Variant {variant_suffix} • {issues[0].replace('_', ' ')}"
    return f"Variant {variant_suffix}"


def _normalize_expected_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for dimension, details in section.items():
        if not isinstance(details, dict):
            continue
        rows.append(
            {
                "dimension": dimension,
                "expected": details.get("expected", "not_tested"),
                "rationale": str(details.get("rationale", "")).strip(),
            }
        )
    return rows


def _load_case_summary(case_id: str) -> dict[str, Any]:
    raw_case = _get_loader().load_case(case_id)
    case_content = raw_case.get("case_content", [])
    prompt_block = next(
        (
            block
            for block in case_content
            if isinstance(block, dict) and block.get("block_type") == "prompt"
        ),
        {},
    )

    return {
        "case_id": case_id,
        "prompt_title": str(prompt_block.get("title", "")).strip(),
        "prompt_content": str(prompt_block.get("content", "")).strip(),
    }


def _build_variant(path: Path) -> ScenarioVariant:
    raw_scenario = _read_json(path)
    scenario_key = path.stem
    scenario_group = _scenario_group_from_stem(path.stem)

    return ScenarioVariant(
        scenario_group=scenario_group,
        scenario_key=scenario_key,
        scenario_id=str(raw_scenario.get("scenario_id", "")).strip(),
        case_id=str(raw_scenario.get("case_id", "")).strip(),
        variant_title=_variant_title(raw_scenario, scenario_key),
        primary_issues=tuple(_extract_primary_issues(raw_scenario)),
        source_path=path,
    )


def list_scenario_groups() -> list[dict[str, Any]]:
    grouped: dict[str, list[ScenarioVariant]] = {}
    for path in _list_scenario_paths():
        variant = _build_variant(path)
        grouped.setdefault(variant.scenario_group, []).append(variant)

    result = []
    for group_key, variants in sorted(grouped.items()):
        first = variants[0]
        result.append(
            {
                "scenario_group": group_key,
                "scenario_id": first.scenario_id,
                "case_id": first.case_id,
                "variant_count": len(variants),
                "variants": [
                    {
                        "scenario_key": item.scenario_key,
                        "variant_title": item.variant_title,
                        "primary_issues": list(item.primary_issues),
                    }
                    for item in variants
                ],
            }
        )
    return result


def _find_variant(scenario_group: str, scenario_key: str | None = None) -> ScenarioVariant:
    matches = [_build_variant(path) for path in _list_scenario_paths() if _scenario_group_from_stem(path.stem) == scenario_group]
    if not matches:
        raise FileNotFoundError(f"Scenario group '{scenario_group}' not found.")

    if scenario_key:
        for variant in matches:
            if variant.scenario_key == scenario_key:
                return variant
        raise FileNotFoundError(f"Scenario variant '{scenario_key}' not found.")

    return matches[0]


def build_scenario_preview(scenario_group: str, scenario_key: str | None = None) -> dict[str, Any]:
    variant = _find_variant(scenario_group, scenario_key)
    raw_scenario = _read_json(variant.source_path)
    candidate_profile = raw_scenario.get("candidate_profile", {})
    expected_scores = candidate_profile.get("expected_scores", {})

    preview = {
        "scenario_group": variant.scenario_group,
        "scenario_key": variant.scenario_key,
        "scenario_id": variant.scenario_id,
        "case_id": variant.case_id,
        "variant_title": variant.variant_title,
        "primary_issues": list(variant.primary_issues),
        "source_path": str(variant.source_path),
        "candidate_profile": {
            "candidate_id": str(candidate_profile.get("id", "")).strip(),
            "role": str(candidate_profile.get("persona_instruction", {}).get("role", "")).strip(),
            "behaviour_description": str(
                candidate_profile.get("persona_instruction", {}).get("behaviour_description", "")
            ).strip(),
            "behavioural_rules": [
                str(rule).strip()
                for rule in candidate_profile.get("persona_instruction", {}).get("behavioural_rules", [])
                if str(rule).strip()
            ],
        },
        "expected_scores": {
            "rubric": _normalize_expected_section(expected_scores.get("rubric", {})),
            "case_interaction_quality": _normalize_expected_section(
                expected_scores.get("case_interaction_quality", {})
            ),
            "flat": _flatten_expected_scores(raw_scenario),
        },
        "case_summary": _load_case_summary(variant.case_id),
        "available_grades": [
            {
                "scenario_key": item.scenario_key,
                "variant_title": item.variant_title,
            }
            for item in [
                _build_variant(path)
                for path in _list_scenario_paths()
                if _scenario_group_from_stem(path.stem) == scenario_group
            ]
        ],
    }
    preview["expected_overall"] = compute_expected_overall(preview)
    return preview


def compute_expected_overall(preview: dict[str, Any]) -> int:
    values = []
    flat = preview.get("expected_scores", {}).get("flat", {})
    if isinstance(flat, dict):
        for value in flat.values():
            if isinstance(value, (int, float)):
                values.append(int(value))
    if not values:
        return 0

    average = sum(values) / len(values)
    rounded = int(round(average))
    return max(1, min(4, rounded))


def _state_copy(state: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(state)


def _merge_state(state: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = _state_copy(state)
    merged.update(update)
    return merged


def _summarize_input(state: dict[str, Any]) -> str:
    transcript = state.get("transcript", [])
    if not transcript:
        return "No previous transcript."
    return str(transcript[-1])[:280]


def _build_trace_event(
    step_index: int,
    node_name: str,
    state_before: dict[str, Any],
    state_after: dict[str, Any],
) -> dict[str, Any]:
    agentic = _get_agentic_mvp()
    timestamp = datetime.now(UTC).isoformat()
    action_type = "decision"
    output_text = ""
    agent_role = node_name
    metadata: dict[str, Any] = {}
    transcript_before = state_before.get("transcript", [])
    transcript_after = state_after.get("transcript", [])
    new_lines = transcript_after[len(transcript_before):] if len(transcript_after) >= len(transcript_before) else []

    def _last_new_content(prefix: str) -> str:
        for line in reversed(new_lines):
            if isinstance(line, str) and line.startswith(prefix):
                return line[len(prefix):].strip()
        return ""

    if node_name == "interviewer":
        action_type = str(state_after.get("interviewer_action", "question"))
        output_text = _last_new_content("Interviewer: ") or _last_new_content("Interviewer reveal: ")
        metadata = {
            "enough_evidence": state_after.get("enough_evidence"),
            "next_route": agentic.route_after_interviewer(state_after),
        }
    elif node_name == "candidate":
        action_type = "answer"
        output_text = _last_new_content("Candidate: ")
        metadata = {
            "turn_index": state_after.get("turn_index"),
        }
    elif node_name == "judge":
        action_type = "score" if state_after.get("judge_decision") == "score" else "feedback"
        output_text = str(state_after.get("latest_feedback", "")).strip()
        metadata = {
            "judge_decision": state_after.get("judge_decision"),
            "focus_area": state_after.get("focus_area"),
            "case_performance_ready": bool(state_after.get("case_performance")),
            "quality_dialog_ready": bool(state_after.get("quality_dialog")),
            "judge_reason": state_after.get("judge_reason"),
            "next_route": agentic.route_after_judge(state_after),
        }
    elif node_name == "eval_case_performance":
        action_type = "evaluate_case_performance"
        output_text = "Structured case-performance evaluation completed."
        metadata = {
            "case_performance": state_after.get("case_performance", {}),
        }
    elif node_name == "eval_dialog_quality":
        action_type = "evaluate_dialog_quality"
        output_text = "Structured dialog-quality evaluation completed."
        metadata = {
            "quality_dialog": state_after.get("quality_dialog", {}),
        }
    elif node_name == "give_feedback":
        action_type = "feedback"
        output_text = str(state_after.get("latest_feedback", "")).strip()
        metadata = {
            "case_performance_ready": bool(state_after.get("case_performance")),
            "quality_dialog_ready": bool(state_after.get("quality_dialog")),
        }

    return {
        "step_index": step_index,
        "node_name": node_name,
        "agent_role": agent_role,
        "timestamp": timestamp,
        "input_summary": _summarize_input(state_before),
        "output_text": output_text,
        "action_type": action_type,
        "metadata": metadata,
        "transcript_delta": new_lines,
    }


def _run_node(node_name: str, state: dict[str, Any]) -> dict[str, Any]:
    agentic = _get_agentic_mvp()
    if node_name == "interviewer":
        return agentic.interviewer_node(state)
    if node_name == "candidate":
        return agentic.candidate_node(state)
    if node_name == "judge":
        return agentic.judge_node(state)
    if node_name == "eval_case_performance":
        return agentic.eval_case_performance_node(state)
    if node_name == "eval_dialog_quality":
        return agentic.eval_dialog_quality_node(state)
    if node_name == "give_feedback":
        return agentic.give_feedback_node(state)
    raise ValueError(f"Unsupported node '{node_name}'.")


def _next_node(node_name: str, state: dict[str, Any]) -> str | None:
    agentic = _get_agentic_mvp()
    if node_name == "interviewer":
        return agentic.route_after_interviewer(state)
    if node_name == "candidate":
        return "interviewer"
    if node_name == "judge":
        if hasattr(agentic, "route_after_judge_agentic_02"):
            route = agentic.route_after_judge_agentic_02(state)
        else:
            route = agentic.route_after_judge(state)
        return None if route == "end" else ("eval_case_performance" if route == "evaluate" else route)
    if node_name == "eval_case_performance":
        return "eval_dialog_quality"
    if node_name == "eval_dialog_quality":
        return "give_feedback"
    if node_name == "give_feedback":
        return None
    raise ValueError(f"Unsupported node '{node_name}'.")


def _build_comparison_result(preview: dict[str, Any], final_state: dict[str, Any], node_trace: list[dict[str, Any]]) -> dict[str, Any]:
    expected_overall = compute_expected_overall(preview)

    detected_issues = sorted(
        {
            str(event.get("metadata", {}).get("focus_area", "")).strip()
            for event in node_trace
            if event.get("node_name") == "judge"
            and str(event.get("metadata", {}).get("focus_area", "")).strip()
            not in {"", "none"}
        }
    )
    expected_issues = preview.get("primary_issues", [])

    return {
        "expected_overall": expected_overall,
        "actual_overall": None,
        "overall_delta": None,
        "alignment": "not_computed",
        "expected_issues": expected_issues,
        "detected_issues": detected_issues,
        "missing_expected_issues": [issue for issue in expected_issues if issue not in detected_issues],
        "unexpected_detected_issues": [issue for issue in detected_issues if issue not in expected_issues],
        "notes": "This graph does not compute a single overall score. Review case_performance and quality_dialog directly.",
    }


def _build_graph_view(node_trace: list[dict[str, Any]]) -> dict[str, Any]:
    execution_order = [str(event.get("node_name", "")).strip() for event in node_trace if str(event.get("node_name", "")).strip()]
    execution_path = ["start", *execution_order, "end"]

    positions = {
        "start": {"x": 60, "y": 126},
        "interviewer": {"x": 250, "y": 60},
        "candidate": {"x": 250, "y": 196},
        "judge": {"x": 470, "y": 126},
        "eval_case_performance": {"x": 860, "y": 60},
        "eval_dialog_quality": {"x": 860, "y": 196},
        "give_feedback": {"x": 1080, "y": 126},
        "end": {"x": 1290, "y": 126},
    }

    labels = {
        "start": "Start",
        "interviewer": "Interviewer",
        "candidate": "Candidate",
        "judge": "Judge",
        "eval_case_performance": "Eval Case Performance",
        "eval_dialog_quality": "Eval Dialog Quality",
        "give_feedback": "Give Feedback",
        "end": "End",
    }

    visit_steps: dict[str, list[int]] = {}
    for event in node_trace:
        node_name = str(event.get("node_name", "")).strip()
        if not node_name:
            continue
        visit_steps.setdefault(node_name, []).append(int(event.get("step_index", 0)))

    nodes = []
    for node_id in (
        "start",
        "interviewer",
        "candidate",
        "judge",
        "eval_case_performance",
        "eval_dialog_quality",
        "give_feedback",
        "end",
    ):
        nodes.append(
            {
                "id": node_id,
                "label": labels[node_id],
                "x": positions[node_id]["x"],
                "y": positions[node_id]["y"],
                "visits": visit_steps.get(node_id, []),
                "is_visited": node_id in execution_path,
            }
        )

    base_edges = [
        {"id": "start-interviewer", "from": "start", "to": "interviewer", "label": "start"},
        {"id": "interviewer-candidate", "from": "interviewer", "to": "candidate", "label": "ask_candidate"},
        {"id": "interviewer-judge", "from": "interviewer", "to": "judge", "label": "judge"},
        {"id": "candidate-interviewer", "from": "candidate", "to": "interviewer", "label": "loop"},
        {"id": "judge-interviewer", "from": "judge", "to": "interviewer", "label": "continue"},
        {"id": "judge-case", "from": "judge", "to": "eval_case_performance", "label": "evaluate"},
        {"id": "judge-quality", "from": "judge", "to": "eval_dialog_quality", "label": "evaluate"},
        {"id": "case-quality-join", "from": "eval_case_performance", "to": "eval_dialog_quality", "label": "trace order"},
        {"id": "quality-feedback", "from": "eval_dialog_quality", "to": "give_feedback", "label": "join"},
        {"id": "feedback-end", "from": "give_feedback", "to": "end", "label": "end"},
    ]

    traversed_edges = {
        f"{execution_path[index]}->{execution_path[index + 1]}"
        for index in range(len(execution_path) - 1)
    }

    edges = []
    for edge in base_edges:
        edge_key = f"{edge['from']}->{edge['to']}"
        edge["is_active"] = edge_key in traversed_edges
        edge["from_pos"] = positions[edge["from"]]
        edge["to_pos"] = positions[edge["to"]]
        edges.append(edge)

    path_steps = []
    for index, node_id in enumerate(execution_path, start=1):
        label = labels.get(node_id, node_id.title())
        path_steps.append(
            {
                "step_index": index,
                "node_id": node_id,
                "label": label,
                "kind": "boundary" if node_id in {"start", "end"} else "node",
            }
        )

    transition_counts: dict[str, int] = {}
    transition_steps = []
    for index in range(len(execution_path) - 1):
        edge_key = f"{execution_path[index]}->{execution_path[index + 1]}"
        transition_counts[edge_key] = transition_counts.get(edge_key, 0) + 1
        transition_steps.append(
            {
                "from": execution_path[index],
                "to": execution_path[index + 1],
                "label": labels.get(execution_path[index + 1], execution_path[index + 1].title()),
                "count": transition_counts[edge_key],
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
        "execution_path": execution_path,
        "path_steps": path_steps,
        "transition_steps": transition_steps,
    }


def run_scenario(scenario_group: str, scenario_key: str, seed: int | None = None) -> dict[str, Any]:
    agentic = _get_agentic_mvp()
    preview = build_scenario_preview(scenario_group, scenario_key)
    initial_state = agentic.build_initial_interview_state(
        scenario_ref=preview["source_path"],
        seed=seed,
    )

    state = _state_copy(initial_state)
    node_trace: list[dict[str, Any]] = []
    current_node = "interviewer"
    step_index = 1

    while current_node is not None:
        before = _state_copy(state)
        update = _run_node(current_node, state)
        state = _merge_state(state, update)
        node_trace.append(_build_trace_event(step_index, current_node, before, state))
        current_node = _next_node(current_node, state)
        step_index += 1

    created_at = datetime.now(UTC).isoformat()
    run_id = uuid.uuid4().hex[:12]
    comparison_result = _build_comparison_result(preview, state, node_trace)

    payload = {
        "run_id": run_id,
        "scenario_snapshot": {
            "scenario_group": preview["scenario_group"],
            "scenario_key": preview["scenario_key"],
            "scenario_id": preview["scenario_id"],
            "case_id": preview["case_id"],
            "variant_title": preview["variant_title"],
            "primary_issues": preview["primary_issues"],
            "expected_overall": comparison_result["expected_overall"],
        },
        "transcript": state.get("transcript", []),
        "node_trace": node_trace,
        "graph_view": _build_graph_view(node_trace),
        "actual_scores": {
            "case_performance": state.get("case_performance", {}),
            "quality_dialog": state.get("quality_dialog", {}),
        },
        "expected_scores": preview.get("expected_scores", {}),
        "comparison_result": comparison_result,
        "run_metadata": {
            "created_at": created_at,
            "seed": seed,
            "model": getattr(agentic.llm_server, "model_name", None)
            or getattr(agentic.llm_server, "model", None),
            "temperature": getattr(agentic.llm_server, "temperature", None),
            "source_scenario_path": preview["source_path"],
        },
    }

    save_run(payload)
    return payload
