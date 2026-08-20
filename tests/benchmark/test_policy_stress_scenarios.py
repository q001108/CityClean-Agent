from __future__ import annotations

import socket

import cityclean_agent.benchmark.runner as runner_module
from cityclean_agent.benchmark.runner import BenchmarkMode, BenchmarkRunner
from cityclean_agent.benchmark.scenarios import BenchmarkScenario, scenario_bank
from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus, VehicleStatus


def _scenario_by_id(scenario_id: str) -> BenchmarkScenario:
    return next(scenario for scenario in scenario_bank() if scenario.scenario_id == scenario_id)


def _task_outcome(result, task_id: str):
    return next(outcome for outcome in result.task_outcomes if outcome.task_id == task_id)


def test_policy_stress_scenarios_are_separate_and_deterministic() -> None:
    policy_stress = tuple(
        scenario for scenario in scenario_bank() if scenario.category == "POLICY_STRESS"
    )

    assert [scenario.scenario_id for scenario in policy_stress] == [
        "urgent_timing_tradeoff",
        "overflow_service_tradeoff",
    ]
    for scenario in policy_stress:
        first = scenario.build_initial_state()
        second = scenario.build_initial_state()
        assert first is not second
        assert first.current_time == second.current_time == 0
        assert scenario.scheduled_events[0].timestamp == 10
        assert len(first.tasks) == 2
        assert sum(
            vehicle.status is VehicleStatus.AVAILABLE
            for vehicle in first.vehicles.values()
        ) >= 2


def test_policy_stress_events_reach_active_plans_at_ten(monkeypatch) -> None:
    observed = []
    original_process_event = runner_module.process_event

    def tracked_process_event(sim, event, *, event_agent=None, **kwargs):
        state = sim.get_state()
        observed.append((event.event_type, state.current_time, state.active_plan is not None))
        return original_process_event(sim, event, event_agent=event_agent, **kwargs)

    monkeypatch.setattr(runner_module, "process_event", tracked_process_event)
    runner = BenchmarkRunner()
    runner.run_episode(
        _scenario_by_id("urgent_timing_tradeoff"), BenchmarkMode.FIXED_BALANCED_REPLAN
    )
    runner.run_episode(
        _scenario_by_id("overflow_service_tradeoff"), BenchmarkMode.EVENT_POLICY_REPLAN
    )

    assert observed == [
        (CityEventType.URGENT_TASK, 10, True),
        (CityEventType.WASTE_OVERFLOW, 10, True),
    ]


def test_overflow_policy_stress_event_changes_real_load_before_task_build(monkeypatch) -> None:
    original_city_sim = runner_module.CitySim
    load_transitions = []

    class RecordingCitySim(original_city_sim):
        def inject_event(self, event):
            before = self.get_state().waste_points["WO"].current_load
            applied = super().inject_event(event)
            after = self.get_state().waste_points["WO"].current_load
            load_transitions.append((before, after, applied))
            return applied

    monkeypatch.setattr(runner_module, "CitySim", RecordingCitySim)
    result = BenchmarkRunner().run_episode(
        _scenario_by_id("overflow_service_tradeoff"), BenchmarkMode.EVENT_POLICY_REPLAN
    )

    assert load_transitions == [(3, 4, True)]
    overflow_outcome = _task_outcome(result, "task-E-policy-overflow-WO")
    assert overflow_outcome.priority == 4
    assert overflow_outcome.status == ServiceTaskStatus.COMPLETED.value


def test_task_outcomes_project_final_service_task_facts() -> None:
    static_result = BenchmarkRunner().run_episode(
        _scenario_by_id("urgent_timing_tradeoff"), BenchmarkMode.STATIC_NO_REPLAN
    )
    replanned_result = BenchmarkRunner().run_episode(
        _scenario_by_id("urgent_timing_tradeoff"), BenchmarkMode.EVENT_POLICY_REPLAN
    )

    pending = _task_outcome(static_result, "task-E-policy-urgent-WU")
    completed = _task_outcome(replanned_result, "task-E-policy-urgent-WU")
    assert pending.status == ServiceTaskStatus.PENDING.value
    assert pending.completed_at is None
    assert pending.response_time is None
    assert completed.status == ServiceTaskStatus.COMPLETED.value
    assert completed.completed_at is not None
    assert completed.response_time == completed.completed_at - completed.created_at


def test_original_seven_scenarios_keep_their_benchmark_boundary_results() -> None:
    original_scenarios = tuple(scenario_bank()[:7])
    results = BenchmarkRunner().run_all(original_scenarios)
    terminal_statuses = {
        (result.scenario_id, result.benchmark_mode): result.terminal_status
        for result in results
    }

    assert len(results) == 21
    assert terminal_statuses[("normal_control", BenchmarkMode.STATIC_NO_REPLAN)] == "COMPLETED"
    assert terminal_statuses[("vehicle_breakdown", BenchmarkMode.STATIC_NO_REPLAN)] == "MAX_SIMULATION_TIME"
    assert terminal_statuses[("vehicle_breakdown", BenchmarkMode.FIXED_BALANCED_REPLAN)] == "COMPLETED"
    assert terminal_statuses[("urgent_task", BenchmarkMode.EVENT_POLICY_REPLAN)] == "COMPLETED"
    assert terminal_statuses[("urgent_infeasible", BenchmarkMode.FIXED_BALANCED_REPLAN)] == "INFEASIBLE"


def test_full_twenty_seven_episode_batch_needs_no_network(monkeypatch) -> None:
    def fail_network(*args, **kwargs):
        raise AssertionError("policy stress benchmarks must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    results = BenchmarkRunner().run_all()

    assert len(results) == 27
