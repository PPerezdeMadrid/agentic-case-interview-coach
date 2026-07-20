"""Run an interviewer golden-set CSV (see build_interviewer_golden_sets.py) against the
real interviewer LLM and grade each row generically from whichever `expected_*` /
`must_contain` / `must_not_contain` / `forbidden_substrings` columns are present --
the same script works for all 4 golden-set files.

Each row's `interviewer_input` is the exact rendered SystemMessage `interviewer_node`
would send, run through the same `invoke_json_llm(..., schema=InterviewerMove)` and
`parse_interviewer_output` the real node uses.

Rows with an `expected_socratic_function` also get a classification call against the
3-way taxonomy, graded by `SOCRATIC_JUDGE_LLM` (the independent judge model, not the
interviewer itself, to avoid self-assessment bias).

This costs one (or two) real LLM call per row, so it's a deliberate offline/Makefile
step. Writes a JSON cache (read by the workbench's Agents > Interviewer page); static
per-row metadata is re-merged from the source CSV at page-load time.

Usage (from src/, with the project venv active):
    python main/studio/node_eval/interviewer_eval/run_interviewer_golden_set.py \\
        --csv database/node_eval/interviewer_eval/interviewer_golden_set_evidence_handling.csv
    make interviewer-eval INTERVIEWER_GOLDEN_SET=guardrail
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

STUDIO_DIR = Path(__file__).resolve().parents[2]
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

from langchain_core.messages import SystemMessage  # noqa: E402
from pydantic import BaseModel, ConfigDict  # noqa: E402

import node  # noqa: E402
from llm_server import judge_llm_server  # noqa: E402
from state import InterviewerMove  # noqa: E402
from utils import invoke_json_llm, parse_interviewer_output  # noqa: E402

INTERVIEWER_EVAL_DIR = Path(__file__).resolve().parents[4] / "database" / "node_eval" / "interviewer_eval"
DEFAULT_CSV_PATH = INTERVIEWER_EVAL_DIR / "interviewer_golden_set_evidence_handling.csv"


SOCRATIC_JUDGE_LLM = judge_llm_server

SOCRATIC_FUNCTIONS = (
    "clarity",
    "premise_testing",
    "perspective_testing",
    "others",
)


class _SocraticFunctionGuess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    function: Literal[
        "clarity",
        "premise_testing",
        "perspective_testing",
        "others",
    ]


_CLASSIFY_PROMPT = """Classify the interviewer question below into exactly one Socratic \
question function:

