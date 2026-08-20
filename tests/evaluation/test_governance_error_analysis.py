from __future__ import annotations

import hashlib
import json

import pytest

from cityclean_agent.governance_error_analysis import (
    DEFAULT_GOLD_JSONL_PATH,
    DEFAULT_GOLD_JSON_PATH,
    GovernanceAnalysisError,
    analyze_governance_errors,
    load_approved_gold_records,
    load_evaluation_results,
    render_governance_error_analysis_markdown,
    write_governance_error_analysis_report,
)


def test_analysis_loads_generated_evaluation_shape_from_json(tmp_path) -> None:
    path = tmp_path / "evaluation.json"
    path.write_text(json.dumps(_evaluation()), encoding="utf-8")

    loaded = load_evaluation_results(path)

    assert len(loaded["case_results"]) == 2
    assert loaded["dataset_version"] == "v0.1"


def test_analysis_is_deterministic_and_classifies_confusion_and_errors() -> None:
    first = analyze_governance_errors(_evaluation(), _gold_records())
    second = analyze_governance_errors(_evaluation(), _gold_records())

    assert first == second
    assert first["policy"]["confusion_matrix"] == [
        [0, 1, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [1, 0, 0, 0],
    ]
    assert first["policy"]["taxonomy_counts"] == {
        "A. Risk escalation bias": 1,
        "B. Conservative delay handling": 1,
    }
    assert first["risk"]["under_estimation_count"] == 1
    assert first["risk"]["over_estimation_count"] == 1
    assert first["deadline"]["category_counts"] == {"Missing deadline": 1}
    assert first["targets"]["false_positive_targets"] == {"W1": 1}
    assert first["targets"]["false_negative_targets"] == {"W2": 1}


def test_report_rendering_contains_measurement_sections_without_reasoning() -> None:
    markdown = render_governance_error_analysis_markdown(
        analyze_governance_errors(_evaluation(), _gold_records())
    )

    assert "# Governance Error Analysis Report v0.1" in markdown
    assert "## 3. Policy Error Taxonomy" in markdown
    assert "## 8. Root Cause Classification" in markdown
    assert "reasoning_summary" not in markdown


def test_report_writer_creates_report_without_modifying_frozen_gold(tmp_path) -> None:
    before_json = _sha256(DEFAULT_GOLD_JSON_PATH)
    before_jsonl = _sha256(DEFAULT_GOLD_JSONL_PATH)
    report_path = tmp_path / "governance_error_analysis.md"

    write_governance_error_analysis_report(
        report_path, analyze_governance_errors(_evaluation(), _gold_records())
    )

    assert report_path.exists()
    assert _sha256(DEFAULT_GOLD_JSON_PATH) == before_json
    assert _sha256(DEFAULT_GOLD_JSONL_PATH) == before_jsonl


def test_approved_gold_loader_reads_the_frozen_pair_without_mutation() -> None:
    before_json = _sha256(DEFAULT_GOLD_JSON_PATH)
    before_jsonl = _sha256(DEFAULT_GOLD_JSONL_PATH)

    records = load_approved_gold_records(DEFAULT_GOLD_JSON_PATH, DEFAULT_GOLD_JSONL_PATH)

    assert len(records) == 40
    assert _sha256(DEFAULT_GOLD_JSON_PATH) == before_json
    assert _sha256(DEFAULT_GOLD_JSONL_PATH) == before_jsonl


def test_gold_loader_rejects_inconsistent_serializations(tmp_path) -> None:
    json_path = tmp_path / "gold.json"
    jsonl_path = tmp_path / "gold.jsonl"
    json_path.write_text(json.dumps(list(_gold_records().values())), encoding="utf-8")
    jsonl_path.write_text("", encoding="utf-8")

    with pytest.raises(GovernanceAnalysisError, match="differ"):
        load_approved_gold_records(json_path, jsonl_path)


def _evaluation() -> dict[str, object]:
    return {
        "dataset_version": "v0.1",
        "total_cases": 2,
        "successful_cases": 2,
        "failed_cases": 0,
        "contract_success_rate": 1.0,
        "policy": {
            "accuracy": 0.0,
            "macro_f1": 0.0,
            "confusion_matrix_order": [
                "BALANCED",
                "URGENT_RESPONSE",
                "OVERFLOW_CONTROL",
                "MINIMAL_RESCHEDULE",
            ],
            "confusion_matrix": [
                [0, 1, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
                [1, 0, 0, 0],
            ],
        },
        "risk": {
            "exact_accuracy": 0.0,
            "mae": 2.0,
            "within_one_accuracy": 0.0,
        },
        "deadline": {
            "acceptable_accuracy": 0.5,
            "reference_mae": 0.0,
        },
        "targets": {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "exact_set_accuracy": 0.0,
        },
        "pairs": {
            "total_pairs": 1,
            "both_success_pairs": 1,
            "gold_profile_changed_pairs": 1,
            "correct_profile_changed_pairs": 0,
            "paired_profile_accuracy": 0.0,
        },
        "pair_results": [
            {
                "pair_id": "P1",
                "both_contract_success": True,
                "gold_profile_changed": True,
                "predicted_profile_changed": True,
                "profile_pair_correct": False,
            }
        ],
        "case_results": [
            {
                "case_id": "A",
                "pair_id": "P1",
                "event_type": "URGENT_TASK",
                "contract_success": True,
                "error_type": None,
                "policy_correct": False,
                "gold_policy_profile": "BALANCED",
                "predicted_policy_profile": "URGENT_RESPONSE",
                "gold_risk_level": 1,
                "predicted_risk_level": 3,
                "gold_deadline_range": None,
                "predicted_response_deadline": None,
                "deadline_acceptable": True,
                "gold_priority_targets": [],
                "predicted_priority_targets": ["W1"],
            },
            {
                "case_id": "B",
                "pair_id": "P1",
                "event_type": "VEHICLE_BREAKDOWN",
                "contract_success": True,
                "error_type": None,
                "policy_correct": False,
                "gold_policy_profile": "MINIMAL_RESCHEDULE",
                "predicted_policy_profile": "BALANCED",
                "gold_risk_level": 3,
                "predicted_risk_level": 1,
                "gold_deadline_range": [18, 22],
                "predicted_response_deadline": None,
                "deadline_acceptable": False,
                "gold_priority_targets": ["W2"],
                "predicted_priority_targets": [],
            },
        ],
    }


def _gold_records() -> dict[str, dict[str, object]]:
    return {
        "A": {
            "case_id": "A",
            "event": {"description": "语境 A"},
            "annotation": {"review_status": "approved"},
        },
        "B": {
            "case_id": "B",
            "event": {"description": "语境 B"},
            "annotation": {"review_status": "approved"},
        },
    }


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
