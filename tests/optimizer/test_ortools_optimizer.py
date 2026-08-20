from __future__ import annotations

from copy import deepcopy

import pytest

from cityclean_agent.domain.enums import RoadStatus, ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import (
    CityState,
    Road,
    ServiceTask,
    Vehicle,
    WastePoint,
)
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.optimizer.results import OptimizationStatus
from cityclean_agent.policy.models import PolicyParameters


PARAMETERS = PolicyParameters(
    distance_weight=1,
    lateness_weight=10,
    unserved_task_penalty=100,
    rescheduling_weight=0,
)


def make_state(
    *,
    vehicles: list[Vehicle] | None = None,
    tasks: list[ServiceTask] | None = None,
    roads: list[Road] | None = None,
    current_time: int = 0,
) -> CityState:
    waste_points = {
        "W1": WastePoint("W1", "B", 100, 10, 0, "mixed", "residential", 1),
        "W2": WastePoint("W2", "C", 100, 10, 0, "mixed", "residential", 1),
    }
    vehicle_values = [make_vehicle()] if vehicles is None else vehicles
    road_values = (
        [
            Road("AB", "A", "B", 2, 5),
            Road("AC", "A", "C", 3, 8),
            Road("BC", "B", "C", 1, 4),
        ]
        if roads is None
        else roads
    )
    return CityState(
        current_time=current_time,
        waste_points=waste_points,
        vehicles={vehicle.id: vehicle for vehicle in vehicle_values},
        transfer_stations={},
        road_network=RoadNetwork(road_values),
        tasks={task.task_id: task for task in tasks or []},
    )


def make_vehicle(
    vehicle_id: str = "V1",
    *,
    node_id: str = "A",
    capacity: float = 10,
    current_load: float = 0,
    status: VehicleStatus = VehicleStatus.AVAILABLE,
) -> Vehicle:
    return Vehicle(vehicle_id, node_id, capacity, current_load, status, speed=30)


def make_task(
    task_id: str = "T1",
    *,
    target_id: str = "W1",
    demand: float = 2,
    priority: int = 1,
    deadline: int | None = None,
    status: ServiceTaskStatus = ServiceTaskStatus.PENDING,
) -> ServiceTask:
    return ServiceTask(
        task_id=task_id,
        source_event_id=f"E-{task_id}",
        target_id=target_id,
        demand=demand,
        priority=priority,
        deadline=deadline,
        status=status,
    )


def assigned_task_ids(result) -> set[str]:
    assert result.plan is not None
    return {
        task_id
        for route in result.plan.vehicle_routes
        for task_id in route.task_sequence
    }


def test_single_vehicle_single_task_is_assigned_with_travel_time_eta() -> None:
    result = ORToolsOptimizer().optimize(make_state(tasks=[make_task()]), PARAMETERS)

    assert result.status is OptimizationStatus.FEASIBLE
    assert assigned_task_ids(result) == {"T1"}
    assert result.plan.vehicle_routes[0].planned_arrivals == {"T1": 5}


def test_planned_arrival_excludes_task_service_duration() -> None:
    result = ORToolsOptimizer().optimize(
        make_state(
            tasks=[make_task(priority=10, deadline=15)],
            roads=[Road("AB", "A", "B", 2, 10)],
        ),
        PARAMETERS,
    )

    assert result.status is OptimizationStatus.FEASIBLE
    assert result.plan.vehicle_routes[0].planned_arrivals == {"T1": 10}


def test_multiple_vehicles_and_tasks_are_assigned_within_capacity() -> None:
    result = ORToolsOptimizer().optimize(
        make_state(
            vehicles=[make_vehicle("V1", capacity=5), make_vehicle("V2", node_id="A", capacity=5)],
            tasks=[make_task("T1", demand=4), make_task("T2", target_id="W2", demand=4)],
        ),
        PARAMETERS,
    )

    assert result.status is OptimizationStatus.FEASIBLE
    assert assigned_task_ids(result) == {"T1", "T2"}
    assert {route.vehicle_id for route in result.plan.vehicle_routes} == {"V1", "V2"}


def test_broken_vehicle_is_excluded() -> None:
    result = ORToolsOptimizer().optimize(
        make_state(
            vehicles=[make_vehicle(status=VehicleStatus.BROKEN)],
            tasks=[make_task()],
        ),
        PARAMETERS,
    )

    assert result.status is OptimizationStatus.FEASIBLE
    assert result.plan.vehicle_routes == []
    assert result.plan.unassigned_tasks == ["T1"]


def test_capacity_never_exceeds_current_remaining_capacity() -> None:
    result = ORToolsOptimizer().optimize(
        make_state(
            vehicles=[make_vehicle(capacity=5)],
            tasks=[make_task("T1", demand=4), make_task("T2", target_id="W2", demand=4)],
        ),
        PARAMETERS,
    )

    assert result.status is OptimizationStatus.FEASIBLE
    assert len(assigned_task_ids(result)) == 1
    assert len(result.plan.unassigned_tasks) == 1


