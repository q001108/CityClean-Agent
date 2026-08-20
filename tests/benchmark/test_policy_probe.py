from __future__ import annotations

from copy import deepcopy
import socket

from cityclean_agent.benchmark.policy_probe import (
    build_matched_ordinary_task_probe_state,
    build_overflow_probe_state,
    build_urgent_probe_state,
    compare_policy_profiles,
)
from cityclean_agent.optimizer.results import OptimizationStatus
from cityclean_agent.policy.models import PolicyProfile


def test_urgent_probe_is_deterministic_fair_and_read_only(monkeypatch) -> None:
    state = build_urgent_probe_state()
    original = deepcopy(state)
    profiles = (PolicyProfile.BALANCED, PolicyProfile.URGENT_RESPONSE)

    def fail_network(*args, **kwargs):
        raise AssertionError("policy sensitivity probes must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    first = compare_policy_profiles(state, profiles)
    second = compare_policy_profiles(state, profiles)

    assert first == second
    assert tuple(observation.profile for observation in first) == profiles
    assert all(observation.status is OptimizationStatus.FEASIBLE for observation in first)
    assert state.current_time == original.current_time
    assert state.tasks == original.tasks
    assert state.vehicles == original.vehicles
    assert tuple(state.road_network.roads) == tuple(original.road_network.roads)
    balanced, urgent_response = first
    assert balanced.task_assignments == (("N-close", "V1"), ("U", "V1"))
    assert balanced.planned_completions == (("N-close", 30), ("U", 40))
    assert balanced.deadline_slacks == (("N-close", 0), ("U", 10))
    assert balanced.planned_route_distance == 2.0
    assert urgent_response.task_assignments == (("N-close", "V1"), ("U", "V2"))
    assert urgent_response.planned_completions == (("N-close", 30), ("U", 30))
    assert urgent_response.deadline_slacks == (("N-close", 0), ("U", 20))
    assert urgent_response.planned_route_distance == 51.0


def test_overflow_probe_is_deterministic_fair_and_read_only() -> None:
    state = build_overflow_probe_state()
    original = deepcopy(state)
    profiles = (PolicyProfile.BALANCED, PolicyProfile.OVERFLOW_CONTROL)

    first = compare_policy_profiles(state, profiles)
    second = compare_policy_profiles(state, profiles)

    assert first == second
    assert tuple(observation.profile for observation in first) == profiles
    assert all(observation.status is OptimizationStatus.FEASIBLE for observation in first)
    assert state.current_time == original.current_time
    assert state.tasks == original.tasks
    assert state.vehicles == original.vehicles
    assert tuple(state.road_network.roads) == tuple(original.road_network.roads)
    balanced, overflow_control = first
    assert balanced.unassigned_tasks == ("overflow",)
    assert balanced.planned_route_distance == 10.0
    assert overflow_control.task_assignments[-1] == ("overflow", "V2")
    assert overflow_control.planned_completions[-1] == ("overflow", 45)
    assert overflow_control.deadline_slacks[-1] == ("overflow", 0)
    assert overflow_control.planned_route_distance == 510.0


def test_matched_priority_probe_prefers_higher_priority_without_event_semantics() -> None:
    state = build_matched_ordinary_task_probe_state()
    observations = compare_policy_profiles(
        state,
        (PolicyProfile.BALANCED, PolicyProfile.OVERFLOW_CONTROL),
    )

    balanced, overflow_control = observations
    assert balanced.task_assignments == (("Z-overflow", "V1"),)
    assert balanced.unassigned_tasks == ("A-normal",)
    assert balanced.planned_route_distance == 6.0
    assert overflow_control.task_assignments == (("Z-overflow", "V1"),)
    assert overflow_control.unassigned_tasks == ("A-normal",)
    assert overflow_control.planned_route_distance == 6.0
