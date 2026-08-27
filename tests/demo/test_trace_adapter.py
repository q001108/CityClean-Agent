from __future__ import annotations

import io
import json

from cityclean_agent.demo import run_demo
from cityclean_agent.demo_trace_adapter import (
    NOT_RECORDED_IN_BASELINE,
    SCHEMA_VERSION,
    build_demo_trace,
)


def test_run_demo_result_builds_a_json_serializable_trace() -> None:
    result = run_demo(io.StringIO())

    trace = build_demo_trace(result)

    assert json.loads(json.dumps(trace, ensure_ascii=False)) == trace
    assert trace["schema_version"] == SCHEMA_VERSION
    assert trace["scenario_id"] == "vehicle_breakdown_replan"
    assert [item["step"] for item in trace["timeline"]] == [
        "initial_plan",
        "event_received",
        "policy_decided",
        "tasks_prepared",
        "replanned",
        "simulation_finished",
    ]


def test_trace_preserves_real_demo_facts_and_marks_unrecorded_data() -> None:
    trace = build_demo_trace(run_demo(io.StringIO()))
    timeline = {item["step"]: item for item in trace["timeline"]}

    initial = timeline["initial_plan"]
    assert initial["optimizer"]["status"] == NOT_RECORDED_IN_BASELINE
    assert initial["optimizer"]["plan"]["vehicle_routes"] == [
        {
            "vehicle_id": "V01",
            "task_sequence": ["T01", "T02", "T03"],
            "planned_arrivals": [
                {"task_id": "T01", "arrival_time": 5},
                {"task_id": "T02", "arrival_time": 15},
                {"task_id": "T03", "arrival_time": 25},
            ],
        }
    ]
    assert initial["verifier"] == {"valid": True, "violations": []}

    assert timeline["event_received"]["event"] == {
        "event_id": "demo-breakdown-v01",
        "event_type": "VEHICLE_BREAKDOWN",
        "timestamp": 10,
        "location": "B",
        "description": "Demo vehicle breakdown after the first collection task.",
        "severity": 3,
        "deadline": None,
    }
    assert timeline["policy_decided"]["policy_decision"]["policy_profile"] == (
        "MINIMAL_RESCHEDULE"
    )
    assert timeline["tasks_prepared"] == {
        "step": "tasks_prepared",
        "sim_time": 10,
        "task_builder": {
            "created_tasks": [],
            "updated_tasks": [],
            "message": "no new tasks created",
        },
        "released_task_ids": ["T02", "T03"],
    }

    replanned = timeline["replanned"]
    assert replanned["optimizer"]["status"] == "FEASIBLE"
    assert replanned["verifier"] == {"valid": True, "violations": []}
    assert replanned["plan_changes"]["changed_routes"] == [
        {
            "vehicle_id": "V01",
            "before_task_sequence": ["T01", "T02", "T03"],
            "after_task_sequence": [],
        },
        {
            "vehicle_id": "V02",
            "before_task_sequence": [],
            "after_task_sequence": ["T02", "T03"],
        },
    ]

    assert timeline["simulation_finished"]["metrics"] == {
        "task_completion_rate": 1.0,
        "urgent_task_completion_rate": 0.0,
        "average_response_time": 20.0,
        "overflow_count": 0,
        "total_distance": 22.0,
    }
