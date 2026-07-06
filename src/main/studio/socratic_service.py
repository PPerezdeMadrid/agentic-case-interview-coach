from __future__ import annotations

import os

import requests


SOCRATIC_LABEL_BY_FOCUS_AREA = {
    "structure": "clarification",
    "prioritisation": "alternative_viewpoints",
    "business_logic": "reasons_evidence",
    "assumptions": "assumptions",
    "quantitative_reasoning": "reasons_evidence",
    "communication": "clarification",
    "recommendation": "implications_consequences",
}

REQUEST_TIMEOUT_SECONDS = float(os.environ.get("SOCRATIC_FT_TIMEOUT", "5.0"))


class SocraticServiceUnavailable(Exception):
    pass


def is_socratic_service_enabled() -> bool:
    mode = os.environ.get("SOCRATIC_QUESTION_MODE", "").strip().lower()
    if mode in {"finetuned", "hybrid"}:
        return True
    return os.environ.get("SOCRATIC_FT_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def get_socratic_service_url() -> str:
    return os.environ.get("SOCRATIC_FT_URL", "http://localhost:8008").rstrip("/")


def get_last_candidate_utterance(transcript: list[str]) -> str:
    for line in reversed(transcript):
        if line.startswith("Candidate:"):
            return line.removeprefix("Candidate:").strip()
    return ""


def choose_socratic_label(focus_areas: list[str]) -> str | None:
    for area in focus_areas:
        normalized = str(area).strip().lower()
        label = SOCRATIC_LABEL_BY_FOCUS_AREA.get(normalized)
        if label:
            return label
        if any(keyword in normalized for keyword in ("assumption", "uncertain", "risk")):
            return "assumptions"
        if any(keyword in normalized for keyword in ("recommend", "next step", "implication")):
            return "implications_consequences"
        if any(keyword in normalized for keyword in ("why", "evidence", "driver", "quant", "math")):
            return "reasons_evidence"
        if any(keyword in normalized for keyword in ("clarify", "structure", "concise", "communicat")):
            return "clarification"
        if any(keyword in normalized for keyword in ("priorit", "alternative", "trade-off")):
            return "alternative_viewpoints"
    return None


def generate_socratic_question(label: str, candidate_utterance: str) -> str:
    url = f"{get_socratic_service_url()}/generate-question"
    payload = {
        "label": label,
        "candidate_utterance": candidate_utterance,
    }

    try:
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SocraticServiceUnavailable(str(exc)) from exc

    data = response.json()
    question = str(data.get("question", "")).strip()
    if not question:
        raise SocraticServiceUnavailable("Socratic service returned an empty question.")
    return question


def maybe_generate_socratic_question(
    transcript: list[str],
    focus_areas: list[str],
) -> str | None:
    if not is_socratic_service_enabled():
        return None

    label = choose_socratic_label(focus_areas)
    candidate_utterance = get_last_candidate_utterance(transcript)

    if not label or not candidate_utterance:
        return None

    return generate_socratic_question(label, candidate_utterance)
