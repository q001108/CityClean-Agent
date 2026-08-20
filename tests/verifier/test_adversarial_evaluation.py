from __future__ import annotations

from copy import deepcopy
import json

import cityclean_agent.verifier.evaluation as evaluation_module
from cityclean_agent.verifier.evaluation import (
    VerifierEvaluationCase,
    evaluate_verifier_suite,
    summarize_verifier_evaluation,
    verifier_evaluation_suite,
    write_verifier_evaluation_results,
)
from cityclean_agent.verifier.plan_verifier import PlanVerifier


def test_fixed_adversarial_suite_has_unique_valid_and_invalid_cases() -> None:
    cases = verifier_evaluation_suite()

    assert len(cases) == 15
    assert len({case.case_id for case in cases}) == len(cases)
    assert sum(case.expected_valid for case in cases) == 2
    assert sum(not case.expected_valid for case in cases) == 13


def test_fixed_suite_regression_expectations_and_summary_are_deterministic() -> None:
    first = evaluate_verifier_suite()
    second = evaluate_verifier_suite()
    summary = summarize_verifier_evaluation(first)

    assert first == second
    assert all(result.passed_expectation for result in first)
    assert summary.total_cases == 15
    assert summary.correctly_accepted_valid == 2
    assert summary.correctly_rejected_invalid == 13
    assert summary.invalid_detection_rate == 1.0
    assert summary.valid_acceptance_rate == 1.0
    assert "planned_arrivals_consistent" in summary.detected_violation_type_coverage


def test_evaluation_does_not_mutate_case_state_or_plan() -> None:
    source_case = verifier_evaluation_suite()[1]
    state = source_case.build_state()
    plan = source_case.build_plan()
    original_state = deepcopy(state)
    original_plan = deepcopy(plan)
    case = VerifierEvaluationCase(
        "no-mutation",
        True,
        (),
        lambda: state,
        lambda: plan,
    )

    result = evaluate_verifier_suite([case])[0]

    assert result.passed_expectation
    assert state.current_time == original_state.current_time
    assert state.tasks == original_state.tasks
    assert state.vehicles == original_state.vehicles
    assert state.waste_points == original_state.waste_points
    assert tuple(state.road_network.roads) == tuple(original_state.road_network.roads)
    assert plan == original_plan


def test_evaluation_submits_each_case_directly_to_plan_verifier(monkeypatch) -> None:
    calls = []

    class CountingVerifier:
        def __init__(self) -> None:
            self._verifier = PlanVerifier()

        def verify(self, state, plan):
            calls.append((state, plan))
            return self._verifier.verify(state, plan)

    monkeypatch.setattr(evaluation_module, "PlanVerifier", CountingVerifier)
    results = evaluation_module.evaluate_verifier_suite()

    assert len(calls) == len(results) == 15
    assert all(result.passed_expectation for result in results)


def test_evaluation_result_json_is_machine_readable(tmp_path) -> None:
    path = tmp_path / "verifier-results.json"
    results = evaluate_verifier_suite()

    write_verifier_evaluation_results(path, results)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["summary"]["invalid_detection_rate"] == 1.0
    assert data["cases"][0]["case_id"] == "valid_single_vehicle"
