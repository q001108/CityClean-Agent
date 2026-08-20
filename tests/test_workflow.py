"""Integration tests for the explicit v0.1 event-driven replanning workflow."""

from __future__ import annotations

from cityclean_agent.domain.enums import (
    CityEventType,
    RoadStatus,
    ServiceTaskStatus,
    VehicleStatus,
)
from cityclean_agent.domain.models import (
    CityEvent,
    CityState,
    DispatchPlan,
    Road,
    ServiceTask,
    Vehicle,
    VehicleRoute,
    WastePoint,
)
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.optimizer.results import OptimizationResult, OptimizationStatus
from cityclean_agent.policy.models import PolicyProfile
from cityclean_agent.simulator.city_sim import CitySim
from cityclean_agent.workflow import WorkflowStatus, process_event


def make_event(
    event_id: str,
    event_type: CityEventType,
    affected_entities: list[str],
    *,
    timestamp: int = 0,
    deadline: int | None = None,
    severity: int = 1,
) -> CityEvent:
    return CityEvent(
        event_id=event_id,
        event_type=event_type,
        timestamp=timestamp,
        location="A",
        description="workflow test event",
        affected_entities=affected_entities,
        severity=severity,
        deadline=deadline,
    )


def make_state(
    *,
    current_time: int = 0,
    tasks: list[ServiceTask] | None = None,
    vehicles: list[Vehicle] | None = None,
    roads: list[Road] | None = None,
    active_plan: DispatchPlan | None = None,
) -> CityState:
    waste_points = {
        "W1": WastePoint("W1", "B", 20, 8, 0, "mixed", "residential", 1),
        "W2": WastePoint("W2", "C", 20, 6, 0, "mixed", "residential", 1),
    }
    return CityState(
        current_time=current_time,
        waste_points=waste_points,
        vehicles={
            vehicle.id: vehicle
            for vehicle in vehicles
            or [Vehicle("V1", "A", 20, 0, VehicleStatus.AVAILABLE, 30)]
        },
        transfer_stations={},
        road_network=RoadNetwork(roads or [Road("AB", "A", "B", 1, 5)]),
        tasks={task.task_id: task for task in tasks or []},
        active_plan=active_plan,
    )


def make_task(
    task_id: str,
    target_id: str,
    *,
    demand: float = 3,
    priority: int = 1,
    status: ServiceTaskStatus = ServiceTaskStatus.PENDING,
) -> ServiceTask:
    return ServiceTask(
        task_id=task_id,
        source_event_id=f"source-{task_id}",
        target_id=target_id,
        demand=demand,
        priority=priority,
        deadline=None,
        status=status,
    )


def route_task_ids(plan: DispatchPlan) -> set[str]:
    return {
        task_id
        for route in plan.vehicle_routes
        for task_id in route.task_sequence
    }


def test_normal_workflow_installs_verified_plan_and_citysim_executes_it() -> None:
    sim = CitySim(make_state(tasks=[make_task("T1", "W1")]))

    result = process_event(
        sim, make_event("E1", CityEventType.ROAD_CLOSURE, [])
    )

    assert result.status is WorkflowStatus.SUCCESS
    assert result.verification_result is not None
    assert result.verification_result.valid
    assert result.plan is not None
    assert route_task_ids(result.plan) == {"T1"}
    assert sim.get_state().tasks["T1"].status is ServiceTaskStatus.ASSIGNED

    sim.step()
    sim.step()
    state = sim.get_state()
    assert state.tasks["T1"].status is ServiceTaskStatus.COMPLETED
    assert state.current_time == 10


def test_vehicle_breakdown_preserves_completed_state_and_replans_remaining_work() -> None:
    old_plan = DispatchPlan(
        "old-plan", [VehicleRoute("V1", ["T2"], {"T2": 15})]
    )
    sim = CitySim(
        make_state(
            current_time=10,
            tasks=[
                make_task("T1", "W1", demand=2, status=ServiceTaskStatus.COMPLETED),
                make_task("T2", "W2", status=ServiceTaskStatus.ASSIGNED),
            ],
            vehicles=[
                Vehicle("V1", "A", 20, 2, VehicleStatus.AVAILABLE, 30, ["T2"]),
                Vehicle("V2", "A", 20, 1, VehicleStatus.AVAILABLE, 30),
            ],
            roads=[Road("AC", "A", "C", 1, 5)],
            active_plan=old_plan,
        )
    )

    result = process_event(
        sim, make_event("E1", CityEventType.VEHICLE_BREAKDOWN, ["V1"], timestamp=10)
    )

    assert result.status is WorkflowStatus.SUCCESS
    assert result.verification_result is not None
    assert result.verification_result.valid
    assert result.plan is not None
    assert {route.vehicle_id for route in result.plan.vehicle_routes} == {"V2"}
    assert route_task_ids(result.plan) == {"T2"}

    state = sim.get_state()
    assert state.current_time == 10
    assert state.tasks["T1"].status is ServiceTaskStatus.COMPLETED
    assert state.vehicles["V1"].status is VehicleStatus.BROKEN
    assert state.vehicles["V1"].current_load == 2
    assert state.vehicles["V2"].current_load == 1
    assert state.waste_points["W1"].current_load == 8

    sim.step()
    sim.step()
    assert sim.get_state().tasks["T2"].status is ServiceTaskStatus.COMPLETED


