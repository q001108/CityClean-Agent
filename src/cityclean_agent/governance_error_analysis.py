"""Deterministic post-hoc analysis of frozen Governance Gold evaluation results."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVALUATION_RESULTS_PATH = (
    _PROJECT_ROOT / "artifacts" / "evaluations" / "deepseek_governance_gold_results.json"
)
DEFAULT_GOLD_JSON_PATH = (
    _PROJECT_ROOT / "knowledge_base" / "gold" / "cityclean_governance_gold_v0.1.json"
)
DEFAULT_GOLD_JSONL_PATH = (
    _PROJECT_ROOT / "knowledge_base" / "gold" / "cityclean_governance_gold_v0.1.jsonl"
)
DEFAULT_REPORT_PATH = (
    _PROJECT_ROOT / "knowledge_base" / "reports" / "governance_error_analysis_v0.1.md"
)


class GovernanceAnalysisError(ValueError):
    """Raised when an evaluation result cannot be analyzed against frozen Gold data."""


def load_evaluation_results(path: Path = DEFAULT_EVALUATION_RESULTS_PATH) -> dict[str, Any]:
    """Load generated evaluation output without changing it."""

    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict) or not isinstance(result.get("case_results"), list):
        raise GovernanceAnalysisError("evaluation result must contain case_results")
    return result


def load_approved_gold_records(
    json_path: Path = DEFAULT_GOLD_JSON_PATH,
    jsonl_path: Path = DEFAULT_GOLD_JSONL_PATH,
) -> dict[str, dict[str, Any]]:
    """Load and cross-check the two frozen Gold serializations for analysis only."""

    records = json.loads(json_path.read_text(encoding="utf-8"))
    jsonl_records = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if records != jsonl_records:
        raise GovernanceAnalysisError("Gold JSON and JSONL records differ")
    if not all(record.get("annotation", {}).get("review_status") == "approved" for record in records):
        raise GovernanceAnalysisError("Gold records must be approved")
    by_case_id = {record["case_id"]: record for record in records}
    if len(by_case_id) != len(records):
        raise GovernanceAnalysisError("Gold case_id values must be unique")
    return by_case_id


def analyze_governance_errors(
    evaluation: Mapping[str, Any],
    gold_by_case_id: Mapping[str, Mapping[str, Any]],
    *,
    model_name: str = "deepseek-v4-flash",
) -> dict[str, Any]:
    """Classify observed errors without changing labels, prompts, or predictions."""

    case_results = evaluation["case_results"]
    if len(case_results) != len(gold_by_case_id):
        raise GovernanceAnalysisError("evaluation and Gold case counts differ")
    if {result["case_id"] for result in case_results} != set(gold_by_case_id):
        raise GovernanceAnalysisError("evaluation cases do not match Gold cases")

    calculated_matrix = _calculate_confusion_matrix(
        case_results, evaluation["policy"]["confusion_matrix_order"]
    )
    if calculated_matrix != evaluation["policy"]["confusion_matrix"]:
        raise GovernanceAnalysisError("stored policy confusion matrix is inconsistent")
    pair_results = {
        item["pair_id"]: item for item in evaluation.get("pair_results", [])
    }
    policy_errors = _policy_errors(case_results, gold_by_case_id, pair_results)
    risk = _risk_analysis(case_results)
    deadline = _deadline_analysis(case_results)
    targets = _target_analysis(case_results)
    paired = _paired_analysis(evaluation, pair_results)
    failures = [
        {
            "case_id": result["case_id"],
            "event_type": result["event_type"],
            "error_type": result["error_type"],
        }
        for result in case_results
        if not result["contract_success"]
    ]
    return {
        "dataset_version": evaluation["dataset_version"],
        "model_name": model_name,
        "overview": {
            "total_cases": evaluation["total_cases"],
            "successful_cases": evaluation["successful_cases"],
            "failed_cases": evaluation["failed_cases"],
            "contract_success_rate": evaluation["contract_success_rate"],
        },
        "policy": {
            "accuracy": evaluation["policy"]["accuracy"],
            "macro_f1": evaluation["policy"]["macro_f1"],
            "confusion_matrix_order": evaluation["policy"]["confusion_matrix_order"],
            "confusion_matrix": calculated_matrix,
            "errors": policy_errors,
            "taxonomy_counts": dict(
                sorted(Counter(item["analysis_category"] for item in policy_errors).items())
            ),
        },
        "risk": {
            **evaluation["risk"],
            **risk,
        },
        "deadline": {
            **evaluation["deadline"],
            **deadline,
        },
        "targets": {
            **evaluation["targets"],
            **targets,
        },
        "paired_context": paired,
        "contract_failures": failures,
        "root_cause_summary": _root_cause_summary(
            policy_errors, risk, deadline, targets, failures
        ),
    }


def write_governance_error_analysis_report(path: Path, analysis: Mapping[str, Any]) -> None:
    """Write a Chinese paper-facing report derived from deterministic analysis data."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_governance_error_analysis_markdown(analysis), encoding="utf-8")


