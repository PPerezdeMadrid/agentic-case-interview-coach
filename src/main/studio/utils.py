import json
import re

from langchain_core.messages import HumanMessage

from adapter import (
    get_case_blocks_by_type,
    get_hidden_guidance_blocks,
    get_opening_prompt,
)


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


def _find_fenced_json(text: str) -> str | None:
    """Locate a ```/```json fenced block anywhere in the text, not only ones
    wrapping the entire response (models often add a sentence before/after)."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else None


def _find_balanced_json(text: str) -> str | None:
    """Extract the first brace-balanced {...} object, scanning past any
    conversational preamble the model wrote before the JSON started."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def load_json_object(text: str) -> dict:
    """Parse the JSON object an LLM was asked to return, tolerating the
    conversational preamble/postamble ("Here is the JSON object...", trailing
    notes) and code fences models sometimes add around the payload."""
    cleaned = strip_thinking(text)
    for candidate in (strip_code_fences(cleaned), _find_fenced_json(cleaned), _find_balanced_json(cleaned)):
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
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


def parse_interviewer_output(raw_output: str) -> tuple[str, str, str, bool] | None:
    payload = load_json_object(raw_output)
    if not payload:
        return None

    action = str(payload.get("action", "question")).strip().lower()
    content = str(payload.get("content", "")).strip()
    block_id = str(payload.get("block_id", "")).strip()
    ready_for_judge = bool(payload.get("ready_for_judge", False))

    if action not in {"question", "reveal"}:
        return None
    if not content:
        return None
    return action, content, block_id, ready_for_judge


def normalize_focus_areas(raw_focus_areas: object) -> list[str]:
    if not isinstance(raw_focus_areas, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_focus_areas:
        value = " ".join(str(item).strip().split())
        if not value:
            continue
        dedupe_key = value.lower()
        if dedupe_key in seen:
            continue
        normalized.append(value)
        seen.add(dedupe_key)
    return normalized[:3]


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


def extract_token_usage(response: object, *, node: str, model: str = "") -> dict:
    """Read prompt/completion/total token counts off a ChatOpenAI response.

    Works for both OpenRouter and LM Studio since both go through the same
    OpenAI-compatible `usage` payload in the raw response.
    """
    metadata = getattr(response, "response_metadata", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    token_usage = metadata.get("token_usage")
    token_usage = token_usage if isinstance(token_usage, dict) else {}
    usage_metadata = getattr(response, "usage_metadata", None)
    usage_metadata = usage_metadata if isinstance(usage_metadata, dict) else {}
    model_name = metadata.get("model_name")
    if not isinstance(model_name, str) or not model_name:
        model_name = model if isinstance(model, str) else ""
    return {
        "node": node,
        "model": model_name,
        "usage": {
            "prompt_tokens": token_usage.get("prompt_tokens", usage_metadata.get("input_tokens")),
            "completion_tokens": token_usage.get("completion_tokens", usage_metadata.get("output_tokens")),
            "total_tokens": token_usage.get("total_tokens", usage_metadata.get("total_tokens")),
        },
    }


def invoke_json_llm(llm, messages: list, *, node: str, retries: int = 3) -> tuple[dict, list[dict]]:
    """Invoke an LLM expected to reply with a JSON object, retrying with an
    explicit repair instruction when the reply doesn't parse (e.g. the model
    wrapped it in a preamble/fence `load_json_object` still can't salvage).

    Returns (payload, usage_log). `payload` is only `{}` if every attempt
    failed to produce parseable JSON, so downstream `not_tested` defaults
    reflect a genuine judge coverage gap rather than a parsing failure.
    """
    usage_log: list[dict] = []
    model_name = getattr(llm, "model_name", "")

    response = llm.invoke(messages)
    usage_log.append(extract_token_usage(response, node=node, model=model_name))
    payload = load_json_object(response.content)
    if payload:
        return payload, usage_log

    raw_output = str(response.content).strip()
    for _ in range(max(retries, 1) - 1):
        repair_messages = messages + [
            HumanMessage(
                content=(
                    "Your previous reply was not valid JSON for the required schema.\n"
                    "Return exactly one JSON object as instructed. Do not add markdown, "
                    "code fences, analysis, or any extra text before or after it.\n\n"
                    f"Previous invalid reply:\n{raw_output or '[empty response]'}"
                )
            ),
        ]
        response = llm.invoke(repair_messages)
        usage_log.append(extract_token_usage(response, node=f"{node}_repair", model=model_name))
        raw_output = str(response.content).strip()
        payload = load_json_object(raw_output)
        if payload:
            return payload, usage_log

    return {}, usage_log
