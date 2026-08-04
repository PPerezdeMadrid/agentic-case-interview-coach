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
    """Locate a fenced block anywhere in the text, not just ones wrapping the whole response."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else None


def _find_balanced_json(text: str) -> str | None:
    """Extract the first brace-balanced {...} object, skipping any preamble before it."""
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
    """Parse the JSON object an LLM was asked to return, tolerating preamble/postamble text and code fences."""
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
    """Replay the transcript as real turns so the candidate sees its own prior answers as assistant turns, not text in the system prompt."""
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
    """Swap in the case block's real content on reveal, falling back to a plain question if the
    block_id is missing, unknown, or not candidate-visible."""
    if action != "reveal":
        return action, content

    revealed_block = get_case_block_by_id(case_data, block_id) if block_id else None
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
    """Read prompt/completion/total token counts off a ChatOpenAI response. `duration_seconds`
    is timed by the caller since no provider echoes it back."""
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
    """Build an OpenAI/OpenRouter `response_format: json_schema` payload from a Pydantic model.
    Requires `extra="forbid"` on the model so strict mode's `additionalProperties: false` holds."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "strict": True,
            "schema": schema.model_json_schema(),
        },
    }


def _merge_adjacent_messages(messages: list) -> list:
    """Merge adjacent same-role messages into one -- some OpenRouter providers (e.g. Gemma via
    NextBit) reject back-to-back same-role messages with a "roles must alternate" error."""
    if not messages:
        return list(messages)
    coalesced = [messages[0]]
    for message in messages[1:]:
        previous = coalesced[-1]
        if type(previous) is type(message):
            coalesced[-1] = previous.__class__(content=f"{previous.content}\n\n{message.content}")
        else:
            coalesced.append(message)
    return coalesced


def _is_transient_provider_error(exc: Exception) -> bool:
    """Detect OpenRouter errors worth a backed-off retry: real 429s, 400s carrying a
    `provider_name` (OpenRouter routed to a provider that can't serve this model), and 400s
    whose message says a provider can't serve this model/endpoint even when the payload omits
    `provider_name` (e.g. langchain_openai re-raising `response_dict["error"]` as a bare
    ValueError). A malformed request from our own code has neither shape and should NOT be
    retried."""
    if getattr(exc, "status_code", None) == 429:
        return True
    text = str(exc)
    if "Error code: 429" in text or "'code': 429" in text:
        return True
    if "'provider_name'" in text and ("'code': 400" in text or "Error code: 400" in text):
        return True
    return "does not support endpoint" in text


def _summarize_provider_error(exc: Exception) -> str:
    """Collapse OpenRouter's deeply nested error payload down to one readable line for logging."""
    text = str(exc)
    provider_match = re.search(r"'provider_name':\s*'([^']+)'", text)
    code_match = re.search(r"'code':\s*(\d+)", text)
    message_match = re.search(r"'message':\s*'([^']*)'", text)
    tags = [tag for tag in (
        f"code={code_match.group(1)}" if code_match else None,
        f"provider={provider_match.group(1)}" if provider_match else None,
    ) if tag]
    prefix = f"[{', '.join(tags)}] " if tags else ""
    message = message_match.group(1) if message_match else text[:200]
    return f"{prefix}{message}"


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
    """Invoke an LLM expected to return JSON, retrying with a repair instruction on parse failure.
    `schema` is best-effort -- a rejected request falls back to an unconstrained call, still routed
    through `load_json_object`/`accept`. `on_exhausted` can salvage the last raw text instead of
    returning `{}` once retries run out."""
    usage_log: list[dict] = []
    model_name = getattr(llm, "model_name", "")
    is_acceptable = accept or (lambda payload: bool(payload))
    server_label = node.replace("_", " ").title()

    structured_llm = llm.bind(response_format=_json_schema_response_format(schema)) if schema else llm

    def _invoke_with_backoff(call_llm, invoke_messages: list, max_attempts: int = 4, base_delay: float = 5.0):
        # A short backoff usually lands the next attempt on a different provider in the pool.
        for attempt in range(max_attempts):
            try:
                return call_llm.invoke(invoke_messages)
            except Exception as exc:
                if attempt == max_attempts - 1 or not _is_transient_provider_error(exc):
                    raise
                delay = base_delay * (2 ** attempt)
                print(
                    f"{server_label} server hit a transient provider error "
                    f"(attempt {attempt + 1}/{max_attempts}): {_summarize_provider_error(exc)}; "
                    f"retrying in {delay:.0f}s..."
                )
                time.sleep(delay)

    def _invoke(target_llm, invoke_messages: list):
        invoke_messages = _merge_adjacent_messages(invoke_messages)
        if target_llm is llm:
            try:
                return _invoke_with_backoff(llm, invoke_messages)
            except Exception as exc:
                print(f"Error calling {server_label} server: {_summarize_provider_error(exc)}")
                raise
        try:
            return _invoke_with_backoff(target_llm, invoke_messages)
        except Exception as exc:
            # Some providers advertise structured_outputs support but reject this schema anyway.
            print(f"Structured call to {server_label} server failed ({_summarize_provider_error(exc)}); retrying unconstrained.")
            try:
                return _invoke_with_backoff(llm, invoke_messages)
            except Exception as fallback_exc:
                print(f"Error calling {server_label} server: {_summarize_provider_error(fallback_exc)}")
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
