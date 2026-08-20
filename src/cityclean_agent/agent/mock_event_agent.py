"""A deterministic stand-in for the future LLM-backed Event Agent."""

from cityclean_agent.domain.enums import CityEventType
from cityclean_agent.domain.models import CityEvent, CityState
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile


_PROFILE_BY_EVENT_TYPE = {
    CityEventType.WASTE_OVERFLOW: PolicyProfile.OVERFLOW_CONTROL,
    CityEventType.URGENT_TASK: PolicyProfile.URGENT_RESPONSE,
    CityEventType.VEHICLE_BREAKDOWN: PolicyProfile.MINIMAL_RESCHEDULE,
    CityEventType.ROAD_CLOSURE: PolicyProfile.MINIMAL_RESCHEDULE,
}


class MockEventAgent:
    """Produce validated, repeatable governance decisions without an LLM."""

    def decide(self, event: CityEvent, state: CityState) -> PolicyDecision:
        """Assess an event using only deterministic v0.1 rules."""

        priority_targets = ()
        if event.event_type in {
            CityEventType.WASTE_OVERFLOW,
            CityEventType.URGENT_TASK,
        }:
            priority_targets = tuple(
                target_id
                for target_id in dict.fromkeys(event.affected_entities)
                if target_id in state.waste_points
            )

        return PolicyDecision(
            event_type=event.event_type,
            risk_level=min(max(event.severity, 1), 5),
            reasoning_summary=_reasoning_summary(event.event_type),
            response_deadline=event.deadline,
            priority_targets=priority_targets,
            policy_profile=_PROFILE_BY_EVENT_TYPE[event.event_type],
        )


class FixedBalancedAgent(MockEventAgent):
    """Benchmark-only deterministic agent that always selects BALANCED."""

    def decide(self, event: CityEvent, state: CityState) -> PolicyDecision:
        """Preserve event assessment data while fixing the governance profile."""

        decision = super().decide(event, state)
        return decision.model_copy(update={"policy_profile": PolicyProfile.BALANCED})


def _reasoning_summary(event_type: CityEventType) -> str:
    summaries = {
        CityEventType.WASTE_OVERFLOW: "优先控制垃圾满溢并恢复环境卫生。",
        CityEventType.URGENT_TASK: "优先响应紧急清运需求。",
        CityEventType.VEHICLE_BREAKDOWN: "车辆故障后优先减少既有调度扰动。",
        CityEventType.ROAD_CLOSURE: "道路封闭后优先减少路线执行扰动。",
    }
    return summaries[event_type]
