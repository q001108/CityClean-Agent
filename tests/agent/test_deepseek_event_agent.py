from __future__ import annotations

from copy import deepcopy
import json

import pytest

import cityclean_agent.agent.deepseek_event_agent as deepseek_module
from cityclean_agent.agent.deepseek_event_agent import (
    DEFAULT_DEEPSEEK_MODEL,
    DeepSeekEventAgent,
    DeepSeekEventAgentError,
    build_governance_state_summary,
)
from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import CityEvent, CityState, Road, ServiceTask, Vehicle, WastePoint
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile


class FakeModel:
    def __init__(self, output=None, error: Exception | None = None) -> None:
        self.output = output
        self.error = error
        self.messages = []

    def invoke(self, messages):
        self.messages.append(messages)
        if self.error is not None:
            raise self.error
        return self.output


def make_state() -> CityState:
    return CityState(
        current_time=10,
        waste_points={
            "W1": WastePoint("W1", "B", 10, 10, 0, "mixed", "school", 4)
        },
        vehicles={
            "V1": Vehicle("V1", "A", 5, 0, VehicleStatus.AVAILABLE, 30),
            "V2": Vehicle("V2", "C", 5, 0, VehicleStatus.BROKEN, 30),
        },
        transfer_stations={},
        road_network=RoadNetwork([Road("R1", "A", "B", 9, 5)]),
        tasks={
            "T-high": ServiceTask(
                "T-high",
                "E-old",
                "W1",
                1,
                10,
                30,
                status=ServiceTaskStatus.PENDING,
                created_at=5,
            )
        },
    )


def make_event() -> CityEvent:
    return CityEvent(
        "E-overflow",
        CityEventType.WASTE_OVERFLOW,
        10,
        "B",
        ["W1"],
        4,
        30,
        metadata={"demand": 4},
        description="Waste overflow",
    )


def valid_payload() -> dict[str, object]:
    return {
        "event_type": CityEventType.WASTE_OVERFLOW,
        "risk_level": 4,
        "reasoning_summary": "Control the overflowing waste point.",
        "response_deadline": 30,
        "priority_targets": ["W1"],
        "policy_profile": PolicyProfile.OVERFLOW_CONTROL,
        "constraints": ["Preserve must-serve service."],
    }


def test_fake_structured_model_returns_valid_policy_decision() -> None:
    model = FakeModel(valid_payload())
    decision = DeepSeekEventAgent(model).decide(make_event(), make_state())

    assert isinstance(decision, PolicyDecision)
    assert decision.event_type is CityEventType.WASTE_OVERFLOW
    assert decision.priority_targets == ("W1",)
    assert "JSON" in model.messages[0][0][1]
    assert "event_type" in model.messages[0][0][1]
    assert "risk_level" in model.messages[0][0][1]
    assert "中文" in model.messages[0][0][1]


def test_event_type_mismatch_is_rejected() -> None:
    payload = valid_payload()
    payload["event_type"] = CityEventType.URGENT_TASK

    with pytest.raises(DeepSeekEventAgentError, match="event_type"):
        DeepSeekEventAgent(FakeModel(payload)).decide(make_event(), make_state())


def test_unknown_priority_target_is_rejected() -> None:
    payload = valid_payload()
    payload["priority_targets"] = ["unknown"]

    with pytest.raises(DeepSeekEventAgentError, match="priority target"):
        DeepSeekEventAgent(FakeModel(payload)).decide(make_event(), make_state())


@pytest.mark.parametrize(
    "field_name, value",
    [
        ("risk_level", 0),
        ("policy_profile", "UNSUPPORTED"),
        ("unexpected", "extra"),
        ("distance_weight", 1),
    ],
)
def test_invalid_or_forbidden_structured_fields_are_rejected(field_name, value) -> None:
    payload = valid_payload()
    payload[field_name] = value

    with pytest.raises(DeepSeekEventAgentError):
        DeepSeekEventAgent(FakeModel(payload)).decide(make_event(), make_state())


def test_past_response_deadline_is_rejected() -> None:
    payload = valid_payload()
    payload["response_deadline"] = 9

    with pytest.raises(DeepSeekEventAgentError, match="deadline"):
        DeepSeekEventAgent(FakeModel(payload)).decide(make_event(), make_state())


