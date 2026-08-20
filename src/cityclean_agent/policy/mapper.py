"""Deterministic conversion from governance profiles to integer parameters."""

from cityclean_agent.policy.models import (
    PolicyDecision,
    PolicyParameters,
    PolicyProfile,
)


POLICY_PARAMETERS_BY_PROFILE: dict[PolicyProfile, PolicyParameters] = {
    PolicyProfile.BALANCED: PolicyParameters(
        distance_weight=1,
        lateness_weight=3,
        unserved_task_penalty=100,
        rescheduling_weight=1,
    ),
    PolicyProfile.URGENT_RESPONSE: PolicyParameters(
        distance_weight=1,
        lateness_weight=10,
        unserved_task_penalty=1_000,
        rescheduling_weight=3,
    ),
    PolicyProfile.OVERFLOW_CONTROL: PolicyParameters(
        distance_weight=1,
        lateness_weight=8,
        unserved_task_penalty=800,
        rescheduling_weight=2,
    ),
    PolicyProfile.MINIMAL_RESCHEDULE: PolicyParameters(
        distance_weight=2,
        lateness_weight=5,
        unserved_task_penalty=500,
        rescheduling_weight=10,
    ),
}


def map_policy_parameters(decision: PolicyDecision) -> PolicyParameters:
    """Return the fixed parameter set for a validated policy decision."""

    return POLICY_PARAMETERS_BY_PROFILE[decision.policy_profile]
