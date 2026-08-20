from __future__ import annotations

import json

from cityclean_agent.agent.deepseek_event_agent import DeepSeekEventAgent
from cityclean_agent.domain.enums import CityEventType
from cityclean_agent.live_e2e import live_e2e_cases, run_live_e2e_case
from cityclean_agent.policy.models import PolicyProfile


class EventAwareFakeModel:
    """Offline structured-output runnable matching the real-agent boundary."""

    def __init__(self) -> None:
        self.messages = []

    def invoke(self, messages):
        self.messages.append(messages)
        summary = json.loads(messages[1][1])
        event = summary["event"]
        event_type = event["event_type"]
        target = (
            event["affected_entities"]
            if event_type
            in {CityEventType.URGENT_TASK.value, CityEventType.WASTE_OVERFLOW.value}
            else []
        )
        return {
            "event_type": event_type,
            "risk_level": 4,
            "reasoning_summary": "Use the supplied governance context.",
            "response_deadline": summary["current_time"] + 10,
            "priority_targets": target,
            "policy_profile": PolicyProfile.URGENT_RESPONSE,
            "constraints": ["Use the deterministic optimizer for dispatch."],
        }


class InvalidEventTypeModel:
    def invoke(self, messages):
        del messages
        return {
            "event_type": CityEventType.ROAD_CLOSURE,
            "risk_level": 4,
            "reasoning_summary": "Invalid event type for this case.",
            "response_deadline": 30,
            "priority_targets": [],
            "policy_profile": PolicyProfile.BALANCED,
            "constraints": [],
        }


def test_deepseek_compatible_fake_agent_completes_urgent_workflow() -> None:
    model = EventAwareFakeModel()
    case = live_e2e_cases()[0]

    result = run_live_e2e_case(DeepSeekEventAgent(model), case)

    assert result.success
    assert result.workflow_status == "SUCCESS"
    assert result.verification_valid is True
    assert result.target_task_outcome is not None
    assert result.target_task_outcome["status"] == "COMPLETED"
    summary = json.loads(model.messages[0][1][1])
    assert summary["event"]["natural_language_description"] == case.event.description


def test_invalid_deepseek_result_blocks_replanning_downstream() -> None:
    case = live_e2e_cases()[0]

    result = run_live_e2e_case(DeepSeekEventAgent(InvalidEventTypeModel()), case)

    assert not result.success
    assert result.workflow_status is None
    assert result.verification_valid is None
    assert result.replanned_route_summary is None
    assert result.target_task_outcome is None
    assert "event_type" in (result.error or "")


def test_all_live_cases_execute_with_the_same_offline_agent_boundary() -> None:
    agent = DeepSeekEventAgent(EventAwareFakeModel())

    results = tuple(run_live_e2e_case(agent, case) for case in live_e2e_cases())

    assert len(results) == 3
    assert all(result.success for result in results)
    assert all(result.workflow_status == "SUCCESS" for result in results)
    assert all(result.verification_valid is True for result in results)


def test_live_e2e_result_is_json_serializable() -> None:
    result = run_live_e2e_case(DeepSeekEventAgent(EventAwareFakeModel()), live_e2e_cases()[0])

    serialized = json.dumps(result.to_dict())

    assert "urgent_timing_tradeoff_live" in serialized
    assert '"total_distance"' in serialized
