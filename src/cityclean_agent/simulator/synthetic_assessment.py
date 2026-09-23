"""Auditable governance assessment for the deterministic map sandbox."""

from __future__ import annotations

from enum import Enum
from time import perf_counter

from pydantic import Field, model_validator

from cityclean_agent.agent.deepseek_event_agent import (
    DEFAULT_DEEPSEEK_MODEL,
    DeepSeekEventAgent,
)
from cityclean_agent.agent.protocols import EventDecisionAgent
from cityclean_agent.policy.mapper import map_policy_parameters
from cityclean_agent.policy.models import PolicyDecision
from cityclean_agent.simulator.synthetic_dispatch import (
    SyntheticDispatchRequest,
    build_rule_policy_decision,
    build_synthetic_batch_event,
    build_synthetic_state,
)
from cityclean_agent.simulator.synthetic_network import (
    RiskLevel,
    SandboxContract,
    SiteType,
    generate_synthetic_network,
)


class SyntheticAssessmentMode(str, Enum):
    RULE = "RULE"
    DEEPSEEK = "DEEPSEEK"


class SyntheticAssessmentRequest(SandboxContract):
    seed: int = Field(default=20260922, ge=0, le=2_147_483_647)
    selected_bin_count: int = Field(default=18, ge=5, le=30)
    vehicle_count: int = Field(default=8, ge=2, le=12)
    vehicle_capacity_liters: float = Field(default=2200, ge=100, le=10_000)
    service_target_budget: int | None = Field(default=None, ge=1, le=30)
    agent_mode: SyntheticAssessmentMode = SyntheticAssessmentMode.RULE

    @model_validator(mode="after")
    def validate_target_budget(self) -> SyntheticAssessmentRequest:
        if (
            self.service_target_budget is not None
            and self.service_target_budget > self.selected_bin_count
        ):
            raise ValueError("service_target_budget must not exceed selected_bin_count")
        return self


class SyntheticTargetFact(SandboxContract):
    target_id: str
    site_type: SiteType
    site_name: str
    fill_ratio: float
    risk_score: float
    risk_level: RiskLevel
    forecast_hours_to_overflow: float
    sensitivity: str
    service_window: str
    service_window_open: bool
    access_constraint: str
    sensor_confidence: float
    risk_reasons: tuple[str, ...]


class SyntheticAssessmentFacts(SandboxContract):
    current_minute: int
    candidate_count: int
    service_target_budget: int
    vehicle_count: int
    fleet_capacity_liters: float
    candidate_load_liters: float
    critical_target_count: int
    sensitive_target_count: int
    candidates: tuple[SyntheticTargetFact, ...]


class SyntheticOptimizationParameters(SandboxContract):
    distance_weight: int
    lateness_weight: int
    unserved_task_penalty: int
    rescheduling_weight: int


class SyntheticAssessmentResponse(SandboxContract):
    scenario_id: str
    data_mode: str = "synthetic"
    agent_mode: SyntheticAssessmentMode
    agent_name: str
    model_name: str | None
    model_call_status: str
    validated: bool
    latency_ms: int
    input_facts: SyntheticAssessmentFacts
    policy_decision: PolicyDecision
    optimization_parameters: SyntheticOptimizationParameters


