"""Validated frozen-policy replay and fair v0.2 ablation execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cityclean_agent.agent.deepseek_event_agent import validate_policy_decision
from cityclean_agent.agent.mock_event_agent import FixedBalancedAgent
from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus
from cityclean_agent.domain.models import CityEvent
from cityclean_agent.domain.task_builder import build_task_changes
from cityclean_agent.live_e2e import LiveE2ECase, live_e2e_cases
from cityclean_agent.metrics.calculator import MetricsCalculator
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.optimizer.results import OptimizationStatus
from cityclean_agent.policy.mapper import POLICY_PARAMETERS_BY_PROFILE
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile
from cityclean_agent.simulator.city_sim import CitySim
from cityclean_agent.trace_provenance import TraceProvenance, TraceSource
from cityclean_agent.verifier.plan_verifier import PlanVerifier
from cityclean_agent.workflow import WorkflowStatus, process_event


TRACE_SCHEMA_VERSION = "2.0-trace"
SELECTED_CASE_ID = "urgent_timing_tradeoff_live"


class TraceComplaint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(min_length=1)
    source: Literal["USER_AUTHORED"]


class TraceCityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    event_type: CityEventType
    timestamp: int = Field(ge=0)
    location: str = Field(min_length=1)
    affected_entities: tuple[str, ...]
    severity: int = Field(ge=0)
    deadline: int | None = Field(default=None, ge=0)
    description: str | None = None

    def to_domain(self) -> CityEvent:
        return CityEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            timestamp=self.timestamp,
            location=self.location,
            affected_entities=list(self.affected_entities),
            severity=self.severity,
            deadline=self.deadline,
            description=self.description,
        )


class RecordedV2Trace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[TRACE_SCHEMA_VERSION]
    provenance: TraceProvenance
    complaint: TraceComplaint
    city_event: TraceCityEvent
    policy_decision: PolicyDecision

    @model_validator(mode="after")
    def _validate_recorded_policy_trace(self) -> "RecordedV2Trace":
        if self.provenance.trace_source is not TraceSource.RECORDED_REAL_API:
            raise ValueError("Full LLM replay requires RECORDED_REAL_API provenance")
        if not self.provenance.success:
            raise ValueError("Full LLM replay requires a successful captured trace")
        if self.provenance.scenario_id != SELECTED_CASE_ID:
            raise ValueError("trace scenario does not match the selected v0.2 case")
        if self.provenance.input_hash != trace_input_hash(self.complaint.content, self.city_event):
            raise ValueError("trace input_hash does not match its complaint and CityEvent")
        if self.policy_decision.event_type is not self.city_event.event_type:
            raise ValueError("trace decision event_type does not match its CityEvent")
        return self


class RecordedPolicyAgent:
    """Replay a validated saved decision without provider access."""

    def __init__(self, decision: PolicyDecision) -> None:
        self._decision = decision

    def decide(self, event: CityEvent, state: Any) -> PolicyDecision:
        return validate_policy_decision(self._decision, event, state)


def load_recorded_v2_trace(path: str | Path) -> RecordedV2Trace:
    return RecordedV2Trace.model_validate_json(Path(path).read_text(encoding="utf-8"))


def trace_input_hash(complaint: str, event: TraceCityEvent) -> str:
    payload = {"complaint": complaint, "city_event": event.model_dump(mode="json")}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def run_fair_ablation(trace: RecordedV2Trace | None = None) -> list[dict[str, Any]]:
    """Run all conditions from identical state/event/tick/time inputs.

    Full is deliberately unavailable without a validated saved real policy.
    Fixed and Static remain deterministic, but use the exact same live case
    event rather than a lookalike benchmark event.
    """

    case = _selected_case()
    shared = _shared_inputs(case)
    full = (
        _run_replanning_mode(case, "FULL_LLM_POLICY_REPLAN", RecordedPolicyAgent(trace.policy_decision), shared)
        if trace is not None
        else _unavailable_full(shared)
    )
    return [
        full,
        _run_replanning_mode(case, "FIXED_BALANCED_REPLAN", FixedBalancedAgent(), shared),
        _run_static_mode(case, shared),
    ]


def _run_replanning_mode(case: LiveE2ECase, mode: str, agent: Any, shared: dict[str, Any]) -> dict[str, Any]:
    sim = CitySim(case.build_initial_state())
    _install_initial_plan(sim)
    _advance_to_event(sim, case.event.timestamp)
    outcome = process_event(sim, case.event, event_agent=agent)
    _run_until_terminal(sim, case.max_simulation_time)
    state = sim.get_state()
    metrics = MetricsCalculator().calculate(state, sim.get_runtime_stats())
    return _result_payload(
        mode, shared, outcome.status.value, outcome.reason,
        outcome.verification_result.valid if outcome.verification_result else None,
        _all_tasks_completed(state), metrics, outcome.policy_decision,
    )


def _run_static_mode(case: LiveE2ECase, shared: dict[str, Any]) -> dict[str, Any]:
    sim = CitySim(case.build_initial_state())
    _install_initial_plan(sim)
    _advance_to_event(sim, case.event.timestamp)
    if not sim.inject_event(case.event):
        raise RuntimeError("static v2 event was unexpectedly ignored")
    sim.apply_task_changes(build_task_changes(case.event, sim.get_state()))
    _run_until_terminal(sim, case.max_simulation_time)
    state = sim.get_state()
    metrics = MetricsCalculator().calculate(state, sim.get_runtime_stats())
    return _result_payload(
        "STATIC_NO_REPLAN", shared, "STATIC_APPLIED", None, None,
        _all_tasks_completed(state), metrics, None,
    )


def _result_payload(
    mode: str, shared: dict[str, Any], optimizer_status: str, reason: str | None,
    verifier_passed: bool | None, completed: bool, metrics: Any,
    decision: PolicyDecision | None,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "label": {
            "FULL_LLM_POLICY_REPLAN": "Full LLM 策略重规划",
            "FIXED_BALANCED_REPLAN": "固定 BALANCED 重规划",
            "STATIC_NO_REPLAN": "静态不重规划",
        }[mode],
        "availability": "READY",
        "reason": reason,
        "shared_inputs": shared,
        "metrics": {
            "task_completion_rate": metrics.task_completion_rate,
            "urgent_task_completion_rate": metrics.urgent_task_completion_rate,
            "average_response_time": metrics.average_response_time,
            "overflow_count": metrics.overflow_count,
            "total_distance": metrics.total_distance,
        },
        "optimizer_status": optimizer_status,
        "verifier_passed": verifier_passed,
        "completed": completed,
        "policy_decision": decision.model_dump(mode="json") if decision else None,
    }


def _unavailable_full(shared: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "FULL_LLM_POLICY_REPLAN",
        "label": "Full LLM 策略重规划",
        "availability": "PROVENANCE_REQUIRED",
        "reason": "需要含真实 PolicyDecision 的逐轨迹 provenance 才可运行。",
        "shared_inputs": shared,
        "metrics": None,
        "optimizer_status": None,
        "verifier_passed": None,
        "completed": None,
        "policy_decision": None,
    }


def _selected_case() -> LiveE2ECase:
    return next(case for case in live_e2e_cases() if case.case_id == SELECTED_CASE_ID)


def _shared_inputs(case: LiveE2ECase) -> dict[str, Any]:
    return {
        "initial_state_id": "urgent_timing_tradeoff@seed-0",
        "event_id": case.event.event_id,
        "event_type": case.event.event_type.value,
        "event_time": case.event.timestamp,
        "event_targets": list(case.event.affected_entities),
        "seed": 0,
        "tick_minutes": 5,
        "max_simulation_time": case.max_simulation_time,
        "task_builder": "cityclean_agent.domain.task_builder.build_task_changes",
        "metrics": "cityclean_agent.metrics.calculator.MetricsCalculator",
    }


def _install_initial_plan(sim: CitySim) -> None:
    result = ORToolsOptimizer().optimize(
        sim.get_state(), POLICY_PARAMETERS_BY_PROFILE[PolicyProfile.BALANCED]
    )
    if result.status is not OptimizationStatus.FEASIBLE or result.plan is None:
        raise RuntimeError(f"initial v2 plan is infeasible: {result.reason}")
    if not PlanVerifier().verify(sim.get_state(), result.plan).valid:
        raise RuntimeError("initial v2 plan failed verification")
    sim.install_plan(result.plan)


def _advance_to_event(sim: CitySim, event_time: int) -> None:
    while sim.get_state().current_time < event_time:
        sim.step()


def _run_until_terminal(sim: CitySim, max_time: int) -> None:
    while sim.get_state().current_time < max_time and not _all_tasks_completed(sim.get_state()):
        sim.step()


def _all_tasks_completed(state: Any) -> bool:
    return all(task.status is ServiceTaskStatus.COMPLETED for task in state.tasks.values())
