"""Deterministic conversion of task-producing events into service-task changes."""

from __future__ import annotations

from dataclasses import dataclass, replace
from numbers import Real

from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus
from cityclean_agent.domain.models import CityEvent, CityState, ServiceTask, WastePoint


URGENT_TASK_MIN_PRIORITY = 10


@dataclass(frozen=True, slots=True)
class TaskBuildResult:
    """Task changes proposed from one event without mutating CityState."""

    event_id: str
    created_tasks: tuple[ServiceTask, ...] = ()
    updated_tasks: tuple[ServiceTask, ...] = ()


def build_task_changes(event: CityEvent, state: CityState) -> TaskBuildResult:
    """Build deterministic ServiceTask changes for one CityEvent.

    The function only reads ``state``. CitySim applies the returned changes so
    it remains the sole owner of mutable CityState.
    """

    if event.event_type not in {
        CityEventType.WASTE_OVERFLOW,
        CityEventType.URGENT_TASK,
    }:
        return TaskBuildResult(event_id=event.event_id)

    if any(task.source_event_id == event.event_id for task in state.tasks.values()):
        return TaskBuildResult(event_id=event.event_id)

    created_tasks: list[ServiceTask] = []
    updated_tasks: list[ServiceTask] = []
    for target_id in dict.fromkeys(event.affected_entities):
        waste_point = state.waste_points.get(target_id)
        if waste_point is None:
            raise ValueError(f"event target is not an existing WastePoint: {target_id}")

        requested_demand = _requested_demand(event, waste_point)
        requested_priority = _requested_priority(event, waste_point)
        existing_task = _unfinished_task_for_target(state, target_id)
        if existing_task is None:
            created_tasks.append(
                ServiceTask(
                    task_id=f"task-{event.event_id}-{target_id}",
                    source_event_id=event.event_id,
                    target_id=target_id,
                    demand=requested_demand,
                    priority=requested_priority,
                    deadline=event.deadline,
                    created_at=state.current_time,
                )
            )
            continue

        updated_task = replace(
            existing_task,
            demand=max(existing_task.demand, requested_demand),
            priority=max(existing_task.priority, requested_priority),
            deadline=_earlier_deadline(existing_task.deadline, event.deadline),
        )
        if updated_task != existing_task:
            updated_tasks.append(updated_task)

    return TaskBuildResult(
        event_id=event.event_id,
        created_tasks=tuple(created_tasks),
        updated_tasks=tuple(updated_tasks),
    )


def _unfinished_task_for_target(state: CityState, target_id: str) -> ServiceTask | None:
    candidates = sorted(
        (
            task
            for task in state.tasks.values()
            if task.target_id == target_id
            and task.status is not ServiceTaskStatus.COMPLETED
        ),
        key=lambda task: task.task_id,
    )
    return candidates[0] if candidates else None


def _requested_demand(event: CityEvent, waste_point: WastePoint) -> float:
    demand = event.metadata.get("demand", waste_point.current_load)
    if isinstance(demand, bool) or not isinstance(demand, Real) or demand <= 0:
        raise ValueError("event demand must be a positive number")
    return float(demand)


def _requested_priority(event: CityEvent, waste_point: WastePoint) -> int:
    if event.event_type is CityEventType.URGENT_TASK:
        return max(URGENT_TASK_MIN_PRIORITY, event.severity, waste_point.priority)
    return max(event.severity, waste_point.priority)


def _earlier_deadline(
    current_deadline: int | None, event_deadline: int | None
) -> int | None:
    if current_deadline is None:
        return event_deadline
    if event_deadline is None:
        return current_deadline
    return min(current_deadline, event_deadline)
