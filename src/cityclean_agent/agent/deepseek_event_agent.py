"""Real DeepSeek-backed event assessment with strict structured output."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
from pydantic import ValidationError

from cityclean_agent.domain.constants import MUST_SERVE_PRIORITY_THRESHOLD
from cityclean_agent.domain.enums import ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import CityEvent, CityState
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile


DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
_MAX_REASONING_SUMMARY_LENGTH = 500
_FORBIDDEN_OPTIMIZATION_FIELDS = frozenset(
    {
        "distance_weight",
        "lateness_weight",
        "unserved_task_penalty",
        "rescheduling_weight",
    }
)

_SYSTEM_PROMPT = """You are the CityClean governance event assessor.
Return only the requested JSON structured PolicyDecision. Assess governance urgency,
risk level, valid priority targets, a response deadline, an existing policy profile,
a short reasoning summary, and a small number of governance constraints.

Your JSON must contain exactly these fields and no others:
- event_type: the input event_type string unchanged.
- risk_level: an integer from 1 through 5, not a word such as HIGH.
- reasoning_summary: a short non-empty string.
- response_deadline: an absolute simulation-minute integer at or after current_time, or null.
- priority_targets: an array containing only existing WastePoint IDs.
- policy_profile: BALANCED, URGENT_RESPONSE, OVERFLOW_CONTROL, or MINIMAL_RESCHEDULE.
- constraints: an array of short governance strings.
Do not rename these fields or add fields such as governance_urgency or valid_priority_targets.

The structured event_type, timestamp, location, and affected_entities are system facts.
When natural_language_description is present, use it only as additional governance
context together with severity and the city summary. It must not override those facts
or be used to invent a different event type or target.

You must not assign vehicles, generate routes, calculate shortest paths, capacity,
ETA, task sequences, distances, OR-Tools objectives, or optimization weights.
Deterministic routing and dispatch are performed by a separate optimizer.
Only use these policy profiles: BALANCED, URGENT_RESPONSE, OVERFLOW_CONTROL,
MINIMAL_RESCHEDULE."""


class DeepSeekEventAgentError(RuntimeError):
    """Raised when a real-model output cannot satisfy the CityClean contract."""


class DeepSeekEventAgent:
    """Assess a structured CityEvent with DeepSeek and return PolicyDecision."""

    def __init__(self, model: Any | None = None) -> None:
        self._model = model if model is not None else self._create_structured_model()

    def decide(self, event: CityEvent, state: CityState) -> PolicyDecision:
        """Return a validated policy decision without mutating the supplied state."""

        messages = [
            ("system", _SYSTEM_PROMPT),
            (
                "human",
                json.dumps(
                    build_governance_state_summary(event, state),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
            ),
        ]
        try:
            output = self._model.invoke(messages)
        except Exception as exc:
            raise DeepSeekEventAgentError(
                f"DeepSeek model invocation failed: {exc}"
            ) from exc

        decision = _validate_structured_output(output)
        _validate_cross_object_contract(decision, event, state)
        return decision

    def _create_structured_model(self) -> Any:
        load_dotenv()
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise DeepSeekEventAgentError("DEEPSEEK_API_KEY is not configured")
        try:
            chat_model = ChatDeepSeek(
                model=DEFAULT_DEEPSEEK_MODEL,
                api_key=api_key,
                temperature=0,
                max_retries=2,
            )
            return chat_model.with_structured_output(
                PolicyDecision,
                method="json_mode",
            )
        except Exception as exc:
            raise DeepSeekEventAgentError(
                f"DeepSeek structured-output model configuration failed: {exc}"
            ) from exc


def build_governance_state_summary(
    event: CityEvent, state: CityState
) -> dict[str, object]:
    """Build the compact deterministic governance context sent to the model."""

    affected_targets = []
    for target_id in sorted(set(event.affected_entities)):
        point = state.waste_points.get(target_id)
        if point is not None:
            affected_targets.append(
                {
                    "id": point.id,
                    "current_load": point.current_load,
                    "capacity": point.capacity,
                    "priority": point.priority,
                    "is_overflow": point.current_load >= point.capacity,
                }
            )

    unfinished_tasks = [
        task
        for task in state.tasks.values()
        if task.status is not ServiceTaskStatus.COMPLETED
    ]
    high_priority_tasks = [
        {
            "task_id": task.task_id,
            "target_id": task.target_id,
            "priority": task.priority,
            "status": task.status.value,
            "deadline": task.deadline,
        }
        for task in sorted(unfinished_tasks, key=lambda task: task.task_id)
        if task.priority >= MUST_SERVE_PRIORITY_THRESHOLD
    ]
    return {
        "current_time": state.current_time,
        "event": {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "timestamp": event.timestamp,
            "severity": event.severity,
            "affected_entities": list(event.affected_entities),
            "metadata": {key: event.metadata[key] for key in sorted(event.metadata)},
            **(
                {"natural_language_description": event.description}
                if event.description is not None
                else {}
            ),
        },
        "affected_targets": affected_targets,
        "vehicle_summary": {
            "total": len(state.vehicles),
            "available": sum(
                vehicle.status is VehicleStatus.AVAILABLE
                for vehicle in state.vehicles.values()
            ),
            "broken": sum(
                vehicle.status is VehicleStatus.BROKEN
                for vehicle in state.vehicles.values()
            ),
            "en_route": sum(
                vehicle.status is VehicleStatus.EN_ROUTE
                for vehicle in state.vehicles.values()
            ),
            "servicing": sum(
                vehicle.status is VehicleStatus.SERVICING
                for vehicle in state.vehicles.values()
            ),
        },
        "task_summary": {
            "unfinished_task_count": len(unfinished_tasks),
            "must_serve_task_count": len(high_priority_tasks),
            "high_priority_tasks": high_priority_tasks,
        },
    }


def _validate_structured_output(output: Any) -> PolicyDecision:
    if isinstance(output, PolicyDecision):
        return output
    if not isinstance(output, Mapping):
        raise DeepSeekEventAgentError("DeepSeek returned no structured PolicyDecision")
    forbidden_fields = _FORBIDDEN_OPTIMIZATION_FIELDS.intersection(output)
    if forbidden_fields:
        raise DeepSeekEventAgentError(
            "DeepSeek output must not contain optimizer weight fields"
        )
    try:
        return PolicyDecision.model_validate(dict(output))
    except ValidationError as exc:
        raise DeepSeekEventAgentError("DeepSeek returned an invalid PolicyDecision") from exc


def _validate_cross_object_contract(
    decision: PolicyDecision, event: CityEvent, state: CityState
) -> None:
    if decision.event_type is not event.event_type:
        raise DeepSeekEventAgentError("PolicyDecision event_type does not match CityEvent")
    invalid_targets = set(decision.priority_targets).difference(state.waste_points)
    if invalid_targets:
        raise DeepSeekEventAgentError("PolicyDecision contains an unknown priority target")
    if not isinstance(decision.policy_profile, PolicyProfile):
        raise DeepSeekEventAgentError("PolicyDecision contains an invalid policy profile")
    if (
        not decision.reasoning_summary.strip()
        or len(decision.reasoning_summary) > _MAX_REASONING_SUMMARY_LENGTH
    ):
        raise DeepSeekEventAgentError("PolicyDecision reasoning_summary is invalid")
    if (
        decision.response_deadline is not None
        and decision.response_deadline < state.current_time
    ):
        raise DeepSeekEventAgentError("PolicyDecision response_deadline is in the past")
