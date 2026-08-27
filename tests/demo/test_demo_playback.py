from __future__ import annotations

import io
import json

from cityclean_agent.demo import run_demo
from cityclean_agent.demo_playback import SCENARIO_ID, SCHEMA_VERSION, run_demo_playback
from cityclean_agent.domain.enums import ServiceTaskStatus, VehicleStatus


FRAME_STEPS = (
    "initial",
    "before_event",
    "event_received",
    "tasks_released",
    "replanned",
    "final",
)


def test_playback_runs_is_json_serializable_and_has_stable_frame_order() -> None:
    playback = run_demo_playback()

    assert json.loads(json.dumps(playback)) == playback
    assert playback["schema_version"] == SCHEMA_VERSION
    assert playback["scenario_id"] == SCENARIO_ID
    assert tuple(frame["step"] for frame in playback["frames"]) == FRAME_STEPS
    assert [frame["sim_time"] for frame in playback["frames"]] == [0, 10, 10, 10, 10, 30]


def test_every_frame_projects_the_required_city_state_and_runtime_stats() -> None:
    playback = run_demo_playback()

    for frame in playback["frames"]:
        state = frame["state"]
        assert {"roads", "vehicles", "waste_points", "tasks", "active_plan", "active_events"} <= set(state)
        assert set(frame["runtime_stats"]) == {"total_distance", "overflow_count"}
        assert all(
            {"road_id", "from_node", "to_node", "distance", "travel_time", "status"}
            <= set(road)
            for road in state["roads"]
        )


def test_event_and_task_release_frames_contain_actual_citysim_state_changes() -> None:
    frames = {frame["step"]: frame for frame in run_demo_playback()["frames"]}
    event = frames["event_received"]["event"]
    vehicle_statuses = {
        vehicle["vehicle_id"]: vehicle["status"]
        for vehicle in frames["event_received"]["state"]["vehicles"]
    }

    assert all(
        vehicle_statuses[vehicle_id] == VehicleStatus.BROKEN.value
        for vehicle_id in event["affected_entities"]
    )
    released = frames["tasks_released"]
    released_task_ids = released["released_task_ids"]
    task_statuses = {
        task["task_id"]: task["status"] for task in released["state"]["tasks"]
    }
    assert released_task_ids
    assert all(task_statuses[task_id] == ServiceTaskStatus.PENDING.value for task_id in released_task_ids)
    assert released["completed_task_ids"]
    assert released["state"]["active_plan"] is None


def test_replanned_frame_is_verified_and_playback_matches_fixed_demo_final_facts() -> None:
    playback = run_demo_playback()
    frames = {frame["step"]: frame for frame in playback["frames"]}
    demo_result = run_demo(io.StringIO())

    replanned = frames["replanned"]
    assert replanned["workflow_status"] == "SUCCESS"
    assert replanned["verifier"]["valid"] is True
    assert len(replanned["verifier"]["violations"]) == 0
    assert replanned["plan_changes"]["changed_routes"]
    assert frames["tasks_released"]["released_task_ids"] == list(
        demo_result.released_task_ids
    )
    assert frames["before_event"]["sim_time"] == demo_result.incident_time

    final_state = frames["final"]["state"]
    assert {
        task["task_id"]: task["status"] for task in final_state["tasks"]
    } == {
        task_id: task.status.value for task_id, task in demo_result.final_state.tasks.items()
    }
    assert {
        vehicle["vehicle_id"]: (
            vehicle["current_node_id"],
            vehicle["current_load"],
            vehicle["status"],
            vehicle["assigned_tasks"],
        )
        for vehicle in final_state["vehicles"]
    } == {
        vehicle_id: (
            vehicle.current_node_id,
            vehicle.current_load,
            vehicle.status.value,
            vehicle.assigned_tasks,
        )
        for vehicle_id, vehicle in demo_result.final_state.vehicles.items()
    }
    assert final_state["active_plan"] == replanned["plan"]
    assert frames["final"]["metrics"] == {
        "task_completion_rate": demo_result.final_metrics.task_completion_rate,
        "urgent_task_completion_rate": demo_result.final_metrics.urgent_task_completion_rate,
        "average_response_time": demo_result.final_metrics.average_response_time,
        "overflow_count": demo_result.final_metrics.overflow_count,
        "total_distance": demo_result.final_metrics.total_distance,
    }


def test_playback_is_deterministic() -> None:
    assert run_demo_playback() == run_demo_playback()
