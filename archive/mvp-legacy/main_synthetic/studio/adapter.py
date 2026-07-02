from __future__ import annotations

from typing import Any


def get_opening_prompt(case_data: dict[str, Any]) -> dict[str, Any] | None:
    """Return the opening prompt block for the candidate."""
    opening_block = case_data.get("opening_block")
    if isinstance(opening_block, dict):
        return opening_block

    for block in get_case_blocks_by_type(case_data, "prompt"):
        if block.get("block_type") == "prompt":
            return block
    return None


def get_candidate_visible_blocks(case_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return all blocks the candidate is allowed to see.

    In practice these are also the candidate-visible exhibits.
    """
    visible_blocks = case_data.get("visible_blocks", [])
    if not isinstance(visible_blocks, list):
        return []
    return [block for block in visible_blocks if isinstance(block, dict)]


def get_hidden_guidance_blocks(case_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return interviewer-only guidance blocks."""
    return get_case_blocks_by_type(case_data, "guidance")


def get_final_recommendation_blocks(case_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the final recommendation blocks from the case."""
    return get_case_blocks_by_type(case_data, "final_recommendation")


def get_case_blocks_by_type(case_data: dict[str, Any], block_type: str) -> list[dict[str, Any]]:
    """Return all case blocks matching a given block_type."""
    blocks_by_type = case_data.get("blocks_by_type", {})
    if isinstance(blocks_by_type, dict):
        blocks = blocks_by_type.get(block_type, [])
        if isinstance(blocks, list):
            return [block for block in blocks if isinstance(block, dict)]

    case_content = case_data.get("case_content", [])
    if not isinstance(case_content, list):
        return []

    return [
        block
        for block in case_content
        if isinstance(block, dict) and block.get("block_type") == block_type
    ]


def get_case_block_by_id(case_data: dict[str, Any], block_id: str) -> dict[str, Any] | None:
    """Return one case block by block_id."""
    case_content = case_data.get("case_content", [])
    if not isinstance(case_content, list):
        return None

    for block in case_content:
        if isinstance(block, dict) and block.get("block_id") == block_id:
            return block
    return None
