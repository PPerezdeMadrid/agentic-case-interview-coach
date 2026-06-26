import json
import re

from adapter import (
    get_case_blocks_by_type,
    get_hidden_guidance_blocks,
    get_opening_prompt,
)


FOCUS_AREA_VALUES = {
    "structure",
    "prioritisation",
    "business_logic",
    "assumptions",
    "quantitative_reasoning",
    "communication",
    "recommendation",
}


def strip_thinking(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()
    return cleaned


def load_json_object(text: str) -> dict:
    try:
        payload = json.loads(strip_code_fences(strip_thinking(text)))
        return payload if isinstance(payload, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def normalize_string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item).strip()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def format_case_blocks(blocks: list[dict]) -> str:
    if not blocks:
        return "None."

    formatted_blocks = []
    for block in blocks:
        title = str(block.get("title", "")).strip() or str(block.get("block_id", "")).strip() or "Untitled block"
        content = str(block.get("content", "")).strip()
        formatted_blocks.append(f"- {title}: {content}")
    return "\n".join(formatted_blocks)


def format_full_case_data(case_data: dict) -> str:
    if not isinstance(case_data, dict):
        return "None."

    case_content = case_data.get("case_content", [])
    if isinstance(case_content, list) and case_content:
        return format_case_blocks([block for block in case_content if isinstance(block, dict)])

    try:
        return json.dumps(case_data, ensure_ascii=True, indent=2)
    except (TypeError, ValueError):
        return "None."


def format_rubric(rubric_data: dict) -> str:
    dimensions = rubric_data.get("dimensions", [])
    if not isinstance(dimensions, list) or not dimensions:
        return "No rubric dimensions available."

    formatted_dimensions = []
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            continue
        dimension_id = str(dimension.get("dimension_id", "")).strip() or "unknown_dimension"
        description = str(dimension.get("description", "")).strip()
        criteria = dimension.get("criteria", {})
        formatted_dimensions.append(f"- {dimension_id}: {description}")
        if isinstance(criteria, dict):
            for score, criterion in criteria.items():
                formatted_dimensions.append(f"  Score {score}: {criterion}")
    return "\n".join(formatted_dimensions) if formatted_dimensions else "No rubric dimensions available."


def format_candidate_persona(candidate_profile: dict) -> str:
    if not isinstance(candidate_profile, dict):
        return "No scenario persona provided."

    persona = candidate_profile.get("persona_instruction", {})
    if not isinstance(persona, dict):
        return "No scenario persona provided."

    role = str(persona.get("role", "")).strip()
    description = str(persona.get("behaviour_description", "")).strip()
    rules = persona.get("behavioural_rules", [])
    case_facts = persona.get("case_specific_facts", [])
    roadmap = persona.get("solution_roadmap", [])
    math_guidance = persona.get("math_guidance", [])

    sections = []
    if role:
        sections.append(f"Role:\n{role}")
    if description:
        sections.append(f"Behaviour description:\n{description}")
    if isinstance(rules, list):
        cleaned_rules = [f"- {str(rule).strip()}" for rule in rules if str(rule).strip()]
        if cleaned_rules:
            sections.append("Behavioural rules:\n" + "\n".join(cleaned_rules))
    if isinstance(case_facts, list):
        cleaned_facts = [f"- {str(fact).strip()}" for fact in case_facts if str(fact).strip()]
        if cleaned_facts:
            sections.append("Case-specific facts to use:\n" + "\n".join(cleaned_facts))
    if isinstance(roadmap, list):
        cleaned_steps = [
            f"{index}. {str(step).strip()}"
            for index, step in enumerate(roadmap, start=1)
            if str(step).strip()
        ]
        if cleaned_steps:
            sections.append("Case-solving roadmap:\n" + "\n".join(cleaned_steps))
    if isinstance(math_guidance, list):
        cleaned_math = [f"- {str(item).strip()}" for item in math_guidance if str(item).strip()]
        if cleaned_math:
            sections.append("Math guidance:\n" + "\n".join(cleaned_math))
    return "\n\n".join(sections) if sections else "No scenario persona provided."


def extract_case_prompt(case_data: dict) -> str:
    opening_block = get_opening_prompt(case_data)
    if not isinstance(opening_block, dict):
        return "Walk me through your approach."
    return str(opening_block.get("content", "")).strip() or "Walk me through your approach."


def extract_case_guidance(case_data: dict) -> str:
    return format_case_blocks(get_hidden_guidance_blocks(case_data))


def extract_case_recommendation(case_data: dict) -> str:
    return format_case_blocks(get_case_blocks_by_type(case_data, "final_recommendation"))


def parse_interviewer_output(raw_output: str) -> tuple[str, str, str, bool]:
    payload = load_json_object(raw_output)
    action = str(payload.get("action", "question")).strip().lower()
    content = str(payload.get("content", "")).strip()
    block_id = str(payload.get("block_id", "")).strip()
    ready_for_judge = bool(payload.get("ready_for_judge", False))

    if action not in {"question", "reveal"}:
        action = "question"
    if not content:
        content = "Could you walk me through your approach?"
    return action, content, block_id, ready_for_judge


def normalize_focus_areas(raw_focus_areas: object) -> list[str]:
    if not isinstance(raw_focus_areas, list):
        return []
    normalized = []
    for item in raw_focus_areas:
        value = str(item).strip().lower()
        if value in FOCUS_AREA_VALUES and value not in normalized:
            normalized.append(value)
    return normalized


def merge_focus_areas(existing: list[str], new_values: list[str]) -> list[str]:
    merged = list(existing)
    for value in new_values:
        if value not in merged:
            merged.append(value)
    return merged


def score_value(value: object) -> int | str:
    if isinstance(value, str) and value.strip().lower() == "not_tested":
        return "not_tested"
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return "not_tested"
    return max(1, min(4, numeric))


def normalize_eval_payload(payload: dict, fields: list[str]) -> dict:
    normalized = {}
    for field in fields:
        item = payload.get(field, {})
        if not isinstance(item, dict):
            item = {}
        normalized[field] = {
            "score": score_value(item.get("score", "not_tested")),
            "rationale": str(item.get("rationale", "")).strip() or "No rationale provided.",
        }
    return normalized
