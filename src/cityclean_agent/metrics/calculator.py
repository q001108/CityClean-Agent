"""Small, read-only calculations for the v0.1 benchmark foundation."""

from __future__ import annotations

from dataclasses import dataclass

from cityclean_agent.domain.constants import MUST_SERVE_PRIORITY_THRESHOLD
from cityclean_agent.domain.enums import ServiceTaskStatus
from cityclean_agent.domain.models import CityState, ServiceTask
from cityclean_agent.simulator.city_sim import RuntimeStats


@dataclass(frozen=True, slots=True)
class Metrics:
    """The five deterministic metrics supported by Phase 8A."""

    task_completion_rate: float
    urgent_task_completion_rate: float
    average_response_time: float
    overflow_count: int
    total_distance: float


class MetricsCalculator:
    """Calculate metrics without modifying CitySim or any supplied snapshot."""

    def calculate(self, state: CityState, runtime_stats: RuntimeStats) -> Metrics:
        """Return deterministic metrics for one CitySim state and run counters."""

        tasks = tuple(state.tasks.values())
        completed_tasks = tuple(
            task
            for task in tasks
            if task.status is ServiceTaskStatus.COMPLETED
        )
        urgent_tasks = tuple(
            task
            for task in tasks
            if task.priority >= MUST_SERVE_PRIORITY_THRESHOLD
        )
        completed_urgent_tasks = tuple(
            task
            for task in urgent_tasks
            if task.status is ServiceTaskStatus.COMPLETED
        )
        response_times = tuple(
            task.completed_at - task.created_at
            for task in completed_tasks
            if task.completed_at is not None
        )

        return Metrics(
            task_completion_rate=_rate(len(completed_tasks), len(tasks)),
            urgent_task_completion_rate=_rate(
                len(completed_urgent_tasks), len(urgent_tasks)
            ),
            average_response_time=(
                sum(response_times) / len(response_times)
                if response_times
                else 0.0
            ),
            overflow_count=runtime_stats.overflow_count,
            total_distance=runtime_stats.total_distance,
        )


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
