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


CANDIDATE_SYSTEM_PROMPT = _load_prompt("candidate_system_prompt.md")
INTERVIEWER_GRAPH_SYSTEM_PROMPT = _compose_prompt(
    "interviewer_graph_system_prompt.md",
    "interviewer_question_style_few_shots.md",
)
JUDGE_GRAPH_SYSTEM_PROMPT = _load_prompt("judge_graph_system_prompt.md")
CASE_EVAL_SYSTEM_PROMPT = _load_prompt("case_eval_system_prompt.md")
DIALOG_EVAL_SYSTEM_PROMPT = _load_prompt("dialog_eval_system_prompt.md")
FEEDBACK_SYSTEM_PROMPT = _load_prompt("feedback_system_prompt.md")
CASE_GUIDE_NAVIGATION_PROMPT = _load_prompt("case_guide_navigation_prompt.md")
# Baseline is a single node that combines interviewer, judge, and grader, so
# unlike the agentic graph's specialized per-role prompts, it is written as one
# standalone persona instead of composed from their files: that specialization
# gap is exactly what the baseline-vs-agentic comparison is meant to isolate.
# It still shares grading criteria and question style with the agentic graph's
# equivalent nodes by construction, just folded into a single coherent voice.
BASELINE_GRAPH_SYSTEM_PROMPT = _load_prompt("baseline_graph_system_prompt.md")
