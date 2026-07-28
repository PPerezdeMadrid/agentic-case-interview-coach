import json
import re
import time
from typing import Callable

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from adapter import (
    get_case_block_by_id,
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


def get_candidate_visible_transcript(transcript: list[str]) -> list[str]:
    visible_prefixes = ("Interviewer:", "Interviewer reveal:", "Candidate:")
    return [line for line in transcript if line.startswith(visible_prefixes)]


def candidate_transcript_messages(visible_transcript: list[str]) -> list:
    """Replay the visible transcript as real conversation turns so the candidate
    sees its own prior answers as assistant turns instead of as text described
    inside the system prompt.
    """
    messages: list = []
    for line in visible_transcript:
        if line.startswith("Candidate:"):
            messages.append(AIMessage(content=line[len("Candidate:"):].strip()))
        elif line.startswith("Interviewer reveal:"):
            messages.append(HumanMessage(content="[revealed fact] " + line[len("Interviewer reveal:"):].strip()))
        else:
            messages.append(HumanMessage(content=line[len("Interviewer:"):].strip()))
    return messages


def resolve_reveal_content(case_data: dict, action: str, block_id: str, content: str) -> tuple[str, str]:
    """Swap in the case block's real content when the interviewer/baseline chose to
    reveal one, falling back to a plain question if the block isn't actually
    candidate-visible. Shared by node.interviewer_node and baseline.baseline_node."""
    if action != "reveal" or not block_id:
        return action, content

    revealed_block = get_case_block_by_id(case_data, block_id)
    if not isinstance(revealed_block, dict) or revealed_block.get("visible_to_candidate") is not True:
        return "question", content

    revealed_content = str(revealed_block.get("content", "")).strip()
    return action, (revealed_content or content)


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


def format_rubric(rubric_data: dict, fields: list[str] | None = None) -> str:
    dimensions = rubric_data.get("dimensions", [])
    if not isinstance(dimensions, list) or not dimensions:
        return "No rubric dimensions available."

    if fields is not None:
        dimensions = [
            dimension
            for dimension in dimensions
            if isinstance(dimension, dict) and dimension.get("dimension_id") in fields
        ]
        if not dimensions:
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

    reference_scores = candidate_profile.get("reference_scores", {})
    if isinstance(reference_scores, dict):
        rationale_lines = []
        for group_key in ("rubric", "case_interaction_quality"):
            group = reference_scores.get(group_key, {})
            if not isinstance(group, dict):
                continue
            for dimension_id, entry in group.items():
                if not isinstance(entry, dict):
                    continue
                rationale = str(entry.get("rationale", "")).strip()
                if rationale:
                    label = str(dimension_id).replace("_", " ").strip()
                    rationale_lines.append(f"- {label}: {rationale}")
        if rationale_lines:
            sections.append(
                "How you must actually come across in this interview, trait by trait:\n"
                + "\n".join(rationale_lines)
            )
    return "\n\n".join(sections) if sections else "No scenario persona provided."


def extract_case_prompt(case_data: dict) -> str:
    opening_block = get_opening_prompt(case_data)
    if not isinstance(opening_block, dict):
        return "Walk me through your approach."
    return str(opening_block.get("content", "")).strip() or "Walk me through your approach."


def extract_case_guidance(case_data: dict) -> str:
    return format_case_blocks(get_hidden_guidance_blocks(case_data))


def extract_case_data_facts(case_data: dict) -> str:
    return format_case_blocks(get_case_blocks_by_type(case_data, "data"))


def extract_case_recommendation(case_data: dict) -> str:
    return format_case_blocks(get_case_blocks_by_type(case_data, "final_recommendation"))


def parse_interviewer_output(payload: dict) -> tuple[str, str, str, bool, str] | None:
    if not payload:
        return None

    action = str(payload.get("action", "question")).strip().lower()
    content = str(payload.get("content", "")).strip()
    block_id = str(payload.get("block_id", "")).strip()
    ready_for_judge = bool(payload.get("ready_for_judge", False))
    reasoning = str(payload.get("reasoning", "")).strip()

    if action not in {"question", "reveal"}:
        return None
    if not content:
        return None
    return action, content, block_id, ready_for_judge, reasoning


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


def extract_token_usage(response: object, *, node: str, model: str = "", duration_seconds: float | None = None) -> dict:
    """Read prompt/completion/total token counts off a ChatOpenAI response.

    Works for both OpenRouter and LM Studio since both go through the same
    OpenAI-compatible `usage` payload in the raw response.

    `duration_seconds`, when given, is the wall-clock time the triggering
    `llm.invoke()` call took -- timed by the caller since it isn't part of
    the response payload itself (unlike token counts, no provider echoes
    this back).
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
        "duration_seconds": round(duration_seconds, 3) if duration_seconds is not None else None,
        "usage": {
            "prompt_tokens": token_usage.get("prompt_tokens", usage_metadata.get("input_tokens")),
            "completion_tokens": token_usage.get("completion_tokens", usage_metadata.get("output_tokens")),
            "total_tokens": token_usage.get("total_tokens", usage_metadata.get("total_tokens")),
        },
    }


def _json_schema_response_format(schema: type[BaseModel]) -> dict:
    """Build an OpenAI/OpenRouter `response_format: json_schema` payload from a
    Pydantic model. Requires `extra="forbid"` on the model so every generated
    object schema has `additionalProperties: false`, as strict mode expects."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "strict": True,
            "schema": schema.model_json_schema(),
        },
    }


