"""Explicit, small real-agent closed-loop smoke cases outside the benchmark bank."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from cityclean_agent.agent.deepseek_event_agent import DeepSeekEventAgentError
from cityclean_agent.benchmark.scenarios import scenario_bank
from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus
from cityclean_agent.domain.models import CityEvent, CityState, DispatchPlan, ServiceTask
from cityclean_agent.metrics.calculator import Metrics, MetricsCalculator
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.optimizer.results import OptimizationStatus
from cityclean_agent.policy.mapper import POLICY_PARAMETERS_BY_PROFILE
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile
from cityclean_agent.simulator.city_sim import CitySim
from cityclean_agent.verifier.plan_verifier import PlanVerifier
from cityclean_agent.workflow import WorkflowStatus, process_event


@dataclass(frozen=True, slots=True)
class LiveE2ECase:
    """One fixed, manual-only real-agent closed-loop smoke case."""

    case_id: str
    build_initial_state: Callable[[], CityState]
    event: CityEvent
    target_task_id: str | None
    max_simulation_time: int


@dataclass(frozen=True, slots=True)
class LiveE2EResult:
    """Final observable facts from one live agent workflow execution."""

    case_id: str
    success: bool
    event_type: str
    policy_decision: dict[str, object] | None
    workflow_status: str | None
    verification_valid: bool | None
    initial_route_summary: dict[str, tuple[str, ...]]
    replanned_route_summary: dict[str, tuple[str, ...]] | None
    final_task_statuses: dict[str, str]
    target_task_outcome: dict[str, object] | None
    final_metrics: Metrics | None
    error: str | None

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible facts without provider internals or credentials."""

        return {
            "case_id": self.case_id,
            "success": self.success,
            "event_type": self.event_type,
            "policy_decision": self.policy_decision,
            "workflow_status": self.workflow_status,
            "verification_valid": self.verification_valid,
            "initial_route_summary": {
                vehicle_id: list(tasks)
                for vehicle_id, tasks in self.initial_route_summary.items()
            },
            "replanned_route_summary": (
                {
                    vehicle_id: list(tasks)
                    for vehicle_id, tasks in self.replanned_route_summary.items()
                }
                if self.replanned_route_summary is not None
                else None
            ),
            "final_task_statuses": self.final_task_statuses,
            "target_task_outcome": self.target_task_outcome,
            "final_metrics": (
                asdict(self.final_metrics) if self.final_metrics is not None else None
            ),
            "error": self.error,
        }


def live_e2e_cases() -> tuple[LiveE2ECase, ...]:
    """Return the three fixed live-only cases without changing scenario_bank()."""

    scenarios = {scenario.scenario_id: scenario for scenario in scenario_bank()}
    urgent = scenarios["urgent_timing_tradeoff"]
    overflow = scenarios["overflow_service_tradeoff"]
    closure = scenarios["road_closure_detour"]
    return (
        LiveE2ECase(
            case_id="urgent_timing_tradeoff_live",
            build_initial_state=urgent.build_initial_state,
            event=CityEvent(
                "E-live-urgent",
                CityEventType.URGENT_TASK,
                10,
                "C",
                ["WU"],
                10,
                40,
                description=(
                    "大型活动刚结束，出口处人流密集，需要尽快完成临时清运任务，"
                    "以保障疏散通行和环境卫生。"
                ),
            ),
            target_task_id="task-E-live-urgent-WU",
            max_simulation_time=urgent.max_simulation_time,
        ),
        LiveE2ECase(
            case_id="overflow_service_tradeoff_live",
            build_initial_state=overflow.build_initial_state,
            event=CityEvent(
                "E-live-overflow",
                CityEventType.WASTE_OVERFLOW,
                10,
                "F",
                ["WO"],
                3,
                None,
                description=(
                    "学校放学高峰时，校门附近垃圾点已经满溢。家长持续反映异味，"
                    "应优先控制卫生影响。"
                ),
            ),
            target_task_id="task-E-live-overflow-WO",
            max_simulation_time=overflow.max_simulation_time,
        ),
        LiveE2ECase(
            case_id="road_closure_context_live",
            build_initial_state=closure.build_initial_state,
            event=CityEvent(
                "E-live-closure",
                CityEventType.ROAD_CLOSURE,
                10,
                "C-D",
                ["CD"],
                3,
                None,
                description=(
                    "活动散场期间一条主干道突然封闭，多个既有清运路线受阻，"
                    "附近任务仍在持续累积。"
                ),
            ),
            target_task_id="T03",
            max_simulation_time=closure.max_simulation_time,
        ),
    )


