from __future__ import annotations

import pytest

from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import CityEvent, CityState, Road, ServiceTask, Vehicle, WastePoint
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.domain.task_builder import (
    URGENT_TASK_MIN_PRIORITY,
    build_task_changes,
)
from cityclean_agent.simulator.city_sim import CitySim


def make_state(*, tasks: dict[str, ServiceTask] | None = None) -> CityState:
    waste_point = WastePoint(
        id="W1",
        node_id="N1",
        capacity=20,
        current_load=8,
        generation_rate=1,
        waste_type="mixed",
        zone_type="school",
        priority=2,
    )
    vehicle = Vehicle(
        id="V1",
        current_node_id="N1",
        capacity=30,
        current_load=0,
        status=VehicleStatus.AVAILABLE,
        speed=30,
    )
    return CityState(
        current_time=0,
        waste_points={"W1": waste_point},
        vehicles={"V1": vehicle},
        transfer_stations={},
        road_network=RoadNetwork([Road("R1", "N1", "N2", 1, 5)]),
        tasks={} if tasks is None else tasks,
    )


def make_event(
    event_id: str,
    event_type: CityEventType,
    target_id: str = "W1",
    *,
    severity: int = 3,
    deadline: int | None = 30,
    demand: float | None = None,
) -> CityEvent:
    metadata = {} if demand is None else {"demand": demand}
    return CityEvent(
        event_id=event_id,
        event_type=event_type,
        timestamp=0,
        location="N1",
        description="test event",
        affected_entities=[target_id],
        severity=severity,
        deadline=deadline,
        metadata=metadata,
    )


def apply_event_tasks(sim: CitySim, event: CityEvent):
    changes = build_task_changes(event, sim.get_state())
    sim.apply_task_changes(changes)
    return changes


def test_overflow_creates_service_task_for_existing_waste_point() -> None:
    sim = CitySim(make_state())
    changes = apply_event_tasks(sim, make_event("E1", CityEventType.WASTE_OVERFLOW))

    task = changes.created_tasks[0]
    assert task.task_id == "task-E1-W1"
    assert task.target_id == "W1"
    assert task.demand == 8
    assert task.priority == 3
    assert sim.get_state().tasks == {task.task_id: task}


def test_urgent_task_creates_high_priority_service_task() -> None:
    sim = CitySim(make_state())
    changes = apply_event_tasks(sim, make_event("E1", CityEventType.URGENT_TASK))

    task = changes.created_tasks[0]
    assert task.priority == URGENT_TASK_MIN_PRIORITY
    assert task.service_duration_min == 5


def test_same_event_does_not_create_duplicate_task() -> None:
    sim = CitySim(make_state())
    event = make_event("E1", CityEventType.WASTE_OVERFLOW)
    apply_event_tasks(sim, event)

    changes = apply_event_tasks(sim, event)

    assert changes.created_tasks == ()
    assert changes.updated_tasks == ()
    assert len(sim.get_state().tasks) == 1


def test_overflow_updates_existing_pending_task_without_creating_another() -> None:
    existing_task = ServiceTask(
        task_id="T1",
        source_event_id="E0",
        target_id="W1",
        demand=4,
        priority=1,
        deadline=40,
    )
    sim = CitySim(make_state(tasks={"T1": existing_task}))

    changes = apply_event_tasks(
        sim,
        make_event(
            "E1", CityEventType.WASTE_OVERFLOW, severity=5, deadline=20, demand=9
        ),
    )

    assert changes.created_tasks == ()
    assert len(changes.updated_tasks) == 1
    updated_task = sim.get_state().tasks["T1"]
    assert updated_task.demand == 9
    assert updated_task.priority == 5
    assert updated_task.deadline == 20


def test_urgent_event_updates_existing_unfinished_task() -> None:
    existing_task = ServiceTask(
        task_id="T1",
        source_event_id="E0",
        target_id="W1",
        demand=4,
        priority=2,
        deadline=None,
    )
    sim = CitySim(make_state(tasks={"T1": existing_task}))

    changes = apply_event_tasks(
        sim, make_event("E1", CityEventType.URGENT_TASK, deadline=15)
    )

    assert changes.created_tasks == ()
    updated_task = sim.get_state().tasks["T1"]
    assert updated_task.priority == URGENT_TASK_MIN_PRIORITY
    assert updated_task.deadline == 15


def test_completed_task_is_not_revived_by_later_event() -> None:
    completed_task = ServiceTask(
        task_id="T1",
        source_event_id="E0",
        target_id="W1",
        demand=4,
        priority=2,
        deadline=10,
        status=ServiceTaskStatus.COMPLETED,
    )
    sim = CitySim(make_state(tasks={"T1": completed_task}))

    changes = apply_event_tasks(sim, make_event("E1", CityEventType.WASTE_OVERFLOW))

    state = sim.get_state()
    assert {task.task_id for task in changes.created_tasks} == {"task-E1-W1"}
    assert state.tasks["T1"].status is ServiceTaskStatus.COMPLETED
    assert state.tasks["task-E1-W1"].status is ServiceTaskStatus.PENDING


def test_urgent_task_rejects_nonexistent_waste_point() -> None:
    with pytest.raises(ValueError, match="existing WastePoint"):
        build_task_changes(
            make_event("E1", CityEventType.URGENT_TASK, target_id="UNKNOWN"),
            make_state(),
        )


@pytest.mark.parametrize(
    "event_type",
    [CityEventType.VEHICLE_BREAKDOWN, CityEventType.ROAD_CLOSURE],
)
def test_non_task_events_do_not_create_or_update_tasks(event_type: CityEventType) -> None:
    sim = CitySim(make_state())

    changes = apply_event_tasks(sim, make_event("E1", event_type))

    assert changes.created_tasks == ()
    assert changes.updated_tasks == ()
    assert sim.get_state().tasks == {}


def test_task_builder_is_deterministic_and_does_not_mutate_input_state() -> None:
    event = make_event("E1", CityEventType.URGENT_TASK, demand=6)
    state_a = make_state()
    state_b = make_state()

    changes_a = build_task_changes(event, state_a)
    changes_b = build_task_changes(event, state_b)

    assert changes_a == changes_b
    assert state_a.tasks == {}
    assert state_b.tasks == {}


def test_task_builder_does_not_use_event_description() -> None:
    event_a = make_event("E1", CityEventType.URGENT_TASK)
    event_b = make_event("E1", CityEventType.URGENT_TASK)
    event_b.description = "A different natural-language governance context."

    assert build_task_changes(event_a, make_state()) == build_task_changes(
        event_b, make_state()
    )
