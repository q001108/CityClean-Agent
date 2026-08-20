from __future__ import annotations

from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus, VehicleStatus
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
from cityclean_agent.domain.task_builder import build_task_changes
from cityclean_agent.simulator.city_sim import CitySim, RuntimeStats
from cityclean_agent.workflow import process_event


def make_task(
    task_id: str = "T1",
    *,
    demand: float = 2,
    status: ServiceTaskStatus = ServiceTaskStatus.PENDING,
    created_at: int = 0,
) -> ServiceTask:
    return ServiceTask(
        task_id=task_id,
        source_event_id="E0",
        target_id="W1",
        demand=demand,
        priority=1,
        deadline=None,
        status=status,
        created_at=created_at,
    )


def make_state(
    *,
    point_load: float = 2,
    point_capacity: float = 20,
    generation_rate: float = 0,
    vehicle_node: str = "A",
    tasks: list[ServiceTask] | None = None,
    roads: list[Road] | None = None,
    active_plan: DispatchPlan | None = None,
) -> CityState:
    return CityState(
        current_time=0,
        waste_points={
            "W1": WastePoint(
                "W1",
                "B",
                point_capacity,
                point_load,
                generation_rate,
                "mixed",
                "residential",
                1,
            )
        },
        vehicles={
            "V1": Vehicle("V1", vehicle_node, 30, 0, VehicleStatus.AVAILABLE, 30)
        },
        transfer_stations={},
        road_network=RoadNetwork(
            roads if roads is not None else [Road("AB", "A", "B", 2, 5)]
        ),
        tasks={task.task_id: task for task in tasks or []},
        active_plan=active_plan,
    )


def test_task_builder_records_current_simulation_time_as_created_at() -> None:
    state = make_state()
    state.current_time = 12
    event = CityEvent(
        "E1",
        CityEventType.URGENT_TASK,
        12,
        "B",
        ["W1"],
        2,
        30,
        description="urgent",
    )

    changes = build_task_changes(event, state)

    assert changes.created_tasks[0].created_at == 12


def test_citysim_records_actual_service_completion_time() -> None:
    sim = CitySim(
        make_state(
            vehicle_node="B",
            tasks=[make_task(created_at=4)],
            active_plan=DispatchPlan("P1", [VehicleRoute("V1", ["T1"])]),
        )
    )

    sim.step()

    task = sim.get_state().tasks["T1"]
    assert task.status is ServiceTaskStatus.COMPLETED
    assert task.completed_at == 5


def test_distance_is_counted_when_a_road_segment_is_actually_completed() -> None:
    sim = CitySim(
        make_state(
            tasks=[make_task()],
            active_plan=DispatchPlan("P1", [VehicleRoute("V1", ["T1"])]),
        )
    )

    sim.step()

    assert sim.get_runtime_stats() == RuntimeStats(total_distance=2.0, overflow_count=0)


def test_distance_accumulates_only_after_multiple_ticks_finish_a_road() -> None:
    sim = CitySim(
        make_state(
            tasks=[make_task()],
            roads=[Road("AB", "A", "B", 2, 10)],
            active_plan=DispatchPlan("P1", [VehicleRoute("V1", ["T1"])]),
        )
    )

    sim.step()
    assert sim.get_runtime_stats().total_distance == 0.0
    sim.step()
    assert sim.get_runtime_stats().total_distance == 2.0


def test_replanning_counts_only_executed_distance_not_old_plan_distance() -> None:
    sim = CitySim(
        make_state(
            tasks=[make_task(status=ServiceTaskStatus.ASSIGNED)],
            roads=[
                Road("AB", "A", "B", 100, 5),
                Road("AX", "A", "X", 2, 3),
                Road("XB", "X", "B", 2, 3),
            ],
            active_plan=DispatchPlan("old", [VehicleRoute("V1", ["T1"])]),
        )
    )

    result = process_event(
        sim,
        CityEvent(
            "E1", CityEventType.ROAD_CLOSURE, 0, "A", ["AB"], 1, None,
            description="closure",
        ),
    )

    assert result.plan is not None
    assert sim.get_runtime_stats().total_distance == 0.0
    sim.step()
    sim.step()
    assert sim.get_runtime_stats().total_distance == 4.0


def test_reset_clears_runtime_stats() -> None:
    sim = CitySim(
        make_state(
            point_load=9,
            point_capacity=10,
            generation_rate=1,
            tasks=[make_task()],
            active_plan=DispatchPlan("P1", [VehicleRoute("V1", ["T1"])]),
        )
    )

    sim.step()
    assert sim.get_runtime_stats() == RuntimeStats(total_distance=2.0, overflow_count=1)
    sim.reset()
    assert sim.get_runtime_stats() == RuntimeStats(total_distance=0.0, overflow_count=0)


def test_first_overflow_transition_counts_once_and_persistent_overflow_does_not_repeat() -> None:
    sim = CitySim(
        make_state(point_load=9, point_capacity=10, generation_rate=1, roads=[])
    )

    sim.step()
    assert sim.get_runtime_stats().overflow_count == 1
    sim.step()
    assert sim.get_runtime_stats().overflow_count == 1


def test_cleanup_below_capacity_allows_a_future_overflow_incident() -> None:
    sim = CitySim(
        make_state(
            point_load=9,
            point_capacity=10,
            generation_rate=1,
            vehicle_node="B",
            tasks=[make_task(demand=10)],
            roads=[],
        )
    )

    sim.step()
    assert sim.get_runtime_stats().overflow_count == 1
    sim.install_plan(DispatchPlan("P1", [VehicleRoute("V1", ["T1"])]))
    sim.step()
    assert sim.get_state().waste_points["W1"].current_load == 9
    assert sim.get_runtime_stats().overflow_count == 1
    sim.step()
    assert sim.get_runtime_stats().overflow_count == 2


def test_external_overflow_event_uses_the_same_incident_rule() -> None:
    sim = CitySim(
        make_state(point_load=9, point_capacity=10, generation_rate=0, roads=[])
    )
    first_event = CityEvent(
        "E1", CityEventType.WASTE_OVERFLOW, 0, "B", ["W1"], 1, None,
        description="overflow",
    )
    second_event = CityEvent(
        "E2", CityEventType.WASTE_OVERFLOW, 0, "B", ["W1"], 1, None,
        description="overflow",
    )

    sim.inject_event(first_event)
    assert sim.get_runtime_stats().overflow_count == 1
    sim.inject_event(second_event)
    assert sim.get_runtime_stats().overflow_count == 1