def assess_synthetic_scenario(
    request: SyntheticAssessmentRequest,
    *,
    deepseek_agent: EventDecisionAgent | None = None,
) -> SyntheticAssessmentResponse:
    """Assess Top-N deterministic risks without running routing optimization."""

    network = generate_synthetic_network(seed=request.seed)
    candidates = sorted(
        network.bins,
        key=lambda item: (-item.risk_score, item.bin_id),
    )[: request.selected_bin_count]
    dispatch_request = SyntheticDispatchRequest(
        seed=request.seed,
        selected_bin_count=request.selected_bin_count,
        vehicle_count=request.vehicle_count,
        vehicle_capacity_liters=request.vehicle_capacity_liters,
        service_target_budget=request.service_target_budget,
    )
    state = build_synthetic_state(network, candidates, dispatch_request)
    event = build_synthetic_batch_event(
        request.seed,
        candidates,
        state.current_time,
        service_target_budget=request.service_target_budget,
    )
    if request.agent_mode is SyntheticAssessmentMode.DEEPSEEK:
        agent = deepseek_agent if deepseek_agent is not None else DeepSeekEventAgent()
        agent_name = "DeepSeek 真实模型"
        model_name = DEFAULT_DEEPSEEK_MODEL
        model_call_status = "SUCCESS"
    else:
        agent = None
        agent_name = "固定规则基线"
        model_name = None
        model_call_status = "NOT_REQUESTED"

    started_at = perf_counter()
    decision = (
        build_rule_policy_decision(
            event,
            state,
            service_target_budget=request.service_target_budget,
        )
        if agent is None
        else agent.decide(event, state)
    )
    latency_ms = max(0, round((perf_counter() - started_at) * 1000))
    if not decision.priority_targets:
        raise ValueError("治理研判未选择任何优先目标")
    effective_budget = request.service_target_budget or len(candidates)
    if len(decision.priority_targets) > effective_budget:
        raise ValueError("治理研判选择的优先目标超过本轮资源预算")
    parameters = map_policy_parameters(decision)
    sensitive_types = {SiteType.SCHOOL, SiteType.HOSPITAL, SiteType.TRANSIT}
    facts = SyntheticAssessmentFacts(
        current_minute=state.current_time,
        candidate_count=len(candidates),
        service_target_budget=effective_budget,
        vehicle_count=request.vehicle_count,
        fleet_capacity_liters=request.vehicle_count * request.vehicle_capacity_liters,
        candidate_load_liters=round(
            sum(item.current_load_liters for item in candidates),
            1,
        ),
        critical_target_count=sum(
            item.risk_level is RiskLevel.CRITICAL for item in candidates
        ),
        sensitive_target_count=sum(
            item.site_type in sensitive_types for item in candidates
        ),
        candidates=tuple(
            SyntheticTargetFact(
                target_id=item.bin_id,
                site_type=item.site_type,
                site_name=item.site_name,
                fill_ratio=item.fill_ratio,
                risk_score=item.risk_score,
                risk_level=item.risk_level,
                forecast_hours_to_overflow=item.forecast_hours_to_overflow,
                sensitivity=item.sensitivity,
                service_window=item.service_window,
                service_window_open=_service_window_open(
                    item.service_window,
                    state.current_time,
                ),
                access_constraint=item.access_constraint,
                sensor_confidence=item.sensor_confidence,
                risk_reasons=item.risk_reasons,
            )
            for item in candidates
        ),
    )
    return SyntheticAssessmentResponse(
        scenario_id=network.scenario_id,
        agent_mode=request.agent_mode,
        agent_name=agent_name,
        model_name=model_name,
        model_call_status=model_call_status,
        validated=True,
        latency_ms=latency_ms,
        input_facts=facts,
        policy_decision=decision,
        optimization_parameters=SyntheticOptimizationParameters(
            distance_weight=parameters.distance_weight,
            lateness_weight=parameters.lateness_weight,
            unserved_task_penalty=parameters.unserved_task_penalty,
            rescheduling_weight=parameters.rescheduling_weight,
        ),
    )


def _service_window_open(service_window: str, current_minute: int) -> bool:
    """Evaluate the fixed synthetic HH:MM windows at one simulated minute."""

    if service_window == "全天候":
        return True
    minute_of_day = current_minute % (24 * 60)
    for interval in service_window.split("/"):
        start_text, end_text = (item.strip() for item in interval.split("-", 1))
        start = _clock_minute(start_text)
        end = _clock_minute(end_text)
        if start <= end and start <= minute_of_day <= end:
            return True
        if start > end and (minute_of_day >= start or minute_of_day <= end):
            return True
    return False


def _clock_minute(value: str) -> int:
    hour_text, minute_text = value.split(":", 1)
    return int(hour_text) * 60 + int(minute_text)