def test_replanning_keeps_in_progress_task_locked() -> None:
    old_plan = DispatchPlan(
        "old-plan",
        [VehicleRoute("V1", ["T2"]), VehicleRoute("V2", ["T3"])],
    )
    sim = CitySim(
        make_state(
            tasks=[
                make_task("T1", "W1", demand=2, status=ServiceTaskStatus.COMPLETED),
                make_task("T2", "W1", status=ServiceTaskStatus.IN_PROGRESS),
                make_task("T3", "W2", status=ServiceTaskStatus.ASSIGNED),
            ],
            vehicles=[
                Vehicle("V1", "B", 20, 2, VehicleStatus.SERVICING, 30, ["T2"]),
                Vehicle("V2", "A", 20, 1, VehicleStatus.AVAILABLE, 30, ["T3"]),
            ],
            roads=[Road("AC", "A", "C", 1, 5)],
            active_plan=old_plan,
        )
    )

    result = process_event(
        sim, make_event("E1", CityEventType.ROAD_CLOSURE, [])
    )

    assert result.status is WorkflowStatus.SUCCESS
    assert result.plan is not None
    assert {route.vehicle_id for route in result.plan.vehicle_routes} == {"V2"}
    state = sim.get_state()
    assert state.tasks["T1"].status is ServiceTaskStatus.COMPLETED
    assert state.tasks["T2"].status is ServiceTaskStatus.IN_PROGRESS
    assert state.tasks["T3"].status is ServiceTaskStatus.ASSIGNED
    assert state.vehicles["V1"].current_node_id == "B"
    assert state.vehicles["V1"].current_load == 2
    assert state.vehicles["V1"].assigned_tasks == ["T2"]
    assert state.vehicles["V2"].assigned_tasks == ["T3"]
    assert len(state.vehicles["V2"].assigned_tasks) == len(
        set(state.vehicles["V2"].assigned_tasks)
    )

    sim.step()
    assert sim.get_state().tasks["T2"].status is ServiceTaskStatus.COMPLETED


def test_release_removes_old_assignments_but_keeps_in_progress_assignment() -> None:
    sim = CitySim(
        make_state(
            tasks=[
                make_task("T1", "W1", status=ServiceTaskStatus.COMPLETED),
                make_task("T2", "W1", status=ServiceTaskStatus.IN_PROGRESS),
                make_task("T3", "W2", status=ServiceTaskStatus.ASSIGNED),
            ],
            vehicles=[
                Vehicle("V1", "B", 20, 2, VehicleStatus.SERVICING, 30, ["T1", "T2"]),
                Vehicle("V2", "A", 20, 1, VehicleStatus.AVAILABLE, 30, ["T3"]),
            ],
            roads=[Road("AC", "A", "C", 1, 5)],
            active_plan=DispatchPlan(
                "old-plan",
                [VehicleRoute("V1", ["T2"]), VehicleRoute("V2", ["T3"])],
            ),
        )
    )

    assert sim.release_unstarted_tasks() == ("T3",)

    state = sim.get_state()
    assert state.active_plan is None
    assert state.tasks["T1"].status is ServiceTaskStatus.COMPLETED
    assert state.tasks["T2"].status is ServiceTaskStatus.IN_PROGRESS
    assert state.tasks["T3"].status is ServiceTaskStatus.PENDING
    assert state.vehicles["V1"].assigned_tasks == ["T2"]
    assert state.vehicles["V2"].assigned_tasks == []


def test_road_closure_updates_network_and_replans_using_alternative_path() -> None:
    old_plan = DispatchPlan(
        "old-plan", [VehicleRoute("V1", ["T1"], {"T1": 5})]
    )
    sim = CitySim(
        make_state(
            tasks=[make_task("T1", "W1", status=ServiceTaskStatus.ASSIGNED)],
            vehicles=[Vehicle("V1", "A", 20, 0, VehicleStatus.AVAILABLE, 30, ["T1"])],
            roads=[
                Road("AB", "A", "B", 1, 5),
                Road("AX", "A", "X", 1, 3),
                Road("XB", "X", "B", 1, 3),
            ],
            active_plan=old_plan,
        )
    )

    result = process_event(
        sim, make_event("E1", CityEventType.ROAD_CLOSURE, ["AB"])
    )

    assert result.status is WorkflowStatus.SUCCESS
    assert result.plan is not None
    assert result.plan.vehicle_routes[0].planned_arrivals == {"T1": 6}
    state = sim.get_state()
    assert state.road_network.get_road("AB").status is RoadStatus.CLOSED


