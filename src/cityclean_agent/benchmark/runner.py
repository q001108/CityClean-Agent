"""Explicit deterministic execution of fixed CityClean-Agent episodes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

from cityclean_agent.agent.mock_event_agent import FixedBalancedAgent, MockEventAgent
from cityclean_agent.domain.enums import ServiceTaskStatus
from cityclean_agent.domain.models import CityState, DispatchPlan
from cityclean_agent.domain.task_builder import build_task_changes
from cityclean_agent.metrics.calculator import Metrics, MetricsCalculator
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.optimizer.results import OptimizationStatus
from cityclean_agent.policy.mapper import POLICY_PARAMETERS_BY_PROFILE
from cityclean_agent.policy.models import PolicyProfile
from cityclean_agent.simulator.city_sim import CitySim
from cityclean_agent.verifier.plan_verifier import PlanVerifier
from cityclean_agent.workflow import WorkflowStatus, process_event

from cityclean_agent.benchmark.scenarios import BenchmarkScenario, scenario_bank


class BenchmarkMode(str, Enum):
    """The fixed v0.1 comparison conditions for one benchmark episode."""

    STATIC_NO_REPLAN = "STATIC_NO_REPLAN"
    FIXED_BALANCED_REPLAN = "FIXED_BALANCED_REPLAN"
    EVENT_POLICY_REPLAN = "EVENT_POLICY_REPLAN"


_DEFAULT_BENCHMARK_MODES = tuple(BenchmarkMode)


@dataclass(frozen=True, slots=True)
class WorkflowOutcome:
    """The recorded outcome of one scheduled event workflow call."""

    event_id: str
    status: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class TaskOutcome:
    """Final task facts projected from CityState for per-task benchmark analysis."""

    task_id: str
    priority: int
    status: str
    created_at: int
    completed_at: int | None
    response_time: int | None


@dataclass(frozen=True, slots=True)
class BenchmarkEpisodeResult:
    """Minimal, machine-readable terminal result for one benchmark episode."""

    scenario_id: str
    scenario_category: str
    benchmark_mode: BenchmarkMode
    terminal_time: int
    terminal_status: str
    workflow_outcomes: tuple[WorkflowOutcome, ...]
    final_task_statuses: dict[str, str]
    task_outcomes: tuple[TaskOutcome, ...]
    metrics: Metrics
    remaining_unfinished_tasks: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize only fields already measured by this episode result."""

        return {
            "scenario_id": self.scenario_id,
            "scenario_category": self.scenario_category,
            "benchmark_mode": self.benchmark_mode.value,
            "terminal_time": self.terminal_time,
            "terminal_status": self.terminal_status,
            "workflow_outcomes": [asdict(outcome) for outcome in self.workflow_outcomes],
            "final_task_statuses": self.final_task_statuses,
            "task_outcomes": [asdict(outcome) for outcome in self.task_outcomes],
            "metrics": asdict(self.metrics),
            "remaining_unfinished_tasks": list(self.remaining_unfinished_tasks),
        }


