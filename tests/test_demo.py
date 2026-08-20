from __future__ import annotations

import io
import socket
import subprocess
import sys
from pathlib import Path

from cityclean_agent.demo import run_demo
from cityclean_agent.domain.enums import ServiceTaskStatus, VehicleStatus
from cityclean_agent.simulator.city_sim import CitySim
from cityclean_agent.workflow import WorkflowStatus


def test_demo_runs_closed_loop_with_breakdown_and_final_metrics() -> None:
    output = io.StringIO()

    result = run_demo(output)

    assert result.initial_verification.valid
    assert result.incident_time == 10
    assert result.completed_before_incident == ("T01",)
    assert result.released_task_ids == ("T02", "T03")
    assert result.replanning_result.status is WorkflowStatus.SUCCESS
    assert result.replanning_result.verification_result is not None
    assert result.replanning_result.verification_result.valid
    assert result.replanning_result.plan is not None
    assert {route.vehicle_id for route in result.replanning_result.plan.vehicle_routes} == {
        "V02"
    }
    assert result.final_state.current_time == 30
    assert result.final_state.vehicles["V01"].status is VehicleStatus.BROKEN
    assert all(
        task.status is ServiceTaskStatus.COMPLETED
        for task in result.final_state.tasks.values()
    )
    assert result.final_metrics.task_completion_rate == 1.0
    assert result.final_metrics.urgent_task_completion_rate == 0.0
    assert result.final_metrics.average_response_time == 20.0
    assert result.final_metrics.overflow_count == 0
    assert result.final_metrics.total_distance == 22.0
    rendered = output.getvalue()
    assert "治理响应时限（response_deadline）：无" in rendered
    assert "=== 最终指标 ===" in rendered


def test_demo_does_not_require_network_access(monkeypatch) -> None:
    def fail_network(*args, **kwargs):
        raise AssertionError("demo must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    result = run_demo(io.StringIO())

    assert result.replanning_result.status is WorkflowStatus.SUCCESS


def test_demo_is_deterministic() -> None:
    first = run_demo(io.StringIO())
    second = run_demo(io.StringIO())

    assert first.initial_plan == second.initial_plan
    assert first.released_task_ids == second.released_task_ids
    assert first.completed_before_incident == second.completed_before_incident
    assert first.replanning_result == second.replanning_result
    assert first.final_metrics == second.final_metrics
    assert {
        task_id: task.status for task_id, task in first.final_state.tasks.items()
    } == {
        task_id: task.status for task_id, task in second.final_state.tasks.items()
    }


def test_demo_does_not_reset_citysim_after_construction(monkeypatch) -> None:
    original_reset = CitySim.reset
    reset_count = 0

    def tracked_reset(self) -> None:
        nonlocal reset_count
        reset_count += 1
        original_reset(self)

    monkeypatch.setattr(CitySim, "reset", tracked_reset)

    result = run_demo(io.StringIO())

    assert result.replanning_result.status is WorkflowStatus.SUCCESS
    assert reset_count == 1


def test_module_entry_runs_to_completion() -> None:
    project_root = Path(__file__).resolve().parents[1]

    completed = subprocess.run(
        [sys.executable, "-m", "cityclean_agent"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0, completed.stderr
    assert "=== 初始调度 ===" in completed.stdout
    assert "车辆故障（VEHICLE_BREAKDOWN）" in completed.stdout
    assert "=== 最终指标 ===" in completed.stdout
