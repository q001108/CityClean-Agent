"""Small, validated policy models shared by the agent and optimizer boundary."""

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from cityclean_agent.domain.enums import CityEventType


class PolicyProfile(str, Enum):
    """Finite governance preferences supported by v0.1."""

    BALANCED = "BALANCED"
    URGENT_RESPONSE = "URGENT_RESPONSE"
    OVERFLOW_CONTROL = "OVERFLOW_CONTROL"
    MINIMAL_RESCHEDULE = "MINIMAL_RESCHEDULE"


class PolicyDecision(BaseModel):
    """Validated governance preference, deliberately free of routing details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: CityEventType
    risk_level: int = Field(ge=1, le=5)
    reasoning_summary: str = Field(min_length=1)
    response_deadline: int | None = Field(default=None, ge=0)
    priority_targets: tuple[str, ...] = ()
    policy_profile: PolicyProfile
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PolicyParameters:
    """Fixed integer optimizer parameters derived from a PolicyProfile."""

    distance_weight: int
    lateness_weight: int
    unserved_task_penalty: int
    rescheduling_weight: int
