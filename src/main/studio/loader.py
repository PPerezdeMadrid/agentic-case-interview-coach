from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]


class LoaderError(ValueError):
    """Raised when a scenario, case, or rubric cannot be loaded."""


def _read_json(path: Path) -> dict[str, Any] | list[Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise LoaderError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LoaderError(f"Invalid JSON in {path}: {exc}") from exc


def _coerce_path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


SCENARIOS_DIR = REPO_ROOT / "scenarios" / "synthetic-based"
CASE_DIRS = (REPO_ROOT / "synthetic-dataset",)
RUBRIC_PATH = REPO_ROOT / "scenarios" / "rubric" / "rubric.json"
DEFAULT_RUBRIC_ID = "default_consulting_rubric"
DEFAULT_MAX_JUDGE_ROUNDS = 2
ROUNDS_TILL_JUDGE = 3


def _normalize_case_block(block: dict[str, Any]) -> dict[str, Any]:
    block_type = str(block.get("block_type", "")).strip()
    content = str(block.get("content", "")).strip()

    return {
        "block_id": block.get("block_id", ""),
        "title": block.get("title", ""),
        "source_page": block.get("source_page"),
        "visible_to_candidate": bool(block.get("visible_to_candidate", False)),
        "image": block.get("image"),
        "content": content,
        "block_type": block_type,
    }


def _find_scenario_path(scenario_ref: str | Path) -> Path:
    path = _coerce_path(scenario_ref)
    if path.exists():
        return path.resolve()

    scenario_id = path.stem if path.suffix else str(path)
    candidate_path = SCENARIOS_DIR / f"{scenario_id}.json"
    if candidate_path.exists():
        return candidate_path

    matches = sorted(SCENARIOS_DIR.glob(f"{scenario_id}*.json"))
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise LoaderError(
            f"Scenario reference '{scenario_ref}' is ambiguous. Matches: {[match.name for match in matches]}"
        )

    # Fall back to resolving by scenario_id stored inside the synthetic scenario JSON.
    for candidate in _list_scenario_paths():
        data = _read_json(candidate)
        if isinstance(data, dict) and str(data.get("scenario_id", "")).strip() == scenario_id:
            return candidate

    raise LoaderError(f"Scenario not found for reference '{scenario_ref}'.")


def _list_scenario_paths() -> list[Path]:
    if not SCENARIOS_DIR.exists():
        return []
    return sorted(
        path
        for path in SCENARIOS_DIR.glob("scenario_*.json")
        if path.is_file() and not path.name.startswith("scenario_template")
    )


def _find_case_path(case_id: str) -> Path:
    for directory in CASE_DIRS:
        candidate_path = directory / f"{case_id}.json"
        if candidate_path.exists():
            return candidate_path
    raise LoaderError(f"Case JSON not found for case_id '{case_id}'.")


def load_scenario(scenario_ref: str | Path) -> dict[str, Any]:
    """Load a raw scenario JSON file by path or scenario id."""
    path = _find_scenario_path(scenario_ref)
    data = _read_json(path)
    if not isinstance(data, dict):
        raise LoaderError(f"Scenario file must contain a JSON object: {path}")
    data["_source_path"] = str(path)
    return data


def load_case(case_id: str) -> dict[str, Any]:
    """Load a raw case JSON file by case_id."""
    path = _find_case_path(case_id)
    data = _read_json(path)
    if not isinstance(data, dict):
        raise LoaderError(f"Case file must contain a JSON object: {path}")
    data["_source_path"] = str(path)
    return data


def load_rubric(rubric_id: str = DEFAULT_RUBRIC_ID) -> dict[str, Any]:
    """
    Load the shared rubric.

    The source repo currently exposes a single rubric file, so rubric_id is accepted
    for runtime compatibility but resolved to the shared JSON asset.
    """
    if rubric_id != DEFAULT_RUBRIC_ID:
        raise LoaderError(
            f"Unsupported rubric_id '{rubric_id}'. Available rubric_id: '{DEFAULT_RUBRIC_ID}'."
        )

    data = _read_json(RUBRIC_PATH)
    if not isinstance(data, dict):
        raise LoaderError(f"Rubric file must contain a JSON object: {RUBRIC_PATH}")
    data["_source_path"] = str(RUBRIC_PATH)
    return data


def choose_scenario(scenario_ref: str | None = None, seed: int | None = None) -> dict[str, Any]:
    """Choose a synthetic scenario by reference or at random if omitted."""
    if scenario_ref is not None:
        return load_scenario(scenario_ref)

    available_paths = _list_scenario_paths()
    if not available_paths:
        raise LoaderError(f"No synthetic scenarios found in: {SCENARIOS_DIR}")

    chooser = random.Random(seed)
    return load_scenario(chooser.choice(available_paths))


def adapt_scenario(raw_scenario: dict[str, Any]) -> dict[str, Any]:
    """Return the minimal runtime shape needed from a scenario JSON."""
    scenario_id = str(raw_scenario.get("scenario_id", "")).strip()
    case_id = str(raw_scenario.get("case_id", "")).strip()
    candidate_profile = raw_scenario.get("candidate_profile", {})
    expected_scores = candidate_profile.get("expected_scores", {})

    if not scenario_id:
        raise LoaderError("Scenario is missing 'scenario_id'.")
    if not case_id:
        raise LoaderError(f"Scenario '{scenario_id}' is missing 'case_id'.")
    if not isinstance(candidate_profile, dict):
        raise LoaderError(f"Scenario '{scenario_id}' has invalid 'candidate_profile'.")
    if not isinstance(expected_scores, dict):
        raise LoaderError(f"Scenario '{scenario_id}' has invalid 'candidate_profile.expected_scores'.")

    return {
        "scenario_id": scenario_id,
        "case_id": case_id,
        "rubric_id": DEFAULT_RUBRIC_ID,
        "candidate_model": raw_scenario.get("candidate_model", {}),
        "candidate_profile": candidate_profile,
        "expected_scores": expected_scores,
        "max_judge_rounds": DEFAULT_MAX_JUDGE_ROUNDS,
        "source_path": raw_scenario.get("_source_path", ""),
    }


def adapt_case(raw_case: dict[str, Any]) -> dict[str, Any]:
    """Return a simple case structure without runtime heuristics."""
    raw_blocks = raw_case.get("case_content", [])
    if not isinstance(raw_blocks, list):
        raise LoaderError("Case JSON has invalid 'case_content'; expected a list.")

    blocks = [_normalize_case_block(block) for block in raw_blocks if isinstance(block, dict)]
    opening_block = next(
        (
            block
            for block in blocks
            if block["block_type"] == "prompt"
        ),
        None,
    )

    return {
        "case_content": blocks,
        "opening_block": opening_block,
        "visible_blocks": [block for block in blocks if block["visible_to_candidate"]],
        "hidden_blocks": [block for block in blocks if not block["visible_to_candidate"]],
        "blocks_by_type": {
            "prompt": [block for block in blocks if block["block_type"] == "prompt"],
            "guidance": [block for block in blocks if block["block_type"] == "guidance"],
            "data": [block for block in blocks if block["block_type"] == "data"],
            "math": [block for block in blocks if block["block_type"] == "math"],
            "creative": [block for block in blocks if block["block_type"] == "creative"],
            "expected_analysis": [block for block in blocks if block["block_type"] == "expected_analysis"],
            "final_recommendation": [
                block for block in blocks if block["block_type"] == "final_recommendation"
            ],
        },
        "knowledge_sources": raw_case.get("knowledge_sources", []),
        "source_path": raw_case.get("_source_path", ""),
    }


def adapt_rubric(raw_rubric: dict[str, Any]) -> dict[str, Any]:
    """Adapt the shared rubric JSON into a stable runtime structure."""
    rubric_sections = raw_rubric.get("rubric_sections", {})
    if not isinstance(rubric_sections, dict):
        raise LoaderError("Rubric JSON has invalid 'rubric_sections'; expected an object.")

    dimensions = []
    for dimension_id, config in rubric_sections.items():
        if not isinstance(config, dict):
            continue
        dimensions.append(
            {
                "dimension_id": dimension_id,
                "applies_to": config.get("applies_to", []),
                "description": config.get("description", ""),
                "criteria": config.get("criteria", {}),
            }
        )

    return {
        "rubric_id": DEFAULT_RUBRIC_ID,
        "rubric_name": raw_rubric.get("rubric_name", "Consulting Case Interview Rubric"),
        "score_scale": raw_rubric.get("score_scale", {}),
        "dimensions": dimensions,
        "source": raw_rubric.get("source", ""),
        "source_url": raw_rubric.get("source_url", ""),
        "source_path": raw_rubric.get("_source_path", ""),
    }


def load_simulation_bundle(scenario_ref: str | Path) -> dict[str, Any]:
    """
    Load and adapt one scenario, its referenced case, and the shared rubric.

    Returns a runtime-ready bundle without requiring any edits to the source JSON files.
    """
    raw_scenario = load_scenario(scenario_ref)
    scenario = adapt_scenario(raw_scenario)
    raw_case = load_case(scenario["case_id"])
    case = adapt_case(raw_case)
    rubric = adapt_rubric(load_rubric(scenario["rubric_id"]))

    if case["opening_block"] is None:
        raise LoaderError(f"Case '{scenario['case_id']}' does not contain a prompt block.")

    return {
        "scenario": scenario,
        "case": case,
        "rubric": rubric,
    }


def load_selected_simulation_bundle(
    scenario_ref: str | None = None, seed: int | None = None
) -> dict[str, Any]:
    """Load one synthetic scenario bundle by reference or choose a random one."""
    raw_scenario = choose_scenario(scenario_ref=scenario_ref, seed=seed)
    source_path = str(raw_scenario.get("_source_path", "")).strip()
    if not source_path:
        raise LoaderError("Selected scenario is missing its source path.")
    return load_simulation_bundle(source_path)