def test_urgent_task_creates_high_priority_task_and_uses_urgent_policy() -> None:
    sim = CitySim(make_state())

    result = process_event(
        sim,
        make_event(
            "E1", CityEventType.URGENT_TASK, ["W1"], deadline=20, severity=3
        ),
    )

    assert result.status is WorkflowStatus.SUCCESS
    assert result.policy_decision is not None
    assert result.policy_decision.policy_profile is PolicyProfile.URGENT_RESPONSE
    state = sim.get_state()
    task = state.tasks["task-E1-W1"]
    assert task.priority >= 10
    assert task.status is ServiceTaskStatus.ASSIGNED
    assert result.plan is not None
    assert route_task_ids(result.plan) == {task.task_id}


def test_overflow_task_demand_uses_post_event_waste_load() -> None:
    sim = CitySim(make_state())

    result = process_event(
        sim, make_event("E1", CityEventType.WASTE_OVERFLOW, ["W1"])
    )

    assert result.status is WorkflowStatus.SUCCESS
    state = sim.get_state()
    assert state.waste_points["W1"].current_load == 20
    assert state.tasks["task-E1-W1"].demand == 20
    assert state.tasks["task-E1-W1"].status is ServiceTaskStatus.ASSIGNED


def test_infeasible_workflow_does_not_install_a_plan() -> None:
    sim = CitySim(
        make_state(
            tasks=[
                make_task(
                    "T1", "W1", priority=10, status=ServiceTaskStatus.ASSIGNED
                )
            ],
            vehicles=[Vehicle("V1", "A", 20, 0, VehicleStatus.AVAILABLE, 30, ["T1"])],
            active_plan=DispatchPlan("old-plan", [VehicleRoute("V1", ["T1"])]),
        )
    )

    result = process_event(
        sim,
        make_event("E1", CityEventType.ROAD_CLOSURE, ["AB"]),
    )

    assert result.status is WorkflowStatus.INFEASIBLE
    assert result.reason == "REQUIRED_TASK_UNREACHABLE"
    state = sim.get_state()
    assert state.active_plan is None
    assert state.tasks["T1"].status is ServiceTaskStatus.PENDING
    assert state.vehicles["V1"].assigned_tasks == []
    sim.step()
    assert sim.get_state().tasks["T1"].status is ServiceTaskStatus.PENDING


class InvalidPlanOptimizer:
    """Test-only optimizer replacement that returns a plan the verifier rejects."""

    def optimize(self, state, parameters) -> OptimizationResult:
        del state, parameters
        return OptimizationResult(
            status=OptimizationStatus.FEASIBLE,
            plan=DispatchPlan(
                "invalid-plan", [VehicleRoute("UNKNOWN", ["T1"])]
            ),
        )


def test_verification_failure_does_not_install_invalid_plan() -> None:
    sim = CitySim(
        make_state(
            tasks=[make_task("T1", "W1", status=ServiceTaskStatus.ASSIGNED)],
            vehicles=[Vehicle("V1", "A", 20, 0, VehicleStatus.AVAILABLE, 30, ["T1"])],
            active_plan=DispatchPlan("old-plan", [VehicleRoute("V1", ["T1"])]),
        )
    )

    result = process_event(
        sim,
        make_event("E1", CityEventType.ROAD_CLOSURE, []),
        optimizer=InvalidPlanOptimizer(),
    )

    assert result.status is WorkflowStatus.VERIFICATION_FAILED
    assert result.verification_result is not None
    assert not result.verification_result.valid
    assert sim.get_state().active_plan is None
    assert sim.get_state().tasks["T1"].status is ServiceTaskStatus.PENDING
    assert sim.get_state().vehicles["V1"].assigned_tasks == []
    sim.step()
    assert sim.get_state().tasks["T1"].status is ServiceTaskStatus.PENDING


def test_repeated_workflow_event_is_ignored_without_a_second_state_effect() -> None:
    sim = CitySim(make_state())
    event = make_event("E1", CityEventType.WASTE_OVERFLOW, ["W1"])

    first_result = process_event(sim, event)
    state_after_first = sim.get_state()
    second_result = process_event(sim, event)
    state_after_second = sim.get_state()

    assert first_result.status is WorkflowStatus.SUCCESS
    assert second_result.status is WorkflowStatus.IGNORED
    assert state_after_second.waste_points["W1"] == state_after_first.waste_points["W1"]
    assert state_after_second.tasks == state_after_first.tasks
    assert state_after_second.vehicles == state_after_first.vehicles
    assert state_after_second.active_plan == state_after_first.active_plan
