from __future__ import annotations

from copy import deepcopy

from cityclean_agent.domain.enums import ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import CityState, ServiceTask, Vehicle, WastePoint
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.metrics.calculator import Metrics, MetricsCalculator
from cityclean_agent.simulator.city_sim import RuntimeStats


def make_task(
    task_id: str,
    *,
    priority: int = 1,
    status: ServiceTaskStatus = ServiceTaskStatus.PENDING,
    created_at: int = 0,
    completed_at: int | None = None,
) -> ServiceTask:
    return ServiceTask(
        task_id=task_id,
        source_event_id=f"E-{task_id}",
        target_id="W1",
        demand=1,
        priority=priority,
        deadline=None,
        status=status,
        created_at=created_at,
        completed_at=completed_at,
    )


def make_state(tasks: list[ServiceTask]) -> CityState:
    return CityState(
        current_time=20,
        waste_points={
            "W1": WastePoint("W1", "B", 10, 2, 0, "mixed", "residential", 1)
        },
        vehicles={
            "V1": Vehicle("V1", "A", 10, 0, VehicleStatus.AVAILABLE, 30)
        },
        transfer_stations={},
        road_network=RoadNetwork([]),
        tasks={task.task_id: task for task in tasks},
    )


def calculate(tasks: list[ServiceTask]) -> Metrics:
    return MetricsCalculator().calculate(
        make_state(tasks), RuntimeStats(total_distance=12.5, overflow_count=3)
    )


def test_no_tasks_has_zero_rates_and_zero_average_response_time() -> None:
    assert calculate([]) == Metrics(
        task_completion_rate=0.0,
        urgent_task_completion_rate=0.0,
        average_response_time=0.0,
        overflow_count=3,
        total_distance=12.5,
    )


def test_task_completion_rate_for_partially_completed_tasks() -> None:
    metrics = calculate(
        [
            make_task("T1", status=ServiceTaskStatus.COMPLETED, completed_at=5),
            make_task("T2"),
        ]
    )

    assert metrics.task_completion_rate == 0.5


def test_task_completion_rate_for_all_completed_tasks() -> None:
    metrics = calculate(
        [
            make_task("T1", status=ServiceTaskStatus.COMPLETED, completed_at=5),
            make_task("T2", status=ServiceTaskStatus.COMPLETED, completed_at=7),
        ]
    )

    assert metrics.task_completion_rate == 1.0


def test_urgent_completion_rate_uses_shared_priority_threshold() -> None:
    metrics = calculate(
        [
            make_task(
                "T1", priority=10, status=ServiceTaskStatus.COMPLETED, completed_at=5
            ),
            make_task("T2", priority=10),
            make_task("T3", priority=1, status=ServiceTaskStatus.COMPLETED, completed_at=5),
        ]
    )

    assert metrics.urgent_task_completion_rate == 0.5
    assert metrics.task_completion_rate == 2 / 3


def test_normal_tasks_do_not_enter_urgent_denominator() -> None:
    metrics = calculate(
        [make_task("T1"), make_task("T2", status=ServiceTaskStatus.COMPLETED, completed_at=5)]
    )

    assert metrics.urgent_task_completion_rate == 0.0


def test_response_time_is_completion_minus_creation_time() -> None:
    metrics = calculate(
        [
            make_task(
                "T1",
                status=ServiceTaskStatus.COMPLETED,
                created_at=4,
                completed_at=13,
            )
        ]
    )

    assert metrics.average_response_time == 9.0


def test_uncompleted_tasks_do_not_enter_average_response_time() -> None:
    metrics = calculate(
        [
            make_task(
                "T1",
                status=ServiceTaskStatus.COMPLETED,
                created_at=2,
                completed_at=8,
            ),
            make_task("T2", created_at=0),
        ]
    )

    assert metrics.average_response_time == 6.0


def test_multiple_completed_tasks_use_mean_response_time() -> None:
    metrics = calculate(
        [
            make_task(
                "T1",
                status=ServiceTaskStatus.COMPLETED,
                created_at=1,
                completed_at=6,
            ),
            make_task(
                "T2",
                status=ServiceTaskStatus.COMPLETED,
                created_at=2,
                completed_at=11,
            ),
        ]
    )

    assert metrics.average_response_time == 7.0


def test_calculator_is_deterministic_and_does_not_mutate_inputs() -> None:
    state = make_state(
        [make_task("T1", status=ServiceTaskStatus.COMPLETED, completed_at=5)]
    )
    runtime_stats = RuntimeStats(total_distance=2.0, overflow_count=1)
    original_state = deepcopy(state)

    first = MetricsCalculator().calculate(state, runtime_stats)
    second = MetricsCalculator().calculate(state, runtime_stats)

    assert first == second
    assert state.current_time == original_state.current_time
    assert state.tasks == original_state.tasks
    assert state.vehicles == original_state.vehicles
    assert state.waste_points == original_state.waste_points
