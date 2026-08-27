"""Pydantic validation for the read-only Frontend Experience Contract v2."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cityclean_agent.final_summary import FinalNarrativeSummary
from cityclean_agent.policy.models import PolicyDecision
from cityclean_agent.trace_provenance import TraceProvenance
from cityclean_agent.v2_trace import TraceCityEvent


class _Experience(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experience_id: str
    title: str
    scenario_id: str
    selected_case: bool
    mode: Literal["FULL_LLM_POLICY_REPLAN"]
    availability: Literal["READY", "PROVENANCE_REQUIRED"]
    selected_case_disclosure: str


class _Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: str
    role: Literal["USER", "ASSISTANT"]
    content: str
    created_at: int
    source: Literal["USER_AUTHORED", "MODEL_GENERATED", "EDITORIAL"]


class _IntakeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["COLLECTING", "NEEDS_CLARIFICATION", "READY", "REJECTED"]
    complaint_summary: str | None
    candidate_event_type: str | None
    location_text: str | None
    affected_entity_mentions: list[str]
    missing_fields: list[str]
    rejection_reason: str | None


class _Session(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    scenario_id: str
    messages: list[_Message]
    intake_result: _IntakeResult
    clarification_prompt: str | None


class _Metrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_completion_rate: float
    urgent_task_completion_rate: float
    average_response_time: float
    overflow_count: int
    total_distance: float


class _ExecutionFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    module: str
    status: Literal["NOT_REACHED", "RUNNING", "SUCCESS", "FAIL", "INFEASIBLE"]


class _Summary(FinalNarrativeSummary):
    source: Literal["DETERMINISTIC_TEMPLATE", "RECORDED_REAL_API"]


class _Ablation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["FULL_LLM_POLICY_REPLAN", "FIXED_BALANCED_REPLAN", "STATIC_NO_REPLAN"]
    label: str
    availability: Literal["READY", "PROVENANCE_REQUIRED"]
    reason: str | None
    shared_inputs: dict[str, Any]
    metrics: _Metrics | None
    optimizer_status: str | None
    verifier_passed: bool | None
    completed: bool | None
    policy_decision: PolicyDecision | None


class _ExperimentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gold_cases: int
    successful_calls: int
    contract_success_rate: float
    policy_accuracy: float
    macro_f1: float
    paired_context_accuracy: float
    provider_failures: int


class V2ExperienceContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["2.0"]
    experience: _Experience
    provenance: TraceProvenance
    complaint_session: _Session
    city_event: TraceCityEvent
    policy_decision: PolicyDecision | None
    policy_notice: str
    execution_frames: list[_ExecutionFrame]
    final_metrics: _Metrics
    final_summary: _Summary
    ablation_comparison: list[_Ablation]
    experiment_summary: _ExperimentSummary


def validate_v2_contract(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and return a JSON-safe contract projection."""

    return V2ExperienceContract.model_validate(payload).model_dump(mode="json")