- clarity: makes the candidate define a vague claim more precisely (asks "what do you \
mean by X" / "precisely which X").
- premise_testing: surfaces a claim, assumption, or priority the candidate stated \
without support, and asks for its basis (asks "what's that based on" / "what evidence \
supports X").
- perspective_testing: challenges a one-sided or incomplete frame -- introduces a \
downstream consequence or an alternative angle the candidate's claim ignores (asks \
"what would that mean for Y" / "what about Z instead").
- others: none of the above cleanly fits (e.g. it isn't a pressure-testing question at all).

Interviewer question:
{question}

Output exactly one valid JSON object: {{"function": "<one of the 4 labels above>"}}."""


def _golden_set_name(csv_path: Path) -> str:
    stem = csv_path.stem
    return stem.removeprefix("interviewer_golden_set_") or stem


def _load_rows(csv_path: Path, *, limit: int | None) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows[:limit] if limit is not None else rows


def _split_terms(value: str) -> list[str]:
    return [term.strip() for term in value.split("|") if term.strip()]


def _contains_all(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return all(term.lower() in lowered for term in terms)


def _contains_none(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return not any(term.lower() in lowered for term in terms)

# LLM-as-a-judge
def _classify_socratic_function(question: str) -> str:
    messages = [SystemMessage(content=_CLASSIFY_PROMPT.format(question=question))]
    payload, _usage_log = invoke_json_llm(
        SOCRATIC_JUDGE_LLM,
        messages,
        node="interviewer_golden_set_classify",
        schema=_SocraticFunctionGuess,
    )
    function = str((payload or {}).get("function", "")).strip()
    return function if function in SOCRATIC_FUNCTIONS else "others"


def _interviewer_one(interviewer_input: str, *, classify_function: bool) -> tuple[dict | None, dict | None]:
    """Send interviewer_input through the real interviewer LLM. Returns
    (predicted_dict_or_None, error_dict_or_None)."""
    try:
        payload, _usage_log = invoke_json_llm(
            node.interviewer_llm,
            [SystemMessage(content=interviewer_input)],
            node="interviewer_golden_set_eval",
            schema=InterviewerMove,
            accept=lambda candidate: parse_interviewer_output(candidate) is not None,
            retries=node.MAX_INTERVIEWER_JSON_RETRIES,
        )
    except Exception as exc:  # real API calls can time out / rate-limit / error
        return None, {"message": str(exc)}

    parsed = parse_interviewer_output(payload)
    if parsed is None:
        return None, {"message": "Interviewer LLM did not return a parseable JSON payload."}

    action, content, block_id, ready_for_judge, _reasoning = parsed
    predicted = {
        "action": action,
        "content": content,
        "block_id": block_id,
        "ready_for_judge": ready_for_judge,
        "socratic_function": "",
    }
    if classify_function and content:
        try:
            predicted["socratic_function"] = _classify_socratic_function(content)
        except Exception as exc:
            return predicted, {"message": f"Socratic-function classification failed: {exc}"}
    return predicted, None


def _grade(row: dict[str, str], predicted: dict[str, Any]) -> tuple[bool, list[str]]:
    """Grades one row against whichever expected_*/must_contain-style columns it has.
    Returns (correct, failed_checks) -- failed_checks lists the specific check(s) that
    tripped, for the per-row detail table."""
    failed: list[str] = []

    expected_action = row.get("expected_action", "").strip()
    if expected_action and predicted["action"] != expected_action:
        failed.append(f"action: expected '{expected_action}', got '{predicted['action']}'")

    expected_block_id = row.get("expected_block_id", "").strip()
    if expected_block_id and predicted["block_id"] != expected_block_id:
        failed.append(f"block_id: expected '{expected_block_id}', got '{predicted['block_id'] or '(empty)'}'")

    expected_ready = row.get("expected_ready_for_judge", "").strip()
    if expected_ready:
        expected_bool = expected_ready.lower() == "true"
        if predicted["ready_for_judge"] != expected_bool:
            failed.append(f"ready_for_judge: expected {expected_bool}, got {predicted['ready_for_judge']}")

    must_contain = _split_terms(row.get("must_contain", ""))
    if must_contain and not _contains_all(predicted["content"], must_contain):
        failed.append(f"must_contain: missing at least one of {must_contain}")

    must_not_contain = _split_terms(row.get("must_not_contain", "")) + _split_terms(row.get("forbidden_substrings", ""))
    if must_not_contain and not _contains_none(predicted["content"], must_not_contain):
        failed.append(f"must_not_contain: found a forbidden term from {must_not_contain}")

    expected_function = row.get("expected_socratic_function", "").strip()
    if expected_function and predicted["socratic_function"] != expected_function:
        failed.append(f"socratic_function: expected '{expected_function}', got '{predicted['socratic_function']}'")

    return (len(failed) == 0, failed)


def run(csv_path: Path, *, limit: int | None = None) -> dict[str, Any]:
    golden_set = _golden_set_name(csv_path)
    rows = _load_rows(csv_path, limit=limit)

    records: list[dict[str, Any]] = []
    n_correct = 0
    n_errors = 0

    for index, row in enumerate(rows, start=1):
        conversation_id = row.get("conversation_id", f"row_{index}")
        print(f"[{index}/{len(rows)}] {conversation_id} ({row.get('category', '')})", flush=True)

        classify_function = bool(row.get("expected_socratic_function", "").strip())
        predicted, error = _interviewer_one(row.get("interviewer_input", ""), classify_function=classify_function)

        if error is not None or predicted is None:
            n_errors += 1
            correct, failed_checks = False, []
        else:
            correct, failed_checks = _grade(row, predicted)
            if correct:
                n_correct += 1

        records.append(
            {
                "conversation_id": conversation_id,
                "predicted": predicted,
                "correct": correct,
                "failed_checks": failed_checks,
                "error": error,
            }
        )

    n_scored = len(rows) - n_errors
    accuracy = round(n_correct / n_scored, 4) if n_scored else None

    output = {
        "golden_set": golden_set,
        "csv_path": str(csv_path),
        "model": getattr(node.interviewer_llm, "model_name", ""),
        "socratic_judge_model": getattr(SOCRATIC_JUDGE_LLM, "model_name", ""),
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_total": len(rows),
        "n_scored": n_scored,
        "n_errors": n_errors,
        "n_correct": n_correct,
        "accuracy": accuracy,
        "records": records,
    }

    INTERVIEWER_EVAL_DIR.mkdir(parents=True, exist_ok=True)
    json_path = INTERVIEWER_EVAL_DIR / f"interviewer_golden_set_{golden_set}_results.json"
    json_path.write_text(json.dumps(output, ensure_ascii=True, indent=2), encoding="utf-8")

    print(
        f"\n{n_scored}/{len(rows)} rows scored ({n_errors} errored). "
        f"Accuracy: {accuracy if accuracy is not None else 'n/a'}."
    )
    print(f"Wrote results to {json_path}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an interviewer golden-set CSV against the real interviewer LLM and grade it."
    )
    parser.add_argument(
        "--csv",
        default=str(DEFAULT_CSV_PATH),
        help=f"Path to the golden-set CSV (default: {DEFAULT_CSV_PATH})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only evaluate the first N rows (default: all)",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        parser.error(f"CSV not found: {csv_path}")

    run(csv_path, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