def render_governance_error_analysis_markdown(analysis: Mapping[str, Any]) -> str:
    """Render the fixed report structure without emitting model reasoning text."""

    overview = analysis["overview"]
    policy = analysis["policy"]
    risk = analysis["risk"]
    deadline = analysis["deadline"]
    targets = analysis["targets"]
    paired = analysis["paired_context"]
    lines = [
        "# Governance Error Analysis Report v0.1",
        "",
        "## 1. Evaluation Overview",
        "",
        f"- Gold cases：{overview['total_cases']}",
        f"- 模型：{analysis['model_name']}",
        f"- 成功调用：{overview['successful_cases']}",
        f"- Contract success rate：{overview['contract_success_rate']:.2%}",
        "",
        "本报告仅解释冻结评测结果；不包含 Prompt 调整、标签修改或系统修复建议。",
        "",
        "## 2. Policy Classification Error Analysis",
        "",
        f"- Accuracy：{policy['accuracy']:.2%}",
        f"- Macro-F1：{policy['macro_f1']:.4f}",
        "",
        "### Confusion Matrix",
        "",
        "行=Gold，列=Predicted。",
        "",
        "| Gold \\ Pred | " + " | ".join(policy["confusion_matrix_order"]) + " |",
        "|---|" + "---|" * len(policy["confusion_matrix_order"]),
    ]
    lines.extend(
        "| " + profile + " | " + " | ".join(map(str, row)) + " |"
        for profile, row in zip(policy["confusion_matrix_order"], policy["confusion_matrix"])
    )
    lines.extend(
        [
            "",
            "## 3. Policy Error Taxonomy",
            "",
            "| 分类 | 数量 |",
            "|---|---:|",
        ]
    )
    lines.extend(
        f"| {category} | {count} |"
        for category, count in policy["taxonomy_counts"].items()
    )
    lines.extend(
        [
            "",
            "| Case | Event | Gold | Predicted | Risk Gold/Pred | 归因 | 简短解释 |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    lines.extend(
        "| {case_id} | {event_type} | {gold_policy} | {predicted_policy} | "
        "{gold_risk}/{predicted_risk} | {analysis_category} | {explanation} |".format(
            **item
        )
        for item in policy["errors"]
    )
    lines.extend(
        [
            "",
            "## 4. Risk Error Analysis",
            "",
            f"- Exact Accuracy：{risk['exact_accuracy']:.2%}",
            f"- MAE：{risk['mae']:.4f}",
            f"- ±1 Accuracy：{risk['within_one_accuracy']:.2%}",
            f"- Under-estimation：{risk['under_estimation_count']}，"
            f"按事件类型：{_format_counts(risk['under_estimation_event_types'])}",
            f"- Over-estimation：{risk['over_estimation_count']}，"
            f"按事件类型：{_format_counts(risk['over_estimation_event_types'])}",
            "",
            "风险偏差最大的案例（绝对偏差 ≥2）：",
            "",
            "| Case | Event | Gold | Predicted | Absolute Error |",
            "|---|---|---:|---:|---:|",
        ]
    )
    lines.extend(
        "| {case_id} | {event_type} | {gold_risk} | {predicted_risk} | {abs_error} |".format(
            **item
        )
        for item in risk["largest_error_cases"]
    )
    lines.extend(
        [
            "",
            "## 5. Deadline Error Analysis",
            "",
            "治理响应时限是治理意图指标，不等价于 OR-Tools 调度硬约束。",
            "",
            f"- Acceptable Accuracy：{deadline['acceptable_accuracy']:.2%}",
            f"- Reference MAE：{deadline['reference_mae']:.4f}",
            f"- Too aggressive：{deadline['category_counts'].get('Too aggressive', 0)}",
            f"- Too relaxed：{deadline['category_counts'].get('Too relaxed', 0)}",
            f"- Missing deadline：{deadline['category_counts'].get('Missing deadline', 0)}",
            f"- Unexpected deadline：{deadline['category_counts'].get('Unexpected deadline', 0)}",
            "",
            "| Case | Event | Gold Range | Predicted | 分类 |",
            "|---|---|---|---|---|",
        ]
    )
    lines.extend(
        "| {case_id} | {event_type} | {gold_deadline_range} | "
        "{predicted_deadline} | {category} |".format(**item)
        for item in deadline["misses"]
    )
    lines.extend(
        [
            "",
            "## 6. Priority Target Analysis",
            "",
            f"- Precision：{targets['precision']:.2%}",
            f"- Recall：{targets['recall']:.2%}",
            f"- F1：{targets['f1']:.4f}",
            f"- Exact Set Accuracy：{targets['exact_set_accuracy']:.2%}",
            f"- False positives：{_format_counts(targets['false_positive_targets'])}",
            f"- False negatives：{_format_counts(targets['false_negative_targets'])}",
            "",
            "## 7. Paired Context Analysis",
            "",
            f"- Total pairs：{paired['total_pairs']}",
            f"- Both-success pairs：{paired['both_success_pairs']}",
            f"- Gold profile changed pairs：{paired['gold_profile_changed_pairs']}",
            f"- Predicted profile changed pairs：{paired['predicted_profile_changed_pairs']}",
            f"- Correct context adaptation：{paired['correct_profile_changed_pairs']}",
            f"- Paired profile accuracy：{paired['paired_profile_accuracy']:.2%}",
            "",
            f"描述变化在 {paired['gold_profile_changed_pairs']} 个可评 pair 中要求策略变化，"
            f"但仅 {paired['correct_profile_changed_pairs']} 个 pair 同时匹配两端 Gold profile，"
            "表明当前模型对上下文造成的治理策略切换利用不足。",
            "",
            "## 8. Root Cause Classification",
            "",
            "| 问题 | 数量 | 归因 |",
            "|---|---:|---|",
        ]
    )
    lines.extend(
        f"| {item['problem']} | {item['count']} | {item['root_cause']} |"
        for item in analysis["root_cause_summary"]
    )
    if analysis["contract_failures"]:
        lines.extend(["", "合同失败案例：", ""])
        lines.extend(
            f"- `{item['case_id']}`：{item['error_type']}"
            for item in analysis["contract_failures"]
        )
    lines.extend(
        [
            "",
            "## 分析边界",
            "",
            "本报告是对一次冻结 Gold 评测的测量性归因，不构成模型推理过程，也不提出自动修复。",
        ]
    )
    return "\n".join(lines) + "\n"


def _policy_errors(
    results: Iterable[Mapping[str, Any]],
    gold_by_case_id: Mapping[str, Mapping[str, Any]],
    pair_results: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    errors = []
    for result in results:
        if not result["contract_success"] or result["policy_correct"]:
            continue
        gold = gold_by_case_id[result["case_id"]]
        category, explanation = _policy_error_category(result, pair_results.get(result["pair_id"]))
        errors.append(
            {
                "case_id": result["case_id"],
                "event_type": result["event_type"],
                "gold_policy": result["gold_policy_profile"],
                "predicted_policy": result["predicted_policy_profile"],
                "gold_risk": result["gold_risk_level"],
                "predicted_risk": result["predicted_risk_level"],
                "analysis_category": category,
                "explanation": explanation,
                "description_present": bool(gold["event"].get("description")),
            }
        )
    return errors


def _policy_error_category(
    result: Mapping[str, Any], pair_result: Mapping[str, Any] | None
) -> tuple[str, str]:
    gold = result["gold_policy_profile"]
    predicted = result["predicted_policy_profile"]
    if gold == "BALANCED" and predicted == "URGENT_RESPONSE":
        return "A. Risk escalation bias", "将均衡治理升级为紧急响应，体现治理等级上调。"
    if gold == "MINIMAL_RESCHEDULE" and predicted == "BALANCED":
        return "B. Conservative delay handling", "未体现需要恢复既有调度的最小扰动重调度。"
    if {gold, predicted} == {"OVERFLOW_CONTROL", "URGENT_RESPONSE"}:
        return "C. Overflow / urgent confusion", "在满溢治理与紧急响应之间发生治理语义混淆。"
    if pair_result and pair_result.get("gold_profile_changed"):
        return "D. Context under-utilization", "未充分体现描述变化对 Gold 治理策略的影响。"
    return "D. Context under-utilization", "描述中的场景语境未被充分映射为 Gold 治理策略。"


def _risk_analysis(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    successful = [result for result in results if result["contract_success"]]
    under = [result for result in successful if result["predicted_risk_level"] < result["gold_risk_level"]]
    over = [result for result in successful if result["predicted_risk_level"] > result["gold_risk_level"]]
    largest = [
        {
            "case_id": result["case_id"],
            "event_type": result["event_type"],
            "gold_risk": result["gold_risk_level"],
            "predicted_risk": result["predicted_risk_level"],
                "abs_error": abs(
                    result["predicted_risk_level"] - result["gold_risk_level"]
                ),
            }
            for result in successful
        if abs(result["predicted_risk_level"] - result["gold_risk_level"]) >= 2
    ]
    return {
        "under_estimation_count": len(under),
        "over_estimation_count": len(over),
        "under_estimation_event_types": _event_counts(under),
        "over_estimation_event_types": _event_counts(over),
        "largest_error_cases": sorted(largest, key=lambda item: (-item["abs_error"], item["case_id"])),
    }


def _deadline_analysis(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    misses = []
    for result in results:
        if not result["contract_success"] or result["deadline_acceptable"]:
            continue
        category = _deadline_error_category(result)
        deadline_range = result["gold_deadline_range"]
        misses.append(
            {
                "case_id": result["case_id"],
                "event_type": result["event_type"],
                "gold_deadline_range": deadline_range if deadline_range is not None else "None",
                "predicted_deadline": _format_optional_number(
                    result["predicted_response_deadline"]
                ),
                "category": category,
            }
        )
    return {
        "misses": misses,
        "category_counts": dict(sorted(Counter(item["category"] for item in misses).items())),
        "event_type_counts": {
            category: _event_counts(
                [item for item in misses if item["category"] == category]
            )
            for category in sorted({item["category"] for item in misses})
        },
    }


def _deadline_error_category(result: Mapping[str, Any]) -> str:
    predicted = result["predicted_response_deadline"]
    deadline_range = result["gold_deadline_range"]
    if deadline_range is None:
        return "Unexpected deadline"
    if predicted is None:
        return "Missing deadline"
    if predicted < deadline_range[0]:
        return "Too aggressive"
    return "Too relaxed"


def _target_analysis(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    false_positive = Counter()
    false_negative = Counter()
    for result in results:
        if not result["contract_success"]:
            continue
        gold_targets = set(result["gold_priority_targets"])
        predicted_targets = set(result["predicted_priority_targets"])
        false_positive.update(predicted_targets.difference(gold_targets))
        false_negative.update(gold_targets.difference(predicted_targets))
    return {
        "false_positive_targets": dict(sorted(false_positive.items())),
        "false_negative_targets": dict(sorted(false_negative.items())),
    }


def _paired_analysis(
    evaluation: Mapping[str, Any], pair_results: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    evaluated_pairs = [item for item in pair_results.values() if item["both_contract_success"]]
    return {
        "total_pairs": evaluation["pairs"]["total_pairs"],
        "both_success_pairs": evaluation["pairs"]["both_success_pairs"],
        "gold_profile_changed_pairs": evaluation["pairs"]["gold_profile_changed_pairs"],
        "predicted_profile_changed_pairs": sum(
            item["predicted_profile_changed"] is True for item in evaluated_pairs
        ),
        "correct_profile_changed_pairs": evaluation["pairs"]["correct_profile_changed_pairs"],
        "paired_profile_accuracy": evaluation["pairs"]["paired_profile_accuracy"],
    }


def _root_cause_summary(
    policy_errors: list[Mapping[str, Any]],
    risk: Mapping[str, Any],
    deadline: Mapping[str, Any],
    targets: Mapping[str, Any],
    failures: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    context_errors = sum(
        item["analysis_category"] == "D. Context under-utilization"
        for item in policy_errors
    )
    target_errors = sum(targets["false_positive_targets"].values()) + sum(
        targets["false_negative_targets"].values()
    )
    return [
        {"problem": "Policy 误分类", "count": len(policy_errors), "root_cause": "B. 模型治理偏好"},
        {
            "problem": "Risk 偏差",
            "count": risk["under_estimation_count"] + risk["over_estimation_count"],
            "root_cause": "D. 数值预测困难",
        },
        {
            "problem": "Deadline 误差",
            "count": len(deadline["misses"]),
            "root_cause": "D. 数值预测困难",
        },
        {"problem": "Priority Target 误差", "count": target_errors, "root_cause": "A. 输入信息不足"},
        {"problem": "Context 理解不足", "count": context_errors, "root_cause": "B. 模型治理偏好"},
        {"problem": "Provider failure", "count": len(failures), "root_cause": "E. Provider 稳定性"},
    ]


def _event_counts(items: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(item["event_type"] for item in items).items()))


def _calculate_confusion_matrix(
    results: Iterable[Mapping[str, Any]], order: list[str]
) -> list[list[int]]:
    indexes = {profile: index for index, profile in enumerate(order)}
    matrix = [[0 for _ in order] for _ in order]
    for result in results:
        if not result["contract_success"]:
            continue
        matrix[indexes[result["gold_policy_profile"]]][
            indexes[result["predicted_policy_profile"]]
        ] += 1
    return matrix


def _format_counts(counts: Mapping[str, int]) -> str:
    return "无" if not counts else "，".join(f"{key}={value}" for key, value in counts.items())


def _format_optional_number(value: int | None) -> int | str:
    return value if value is not None else "无"
