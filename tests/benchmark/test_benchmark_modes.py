from __future__ import annotations

from copy import deepcopy

import cityclean_agent.benchmark.runner as runner_module
from cityclean_agent.benchmark.runner import BenchmarkMode, BenchmarkRunner
from cityclean_agent.benchmark.scenarios import BenchmarkScenario, scenario_bank
from cityclean_agent.domain.enums import CityEventType, RoadStatus, VehicleStatus
from cityclean_agent.policy.mapper import POLICY_PARAMETERS_BY_PROFILE
from cityclean_agent.policy.models import PolicyProfile
from cityclean_agent.simulator.city_sim import CitySim


def _scenario_by_id(scenario_id: str) -> BenchmarkScenario:
    return next(scenario for scenario in scenario_bank() if scenario.scenario_id == scenario_id)


def _state_signature(state) -> tuple[object, ...]:
    return (
        state.current_time,
        tuple(sorted((point_id, repr(point)) for point_id, point in state.waste_points.items())),
        tuple(sorted((vehicle_id, repr(vehicle)) for vehicle_id, vehicle in state.vehicles.items())),
        tuple(repr(road) for road in state.road_network.roads),
        tuple(sorted((task_id, repr(task)) for task_id, task in state.tasks.items())),
    )


def test_modes_start_from_fresh_equivalent_initial_states() -> None:
    base_scenario = _scenario_by_id("normal_control")
    built_states = []

    def build_initial_state():
        state = base_scenario.build_initial_state()
        built_states.append(state)
        return state

    scenario = BenchmarkScenario(
        "fairness_probe",
        "NORMAL",
        build_initial_state,
        (),
        base_scenario.max_simulation_time,
    )

    results = BenchmarkRunner().run_all((scenario,), BenchmarkMode)

    assert len(results) == 3
    assert len({id(state) for state in built_states}) == 3
    assert len({_state_signature(state) for state in built_states}) == 1


def test_initial_plans_use_balanced_parameters_in_every_mode(monkeypatch) -> None:
    parameters_seen = []
    original_optimize = runner_module.ORToolsOptimizer.optimize

    def tracked_optimize(self, state, parameters, previous_plan=None):
        parameters_seen.append(parameters)
        return original_optimize(self, state, parameters, previous_plan)

    monkeypatch.setattr(runner_module.ORToolsOptimizer, "optimize", tracked_optimize)

    BenchmarkRunner().run_all((_scenario_by_id("normal_control"),), BenchmarkMode)

    assert parameters_seen == [
        POLICY_PARAMETERS_BY_PROFILE[PolicyProfile.BALANCED]
    ] * len(BenchmarkMode)


def test_normal_control_results_are_equivalent_across_modes() -> None:
    results = BenchmarkRunner().run_all((_scenario_by_id("normal_control"),), BenchmarkMode)

    comparable_results = []
    for result in results:
        payload = result.to_dict()
        del payload["benchmark_mode"]
        comparable_results.append(payload)

    assert comparable_results[0] == comparable_results[1] == comparable_results[2]


def test_static_mode_applies_urgent_event_and_never_calls_replan(monkeypatch) -> None:
    def fail_replan(*args, **kwargs):
        raise AssertionError("STATIC_NO_REPLAN must not call process_event")

    monkeypatch.setattr(runner_module, "process_event", fail_replan)

    result = BenchmarkRunner().run_episode(
        _scenario_by_id("urgent_task"), BenchmarkMode.STATIC_NO_REPLAN
    )

    assert result.workflow_outcomes[0].status == "STATIC_APPLIED"
    assert result.final_task_statuses["task-E-urgent-W05"] == "PENDING"
    assert result.remaining_unfinished_tasks == ("task-E-urgent-W05",)


def test_fixed_and_event_policy_modes_use_expected_agents(monkeypatch) -> None:
    decisions = []
    original_process_event = runner_module.process_event

    def tracked_process_event(sim, event, *, event_agent=None, **kwargs):
        assert event_agent is not None
        decisions.append((event.event_type, event_agent.decide(event, sim.get_state()).policy_profile))
        return original_process_event(sim, event, event_agent=event_agent, **kwargs)

    monkeypatch.setattr(runner_module, "process_event", tracked_process_event)
    event_scenarios = tuple(
        scenario
        for scenario in scenario_bank()
        if scenario.scheduled_events and scenario.scenario_id not in {"breakdown_capacity_tight", "urgent_infeasible"}
    )

    BenchmarkRunner().run_all(event_scenarios, (BenchmarkMode.FIXED_BALANCED_REPLAN,))
    assert all(profile is PolicyProfile.BALANCED for _, profile in decisions)

    decisions.clear()
    BenchmarkRunner().run_all(event_scenarios, (BenchmarkMode.EVENT_POLICY_REPLAN,))
    assert dict(decisions) == {
        CityEventType.VEHICLE_BREAKDOWN: PolicyProfile.MINIMAL_RESCHEDULE,
        CityEventType.ROAD_CLOSURE: PolicyProfile.MINIMAL_RESCHEDULE,
        CityEventType.URGENT_TASK: PolicyProfile.URGENT_RESPONSE,
        CityEventType.WASTE_OVERFLOW: PolicyProfile.OVERFLOW_CONTROL,
    }


def test_all_modes_build_identical_event_tasks(monkeypatch) -> None:
    task_changes = []
    original_apply_task_changes = CitySim.apply_task_changes

    def tracked_apply_task_changes(self, changes):
        task_changes.append(deepcopy(changes))
        original_apply_task_changes(self, changes)

    monkeypatch.setattr(CitySim, "apply_task_changes", tracked_apply_task_changes)

    for mode in BenchmarkMode:
        BenchmarkRunner().run_episode(_scenario_by_id("urgent_task"), mode)

    assert len(task_changes) == len(BenchmarkMode)
    assert task_changes[0] == task_changes[1] == task_changes[2]


def test_breakdown_and_road_closure_change_citysim_state_in_all_modes(monkeypatch) -> None:
    original_city_sim = runner_module.CitySim
    simulations = []

    class RecordingCitySim(original_city_sim):
        def __init__(self, initial_state, tick_minutes=5):
            super().__init__(initial_state, tick_minutes)
            simulations.append(self)

    monkeypatch.setattr(runner_module, "CitySim", RecordingCitySim)

    for mode in BenchmarkMode:
        BenchmarkRunner().run_episode(_scenario_by_id("vehicle_breakdown"), mode)
        assert simulations[-1].get_state().vehicles["V01"].status is VehicleStatus.BROKEN
        BenchmarkRunner().run_episode(_scenario_by_id("road_closure_detour"), mode)
        assert simulations[-1].get_state().road_network.get_road("CD").status is RoadStatus.CLOSED


def test_all_mode_episodes_are_deterministic_and_need_no_network(monkeypatch) -> None:
    import socket

    def fail_network(*args, **kwargs):
        raise AssertionError("benchmark modes must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    first = BenchmarkRunner().run_all()
    second = BenchmarkRunner().run_all()

    assert len(first) == len(second) == 27
    assert first == second