def test_zero_priority_task_uses_the_base_drop_penalty() -> None:
    result = ORToolsOptimizer().optimize(
        make_state(
            tasks=[make_task(priority=0)],
            roads=[Road("AB", "A", "B", 50, 5)],
        ),
        PARAMETERS,
    )

    assert result.status is OptimizationStatus.FEASIBLE
    assert assigned_task_ids(result) == {"T1"}


def test_soft_lateness_is_weighted_by_task_priority() -> None:
    result = ORToolsOptimizer().optimize(
        make_state(
            current_time=20,
            tasks=[
                make_task("A-low", priority=1, deadline=39),
                make_task("Z-high", target_id="W2", priority=9, deadline=39),
            ],
            roads=[
                Road("AB", "A", "B", 1, 5),
                Road("AC", "A", "C", 1, 5),
                Road("BC", "B", "C", 1, 5),
                Road("CB", "C", "B", 1, 5),
            ],
        ),
        PARAMETERS,
    )

    assert result.status is OptimizationStatus.FEASIBLE
    assert result.plan is not None
    assert result.plan.vehicle_routes[0].task_sequence == ["Z-high", "A-low"]


def test_closed_road_is_not_used() -> None:
    closed_road = Road("AB", "A", "B", 2, 5, status=RoadStatus.CLOSED)
    result = ORToolsOptimizer().optimize(
        make_state(tasks=[make_task()], roads=[closed_road]), PARAMETERS
    )

    assert result.status is OptimizationStatus.FEASIBLE
    assert result.plan.unassigned_tasks == ["T1"]


def test_unreachable_normal_task_is_unassigned() -> None:
    result = ORToolsOptimizer().optimize(
        make_state(tasks=[make_task()], roads=[]), PARAMETERS
    )

    assert result.status is OptimizationStatus.FEASIBLE
    assert result.plan.unassigned_tasks == ["T1"]


def test_high_priority_task_is_mandatory_when_reachable() -> None:
    result = ORToolsOptimizer().optimize(
        make_state(tasks=[make_task(priority=10)]), PARAMETERS
    )

    assert result.status is OptimizationStatus.FEASIBLE
    assert assigned_task_ids(result) == {"T1"}
    assert result.plan.unassigned_tasks == []


@pytest.mark.parametrize(
    ("vehicles", "roads", "reason"),
    [
        ([], [Road("AB", "A", "B", 2, 5)], "REQUIRED_TASK_NO_AVAILABLE_VEHICLE"),
        ([make_vehicle()], [], "REQUIRED_TASK_UNREACHABLE"),
    ],
)
def test_unserviceable_high_priority_task_is_infeasible(
    vehicles: list[Vehicle], roads: list[Road], reason: str
) -> None:
    result = ORToolsOptimizer().optimize(
        make_state(vehicles=vehicles, tasks=[make_task(priority=10)], roads=roads),
        PARAMETERS,
    )

    assert result.status is OptimizationStatus.INFEASIBLE
    assert result.plan is None
    assert result.reason == reason


def test_high_priority_hard_deadline_is_satisfied() -> None:
    result = ORToolsOptimizer().optimize(
        make_state(tasks=[make_task(priority=10, deadline=10)]), PARAMETERS
    )

    assert result.status is OptimizationStatus.FEASIBLE
    assert result.plan.vehicle_routes[0].planned_arrivals["T1"] == 5


def test_high_priority_hard_deadline_returns_infeasible_when_unreachable_in_time() -> None:
    result = ORToolsOptimizer().optimize(
        make_state(tasks=[make_task(priority=10, deadline=9)]), PARAMETERS
    )

    assert result.status is OptimizationStatus.INFEASIBLE
    assert result.reason == "REQUIRED_TASK_DEADLINE_UNACHIEVABLE"


def test_completed_tasks_are_excluded_from_optimization() -> None:
    result = ORToolsOptimizer().optimize(
        make_state(tasks=[make_task(status=ServiceTaskStatus.COMPLETED)]), PARAMETERS
    )

    assert result.status is OptimizationStatus.FEASIBLE
    assert result.plan.vehicle_routes == []
    assert result.plan.unassigned_tasks == []


def test_same_input_produces_same_result() -> None:
    state = make_state(tasks=[make_task(), make_task("T2", target_id="W2")])

    first = ORToolsOptimizer().optimize(state, PARAMETERS)
    second = ORToolsOptimizer().optimize(state, PARAMETERS)

    assert first == second


def test_optimizer_does_not_mutate_city_state() -> None:
    state = make_state(tasks=[make_task()])
    original = deepcopy(state)

    ORToolsOptimizer().optimize(state, PARAMETERS)

    assert state.current_time == original.current_time
    assert state.tasks["T1"] == original.tasks["T1"]
    assert state.vehicles["V1"] == original.vehicles["V1"]
    assert state.road_network.get_road("AB") == original.road_network.get_road("AB")
