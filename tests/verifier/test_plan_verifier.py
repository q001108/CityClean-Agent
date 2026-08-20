from __future__ import annotations

from copy import deepcopy

from cityclean_agent.domain.enums import RoadStatus, ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import (
    CityState,
    DispatchPlan,
    Road,
    ServiceTask,
    Vehicle,
    VehicleRoute,
    WastePoint,
)
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.verifier.plan_verifier import PlanVerifier


def make_state(
    *,
    vehicle_status: VehicleStatus = VehicleStatus.AVAILABLE,
    vehicle_capacity: float = 5,
    tasks: list[ServiceTask] | None = None,
    roads: list[Road] | None = None,
) -> CityState:
    waste_points = {
        "W1": WastePoint("W1", "B", 100, 10, 0, "mixed", "residential", 1),
        "W2": WastePoint("W2", "C", 100, 10, 0, "mixed", "residential", 1),
    }
    vehicles = {
        "V1": Vehicle("V1", "A", vehicle_capacity, 0, vehicle_status, 30),
        "V2": Vehicle("V2", "A", vehicle_capacity, 0, VehicleStatus.AVAILABLE, 30),
    }
    road_values = (
        [Road("AB", "A", "B", 2, 5), Road("BC", "B", "C", 1, 4)]
        if roads is None
        else roads
    )
    return CityState(
        current_time=0,
        waste_points=waste_points,
        vehicles=vehicles,
        transfer_stations={},
        road_network=RoadNetwork(road_values),
        tasks={task.task_id: task for task in tasks or [make_task()]},
    )


