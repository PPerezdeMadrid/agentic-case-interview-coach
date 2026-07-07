from __future__ import annotations

from pathlib import Path


TOTAL_TURNS = 3

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROMPTS_DIR = _REPO_ROOT / "doc" / "prompts"


def _load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Prompt file not found: {path}") from exc


def _compose_prompt(*filenames: str) -> str:
    return "\n\n".join(_load_prompt(filename) for filename in filenames)


INTERVIEWER_SYSTEM_PROMPT = _compose_prompt(
    "interviewer_system_prompt.md",
    "interviewer_question_style_few_shots.md",
)
BASELINE_SYSTEM_PROMPT = _load_prompt("baseline_system_prompt.md")
BASELINE_FINAL_FEEDBACK_PROMPT = _load_prompt("baseline_final_feedback_prompt.md")
BASELINE_INFORMATION_PROMPT = _load_prompt("baseline_information_prompt.md")
CANDIDATE_SYSTEM_PROMPT = _load_prompt("candidate_system_prompt.md")
DEFAULT_QUESTION_FALLBACK = _load_prompt("default_question_fallback.md")
INTERVIEWER_GRAPH_SYSTEM_PROMPT = _compose_prompt(
    "interviewer_graph_system_prompt.md",
    "interviewer_question_style_few_shots.md",
)
BASELINE_GRAPH_SYSTEM_PROMPT = _load_prompt("baseline_graph_system_prompt.md")
JUDGE_GRAPH_SYSTEM_PROMPT = _load_prompt("judge_graph_system_prompt.md")
CASE_EVAL_SYSTEM_PROMPT = _load_prompt("case_eval_system_prompt.md")
DIALOG_EVAL_SYSTEM_PROMPT = _load_prompt("dialog_eval_system_prompt.md")
FEEDBACK_SYSTEM_PROMPT = _load_prompt("feedback_system_prompt.md")
CASE_GUIDE_NAVIGATION_PROMPT = _load_prompt("case_guide_navigation_prompt.md")
