"""Stable JSON contract for an independently implemented demo frontend.

This is a presentation-only projection of ``run_demo_playback()`` output.  It
does not modify the demo, workflow, or any Core schema.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cityclean_agent.demo_playback import run_demo_playback


FRONTEND_SCHEMA_VERSION = "1.0"

_SCENARIO_TITLES = {
    "vehicle_breakdown_replan": "车辆故障动态重规划",
}

_FRAME_PRESENTATION = {
    "initial": {"label": "初始调度", "phase_status": "INITIAL"},
    "before_event": {"label": "正常执行", "phase_status": "NORMAL_EXECUTION"},
    "event_received": {"label": "突发故障", "phase_status": "EVENT_RECEIVED"},
    "tasks_released": {"label": "任务释放", "phase_status": "TASKS_RELEASED"},
    "replanned": {"label": "动态重规划", "phase_status": "REPLANNED"},
    "final": {"label": "执行完成", "phase_status": "COMPLETED"},
}

_FRAME_IDS = tuple(_FRAME_PRESENTATION)


def build_frontend_demo(playback: Mapping[str, Any]) -> dict[str, Any]:
    """Project a frozen playback into the stable, JSON-only frontend contract.

    ``playback`` must be the six-frame object returned by
    :func:`cityclean_agent.demo_playback.run_demo_playback`.
    """

    source_frames = _validate_playback(playback)
    frames_by_id = {str(frame["step"]): frame for frame in source_frames}
    initial_assignments = _plan_routes(frames_by_id["initial"].get("plan"))
    released_task_ids = _string_list(
        frames_by_id["tasks_released"].get("released_task_ids")
    )
    replanned_assignments = _plan_routes(frames_by_id["replanned"].get("plan"))
    replanned_verifier = _mapping(frames_by_id["replanned"].get("verifier"))

    frames = [
        _frame_contract(
            frame_id,
            frames_by_id[frame_id],
            initial_assignments=initial_assignments,
            released_task_ids=released_task_ids,
            replanned_assignments=replanned_assignments,
            replanned_verifier=replanned_verifier,
        )
        for frame_id in _FRAME_IDS
    ]
    scenario_id = str(playback["scenario_id"])
    final = frames[-1]
    return {
        "schema_version": FRONTEND_SCHEMA_VERSION,
        "scenario": {
            "scenario_id": scenario_id,
            "scenario_title": _SCENARIO_TITLES.get(scenario_id, scenario_id),
            "demo_mode": "deterministic",
            "frame_count": len(frames),
        },
        "timeline": [
            {
                "id": frame["id"],
                "order": index,
                "label": frame["label"],
                "sim_time": frame["sim_time"],
            }
            for index, frame in enumerate(frames, start=1)
        ],
        "frames": frames,
        "summary": {
            "final_phase_status": final["phase_status"],
            "final_sim_time": final["sim_time"],
        },
    }


def write_frontend_fixture(path: str | Path) -> Path:
    """Generate a UTF-8 fixture directly from the real playback adapter."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            build_frontend_demo(run_demo_playback()),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return destination


