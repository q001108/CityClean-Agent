"""Small deterministic probes for checking policy-parameter sensitivity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from cityclean_agent.domain.enums import VehicleStatus
from cityclean_agent.domain.models import CityState, Road, ServiceTask, Vehicle, WastePoint
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.optimizer.results import OptimizationResult, OptimizationStatus
from cityclean_agent.policy.mapper import POLICY_PARAMETERS_BY_PROFILE
from cityclean_agent.policy.models import PolicyProfile


@dataclass(frozen=True, slots=True)
class PolicyPlanObservation:
    """Read-only summary of one profile's plan for the same input state."""

    profile: PolicyProfile
    status: OptimizationStatus
    task_assignments: tuple[tuple[str, str], ...]
    task_sequences: tuple[tuple[str, tuple[str, ...]], ...]
    unassigned_tasks: tuple[str, ...]
    planned_arrivals: tuple[tuple[str, int], ...]
    planned_completions: tuple[tuple[str, int], ...]
    deadline_slacks: tuple[tuple[str, int], ...]
    planned_route_distance: float | None


def compare_policy_profiles(
    state: CityState, profiles: Iterable[PolicyProfile]
) -> tuple[PolicyPlanObservation, ...]:
    """Optimize the exact same read-only state for each requested profile."""

    optimizer = ORToolsOptimizer()
    return tuple(
        _observe_plan(
            state,
            profile,
            optimizer.optimize(state, POLICY_PARAMETERS_BY_PROFILE[profile]),
        )
        for profile in profiles
    )


def build_urgent_probe_state() -> CityState:
    """Build a t>0 urgent task probe with capacity and lateness trade-offs."""

    return CityState(
        current_time=20,
        waste_points={
            "WN": WastePoint("WN", "B", 20, 5, 0, "mixed", "residential", 1),
            "WU": WastePoint("WU", "C", 20, 5, 0, "mixed", "school", 1),
        },
        vehicles={
            "V1": Vehicle("V1", "A", 2, 0, VehicleStatus.AVAILABLE, 30),
            "V2": Vehicle("V2", "Z", 1, 0, VehicleStatus.AVAILABLE, 30),
        },
        transfer_stations={},
        road_network=RoadNetwork(
            [
                Road("AB", "A", "B", 1, 5),
                Road("BC", "B", "C", 1, 5),
                Road("ZC", "Z", "C", 50, 5),
            ]
        ),
        tasks={
            "U": ServiceTask("U", "E-urgent", "WU", 1, 10, 50, created_at=20),
            "N-close": ServiceTask("N-close", "E-normal", "WN", 1, 1, 30, created_at=20),
        },
    )


def build_overflow_probe_state() -> CityState:
    """Build a t>0 overflow task probe with the same fixed resource trade-off."""

    return _probe_state(
        {
            "N-near": ServiceTask("N-near", "E-normal", "WU", 1, 1, 30, created_at=20),
            "N-late": ServiceTask("N-late", "E-normal", "WN", 1, 1, 35, created_at=20),
            "overflow": ServiceTask("overflow", "E-overflow", "WF", 1, 4, 45, created_at=20),
        }
    )


def build_matched_ordinary_task_probe_state() -> CityState:
    """Build near-equal-cost non-must-serve tasks with one service slot."""

    return CityState(
        current_time=20,
        waste_points={
            "WN": WastePoint("WN", "B", 20, 5, 0, "mixed", "residential", 1),
            "WO": WastePoint("WO", "C", 10, 10, 0, "mixed", "park", 4),
        },
        vehicles={
            "V1": Vehicle("V1", "A", 1, 0, VehicleStatus.AVAILABLE, 30),
        },
        transfer_stations={},
        road_network=RoadNetwork(
            [
                Road("AB", "A", "B", 5, 5),
                Road("AC", "A", "C", 6, 5),
            ]
        ),
        tasks={
            "A-normal": ServiceTask("A-normal", "E-normal", "WN", 1, 1, None, created_at=20),
            "Z-overflow": ServiceTask("Z-overflow", "E-overflow", "WO", 1, 9, None, created_at=20),
        },
    )


def _probe_state(tasks: dict[str, ServiceTask]) -> CityState:
    return CityState(
        current_time=20,
        waste_points={
            "WU": WastePoint("WU", "B", 20, 5, 0, "mixed", "residential", 1),
            "WN": WastePoint("WN", "C", 20, 5, 0, "mixed", "school", 1),
            "WF": WastePoint("WF", "F", 10, 10, 0, "mixed", "park", 4),
        },
        vehicles={
            "V1": Vehicle("V1", "A", 2, 0, VehicleStatus.AVAILABLE, 30),
            "V2": Vehicle("V2", "Z", 1, 0, VehicleStatus.AVAILABLE, 30),
        },
        transfer_stations={},
        road_network=RoadNetwork(
            [
                Road("AB", "A", "B", 5, 5),
                Road("BC", "B", "C", 5, 5),
                Road("CF", "C", "F", 150, 20),
                Road("ZF", "Z", "F", 500, 20),
            ]
        ),
        tasks=tasks,
    )


def _observe_plan(
    state: CityState,
    profile: PolicyProfile,
    result: OptimizationResult,
) -> PolicyPlanObservation:
    if result.status is not OptimizationStatus.FEASIBLE or result.plan is None:
        return PolicyPlanObservation(
            profile=profile,
            status=result.status,
            task_assignments=(),
            task_sequences=(),
            unassigned_tasks=(),
            planned_arrivals=(),
            planned_completions=(),
            deadline_slacks=(),
            planned_route_distance=None,
        )

    assignments: list[tuple[str, str]] = []
    sequences: list[tuple[str, tuple[str, ...]]] = []
    arrivals: list[tuple[str, int]] = []
    completions: list[tuple[str, int]] = []
    deadline_slacks: list[tuple[str, int]] = []
    total_distance = 0.0
    for route in result.plan.vehicle_routes:
        sequences.append((route.vehicle_id, tuple(route.task_sequence)))
        current_node_id = state.vehicles[route.vehicle_id].current_node_id
        for task_id in route.task_sequence:
            task = state.tasks[task_id]
            target_node_id = state.waste_points[task.target_id].node_id
            path = state.road_network.shortest_path(current_node_id, target_node_id)
            assert path is not None
            total_distance += path.total_distance
            assignments.append((task_id, route.vehicle_id))
            arrival = route.planned_arrivals[task_id]
            completion = arrival + task.service_duration_min
            arrivals.append((task_id, arrival))
            completions.append((task_id, completion))
            if task.deadline is not None:
                deadline_slacks.append((task_id, task.deadline - completion))
            current_node_id = target_node_id

    return PolicyPlanObservation(
        profile=profile,
        status=result.status,
        task_assignments=tuple(sorted(assignments)),
        task_sequences=tuple(sequences),
        unassigned_tasks=tuple(sorted(result.plan.unassigned_tasks)),
        planned_arrivals=tuple(sorted(arrivals)),
        planned_completions=tuple(sorted(completions)),
        deadline_slacks=tuple(sorted(deadline_slacks)),
        planned_route_distance=total_distance,
    )