def invoke_json_llm(
    llm,
    messages: list,
    *,
    node: str,
    schema: type[BaseModel] | None = None,
    accept: Callable[[dict], bool] | None = None,
    on_exhausted: Callable[[str], dict] | None = None,
    retries: int = 3,
) -> tuple[dict, list[dict]]:
    """Invoke an LLM expected to reply with a JSON object, retrying with an
    explicit repair instruction when the reply doesn't parse (e.g. the model
    wrapped it in a preamble/fence `load_json_object` still can't salvage).

    `schema`, when given, is sent as a `response_format: json_schema` hint on
    the first attempt. This is best-effort: OpenRouter's open-weight models
    advertise support inconsistently across upstream providers, so a rejected
    request falls back to an unconstrained call, and every reply (constrained
    or not) still goes through `load_json_object` and `accept` rather than
    being trusted outright.

    `accept` decides whether a parsed payload is good enough to return; it
    defaults to "non-empty dict", but callers with extra structural
    requirements (e.g. the interviewer's action/content fields) can pass a
    stricter check so retries keep going until a usable payload appears.

    `on_exhausted`, when given, receives the last raw response text once
    retries run out and can turn it into a usable payload instead of `{}`
    (e.g. the candidate treats un-JSON-ed prose as a perfectly good answer).

    Returns (payload, usage_log). `payload` is only `{}` if every attempt
    failed to produce an accepted payload and `on_exhausted` was not given
    or also came up empty, so downstream `not_tested` defaults reflect a
    genuine coverage gap rather than a parsing failure.
    """
    usage_log: list[dict] = []
    model_name = getattr(llm, "model_name", "")
    is_acceptable = accept or (lambda payload: bool(payload))
    server_label = node.replace("_", " ").title()

    structured_llm = llm.bind(response_format=_json_schema_response_format(schema)) if schema else llm

    def _invoke(target_llm, invoke_messages: list):
        if target_llm is llm:
            try:
                return llm.invoke(invoke_messages)
            except Exception as exc:
                print(f"Error calling {server_label} server: {exc}")
                raise
        try:
            return target_llm.invoke(invoke_messages)
        except Exception as exc:
            # Some OpenRouter-routed providers advertise structured_outputs
            # support but reject this particular schema/request - fall back
            # to an unconstrained call rather than losing the turn.
            print(f"Structured call to {server_label} server failed ({exc}); retrying unconstrained.")
            try:
                return llm.invoke(invoke_messages)
            except Exception as fallback_exc:
                print(f"Error calling {server_label} server: {fallback_exc}")
                raise

    print(f"Calling {server_label} server...")
    started_at = time.perf_counter()
    response = _invoke(structured_llm, messages)
    usage_log.append(extract_token_usage(response, node=node, model=model_name, duration_seconds=time.perf_counter() - started_at))
    payload = load_json_object(response.content)
    if is_acceptable(payload):
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
        print(f"Calling {server_label} server (JSON repair retry)...")
        started_at = time.perf_counter()
        response = _invoke(llm, repair_messages)
        usage_log.append(
            extract_token_usage(response, node=f"{node}_repair", model=model_name, duration_seconds=time.perf_counter() - started_at)
        )
        raw_output = str(response.content).strip()
        payload = load_json_object(raw_output)
        if is_acceptable(payload):
            return payload, usage_log

    if on_exhausted is not None:
        return on_exhausted(raw_output), usage_log
    return {}, usage_log
