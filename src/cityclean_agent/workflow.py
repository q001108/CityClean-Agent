"""Explicit, one-event workflow for the v0.1 replanning loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from cityclean_agent.agent.mock_event_agent import MockEventAgent
from cityclean_agent.domain.models import CityEvent, DispatchPlan
from cityclean_agent.domain.task_builder import build_task_changes
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.optimizer.results import OptimizationResult, OptimizationStatus
from cityclean_agent.policy.mapper import map_policy_parameters
from cityclean_agent.policy.models import PolicyDecision
from cityclean_agent.simulator.city_sim import CitySim
from cityclean_agent.verifier.plan_verifier import PlanVerifier, VerificationResult


class WorkflowStatus(str, Enum):
    """The limited set of outcomes for one event-driven planning attempt."""

    SUCCESS = "SUCCESS"
    INFEASIBLE = "INFEASIBLE"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    IGNORED = "IGNORED"


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    """Observable result of one explicit event-to-plan workflow run."""

    status: WorkflowStatus
    policy_decision: PolicyDecision | None = None
    optimization_result: OptimizationResult | None = None
    verification_result: VerificationResult | None = None
    plan: DispatchPlan | None = None
    reason: str | None = None


def process_event(
    sim: CitySim,
    event: CityEvent,
    *,
    event_agent: MockEventAgent | None = None,
    optimizer: ORToolsOptimizer | None = None,
    verifier: PlanVerifier | None = None,
) -> WorkflowResult:
    """Apply one due event, replan deterministically, and install only valid plans.

    CitySim remains the sole writer of CityState: this function reads snapshots
    and submits explicit task, release, and plan-installation requests to it.
    """

    if event.timestamp > sim.get_state().current_time:
        raise ValueError("workflow events must be due at the current simulation time")
    if not sim.inject_event(event):
        return WorkflowResult(
            status=WorkflowStatus.IGNORED,
            reason="EVENT_ALREADY_PROCESSED",
        )

    sim.release_unstarted_tasks()
    event_agent = event_agent or MockEventAgent()
    optimizer = optimizer or ORToolsOptimizer()
    verifier = verifier or PlanVerifier()

    post_event_state = sim.get_state()
    decision = event_agent.decide(event, post_event_state)
    parameters = map_policy_parameters(decision)

    changes = build_task_changes(event, post_event_state)
    sim.apply_task_changes(changes)
    planning_state = sim.get_state()

    optimization_result = optimizer.optimize(planning_state, parameters)
    if optimization_result.status is OptimizationStatus.INFEASIBLE:
        return WorkflowResult(
            status=WorkflowStatus.INFEASIBLE,
            policy_decision=decision,
            optimization_result=optimization_result,
            reason=optimization_result.reason,
        )
    if optimization_result.plan is None:
        return WorkflowResult(
            status=WorkflowStatus.VERIFICATION_FAILED,
            policy_decision=decision,
            optimization_result=optimization_result,
            reason="FEASIBLE_RESULT_MISSING_PLAN",
        )

    verification_result = verifier.verify(planning_state, optimization_result.plan)
    if not verification_result.valid:
        return WorkflowResult(
            status=WorkflowStatus.VERIFICATION_FAILED,
            policy_decision=decision,
            optimization_result=optimization_result,
            verification_result=verification_result,
            reason="PLAN_VERIFICATION_FAILED",
        )

    sim.install_plan(optimization_result.plan)
    return WorkflowResult(
        status=WorkflowStatus.SUCCESS,
        policy_decision=decision,
        optimization_result=optimization_result,
        verification_result=verification_result,
        plan=optimization_result.plan,
    )
