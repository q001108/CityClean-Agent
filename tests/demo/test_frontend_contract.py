from __future__ import annotations

import json
from pathlib import Path

from cityclean_agent.demo_playback import run_demo_playback
from cityclean_agent.frontend_contract import (
    FRONTEND_SCHEMA_VERSION,
    build_frontend_demo,
    write_frontend_fixture,
)


FRAME_IDS = (
    "initial",
    "before_event",
    "event_received",
    "tasks_released",
    "replanned",
    "final",
)
FIXTURE_PATH = Path("frontend/fixtures/vehicle_breakdown_replan.json")


def test_frontend_contract_is_json_serializable_with_complete_timeline() -> None:
    contract = build_frontend_demo(run_demo_playback())

    assert json.loads(json.dumps(contract, ensure_ascii=False)) == contract
    assert contract["schema_version"] == FRONTEND_SCHEMA_VERSION
    assert contract["scenario"] == {
        "scenario_id": "vehicle_breakdown_replan",
        "scenario_title": "车辆故障动态重规划",
        "demo_mode": "deterministic",
        "frame_count": 6,
    }
    assert tuple(item["id"] for item in contract["timeline"]) == FRAME_IDS
    assert [item["order"] for item in contract["timeline"]] == [1, 2, 3, 4, 5, 6]
    assert tuple(frame["id"] for frame in contract["frames"]) == FRAME_IDS


def test_contract_respects_event_verifier_and_metrics_phase_boundaries() -> None:
    frames = {frame["id"]: frame for frame in build_frontend_demo(run_demo_playback())["frames"]}

    assert frames["initial"]["event"] is None
    assert frames["before_event"]["event"] is None
    assert frames["event_received"]["event"]["event_type"] == "VEHICLE_BREAKDOWN"
    assert all(
        frames[frame_id]["verifier"]["state"] == "NOT_REACHED"
        for frame_id in FRAME_IDS[:4]
    )
    assert frames["replanned"]["verifier"] == {
        "state": "PASS",
        "valid": True,
        "violations": [],
    }
    assert frames["final"]["verifier"]["state"] == "PASS"
    assert all(frames[frame_id]["metrics"] is None for frame_id in FRAME_IDS[:-1])
    assert frames["final"]["metrics"] == {
        "task_completion_rate": 1.0,
        "urgent_task_completion_rate": 0.0,
        "average_response_time": 20.0,
        "overflow_count": 0,
        "total_distance": 22.0,
    }


def test_assignment_and_city_references_are_projected_from_real_playback() -> None:
    playback = run_demo_playback()
    frames = {frame["id"]: frame for frame in build_frontend_demo(playback)["frames"]}
    playback_frames = {frame["step"]: frame for frame in playback["frames"]}

    assert frames["replanned"]["assignment"] == {
        "before_assignments": [
            {"vehicle_id": route["vehicle_id"], "task_sequence": route["task_sequence"]}
            for route in playback_frames["initial"]["plan"]["vehicle_routes"]
        ],
        "released_task_ids": playback_frames["tasks_released"]["released_task_ids"],
        "after_assignments": [
            {"vehicle_id": route["vehicle_id"], "task_sequence": route["task_sequence"]}
            for route in playback_frames["replanned"]["plan"]["vehicle_routes"]
        ],
    }
    for frame in frames.values():
        city = frame["city"]
        node_ids = {node["node_id"] for node in city["nodes"]}
        waste_point_nodes = {
            point["waste_point_id"]: point["node_id"] for point in city["waste_points"]
        }
        assert all(
            road["from_node"] in node_ids and road["to_node"] in node_ids
            for road in city["roads"]
        )
        assert all(vehicle["node_id"] in node_ids for vehicle in city["vehicles"])
        assert all(
            task["node_id"] == waste_point_nodes[task["target_id"]]
            for task in city["tasks"]
        )


def test_fixture_matches_runtime_adapter_output() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert fixture == build_frontend_demo(run_demo_playback())


def test_fixture_writer_generates_the_runtime_adapter_payload(tmp_path: Path) -> None:
    generated_path = write_frontend_fixture(tmp_path / "frontend-demo.json")

    assert json.loads(generated_path.read_text(encoding="utf-8")) == build_frontend_demo(
        run_demo_playback()
    )
