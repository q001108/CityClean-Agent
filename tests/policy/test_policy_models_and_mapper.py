import pytest
from pydantic import ValidationError

from cityclean_agent.domain.enums import CityEventType
from cityclean_agent.policy.mapper import (
    POLICY_PARAMETERS_BY_PROFILE,
    map_policy_parameters,
)
from cityclean_agent.policy.models import (
    PolicyDecision,
    PolicyParameters,
    PolicyProfile,
)


def make_decision(profile: PolicyProfile) -> PolicyDecision:
    return PolicyDecision(
        event_type=CityEventType.URGENT_TASK,
        risk_level=4,
        reasoning_summary="urgent response",
        response_deadline=20,
        priority_targets=("W1",),
        policy_profile=profile,
    )


def test_policy_decision_rejects_invalid_risk_level() -> None:
    with pytest.raises(ValidationError, match="risk_level"):
        PolicyDecision(
            event_type=CityEventType.URGENT_TASK,
            risk_level=0,
            reasoning_summary="urgent response",
            policy_profile=PolicyProfile.URGENT_RESPONSE,
        )


def test_policy_decision_rejects_free_optimizer_weights() -> None:
    with pytest.raises(ValidationError, match="distance_weight"):
        PolicyDecision(
            event_type=CityEventType.URGENT_TASK,
            risk_level=4,
            reasoning_summary="urgent response",
            policy_profile=PolicyProfile.URGENT_RESPONSE,
            distance_weight=0.43,
        )


@pytest.mark.parametrize("profile", list(PolicyProfile))
def test_each_profile_maps_to_fixed_integer_parameters(profile: PolicyProfile) -> None:
    parameters = map_policy_parameters(make_decision(profile))

    assert parameters == POLICY_PARAMETERS_BY_PROFILE[profile]
    assert isinstance(parameters, PolicyParameters)
    assert all(
        isinstance(getattr(parameters, field_name), int)
        for field_name in (
            "distance_weight",
            "lateness_weight",
            "unserved_task_penalty",
            "rescheduling_weight",
        )
    )


def test_mapper_is_deterministic() -> None:
    decision = make_decision(PolicyProfile.OVERFLOW_CONTROL)

    assert map_policy_parameters(decision) == map_policy_parameters(decision)