class BenchmarkRunner:
    """Run fixed scenarios under a deterministic comparison mode."""

    def run_episode(
        self,
        scenario: BenchmarkScenario,
        mode: BenchmarkMode = BenchmarkMode.EVENT_POLICY_REPLAN,
    ) -> BenchmarkEpisodeResult:
        """Run one scenario until completion, failure, or its explicit time limit."""

        sim = CitySim(scenario.build_initial_state())
        self._install_initial_plan(sim)
        events = tuple(
            sorted(scenario.scheduled_events, key=lambda event: (event.timestamp, event.event_id))
        )
        event_index = 0
        workflow_outcomes: list[WorkflowOutcome] = []
        failure_status: str | None = None

        while True:
            state = sim.get_state()
            while event_index < len(events) and events[event_index].timestamp <= state.current_time:
                event = events[event_index]
                workflow_result = self._handle_event(sim, event, mode)
                workflow_outcomes.append(workflow_result)
                event_index += 1
                if workflow_result.status in {
                    WorkflowStatus.INFEASIBLE.value,
                    WorkflowStatus.VERIFICATION_FAILED.value,
                }:
                    failure_status = workflow_result.status
                    break
                state = sim.get_state()

            if failure_status is not None:
                break
            state = sim.get_state()
            if event_index == len(events) and _all_tasks_completed(state):
                break
            if state.current_time >= scenario.max_simulation_time:
                break
            sim.step()

        final_state = sim.get_state()
        unfinished_task_ids = tuple(
            sorted(
                task.task_id
                for task in final_state.tasks.values()
                if task.status is not ServiceTaskStatus.COMPLETED
            )
        )
        return BenchmarkEpisodeResult(
            scenario_id=scenario.scenario_id,
            scenario_category=scenario.category,
            benchmark_mode=mode,
            terminal_time=final_state.current_time,
            terminal_status=(
                failure_status
                or ("COMPLETED" if not unfinished_task_ids else "MAX_SIMULATION_TIME")
            ),
            workflow_outcomes=tuple(workflow_outcomes),
            final_task_statuses={
                task_id: final_state.tasks[task_id].status.value
                for task_id in sorted(final_state.tasks)
            },
            task_outcomes=tuple(
                TaskOutcome(
                    task_id=task.task_id,
                    priority=task.priority,
                    status=task.status.value,
                    created_at=task.created_at,
                    completed_at=task.completed_at,
                    response_time=(
                        task.completed_at - task.created_at
                        if task.status is ServiceTaskStatus.COMPLETED
                        and task.completed_at is not None
                        else None
                    ),
                )
                for task in sorted(final_state.tasks.values(), key=lambda task: task.task_id)
            ),
            metrics=MetricsCalculator().calculate(final_state, sim.get_runtime_stats()),
            remaining_unfinished_tasks=unfinished_task_ids,
        )

    def run_all(
        self,
        scenarios: Iterable[BenchmarkScenario] | None = None,
        modes: Iterable[BenchmarkMode] | None = None,
    ) -> tuple[BenchmarkEpisodeResult, ...]:
        """Run every supplied scenario under every supplied mode in stable order."""

        selected_scenarios = scenario_bank() if scenarios is None else tuple(scenarios)
        selected_modes = _DEFAULT_BENCHMARK_MODES if modes is None else tuple(modes)
        return tuple(
            self.run_episode(scenario, mode)
            for scenario in selected_scenarios
            for mode in selected_modes
        )

    def _handle_event(
        self, sim: CitySim, event, mode: BenchmarkMode
    ) -> WorkflowOutcome:
        if mode is BenchmarkMode.STATIC_NO_REPLAN:
            return self._apply_static_event(sim, event)

        event_agent = (
            FixedBalancedAgent()
            if mode is BenchmarkMode.FIXED_BALANCED_REPLAN
            else MockEventAgent()
        )
        result = process_event(sim, event, event_agent=event_agent)
        return WorkflowOutcome(
            event_id=event.event_id,
            status=result.status.value,
            reason=result.reason,
        )

    def _apply_static_event(self, sim: CitySim, event) -> WorkflowOutcome:
        """Apply the same event and task changes without replanning the old route."""

        if not sim.inject_event(event):
            return WorkflowOutcome(
                event_id=event.event_id,
                status=WorkflowStatus.IGNORED.value,
                reason="EVENT_ALREADY_PROCESSED",
            )
        changes = build_task_changes(event, sim.get_state())
        sim.apply_task_changes(changes)
        return WorkflowOutcome(
            event_id=event.event_id,
            status="STATIC_APPLIED",
            reason=None,
        )

    def _install_initial_plan(self, sim: CitySim) -> None:
        result = ORToolsOptimizer().optimize(
            sim.get_state(), POLICY_PARAMETERS_BY_PROFILE[PolicyProfile.BALANCED]
        )
        if result.status is not OptimizationStatus.FEASIBLE or result.plan is None:
            raise RuntimeError(f"initial benchmark plan is infeasible: {result.reason}")
        verification = PlanVerifier().verify(sim.get_state(), result.plan)
        if not verification.valid:
            raise RuntimeError("initial benchmark plan failed verification")
        sim.install_plan(result.plan)


def write_results(
    path: Path, results: Iterable[BenchmarkEpisodeResult]
) -> None:
    """Write JSON generated directly from BenchmarkEpisodeResult values."""

    path.write_text(
        json.dumps(
            [result.to_dict() for result in results],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _all_tasks_completed(state: CityState) -> bool:
    return all(
        task.status is ServiceTaskStatus.COMPLETED for task in state.tasks.values()
    )
