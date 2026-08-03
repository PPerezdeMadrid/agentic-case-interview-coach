from __future__ import annotations

from pathlib import Path


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


CANDIDATE_SYSTEM_PROMPT = _load_prompt("candidate_system_prompt.md")
INTERVIEWER_GRAPH_SYSTEM_PROMPT = _compose_prompt(
    "interviewer_graph_system_prompt.md",
    "interviewer_question_style_few_shots.md",
)
JUDGE_GRAPH_SYSTEM_PROMPT = _load_prompt("judge_graph_system_prompt.md")
CASE_EVAL_SYSTEM_PROMPT = _compose_prompt(
    "case_eval_system_prompt.md",
    "case_eval_calibration_few_shots.md",
)
DIALOG_EVAL_SYSTEM_PROMPT = _compose_prompt(
    "dialog_eval_system_prompt.md",
    "dialog_eval_calibration_few_shots.md",
)
FEEDBACK_SYSTEM_PROMPT = _load_prompt("feedback_system_prompt.md")
CASE_GUIDE_NAVIGATION_PROMPT = _load_prompt("case_guide_navigation_prompt.md")
# One standalone persona rather than composed from per-role files like the agentic graph --
# that specialization gap is exactly what the baseline-vs-agentic comparison is meant to isolate.
BASELINE_GRAPH_SYSTEM_PROMPT = _load_prompt("baseline_graph_system_prompt.md")
