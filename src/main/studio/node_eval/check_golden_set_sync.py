"""Checks that each baseline golden-set CSV has the same conversation_ids as the judge/interviewer CSV it mirrors -- catches drift when upstream ITEMS grows but the baseline builder isn't re-run. Compares by id set, not row count, so same-size-but-different-ids drift is caught too.

Usage: make golden-set-sync-check
"""
from __future__ import annotations

import csv
from pathlib import Path

DATABASE_DIR = Path(__file__).resolve().parents[3] / "database" / "node_eval"

# turn_control has no baseline counterpart (see build_baseline_golden_sets.py), so it's not one of these pairs.
PAIRS = [
    ("judge_eval/judge_golden_set_worldcup.csv", "baseline_eval/baseline_golden_set_worldcup.csv"),
    (
        "interviewer_eval/interviewer_golden_set_socratic_function.csv",
        "baseline_eval/baseline_golden_set_socratic_function.csv",
    ),
    (
        "interviewer_eval/interviewer_golden_set_evidence_handling.csv",
        "baseline_eval/baseline_golden_set_evidence_handling.csv",
    ),
    ("interviewer_eval/interviewer_golden_set_guardrail.csv", "baseline_eval/baseline_golden_set_guardrail.csv"),
]


def _read_ids(relative_path: str) -> set[str]:
    path = DATABASE_DIR / relative_path
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["conversation_id"] for row in csv.DictReader(handle)}


def main() -> int:
    ok = True
    for source_rel, baseline_rel in PAIRS:
        source_ids = _read_ids(source_rel)
        baseline_ids = _read_ids(baseline_rel)
        missing_from_baseline = source_ids - baseline_ids
        extra_in_baseline = baseline_ids - source_ids

        if not missing_from_baseline and not extra_in_baseline:
            print(f"OK   {baseline_rel} ({len(baseline_ids)} rows, matches {source_rel})")
            continue

        ok = False
        print(f"DRIFT {baseline_rel} out of sync with {source_rel}:")
        if missing_from_baseline:
            print(f"  missing from baseline: {sorted(missing_from_baseline)}")
        if extra_in_baseline:
            print(f"  extra in baseline (not in source): {sorted(extra_in_baseline)}")

    if not ok:
        print(
            "\nRe-run the matching baseline builder (build_baseline_judge_golden_set.py "
            "or build_baseline_golden_sets.py) to fix drift."
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