def run_live_e2e_case(agent: Any, case: LiveE2ECase) -> LiveE2EResult:
    """Run exactly one event-agent call through the formal closed-loop components."""

    sim = CitySim(case.build_initial_state())
    _install_initial_plan(sim)
    _advance_to_event(sim, case.event.timestamp)
    initial_route_summary = _route_summary(sim.get_state().active_plan)
    try:
        workflow_result = process_event(sim, case.event, event_agent=agent)
    except DeepSeekEventAgentError as exc:
        return _failure_result(
            case, sim, initial_route_summary, error=str(exc)
        )

    decision = workflow_result.policy_decision
    verification_valid = (
        workflow_result.verification_result.valid
        if workflow_result.verification_result is not None
        else None
    )
    if workflow_result.status is not WorkflowStatus.SUCCESS:
        return _failure_result(
            case,
            sim,
            initial_route_summary,
            workflow_status=workflow_result.status.value,
            policy_decision=decision,
            verification_valid=verification_valid,
            error=workflow_result.reason or workflow_result.status.value,
        )

    _run_until_terminal(sim, case.max_simulation_time)
    final_state = sim.get_state()
    timed_out = not _all_tasks_completed(final_state)
    return LiveE2EResult(
        case_id=case.case_id,
        success=not timed_out,
        event_type=case.event.event_type.value,
        policy_decision=_decision_dict(decision),
        workflow_status=workflow_result.status.value,
        verification_valid=verification_valid,
        initial_route_summary=initial_route_summary,
        replanned_route_summary=_route_summary(workflow_result.plan),
        final_task_statuses=_task_statuses(final_state),
        target_task_outcome=_task_outcome(final_state.tasks.get(case.target_task_id)),
        final_metrics=MetricsCalculator().calculate(final_state, sim.get_runtime_stats()),
        error="SIMULATION_TIMEOUT" if timed_out else None,
    )


def write_live_e2e_results(path: Path, results: Iterable[LiveE2EResult]) -> None:
    """Write the small live smoke result set as JSON."""

    path.write_text(
        json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _install_initial_plan(sim: CitySim) -> None:
    result = ORToolsOptimizer().optimize(
        sim.get_state(), POLICY_PARAMETERS_BY_PROFILE[PolicyProfile.BALANCED]
    )
    if result.status is not OptimizationStatus.FEASIBLE or result.plan is None:
        raise RuntimeError(f"initial live plan is infeasible: {result.reason}")
    if not PlanVerifier().verify(sim.get_state(), result.plan).valid:
        raise RuntimeError("initial live plan failed verification")
    sim.install_plan(result.plan)


def _advance_to_event(sim: CitySim, event_timestamp: int) -> None:
    while sim.get_state().current_time < event_timestamp:
        sim.step()


def _run_until_terminal(sim: CitySim, max_simulation_time: int) -> None:
    while (
        sim.get_state().current_time < max_simulation_time
        and not _all_tasks_completed(sim.get_state())
    ):
        sim.step()


def _all_tasks_completed(state: CityState) -> bool:
    return all(
        task.status is ServiceTaskStatus.COMPLETED for task in state.tasks.values()
    )


def _route_summary(plan: DispatchPlan | None) -> dict[str, tuple[str, ...]]:
    if plan is None:
        return {}
    return {
        route.vehicle_id: tuple(route.task_sequence)
        for route in sorted(plan.vehicle_routes, key=lambda route: route.vehicle_id)
    }


def _task_statuses(state: CityState) -> dict[str, str]:
    return {
        task_id: state.tasks[task_id].status.value for task_id in sorted(state.tasks)
    }


def _task_outcome(task: ServiceTask | None) -> dict[str, object] | None:
    if task is None:
        return None
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
        "response_time": (
            task.completed_at - task.created_at
            if task.status is ServiceTaskStatus.COMPLETED
            and task.completed_at is not None
            else None
        ),
    }


def _decision_dict(decision: PolicyDecision | None) -> dict[str, object] | None:
    return decision.model_dump(mode="json") if decision is not None else None


def _failure_result(
    case: LiveE2ECase,
    sim: CitySim,
    initial_route_summary: dict[str, tuple[str, ...]],
    *,
    error: str,
    workflow_status: str | None = None,
    policy_decision: PolicyDecision | None = None,
    verification_valid: bool | None = None,
) -> LiveE2EResult:
    state = sim.get_state()
    return LiveE2EResult(
        case_id=case.case_id,
        success=False,
        event_type=case.event.event_type.value,
        policy_decision=_decision_dict(policy_decision),
        workflow_status=workflow_status,
        verification_valid=verification_valid,
        initial_route_summary=initial_route_summary,
        replanned_route_summary=None,
        final_task_statuses=_task_statuses(state),
        target_task_outcome=_task_outcome(state.tasks.get(case.target_task_id)),
        final_metrics=MetricsCalculator().calculate(state, sim.get_runtime_stats()),
        error=error,
    )
