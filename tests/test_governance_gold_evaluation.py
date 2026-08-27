from __future__ import annotations

import json
from collections import Counter

import pytest

from cityclean_agent.agent.deepseek_event_agent import (
    DeepSeekEventAgentError,
    build_governance_state_summary,
)
from cityclean_agent.domain.constants import MUST_SERVE_PRIORITY_THRESHOLD
from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus, VehicleStatus
from cityclean_agent.governance_gold_evaluation import (
    DEFAULT_GOLD_JSON_PATH,
    DEFAULT_GOLD_JSONL_PATH,
    GoldIntegrityError,
    GovernanceGoldCase,
    build_gold_case_agent_input,
    build_gold_case_event,
    build_gold_case_state,
    evaluate_governance_gold,
    load_governance_gold_cases,
    validate_governance_gold_integrity,
    write_governance_gold_evaluation_results,
)
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile


class CapturingAgent:
    def __init__(self) -> None:
        self.events = []
        self.summaries = []

    def decide(self, event, state) -> PolicyDecision:
        self.events.append(event)
        self.summaries.append(build_governance_state_summary(event, state))
        targets = tuple(target_id for target_id in event.affected_entities if target_id in state.waste_points)
        return PolicyDecision(
            event_type=event.event_type,
            risk_level=3,
            reasoning_summary="离线测试。",
            response_deadline=event.deadline,
            priority_targets=targets,
            policy_profile=PolicyProfile.BALANCED,
        )


class ScriptedAgent:
    def __init__(self, decisions: dict[str, PolicyDecision]) -> None:
        self._decisions = decisions

    def decide(self, event, state) -> PolicyDecision:
        return self._decisions[event.event_id]


class FailingAgent:
    def decide(self, event, state) -> PolicyDecision:
        raise DeepSeekEventAgentError("DeepSeek 模型调用失败：offline test")


def test_frozen_gold_integrity_matches_v01_contract() -> None:
    integrity = validate_governance_gold_integrity(
        DEFAULT_GOLD_JSON_PATH, DEFAULT_GOLD_JSONL_PATH
    )

    assert integrity.total_cases == 40
    assert integrity.paired_groups == 20
    assert integrity.event_type_counts == {
        "WASTE_OVERFLOW": 10,
        "URGENT_TASK": 10,
        "VEHICLE_BREAKDOWN": 10,
        "ROAD_CLOSURE": 10,
    }
    assert integrity.policy_profile_counts == {
        "BALANCED": 7,
        "URGENT_RESPONSE": 20,
        "OVERFLOW_CONTROL": 5,
        "MINIMAL_RESCHEDULE": 8,
    }
    assert integrity.risk_level_counts == {1: 4, 2: 11, 3: 7, 4: 13, 5: 5}
    assert integrity.all_approved
    assert integrity.jsonl_consistent


