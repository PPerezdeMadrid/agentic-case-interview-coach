from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig


MAIN_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = MAIN_DIR / "artifacts"
RUNS_DB_PATH = ARTIFACTS_DIR / "runs.sqlite"


def ensure_runs_db() -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(RUNS_DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                graph_name TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                scenario_ref TEXT,
                case_prompt TEXT,
                turn_index INTEGER,
                judge_round INTEGER,
                enough_evidence INTEGER NOT NULL,
                focus_areas_json TEXT NOT NULL,
                transcript_json TEXT NOT NULL,
                case_performance_json TEXT NOT NULL,
                quality_dialog_json TEXT NOT NULL,
                final_feedback TEXT,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_graph_created_at ON runs(graph_name, created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_thread_id ON runs(thread_id)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_state_traces (
                trace_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                graph_name TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                node_name TEXT NOT NULL,
                actor TEXT NOT NULL,
                scenario_ref TEXT,
                turn_index_before INTEGER,
                turn_index_after INTEGER,
                judge_round_before INTEGER,
                judge_round_after INTEGER,
                enough_evidence_before INTEGER,
                enough_evidence_after INTEGER,
                focus_areas_before_json TEXT NOT NULL,
                focus_areas_after_json TEXT NOT NULL,
                changed_fields_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_state_traces_run_step ON agent_state_traces(run_id, step_index)"
        )

    return RUNS_DB_PATH


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _read_value(container: Any, key: str) -> Any:
    if isinstance(container, Mapping):
        return container.get(key)
    return getattr(container, key, None)


def _iter_container_values(container: Any) -> list[Any]:
    if isinstance(container, Mapping):
        return list(container.values())
    if isinstance(container, (list, tuple)):
        return list(container)
    values = _read_value(container, "__dict__")
    if isinstance(values, dict):
        return list(values.values())
    return []


def _find_first_string(
    container: Any,
    keys: tuple[str, ...],
    *,
    max_depth: int = 4,
) -> str | None:
    seen: set[int] = set()

    def _walk(value: Any, depth: int) -> str | None:
        if value is None or depth > max_depth:
            return None

        value_id = id(value)
        if value_id in seen:
            return None
        seen.add(value_id)

        for key in keys:
            candidate = _read_value(value, key)
            if candidate is None:
                continue
            text = str(candidate).strip()
            if text:
                return text

        for nested in _iter_container_values(value):
            match = _walk(nested, depth + 1)
            if match:
                return match

        return None

    return _walk(container, 0)


def _extract_thread_id(config: Any) -> str:
    thread_id = _find_first_string(
        config,
        (
            "thread_id",
            "threadId",
            "conversation_id",
            "conversationId",
            "session_id",
            "sessionId",
            "run_id",
            "runId",
        ),
    )
    return thread_id or "unknown"


def resolve_thread_id(state: dict[str, Any] | None = None, config: Any = None) -> str:
    if isinstance(state, dict):
        state_thread_id = str(state.get("thread_id", "") or "").strip()
        if state_thread_id:
            return state_thread_id
    return _extract_thread_id(config)


def _extract_scenario_ref(state: dict[str, Any], config: Any) -> str:
    state_scenario_ref = str(state.get("scenario_ref", "") or "").strip()
    if state_scenario_ref:
        return state_scenario_ref

    scenario_ref = _find_first_string(
        config,
        (
            "scenario_ref",
            "scenarioRef",
            "scenario_id",
            "scenarioId",
        ),
    )
    if scenario_ref:
        return scenario_ref

    case_data = state.get("case_data", {})
    if isinstance(case_data, dict):
        source_path = str(case_data.get("source_path", "") or "").strip()
        if source_path:
            return Path(source_path).stem

    return ""


def _extract_final_feedback(transcript: Any) -> str | None:
    if not isinstance(transcript, list):
        return None

    for line in reversed(transcript):
        if not isinstance(line, str):
            continue
        if line.startswith("Give Feedback: "):
            return line.removeprefix("Give Feedback: ").strip() or None

    return None


def _resolve_run_id(state: dict[str, Any], config: Any = None) -> str:
    state_run_id = str(state.get("run_id", "") or "").strip()
    if state_run_id:
        return state_run_id

    config_run_id = _find_first_string(
        config,
        (
            "run_id",
            "runId",
        ),
    )
    if config_run_id:
        return config_run_id

    return str(uuid.uuid4())


def _snapshot_trace_relevant_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "turn_index": int(state.get("turn_index", 0) or 0),
        "judge_round": int(state.get("judge_round", 0) or 0),
        "enough_evidence": bool(state.get("enough_evidence", False)),
        "focus_areas": state.get("focus_areas", []),
        "transcript": state.get("transcript", []),
        "data_gathered": state.get("data_gathered", []),
        "case_guidance": state.get("case_guidance", ""),
        "case_prompt": state.get("case_prompt", ""),
        "retrieved_profitability_context": state.get("retrieved_profitability_context", []),
        "case_performance": state.get("case_performance", {}),
        "quality_dialog": state.get("quality_dialog", {}),
    }


def _compute_state_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    changes: dict[str, dict[str, Any]] = {}
    for key in sorted(set(before) | set(after)):
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value == after_value:
            continue
        changes[key] = {
            "before": before_value,
            "after": after_value,
        }
    return changes


def persist_agent_state_trace(
    *,
    graph_name: str,
    node_name: str,
    actor: str,
    state_before: dict[str, Any],
    state_after: dict[str, Any],
    config: Any = None,
) -> str:
    db_path = ensure_runs_db()
    trace_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    before_snapshot = _snapshot_trace_relevant_state(state_before)
    after_snapshot = _snapshot_trace_relevant_state(state_after)
    changes = _compute_state_changes(before_snapshot, after_snapshot)

    with sqlite3.connect(db_path, timeout=30) as connection:
        connection.execute(
            """
            INSERT INTO agent_state_traces (
                trace_id,
                run_id,
                graph_name,
                thread_id,
                step_index,
                node_name,
                actor,
                scenario_ref,
                turn_index_before,
                turn_index_after,
                judge_round_before,
                judge_round_after,
                enough_evidence_before,
                enough_evidence_after,
                focus_areas_before_json,
                focus_areas_after_json,
                changed_fields_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id,
                _resolve_run_id(state_after, config),
                graph_name,
                resolve_thread_id(state_after, config),
                int(state_after.get("trace_step_index", 0) or 0),
                node_name,
                actor,
                _extract_scenario_ref(state_after, config),
                before_snapshot["turn_index"],
                after_snapshot["turn_index"],
                before_snapshot["judge_round"],
                after_snapshot["judge_round"],
                1 if before_snapshot["enough_evidence"] else 0,
                1 if after_snapshot["enough_evidence"] else 0,
                _json_dumps(before_snapshot["focus_areas"]),
                _json_dumps(after_snapshot["focus_areas"]),
                _json_dumps(changes),
                created_at,
            ),
        )

    return trace_id


def persist_run(graph_name: str, state: dict[str, Any], config: Any = None) -> str:
    db_path = ensure_runs_db()
    run_id = _resolve_run_id(state, config)
    transcript = state.get("transcript", [])
    created_at = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(db_path, timeout=30) as connection:
        connection.execute(
            """
            INSERT INTO runs (
                run_id,
                graph_name,
                thread_id,
                scenario_ref,
                case_prompt,
                turn_index,
                judge_round,
                enough_evidence,
                focus_areas_json,
                transcript_json,
                case_performance_json,
                quality_dialog_json,
                final_feedback,
                state_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                graph_name,
                resolve_thread_id(state, config),
                _extract_scenario_ref(state, config),
                str(state.get("case_prompt", "") or ""),
                int(state.get("turn_index", 0) or 0),
                int(state.get("judge_round", 0) or 0),
                1 if bool(state.get("enough_evidence", False)) else 0,
                _json_dumps(state.get("focus_areas", [])),
                _json_dumps(transcript),
                _json_dumps(state.get("case_performance", {})),
                _json_dumps(state.get("quality_dialog", {})),
                _extract_final_feedback(transcript),
                _json_dumps(state),
                created_at,
            ),
        )

    return run_id


def make_persist_run_node(graph_name: str):
    def persist_run_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        persist_run(graph_name=graph_name, state=state, config=config)
        return {}

    return persist_run_node


def make_trace_node(
    graph_name: str,
    node_name: str,
    actor: str,
    node_fn,
):
    def traced_node(
        state: dict[str, Any],
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        state_before = dict(state)
        update = node_fn(state)
        run_id = _resolve_run_id(state_before, config)
        step_index = int(state_before.get("trace_step_index", 0) or 0) + 1
        update_with_meta = dict(update)
        update_with_meta["run_id"] = run_id
        update_with_meta["trace_step_index"] = step_index

        state_after = dict(state_before)
        state_after.update(update_with_meta)
        persist_agent_state_trace(
            graph_name=graph_name,
            node_name=node_name,
            actor=actor,
            state_before=state_before,
            state_after=state_after,
            config=config,
        )
        return update_with_meta

    return traced_node
