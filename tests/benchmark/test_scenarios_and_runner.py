from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

from cityclean_agent.benchmark.runner import BenchmarkMode, BenchmarkRunner, write_results
from cityclean_agent.benchmark.scenarios import scenario_bank
from cityclean_agent.metrics.calculator import MetricsCalculator
from cityclean_agent.simulator.city_sim import CitySim


def scenario_by_id(scenario_id: str):
    return next(scenario for scenario in scenario_bank() if scenario.scenario_id == scenario_id)


def test_all_fixed_scenarios_build_fresh_city_states_with_unique_ids() -> None:
    scenarios = scenario_bank()

    assert [scenario.scenario_id for scenario in scenarios] == [
        "normal_control",
        "vehicle_breakdown",
        "road_closure_detour",
        "urgent_task",
        "waste_overflow",
        "breakdown_capacity_tight",
        "urgent_infeasible",
        "urgent_timing_tradeoff",
        "overflow_service_tradeoff",
    ]
    assert len({scenario.scenario_id for scenario in scenarios}) == len(scenarios)
    for scenario in scenarios:
        first_state = scenario.build_initial_state()
        second_state = scenario.build_initial_state()
        assert first_state is not second_state
        assert first_state.current_time == second_state.current_time == 0
        assert scenario.max_simulation_time > 0


def test_same_scenario_run_twice_is_deterministic() -> None:
    scenario = scenario_by_id("vehicle_breakdown")

    first = BenchmarkRunner().run_episode(scenario)
    second = BenchmarkRunner().run_episode(scenario)

    assert first == second


def test_normal_control_completes_normally() -> None:
    result = BenchmarkRunner().run_episode(scenario_by_id("normal_control"))

    assert result.terminal_status == "COMPLETED"
    assert result.remaining_unfinished_tasks == ()
    assert result.metrics.task_completion_rate == 1.0
    assert result.workflow_outcomes == ()


def test_vehicle_breakdown_runs_the_formal_replanning_workflow() -> None:
    result = BenchmarkRunner().run_episode(scenario_by_id("vehicle_breakdown"))

    assert result.terminal_status == "COMPLETED"
    assert result.workflow_outcomes[0].event_id == "E-breakdown"
    assert result.workflow_outcomes[0].status == "SUCCESS"
    assert result.metrics.task_completion_rate == 1.0
    assert result.metrics.total_distance == 23.0


def test_road_closure_replans_using_the_detour() -> None:
    result = BenchmarkRunner().run_episode(scenario_by_id("road_closure_detour"))

    assert result.terminal_status == "COMPLETED"
    assert result.workflow_outcomes[0].status == "SUCCESS"
    assert result.metrics.total_distance == 7.0


def test_urgent_task_creates_and_completes_a_must_serve_task() -> None:
    result = BenchmarkRunner().run_episode(scenario_by_id("urgent_task"))

    assert result.terminal_status == "COMPLETED"
    assert result.workflow_outcomes[0].status == "SUCCESS"
    assert result.final_task_statuses["task-E-urgent-W05"] == "COMPLETED"
    assert result.metrics.urgent_task_completion_rate == 1.0


def test_waste_overflow_records_real_overflow_and_service_task() -> None:
    scenario = scenario_by_id("waste_overflow")
    initial_state = scenario.build_initial_state()
    result = BenchmarkRunner().run_episode(scenario)

    assert result.terminal_status == "COMPLETED"
    assert scenario.scheduled_events[0].timestamp == 10
    assert initial_state.tasks
    assert initial_state.waste_points["W05"].current_load < initial_state.waste_points["W05"].capacity
    assert result.workflow_outcomes[0].status == "SUCCESS"
    assert result.final_task_statuses["task-E-overflow-W05"] == "COMPLETED"
    assert all(status == "COMPLETED" for status in result.final_task_statuses.values())
    assert result.metrics.overflow_count == 1


def test_stress_scenarios_record_max_time_and_infeasible_boundaries() -> None:
    tight = BenchmarkRunner().run_episode(scenario_by_id("breakdown_capacity_tight"))
    infeasible = BenchmarkRunner().run_episode(scenario_by_id("urgent_infeasible"))

    assert tight.terminal_status == "MAX_SIMULATION_TIME"
    assert tight.terminal_time == 35
    assert tight.remaining_unfinished_tasks
    assert infeasible.terminal_status == "INFEASIBLE"
    assert infeasible.workflow_outcomes[0].status == "INFEASIBLE"


def test_runner_uses_metrics_calculator_once_per_episode(monkeypatch) -> None:
    original_calculate = MetricsCalculator.calculate
    call_count = 0

    def tracked_calculate(self, state, runtime_stats):
        nonlocal call_count
        call_count += 1
        return original_calculate(self, state, runtime_stats)

    monkeypatch.setattr(MetricsCalculator, "calculate", tracked_calculate)

    BenchmarkRunner().run_episode(scenario_by_id("normal_control"))

    assert call_count == 1


def test_runner_does_not_reset_citysim_to_handle_events(monkeypatch) -> None:
    original_reset = CitySim.reset
    reset_count = 0

    def tracked_reset(self) -> None:
        nonlocal reset_count
        reset_count += 1
        original_reset(self)

    monkeypatch.setattr(CitySim, "reset", tracked_reset)

    BenchmarkRunner().run_episode(scenario_by_id("vehicle_breakdown"))

    assert reset_count == 1


def test_runner_does_not_require_network_access(monkeypatch) -> None:
    def fail_network(*args, **kwargs):
        raise AssertionError("benchmark runner must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    result = BenchmarkRunner().run_episode(scenario_by_id("normal_control"))

    assert result.terminal_status == "COMPLETED"


def test_batch_runner_and_json_output_are_complete_and_serializable(tmp_path: Path) -> None:
    results = BenchmarkRunner().run_all()
    output_path = tmp_path / "benchmark_comparison_results.json"

    write_results(output_path, results)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert len(results) == len(scenario_bank()) * len(BenchmarkMode) == 27
    assert len(payload) == 27
    assert payload[0]["scenario_id"] == "normal_control"
    assert payload[0]["benchmark_mode"] == BenchmarkMode.STATIC_NO_REPLAN.value
    assert {
        (result.scenario_id, result.benchmark_mode) for result in results
    } == {
        (scenario.scenario_id, mode)
        for scenario in scenario_bank()
        for mode in BenchmarkMode
    }
    assert set(payload[0]) == {
        "scenario_id",
        "scenario_category",
        "benchmark_mode",
        "terminal_time",
        "terminal_status",
        "workflow_outcomes",
        "final_task_statuses",
        "task_outcomes",
        "metrics",
        "remaining_unfinished_tasks",
    }


def test_batch_module_entry_runs_in_a_temporary_output_directory(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "cityclean_agent.benchmark"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "normal_control" in completed.stdout
    assert "urgent_infeasible" in completed.stdout
    assert "STATIC_NO_REPLAN" in completed.stdout
    assert "EVENT_POLICY_REPLAN" in completed.stdout
    assert (tmp_path / "benchmark_comparison_results.json").is_file()
