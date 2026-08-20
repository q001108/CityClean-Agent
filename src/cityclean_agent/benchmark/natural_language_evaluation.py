"""Small fixed live-evaluation cases for natural-language governance context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from cityclean_agent.agent.deepseek_event_agent import DeepSeekEventAgentError
from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import CityEvent, CityState, Road, ServiceTask, Vehicle, WastePoint
from cityclean_agent.domain.road_network import RoadNetwork


@dataclass(frozen=True, slots=True)
class NaturalLanguageEvaluationCase:
    """One fixed CityEvent context evaluated without running a city workflow."""

    case_id: str
    event: CityEvent
    build_state: Callable[[], CityState]


@dataclass(frozen=True, slots=True)
class NaturalLanguageEvaluationResult:
    """Only final contract facts from one real-model governance assessment."""

    case_id: str
    event_type: str
    description: str | None
    success: bool
    policy_profile: str | None
    risk_level: int | None
    response_deadline: int | None
    priority_targets: tuple[str, ...]
    reasoning_summary: str | None
    error_type: str | None
    error_message: str | None

    def to_dict(self) -> dict[str, object]:
        """Return a machine-readable record without provider internals."""

        return {
            "case_id": self.case_id,
            "event_type": self.event_type,
            "description": self.description,
            "success": self.success,
            "policy_profile": self.policy_profile,
            "risk_level": self.risk_level,
            "response_deadline": self.response_deadline,
            "priority_targets": list(self.priority_targets),
            "reasoning_summary": self.reasoning_summary,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


def natural_language_evaluation_cases() -> tuple[NaturalLanguageEvaluationCase, ...]:
    """Return twelve deterministic paired contexts, three per supported event type."""

    return tuple(
        _case(case_id, event_type, description)
        for event_type, descriptions in _DESCRIPTIONS_BY_EVENT_TYPE
        for case_id, description in descriptions
    )


def run_natural_language_evaluation(
    agent: Any,
    cases: Iterable[NaturalLanguageEvaluationCase] | None = None,
) -> tuple[NaturalLanguageEvaluationResult, ...]:
    """Evaluate supplied cases once each, recording contract failures explicitly."""

    selected_cases = natural_language_evaluation_cases() if cases is None else tuple(cases)
    return tuple(_evaluate_case(agent, case) for case in selected_cases)


def evaluation_summary(
    results: Iterable[NaturalLanguageEvaluationResult],
) -> dict[str, int | float]:
    """Summarize direct API-plus-contract successes without retrying cases."""

    result_list = tuple(results)
    successful_cases = sum(result.success for result in result_list)
    total_cases = len(result_list)
    return {
        "total_cases": total_cases,
        "successful_cases": successful_cases,
        "contract_success_rate": successful_cases / total_cases if total_cases else 0.0,
    }


def write_natural_language_evaluation_results(
    path: Path,
    results: Iterable[NaturalLanguageEvaluationResult],
) -> None:
    """Persist only the fixed-case results and their contract-success summary."""

    result_list = tuple(results)
    path.write_text(
        json.dumps(
            {
                "summary": evaluation_summary(result_list),
                "results": [result.to_dict() for result in result_list],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _evaluate_case(agent: Any, case: NaturalLanguageEvaluationCase) -> NaturalLanguageEvaluationResult:
    try:
        decision = agent.decide(case.event, case.build_state())
    except DeepSeekEventAgentError as exc:
        return NaturalLanguageEvaluationResult(
            case_id=case.case_id,
            event_type=case.event.event_type.value,
            description=case.event.description,
            success=False,
            policy_profile=None,
            risk_level=None,
            response_deadline=None,
            priority_targets=(),
            reasoning_summary=None,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    return NaturalLanguageEvaluationResult(
        case_id=case.case_id,
        event_type=case.event.event_type.value,
        description=case.event.description,
        success=True,
        policy_profile=decision.policy_profile.value,
        risk_level=decision.risk_level,
        response_deadline=decision.response_deadline,
        priority_targets=decision.priority_targets,
        reasoning_summary=decision.reasoning_summary,
        error_type=None,
        error_message=None,
    )


def _case(
    case_id: str, event_type: CityEventType, description: str
) -> NaturalLanguageEvaluationCase:
    affected_entities = {
        CityEventType.WASTE_OVERFLOW: ["W1"],
        CityEventType.URGENT_TASK: ["W1"],
        CityEventType.VEHICLE_BREAKDOWN: ["V1"],
        CityEventType.ROAD_CLOSURE: ["AB"],
    }[event_type]
    return NaturalLanguageEvaluationCase(
        case_id=case_id,
        event=CityEvent(
            event_id=f"E-{case_id}",
            event_type=event_type,
            timestamp=20,
            location="central-zone",
            description=description,
            affected_entities=affected_entities,
            severity=3,
            deadline=50,
        ),
        build_state=_evaluation_state,
    )


def _evaluation_state() -> CityState:
    """Build the same compact, realistic state for every paired context."""

    return CityState(
        current_time=20,
        waste_points={
            "W1": WastePoint("W1", "B", 10, 10, 0, "mixed", "residential", 4),
            "W2": WastePoint("W2", "C", 20, 6, 0, "mixed", "school", 2),
        },
        vehicles={
            "V1": Vehicle("V1", "A", 10, 0, VehicleStatus.AVAILABLE, 30),
            "V2": Vehicle("V2", "D", 10, 0, VehicleStatus.AVAILABLE, 30),
            "V3": Vehicle("V3", "C", 10, 0, VehicleStatus.BROKEN, 30),
        },
        transfer_stations={},
        road_network=RoadNetwork(
            [Road("AB", "A", "B", 1, 5), Road("BC", "B", "C", 1, 5)]
        ),
        tasks={
            "T-high": ServiceTask(
                "T-high",
                "existing",
                "W2",
                2,
                10,
                50,
                status=ServiceTaskStatus.PENDING,
                created_at=10,
            ),
            "T-normal": ServiceTask(
                "T-normal",
                "existing",
                "W1",
                2,
                1,
                None,
                status=ServiceTaskStatus.PENDING,
                created_at=10,
            ),
        },
    )


_DESCRIPTIONS_BY_EVENT_TYPE: tuple[
    tuple[CityEventType, tuple[tuple[str, str], ...]], ...
] = (
    (
        CityEventType.WASTE_OVERFLOW,
        (
            ("overflow-routine", "A residential waste point has just reached capacity with no reported complaints."),
            ("overflow-school", "Waste is overflowing near a school entrance during dismissal, and guardians have complained."),
            ("overflow-hospital", "Overflow beside a hospital entrance is causing odor and hygiene concerns for patients."),
        ),
    ),
    (
        CityEventType.URGENT_TASK,
        (
            ("urgent-routine", "A resident requests a routine additional collection with no immediate public impact."),
            ("urgent-event", "A large event is ending nearby and temporary waste is blocking the exit flow."),
            ("urgent-medical", "A time-sensitive cleanup request was reported beside a hospital outpatient entrance."),
        ),
    ),
    (
        CityEventType.VEHICLE_BREAKDOWN,
        (
            ("breakdown-backup", "A vehicle assigned only ordinary work failed while backup vehicles are available."),
            ("breakdown-peak", "A vehicle failed during peak demand while important unfinished collections remain."),
            ("breakdown-sensitive", "A vehicle failed near a school dismissal period with sanitation complaints increasing."),
        ),
    ),
    (
        CityEventType.ROAD_CLOSURE,
        (
            ("closure-local", "A local side street is closed for short repairs; alternative streets remain open."),
            ("closure-arterial", "A major road is suddenly closed during event dispersal, blocking several collection approaches."),
            ("closure-safety", "An emergency road closure near a hospital is delaying sanitation access and waste is accumulating."),
        ),
    ),
)