def test_integrity_failure_stops_evaluation_when_jsonl_differs(tmp_path) -> None:
    json_path = tmp_path / "gold.json"
    jsonl_path = tmp_path / "gold.jsonl"
    json_path.write_text(DEFAULT_GOLD_JSON_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    jsonl_path.write_text("", encoding="utf-8")

    with pytest.raises(GoldIntegrityError, match="differ"):
        validate_governance_gold_integrity(json_path, jsonl_path)


def test_gold_event_and_state_builder_preserve_context_facts() -> None:
    case = load_governance_gold_cases()[0]
    event = build_gold_case_event(case)
    state = build_gold_case_state(case)
    context = case.state_context

    assert event.event_type.value == case.event_data["event_type"]
    assert event.timestamp == case.event_data["timestamp"]
    assert event.location == case.event_data["location"]
    assert event.affected_entities == case.event_data["affected_entities"]
    assert event.metadata == case.event_data["metadata"]
    assert event.description == case.event_data["description"]
    assert state.current_time == context["current_time"]
    assert Counter(vehicle.status for vehicle in state.vehicles.values()) == Counter(
        {
            VehicleStatus.AVAILABLE: context["vehicle_summary"]["available"],
            VehicleStatus.BROKEN: context["vehicle_summary"]["broken"],
            VehicleStatus.EN_ROUTE: context["vehicle_summary"]["en_route"],
            VehicleStatus.SERVICING: context["vehicle_summary"]["servicing"],
        }
    )
    assert len(state.tasks) == context["task_summary"]["unfinished"]
    assert sum(task.status is ServiceTaskStatus.ASSIGNED for task in state.tasks.values()) == context["task_summary"]["assigned"]
    assert sum(task.priority >= MUST_SERVE_PRIORITY_THRESHOLD for task in state.tasks.values()) == context["task_summary"]["must_serve"]
    assert state.active_plan is not None
    point = state.waste_points[context["primary_target_id"]]
    expected_point = context["relevant_waste_points"][0]
    assert (point.id, point.current_load, point.capacity, point.priority) == (
        expected_point["id"],
        expected_point["current_load"],
        expected_point["capacity"],
        expected_point["priority"],
    )


def test_gold_agent_input_is_deterministic_and_excludes_gold_labels_and_rationale() -> None:
    case = load_governance_gold_cases()[0]
    first_event, first_state = build_gold_case_agent_input(case)
    second_event, second_state = build_gold_case_agent_input(case)
    first_summary = build_governance_state_summary(first_event, first_state)
    second_summary = build_governance_state_summary(second_event, second_state)
    agent = CapturingAgent()

    evaluate_governance_gold(agent, (case,))

    serialized = json.dumps(agent.summaries[0], ensure_ascii=False, sort_keys=True)
    assert first_summary == second_summary
    assert agent.events[0].description == case.event_data["description"]
    assert "gold" not in first_summary
    assert "annotation" not in first_summary
    assert case.annotation["rationale"] not in serialized
    assert str(case.gold["policy_profile"]) not in serialized


def test_all_frozen_cases_build_and_evaluate_with_an_offline_agent(monkeypatch) -> None:
    def fail_network(*args, **kwargs):
        raise AssertionError("offline Gold evaluation test must not access the network")

    monkeypatch.setattr("socket.create_connection", fail_network)
    cases = load_governance_gold_cases()
    agent = CapturingAgent()

    summary = evaluate_governance_gold(agent, cases)

    assert summary.total_cases == 40
    assert summary.successful_cases == 40
    assert summary.total_pairs == 20
    assert len(agent.events) == 40


def test_quality_metrics_confusion_deadlines_targets_and_pairs_are_measured() -> None:
    cases = (
        _case("A", "P1", "BALANCED", 1, (1, 1), None, None, ()),
        _case("B", "P1", "URGENT_RESPONSE", 3, (2, 4), 20, (19, 21), ("W1",)),
        _case("C", "P2", "OVERFLOW_CONTROL", 4, (4, 5), 30, (30, 30), ("W1",)),
        _case("D", "P2", "MINIMAL_RESCHEDULE", 5, (5, 5), None, None, ()),
    )
    decisions = {
        "E-A": _decision(PolicyProfile.BALANCED, 1, None, ()),
        "E-B": _decision(PolicyProfile.URGENT_RESPONSE, 2, 21, ("W1",)),
        "E-C": _decision(PolicyProfile.BALANCED, 2, None, ("W1",)),
        "E-D": _decision(PolicyProfile.MINIMAL_RESCHEDULE, 5, None, ()),
    }

    summary = evaluate_governance_gold(ScriptedAgent(decisions), cases)

    assert summary.contract_success_rate == 1.0
    assert summary.policy_accuracy == 0.75
    assert summary.policy_confusion_matrix == (
        (1, 0, 0, 0),
        (0, 1, 0, 0),
        (1, 0, 0, 0),
        (0, 0, 0, 1),
    )
    assert summary.policy_per_class_precision["OVERFLOW_CONTROL"] == 0.0
    assert summary.policy_per_class_recall["OVERFLOW_CONTROL"] == 0.0
    assert summary.policy_per_class_f1["OVERFLOW_CONTROL"] == 0.0
    assert summary.risk_exact_accuracy == 0.5
    assert summary.risk_mae == 0.75
    assert summary.risk_within_one_accuracy == 0.75
    assert summary.risk_acceptable_range_accuracy == 0.75
    assert summary.deadline_acceptable_accuracy == 0.75
    assert summary.deadline_reference_mae == 1.0
    assert summary.deadline_numeric_evaluable_cases == 1
    assert summary.deadline_none_gold_cases == 2
    assert summary.deadline_predicted_none_cases == 3
    assert summary.target_precision == 1.0
    assert summary.target_recall == 1.0
    assert summary.target_f1 == 1.0
    assert summary.target_exact_set_accuracy == 1.0
    assert summary.total_pairs == 2
    assert summary.both_success_pairs == 2
    assert summary.gold_profile_changed_pairs == 2
    assert summary.correct_profile_changed_pairs == 1
    assert summary.paired_profile_accuracy == 0.5


def test_failed_contracts_do_not_contribute_prediction_quality_metrics() -> None:
    summary = evaluate_governance_gold(FailingAgent(), (_case("A", "P1", "BALANCED", 1, (1, 1), None, None, ()),))

    assert summary.successful_cases == 0
    assert summary.failed_cases == 1
    assert summary.contract_success_rate == 0.0
    assert summary.policy_accuracy == 0.0
    assert summary.policy_macro_f1 == 0.0
    assert summary.risk_mae == 0.0
    assert summary.target_f1 == 0.0
    assert summary.case_results[0].error_type == "provider_error"


def test_result_serialization_is_machine_readable_without_gold_rationale(tmp_path) -> None:
    case = _case("A", "P1", "BALANCED", 1, (1, 1), None, None, ())
    summary = evaluate_governance_gold(
        ScriptedAgent({"E-A": _decision(PolicyProfile.BALANCED, 1, None, ())}),
        (case,),
    )
    path = tmp_path / "evaluation.json"

    write_governance_gold_evaluation_results(path, summary)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["total_cases"] == 1
    assert data["case_results"][0]["reasoning_summary"] == "离线测试。"
    assert "annotation" not in data["case_results"][0]
    assert "rationale" not in json.dumps(data, ensure_ascii=False)


def _case(
    case_id: str,
    pair_id: str,
    profile: str,
    risk: int,
    risk_range: tuple[int, int],
    deadline_reference: int | None,
    deadline_range: tuple[int, int] | None,
    targets: tuple[str, ...],
) -> GovernanceGoldCase:
    return GovernanceGoldCase(
        case_id=case_id,
        pair_id=pair_id,
        event_type=CityEventType.URGENT_TASK.value,
        dataset_version="test",
        event_data={
            "event_id": f"E-{case_id}",
            "event_type": CityEventType.URGENT_TASK.value,
            "timestamp": 10,
            "location": "W1-node",
            "affected_entities": ["W1"],
            "severity": 3,
            "deadline": 50,
            "metadata": {"demand": 1},
            "description": "测试描述。",
        },
        state_context={
            "current_time": 10,
            "vehicle_summary": {
                "total": 1,
                "available": 1,
                "broken": 0,
                "en_route": 0,
                "servicing": 0,
            },
            "task_summary": {"unfinished": 1, "must_serve": 0, "assigned": 0},
            "primary_target_id": "W1",
            "relevant_waste_points": [
                {"id": "W1", "current_load": 1, "capacity": 10, "priority": 1}
            ],
            "active_plan_exists": False,
        },
        gold={
            "policy_profile": profile,
            "risk_level": risk,
            "acceptable_risk_range": list(risk_range),
            "response_deadline_reference": deadline_reference,
            "response_deadline_range": list(deadline_range) if deadline_range else None,
            "priority_targets": list(targets),
        },
        annotation={"review_status": "approved", "rationale": "测试标注。"},
    )


def _decision(
    profile: PolicyProfile, risk: int, deadline: int | None, targets: tuple[str, ...]
) -> PolicyDecision:
    return PolicyDecision(
        event_type=CityEventType.URGENT_TASK,
        risk_level=risk,
        reasoning_summary="离线测试。",
        response_deadline=deadline,
        priority_targets=targets,
        policy_profile=profile,
    )