def test_response_deadline_equal_to_current_time_is_rejected() -> None:
    payload = valid_payload()
    payload["response_deadline"] = 10

    with pytest.raises(DeepSeekEventAgentError, match="deadline"):
        DeepSeekEventAgent(FakeModel(payload)).decide(make_event(), make_state())


def test_response_deadline_is_an_absolute_simulation_minute() -> None:
    state = make_state()
    state.current_time = 20
    payload = valid_payload()
    payload["response_deadline"] = 30

    decision = DeepSeekEventAgent(FakeModel(payload)).decide(make_event(), state)

    assert decision.response_deadline == 30
    payload["response_deadline"] = 10
    with pytest.raises(DeepSeekEventAgentError, match="deadline"):
        DeepSeekEventAgent(FakeModel(payload)).decide(make_event(), state)


def test_state_summary_is_deterministic_compact_and_read_only() -> None:
    state = make_state()
    original = deepcopy(state)
    event = make_event()

    first = build_governance_state_summary(event, state)
    second = build_governance_state_summary(event, state)
    serialized = json.dumps(first, sort_keys=True)

    assert first == second
    assert first["current_time"] == 10
    assert first["affected_targets"] == [
        {
            "id": "W1",
            "current_load": 10,
            "capacity": 10,
            "priority": 4,
            "is_overflow": True,
        }
    ]
    assert first["vehicle_summary"] == {
        "total": 2,
        "available": 1,
        "broken": 1,
        "en_route": 0,
        "servicing": 0,
    }
    assert first["task_summary"]["must_serve_task_count"] == 1
    assert "R1" not in serialized
    assert state.tasks == original.tasks
    assert state.vehicles == original.vehicles
    assert tuple(state.road_network.roads) == tuple(original.road_network.roads)


def test_state_summary_includes_only_present_natural_language_description() -> None:
    with_description = make_event()
    without_description = make_event()
    without_description.description = None

    described_summary = build_governance_state_summary(with_description, make_state())
    undescribed_summary = build_governance_state_summary(without_description, make_state())

    assert described_summary["event"]["natural_language_description"] == "Waste overflow"
    assert "natural_language_description" not in undescribed_summary["event"]


def test_fake_model_failure_is_explicit() -> None:
    with pytest.raises(DeepSeekEventAgentError, match="模型调用失败"):
        DeepSeekEventAgent(FakeModel(error=RuntimeError("network failure"))).decide(
            make_event(), make_state()
        )


def test_same_fake_output_produces_the_same_policy_decision() -> None:
    agent = DeepSeekEventAgent(FakeModel(valid_payload()))

    assert agent.decide(make_event(), make_state()) == agent.decide(make_event(), make_state())


def test_injected_fake_model_does_not_construct_real_provider_even_with_key(monkeypatch) -> None:
    class FailIfConstructed:
        def __init__(self, **kwargs) -> None:
            raise AssertionError("default pytest must not construct the real provider")

    monkeypatch.setattr(deepseek_module, "ChatDeepSeek", FailIfConstructed)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-for-offline-test")

    decision = DeepSeekEventAgent(FakeModel(valid_payload())).decide(make_event(), make_state())

    assert decision.policy_profile is PolicyProfile.OVERFLOW_CONTROL


def test_missing_api_key_fails_explicitly_without_constructing_provider(monkeypatch) -> None:
    monkeypatch.setattr(deepseek_module, "load_dotenv", lambda: False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(DeepSeekEventAgentError, match="未配置"):
        DeepSeekEventAgent()


def test_real_model_configuration_uses_json_mode_without_network(monkeypatch) -> None:
    captured = {}
    fake_runnable = FakeModel(valid_payload())

    class FakeChatDeepSeek:
        def __init__(self, **kwargs) -> None:
            captured["chat_kwargs"] = kwargs

        def with_structured_output(self, schema, *, method):
            captured["schema"] = schema
            captured["method"] = method
            return fake_runnable

    monkeypatch.setattr(deepseek_module, "ChatDeepSeek", FakeChatDeepSeek)
    monkeypatch.setattr(deepseek_module, "load_dotenv", lambda: False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-for-offline-test")

    agent = DeepSeekEventAgent()
    decision = agent.decide(make_event(), make_state())

    assert captured["chat_kwargs"]["model"] == DEFAULT_DEEPSEEK_MODEL
    assert captured["chat_kwargs"]["temperature"] == 0
    assert captured["schema"] is PolicyDecision
    assert captured["method"] == "json_mode"
    assert decision.event_type is CityEventType.WASTE_OVERFLOW