def make_task(
    task_id: str = "T1",
    *,
    target_id: str = "W1",
    demand: float = 2,
    priority: int = 10,
    deadline: int | None = 10,
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


def make_plan(
    *,
    vehicle_id: str = "V1",
    task_ids: list[str] | None = None,
    planned_arrivals: dict[str, int] | None = None,
    unassigned_tasks: list[str] | None = None,
) -> DispatchPlan:
    return DispatchPlan(
        plan_id="P1",
        vehicle_routes=[
            VehicleRoute(
                vehicle_id=vehicle_id,
                task_sequence=task_ids or ["T1"],
                planned_arrivals=planned_arrivals or {},
            )
        ],
        unassigned_tasks=unassigned_tasks or [],
    )


def violation_types(result) -> set[str]:
    return {violation.violation_type for violation in result.violations}


def test_valid_plan_is_accepted() -> None:
    result = PlanVerifier().verify(
        make_state(), make_plan(planned_arrivals={"T1": 5})
    )

    assert result.valid
    assert result.violations == ()


def test_unknown_vehicle_is_rejected() -> None:
    result = PlanVerifier().verify(make_state(), make_plan(vehicle_id="UNKNOWN"))

    assert not result.valid
    assert "vehicle_exists" in violation_types(result)


def test_broken_vehicle_is_rejected() -> None:
    result = PlanVerifier().verify(
        make_state(vehicle_status=VehicleStatus.BROKEN), make_plan()
    )

    assert not result.valid
    assert "vehicle_available" in violation_types(result)


def test_unknown_task_is_rejected() -> None:
    result = PlanVerifier().verify(make_state(), make_plan(task_ids=["UNKNOWN"]))

    assert not result.valid
    assert "task_exists" in violation_types(result)


def test_completed_task_cannot_be_rescheduled() -> None:
    result = PlanVerifier().verify(
        make_state(tasks=[make_task(status=ServiceTaskStatus.COMPLETED)]), make_plan()
    )

    assert not result.valid
    assert "task_status_valid" in violation_types(result)


def test_duplicate_task_in_one_route_is_rejected() -> None:
    plan = make_plan()
    plan.vehicle_routes[0].task_sequence.append("T1")

    result = PlanVerifier().verify(make_state(), plan)

    assert not result.valid
    assert "duplicate_assignment" in violation_types(result)


def test_duplicate_task_across_vehicles_is_rejected() -> None:
    plan = DispatchPlan(
        plan_id="P1",
        vehicle_routes=[
            VehicleRoute("V1", ["T1"]),
            VehicleRoute("V2", ["T1"]),
        ],
    )

    result = PlanVerifier().verify(make_state(), plan)

    assert not result.valid
    assert "duplicate_assignment" in violation_types(result)


def test_closed_or_unreachable_road_is_rejected() -> None:
    result = PlanVerifier().verify(
        make_state(roads=[Road("AB", "A", "B", 2, 5, RoadStatus.CLOSED)]),
        make_plan(),
    )

    assert not result.valid
    assert "road_accessible" in violation_types(result)


def test_capacity_violation_is_rejected() -> None:
    result = PlanVerifier().verify(
        make_state(
            tasks=[
                make_task("T1", demand=3),
                make_task("T2", target_id="W2", demand=3),
            ]
        ),
        make_plan(task_ids=["T1", "T2"]),
    )

    assert not result.valid
    assert "capacity_valid" in violation_types(result)


def test_hard_deadline_is_validated_against_service_completion_time() -> None:
    result = PlanVerifier().verify(
        make_state(tasks=[make_task(deadline=7)]), make_plan()
    )

    assert not result.valid
    assert "deadline_valid" in violation_types(result)


def test_must_serve_task_cannot_be_unassigned() -> None:
    plan = DispatchPlan(plan_id="P1", vehicle_routes=[], unassigned_tasks=["T1"])

    result = PlanVerifier().verify(make_state(), plan)

    assert not result.valid
    assert "must_serve_unassigned" in violation_types(result)


def test_normal_task_may_be_unassigned() -> None:
    plan = DispatchPlan(plan_id="P1", vehicle_routes=[], unassigned_tasks=["T1"])

    result = PlanVerifier().verify(
        make_state(tasks=[make_task(priority=1, deadline=None)]), plan
    )

    assert result.valid


def test_task_cannot_be_assigned_and_unassigned() -> None:
    result = PlanVerifier().verify(
        make_state(), make_plan(unassigned_tasks=["T1"])
    )

    assert not result.valid
    assert "assignment_unassigned_conflict" in violation_types(result)


def test_planned_arrival_must_match_independently_computed_eta() -> None:
    result = PlanVerifier().verify(
        make_state(), make_plan(planned_arrivals={"T1": 4})
    )

    assert not result.valid
    assert "planned_arrivals_consistent" in violation_types(result)


def test_verifier_does_not_mutate_state_or_plan() -> None:
    state = make_state()
    plan = make_plan(planned_arrivals={"T1": 5})
    original_state = deepcopy(state)
    original_plan = deepcopy(plan)

    PlanVerifier().verify(state, plan)

    assert state.tasks["T1"] == original_state.tasks["T1"]
    assert state.vehicles["V1"] == original_state.vehicles["V1"]
    assert state.road_network.get_road("AB") == original_state.road_network.get_road("AB")
    assert plan == original_plan


def test_same_input_produces_same_verification_result() -> None:
    state = make_state()
    plan = make_plan(planned_arrivals={"T1": 5})

    assert PlanVerifier().verify(state, plan) == PlanVerifier().verify(state, plan)


def test_arrival_excludes_service_and_deadline_uses_completion_time() -> None:
    roads = [Road("AB", "A", "B", 2, 10)]
    invalid_state = make_state(
        roads=roads,
        tasks=[make_task(deadline=14)],
    )
    plan = make_plan(planned_arrivals={"T1": 10})

    invalid_result = PlanVerifier().verify(invalid_state, plan)
    assert "deadline_valid" in violation_types(invalid_result)
    assert "planned_arrivals_consistent" not in violation_types(invalid_result)

    valid_state = make_state(
        roads=[Road("AB", "A", "B", 2, 10)],
        tasks=[make_task(deadline=15)],
    )
    valid_result = PlanVerifier().verify(valid_state, plan)
    assert valid_result.valid


def test_later_task_arrival_includes_previous_service_time() -> None:
    state = make_state(
        tasks=[
            make_task("T1", deadline=10),
            make_task("T2", target_id="W2", deadline=19),
        ]
    )
    plan = make_plan(
        task_ids=["T1", "T2"],
        planned_arrivals={"T1": 5, "T2": 14},
    )

    assert PlanVerifier().verify(state, plan).valid
