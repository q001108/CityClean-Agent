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
from cityclean_agent.simulator.city_sim import CitySim


def make_state(*, with_plan: bool = False) -> CityState:
    waste_point = WastePoint(
        id="W1",
        node_id="B",
        capacity=20,
        current_load=5,
        generation_rate=1,
        waste_type="mixed",
        zone_type="residential",
        priority=1,
    )
    vehicle = Vehicle(
        id="V1",
        current_node_id="A",
        capacity=20,
        current_load=0,
        status=VehicleStatus.AVAILABLE,
        speed=30,
    )
    task = ServiceTask(
        task_id="T1",
        source_event_id="E0",
        target_id="W1",
        demand=4,
        priority=1,
        deadline=30,
    )
    plan = (
        DispatchPlan(
            plan_id="P1",
            vehicle_routes=[VehicleRoute(vehicle_id="V1", task_sequence=["T1"])],
        )
        if with_plan
        else None
    )
    return CityState(
        current_time=0,
        waste_points={waste_point.id: waste_point},
        vehicles={vehicle.id: vehicle},
        transfer_stations={},
        road_network=RoadNetwork([Road("R1", "A", "B", 2, 5)]),
        tasks={task.task_id: task},
        active_plan=plan,
    )


def event(
    event_id: str,
    event_type: CityEventType,
    affected_entities: list[str],
    *,
    timestamp: int = 0,
) -> CityEvent:
    return CityEvent(
        event_id=event_id,
        event_type=event_type,
        timestamp=timestamp,
        location="A",
        description="test event",
        affected_entities=affected_entities,
        severity=1,
        deadline=None,
    )


def test_reset_restores_initial_state_repeatedly() -> None:
    sim = CitySim(make_state())
    sim.step()
    sim.inject_event(event("E1", CityEventType.ROAD_CLOSURE, ["R1"]))

    sim.reset()
    first_reset = sim.get_state()
    sim.step()
    sim.reset()
    second_reset = sim.get_state()

    assert first_reset.current_time == second_reset.current_time == 0
    assert first_reset.waste_points["W1"].current_load == 5
    assert second_reset.waste_points["W1"].current_load == 5
    assert first_reset.road_network.get_road("R1").status is RoadStatus.OPEN
    assert second_reset.road_network.get_road("R1").status is RoadStatus.OPEN


def test_same_initial_state_and_inputs_are_deterministic() -> None:
    sim_a = CitySim(make_state())
    sim_b = CitySim(make_state())
    closure = event("E1", CityEventType.ROAD_CLOSURE, ["R1"], timestamp=5)

    for sim in (sim_a, sim_b):
        sim.inject_event(closure)
        sim.step()
        sim.step()

    state_a = sim_a.get_state()
    state_b = sim_b.get_state()
    assert sim_a.calculate_metrics() == sim_b.calculate_metrics()
    assert state_a.current_time == state_b.current_time
    assert state_a.waste_points["W1"].current_load == state_b.waste_points["W1"].current_load
    assert (
        state_a.road_network.get_road("R1").status
        is state_b.road_network.get_road("R1").status
    )


def test_step_generates_waste_and_advances_time_across_multiple_ticks() -> None:
    sim = CitySim(make_state())

    sim.step()
    sim.step()
    sim.step()

    state = sim.get_state()
    assert state.current_time == 15
    assert state.waste_points["W1"].current_load == 20


def test_vehicle_breakdown_changes_vehicle_and_releases_incomplete_task() -> None:
    state = make_state(with_plan=True)
    state.vehicles["V1"].assigned_tasks.append("T1")
    state.tasks["T1"].status = ServiceTaskStatus.ASSIGNED
    sim = CitySim(state)

    assert sim.inject_event(event("E1", CityEventType.VEHICLE_BREAKDOWN, ["V1"]))

    result = sim.get_state()
    assert result.vehicles["V1"].status is VehicleStatus.BROKEN
    assert result.vehicles["V1"].assigned_tasks == []
    assert result.tasks["T1"].status is ServiceTaskStatus.PENDING


def test_road_closure_updates_the_only_road_network_truth_immediately() -> None:
    sim = CitySim(make_state())

    sim.inject_event(event("E1", CityEventType.ROAD_CLOSURE, ["R1"]))

    snapshot = sim.get_state()
    assert snapshot.road_network.get_road("R1").status is RoadStatus.CLOSED
    assert snapshot.road_network.shortest_path("A", "B") is None


def test_event_idempotency_prevents_duplicate_overflow_effects() -> None:
    sim = CitySim(make_state())
    overflow = event("E1", CityEventType.WASTE_OVERFLOW, ["W1"])

    assert sim.inject_event(overflow)
    assert not sim.inject_event(overflow)

    state = sim.get_state()
    assert state.waste_points["W1"].current_load == 20
    assert set(state.active_events) == {"E1"}


def test_get_state_snapshot_cannot_mutate_internal_city_or_road_state() -> None:
    sim = CitySim(make_state())
    snapshot = sim.get_state()
    snapshot.waste_points["W1"].current_load = 999
    snapshot.vehicles["V1"].status = VehicleStatus.BROKEN
    snapshot.road_network.set_road_status("R1", RoadStatus.CLOSED)
    snapshot.active_events["fake"] = event("fake", CityEventType.URGENT_TASK, ["W1"])

    result = sim.get_state()
    assert result.waste_points["W1"].current_load == 5
    assert result.vehicles["V1"].status is VehicleStatus.AVAILABLE
    assert result.road_network.get_road("R1").status is RoadStatus.OPEN
    assert result.active_events == {}


def test_existing_plan_moves_then_services_task_without_exceeding_capacity() -> None:
    sim = CitySim(make_state(with_plan=True))

    sim.step()
    after_travel = sim.get_state()
    assert after_travel.current_time == 5
    assert after_travel.vehicles["V1"].current_node_id == "B"
    assert after_travel.tasks["T1"].status is ServiceTaskStatus.ASSIGNED

    sim.step()
    after_service = sim.get_state()
    assert after_service.tasks["T1"].status is ServiceTaskStatus.COMPLETED
    assert after_service.vehicles["V1"].current_load == 4
    assert after_service.vehicles["V1"].status is VehicleStatus.AVAILABLE
    assert after_service.waste_points["W1"].current_load == 11


def test_calculate_metrics_contains_only_currently_observable_values() -> None:
    sim = CitySim(make_state())
    sim.inject_event(event("E1", CityEventType.VEHICLE_BREAKDOWN, ["V1"]))
    sim.step()

    assert sim.calculate_metrics() == {
        "current_time": 5,
        "task_count": 1,
        "completed_task_count": 0,
        "overflow_count": 0,
        "broken_vehicle_count": 1,
    }
