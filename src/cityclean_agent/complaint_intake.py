"""Small deterministic complaint intake for the fixed v0.2 showcase cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from cityclean_agent.domain.enums import CityEventType
from cityclean_agent.domain.models import CityEvent


class ComplaintRole(str, Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class MessageSource(str, Enum):
    USER_AUTHORED = "USER_AUTHORED"
    MODEL_GENERATED = "MODEL_GENERATED"
    EDITORIAL = "EDITORIAL"


class ComplaintIntakeStatus(str, Enum):
    COLLECTING = "COLLECTING"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class ComplaintMessage:
    message_id: str
    role: ComplaintRole
    content: str
    created_at: int
    source: MessageSource


@dataclass(frozen=True, slots=True)
class ComplaintIntakeResult:
    status: ComplaintIntakeStatus
    complaint_summary: str | None = None
    candidate_event_type: CityEventType | None = None
    location_text: str | None = None
    affected_entity_mentions: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ComplaintSession:
    session_id: str
    scenario_id: str
    messages: tuple[ComplaintMessage, ...]
    intake_result: ComplaintIntakeResult
    resolved_event: CityEvent | None
    clarification_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class ScenarioEntityResolver:
    """Resolve only predeclared aliases; it never creates city entities."""

    scenario_id: str
    event: CityEvent
    aliases: dict[str, str]
    supported_event_type: CityEventType

    def intake(self, message: ComplaintMessage) -> ComplaintSession:
        if message.role is not ComplaintRole.USER or message.source is not MessageSource.USER_AUTHORED:
            raise ValueError("intake accepts only a user-authored complaint")
        text = message.content.strip()
        if not text:
            return self._needs_clarification(message, ("complaint_text",))
        if not _mentions_urgent_collection(text):
            return ComplaintSession(
                session_id=f"session-{self.scenario_id}",
                scenario_id=self.scenario_id,
                messages=(message,),
                intake_result=ComplaintIntakeResult(
                    status=ComplaintIntakeStatus.REJECTED,
                    rejection_reason="当前精选场景仅支持临时紧急清运投诉。",
                ),
                resolved_event=None,
            )
        matched = tuple(
            entity_id
            for alias, entity_id in self.aliases.items()
            if alias in text
        )
        if not matched:
            return self._needs_clarification(message, ("location",))
        if len(set(matched)) != 1:
            return ComplaintSession(
                session_id=f"session-{self.scenario_id}",
                scenario_id=self.scenario_id,
                messages=(message,),
                intake_result=ComplaintIntakeResult(
                    status=ComplaintIntakeStatus.REJECTED,
                    rejection_reason="投诉包含当前精选场景无法唯一解析的多个地点。",
                ),
                resolved_event=None,
            )
        target_id = matched[0]
        if target_id not in self.event.affected_entities:
            return self._needs_clarification(message, ("supported_entity",))
        resolved = CityEvent(
            event_id=self.event.event_id,
            event_type=self.supported_event_type,
            timestamp=self.event.timestamp,
            location=self.event.location,
            affected_entities=list(self.event.affected_entities),
            severity=self.event.severity,
            deadline=self.event.deadline,
            metadata=dict(self.event.metadata),
            description=text,
        )
        return ComplaintSession(
            session_id=f"session-{self.scenario_id}",
            scenario_id=self.scenario_id,
            messages=(message,),
            intake_result=ComplaintIntakeResult(
                status=ComplaintIntakeStatus.READY,
                complaint_summary="活动出口人流密集，需要紧急完成临时清运。",
                candidate_event_type=self.supported_event_type,
                location_text=next(alias for alias, value in self.aliases.items() if value == target_id),
                affected_entity_mentions=(target_id,),
            ),
            resolved_event=resolved,
        )

    def _needs_clarification(
        self, message: ComplaintMessage, missing_fields: tuple[str, ...]
    ) -> ComplaintSession:
        return ComplaintSession(
            session_id=f"session-{self.scenario_id}",
            scenario_id=self.scenario_id,
            messages=(message,),
            intake_result=ComplaintIntakeResult(
                status=ComplaintIntakeStatus.NEEDS_CLARIFICATION,
                missing_fields=missing_fields,
            ),
            resolved_event=None,
            clarification_prompt="请确认当前精选场景中的地点，例如“活动出口”。",
        )


def urgent_timing_tradeoff_resolver(event: CityEvent) -> ScenarioEntityResolver:
    """Return the explicit alias table for the v0.2 selected demonstration."""

    return ScenarioEntityResolver(
        scenario_id="urgent_timing_tradeoff_live",
        event=event,
        aliases={"活动出口": "WU", "出口处": "WU", "临时清运点": "WU"},
        supported_event_type=CityEventType.URGENT_TASK,
    )


def _mentions_urgent_collection(text: str) -> bool:
    return any(token in text for token in ("活动", "人流", "清运", "垃圾", "卫生"))
