from __future__ import annotations

import json

from cityclean_agent.agent.deepseek_event_agent import DeepSeekEventAgentError
from cityclean_agent.benchmark.natural_language_evaluation import (
    evaluation_summary,
    natural_language_evaluation_cases,
    run_natural_language_evaluation,
    write_natural_language_evaluation_results,
)
from cityclean_agent.domain.enums import CityEventType
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.policy.mapper import POLICY_PARAMETERS_BY_PROFILE
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile


class FakeNaturalLanguageAgent:
    def decide(self, event, state) -> PolicyDecision:
        return PolicyDecision(
            event_type=event.event_type,
            risk_level=event.severity,
            reasoning_summary=f"Assessed at minute {state.current_time}.",
            response_deadline=state.current_time + 10,
            priority_targets=("W1",) if event.event_type is not CityEventType.ROAD_CLOSURE else (),
            policy_profile=PolicyProfile.BALANCED,
        )


class FailingNaturalLanguageAgent:
    def decide(self, event, state) -> PolicyDecision:
        raise DeepSeekEventAgentError("invalid structured output")


def test_natural_language_cases_are_unique_paired_and_deterministic() -> None:
    first = natural_language_evaluation_cases()
    second = natural_language_evaluation_cases()

    assert first == second
    assert len(first) == 12
    assert len({case.case_id for case in first}) == 12
    for event_type in CityEventType:
        group = [case for case in first if case.event.event_type is event_type]
        assert len(group) == 3
        assert len({case.event.description for case in group}) == 3
        assert {
            (
                case.event.timestamp,
                case.event.location,
                tuple(case.event.affected_entities),
                case.event.severity,
                case.event.deadline,
            )
            for case in group
        }.__len__() == 1


def test_evaluation_records_successful_contract_results_without_network() -> None:
    results = run_natural_language_evaluation(FakeNaturalLanguageAgent())

    assert len(results) == 12
    assert all(result.success for result in results)
    assert all(result.response_deadline == 30 for result in results)
    assert evaluation_summary(results) == {
        "total_cases": 12,
        "successful_cases": 12,
        "contract_success_rate": 1.0,
    }


def test_evaluation_records_contract_failures_without_retrying() -> None:
    results = run_natural_language_evaluation(FailingNaturalLanguageAgent())

    assert len(results) == 12
    assert all(not result.success for result in results)
    assert all(result.error_type == "DeepSeekEventAgentError" for result in results)
    assert evaluation_summary(results)["contract_success_rate"] == 0.0


def test_optimizer_does_not_use_event_description() -> None:
    routine_case, sensitive_case = natural_language_evaluation_cases()[:2]
    routine_state = routine_case.build_state()
    sensitive_state = sensitive_case.build_state()
    routine_state.active_events = {routine_case.event.event_id: routine_case.event}
    sensitive_state.active_events = {sensitive_case.event.event_id: sensitive_case.event}

    parameters = POLICY_PARAMETERS_BY_PROFILE[PolicyProfile.BALANCED]
    routine_result = ORToolsOptimizer().optimize(routine_state, parameters)
    sensitive_result = ORToolsOptimizer().optimize(sensitive_state, parameters)

    assert routine_result == sensitive_result


def test_evaluation_result_serialization_is_machine_readable(tmp_path) -> None:
    path = tmp_path / "results.json"
    results = run_natural_language_evaluation(FakeNaturalLanguageAgent())

    write_natural_language_evaluation_results(path, results)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["summary"]["total_cases"] == 12
    assert data["results"][0]["description"]
    assert data["results"][0]["error_type"] is None
