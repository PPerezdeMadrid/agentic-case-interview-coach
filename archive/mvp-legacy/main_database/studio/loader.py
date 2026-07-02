from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "config.json"


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


def _load_config() -> dict[str, Any]:
    raw_config = _read_json(CONFIG_PATH)
    if not isinstance(raw_config, dict):
        raise LoaderError(f"Config file must contain a JSON object: {CONFIG_PATH}")
    return raw_config


_CONFIG = _load_config()
_PATHS = _CONFIG.get("paths", {})
_RUNTIME_DEFAULTS = _CONFIG.get("runtime_defaults", {})

SCENARIOS_DIR = REPO_ROOT / str(_PATHS.get("scenarios_dir", "scenarios"))
CASE_DIRS = tuple(
    REPO_ROOT / str(case_dir)
    for case_dir in _PATHS.get(
        "case_dirs",
        [
            "database/harvard_cases",
            "database/duke_cases",
            "database/agsm_cases",
        ],
    )
)
RUBRIC_PATH = REPO_ROOT / str(_PATHS.get("rubric_path", "scenarios/rubric/rubric.json"))
CASE_METADATA_PATH = REPO_ROOT / str(_PATHS.get("case_metadata_path", "database/case_metadata.json"))
DEFAULT_RUBRIC_ID = str(_RUNTIME_DEFAULTS.get("default_rubric_id", "default_consulting_rubric"))
DEFAULT_MAX_JUDGE_ROUNDS = int(_RUNTIME_DEFAULTS.get("default_max_judge_rounds", 2))
ROUNDS_TILL_JUDGE = int(_RUNTIME_DEFAULTS.get("rounds_till_judge", 3))


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
    raise LoaderError(f"Scenario not found for reference '{scenario_ref}'.")


def _find_case_path(case_id: str) -> Path:
    for directory in CASE_DIRS:
        candidate_path = directory / f"{case_id}.json"
        if candidate_path.exists():
            return candidate_path
    raise LoaderError(f"Case JSON not found for case_id '{case_id}'.")


def _list_case_ids_from_dirs() -> list[str]:
    case_ids: list[str] = []
    for directory in CASE_DIRS:
        if not directory.exists():
            continue
        case_ids.extend(path.stem for path in directory.glob("*.json"))
    return sorted(set(case_ids))


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


def load_case_metadata() -> list[dict[str, Any]]:
    """Load the case metadata catalog."""
    data = _read_json(CASE_METADATA_PATH)
    if not isinstance(data, list):
        raise LoaderError(f"Case metadata file must contain a JSON array: {CASE_METADATA_PATH}")
    return [item for item in data if isinstance(item, dict)]


def list_available_cases() -> list[dict[str, Any]]:
    """Return the available case metadata entries."""
    entries = []
    for item in load_case_metadata():
        metadata = item.get("case_metadata", {})
        if isinstance(metadata, dict):
            entries.append(metadata)
    return entries


def _normalize_case_lookup(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def choose_case(case_name: str | None = None, seed: int | None = None) -> dict[str, Any]:
    """
    Choose a case by name or case_id.

    If case_name is omitted, a random case is returned.
    """
    available_cases = list_available_cases()
    if not available_cases:
        raise LoaderError("No cases found in case metadata.")

    if case_name is None:
        chooser = random.Random(seed)
        return chooser.choice(available_cases)

    target = _normalize_case_lookup(case_name)
    matches = [
        metadata
        for metadata in available_cases
        if target in {
            _normalize_case_lookup(str(metadata.get("case_id", ""))),
            _normalize_case_lookup(str(metadata.get("case_name", ""))),
        }
    ]

    if not matches:
        fallback_matches = [
            case_id
            for case_id in _list_case_ids_from_dirs()
            if _normalize_case_lookup(case_id) == target
        ]
        if len(fallback_matches) == 1:
            case_id = fallback_matches[0]
            return {
                "case_id": case_id,
                "case_name": case_id,
            }
        if len(fallback_matches) > 1:
            raise LoaderError(f"Case name '{case_name}' is ambiguous. Matches: {fallback_matches}")
        raise LoaderError(f"No case found for '{case_name}'.")
    if len(matches) > 1:
        raise LoaderError(
            f"Case name '{case_name}' is ambiguous. Matches: {[match.get('case_name') for match in matches]}"
        )
    return matches[0]


def load_selected_case(case_name: str | None = None, seed: int | None = None) -> dict[str, Any]:
    """Load one case by name or choose a random case if no name is provided."""
    metadata = choose_case(case_name=case_name, seed=seed)
    raw_case = load_case(str(metadata.get("case_id", "")))
    case = adapt_case(raw_case)

    if case["opening_block"] is None:
        raise LoaderError(f"Case '{metadata.get('case_id', '')}' does not contain a prompt block.")

    return {
        "case_metadata": metadata,
        "case": case,
    }


def adapt_scenario(raw_scenario: dict[str, Any]) -> dict[str, Any]:
    """Return the minimal runtime shape needed from a scenario JSON."""
    scenario_id = str(raw_scenario.get("scenario_id", "")).strip()
    case_id = str(raw_scenario.get("case_id", "")).strip()
    candidate_profile = raw_scenario.get("candidate_profile", {})
    ground_truth = raw_scenario.get("ground_truth", {})

    if not scenario_id:
        raise LoaderError("Scenario is missing 'scenario_id'.")
    if not case_id:
        raise LoaderError(f"Scenario '{scenario_id}' is missing 'case_id'.")
    if not isinstance(candidate_profile, dict):
        raise LoaderError(f"Scenario '{scenario_id}' has invalid 'candidate_profile'.")
    if not isinstance(ground_truth, dict):
        raise LoaderError(f"Scenario '{scenario_id}' has invalid 'ground_truth'.")

    return {
        "scenario_id": scenario_id,
        "evaluation_item_id": str(raw_scenario.get("evaluation_item_id", "")).strip(),
        "case_id": case_id,
        "rubric_id": DEFAULT_RUBRIC_ID,
        "candidate_model": raw_scenario.get("candidate_model", {}),
        "candidate_profile": candidate_profile,
        "ground_truth": ground_truth,
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
            "expected_analysis": [block for block in blocks if block["block_type"] == "expected_analysis"],
            "final_recommendation": [
                block for block in blocks if block["block_type"] == "final_recommendation"
            ],
        },
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