def _validate_playback(playback: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if not isinstance(playback.get("scenario_id"), str):
        raise ValueError("playback scenario_id must be a string")
    frames = _sequence(playback.get("frames"))
    if not all(isinstance(frame, Mapping) for frame in frames):
        raise ValueError("playback frames must be objects")
    frame_ids = tuple(str(frame.get("step")) for frame in frames)
    if frame_ids != _FRAME_IDS:
        raise ValueError(f"unexpected playback frame order: {frame_ids!r}")
    return list(frames)


def _frame_contract(
    frame_id: str,
    source: Mapping[str, Any],
    *,
    initial_assignments: list[dict[str, Any]],
    released_task_ids: list[str],
    replanned_assignments: list[dict[str, Any]],
    replanned_verifier: Mapping[str, Any],
) -> dict[str, Any]:
    presentation = _FRAME_PRESENTATION[frame_id]
    return {
        "id": frame_id,
        "label": presentation["label"],
        "sim_time": source.get("sim_time"),
        "phase_status": presentation["phase_status"],
        "city": _city_contract(_mapping(source.get("state"))),
        "event": _event_contract(source),
        "decision": _decision_contract(source),
        "assignment": _assignment_contract(
            frame_id,
            initial_assignments,
            released_task_ids,
            replanned_assignments,
        ),
        "optimizer": _optimizer_contract(source),
        "verifier": _verifier_contract(frame_id, source, replanned_verifier),
        "metrics": _metrics_contract(source),
    }


def _city_contract(state: Mapping[str, Any]) -> dict[str, Any]:
    roads = [
        {
            "road_id": road.get("road_id"),
            "from_node": road.get("from_node"),
            "to_node": road.get("to_node"),
            "distance": road.get("distance"),
            "travel_time": road.get("travel_time"),
            "status": road.get("status"),
        }
        for road in _object_list(state.get("roads"))
    ]
    node_ids = sorted(
        {
            node_id
            for road in roads
            for node_id in (road["from_node"], road["to_node"])
            if isinstance(node_id, str)
        }
    )
    waste_points = [
        {
            "waste_point_id": point.get("waste_point_id"),
            "node_id": point.get("node_id"),
            "current_load": point.get("current_load"),
            "capacity": point.get("capacity"),
        }
        for point in _object_list(state.get("waste_points"))
    ]
    waste_point_nodes = {
        point["waste_point_id"]: point["node_id"]
        for point in waste_points
        if isinstance(point["waste_point_id"], str)
    }
    return {
        "nodes": [{"node_id": node_id} for node_id in node_ids],
        "roads": roads,
        "vehicles": [
            {
                "vehicle_id": vehicle.get("vehicle_id"),
                "node_id": vehicle.get("current_node_id"),
                "status": vehicle.get("status"),
                "load": vehicle.get("current_load"),
            }
            for vehicle in _object_list(state.get("vehicles"))
        ],
        "waste_points": waste_points,
        "tasks": [
            {
                "task_id": task.get("task_id"),
                "target_id": task.get("target_id"),
                "node_id": waste_point_nodes.get(task.get("target_id")),
                "status": task.get("status"),
                "priority": task.get("priority"),
            }
            for task in _object_list(state.get("tasks"))
        ],
    }


def _event_contract(source: Mapping[str, Any]) -> dict[str, Any] | None:
    event = _mapping(source.get("event"))
    if not event:
        active_events = _object_list(_mapping(source.get("state")).get("active_events"))
        event = active_events[0] if active_events else {}
    if not event:
        return None
    return {
        "event_type": event.get("event_type"),
        "severity": event.get("severity"),
        "location": event.get("location"),
        "description": event.get("description"),
    }


def _decision_contract(source: Mapping[str, Any]) -> dict[str, Any] | None:
    decision = _mapping(source.get("policy_decision"))
    if not decision:
        return None
    return {
        "risk_level": decision.get("risk_level"),
        "reasoning_summary": decision.get("reasoning_summary"),
        "response_deadline": decision.get("response_deadline"),
        "priority_targets": _string_list(decision.get("priority_targets")),
        "policy_profile": decision.get("policy_profile"),
    }


def _assignment_contract(
    frame_id: str,
    initial_assignments: list[dict[str, Any]],
    released_task_ids: list[str],
    replanned_assignments: list[dict[str, Any]],
) -> dict[str, Any]:
    phase = _FRAME_IDS.index(frame_id)
    return {
        "before_assignments": initial_assignments,
        "released_task_ids": released_task_ids if phase >= _FRAME_IDS.index("tasks_released") else None,
        "after_assignments": replanned_assignments if phase >= _FRAME_IDS.index("replanned") else None,
    }


def _optimizer_contract(source: Mapping[str, Any]) -> dict[str, Any] | None:
    optimizer = _mapping(source.get("optimizer"))
    if not optimizer:
        return None
    plan = _mapping(optimizer.get("plan"))
    return {
        "status": optimizer.get("status"),
        "reason": optimizer.get("reason"),
        "vehicle_routes": _plan_routes(plan),
        "unassigned_tasks": _string_list(plan.get("unassigned_tasks")),
    }


def _verifier_contract(
    frame_id: str,
    source: Mapping[str, Any],
    replanned_verifier: Mapping[str, Any],
) -> dict[str, Any]:
    verifier = _mapping(source.get("verifier"))
    if frame_id == "final":
        verifier = replanned_verifier
    if not verifier or frame_id not in {"replanned", "final"}:
        return {"state": "NOT_REACHED", "valid": None, "violations": None}
    valid = verifier.get("valid")
    return {
        "state": "PASS" if valid is True else "FAIL",
        "valid": valid,
        "violations": _object_list(verifier.get("violations")),
    }


def _metrics_contract(source: Mapping[str, Any]) -> dict[str, Any] | None:
    metrics = _mapping(source.get("metrics"))
    if not metrics:
        return None
    return {
        "task_completion_rate": metrics.get("task_completion_rate"),
        "urgent_task_completion_rate": metrics.get("urgent_task_completion_rate"),
        "average_response_time": metrics.get("average_response_time"),
        "overflow_count": metrics.get("overflow_count"),
        "total_distance": metrics.get("total_distance"),
    }


def _plan_routes(plan: Any) -> list[dict[str, Any]]:
    return [
        {
            "vehicle_id": route.get("vehicle_id"),
            "task_sequence": _string_list(route.get("task_sequence")),
        }
        for route in _object_list(_mapping(plan).get("vehicle_routes"))
    ]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, (list, tuple)) else ()


def _object_list(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in _sequence(value) if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    return [item for item in _sequence(value) if isinstance(item, str)]
