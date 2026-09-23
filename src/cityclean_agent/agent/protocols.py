"""Stable agent boundaries used by deterministic CityClean workflows."""

from __future__ import annotations

from typing import Protocol

from cityclean_agent.domain.models import CityEvent, CityState
from cityclean_agent.policy.models import PolicyDecision


class EventDecisionAgent(Protocol):
    """Return policy guidance without owning routing or mutable city state."""

    def decide(self, event: CityEvent, state: CityState) -> PolicyDecision:
        """Assess one event against a read-only city snapshot."""
