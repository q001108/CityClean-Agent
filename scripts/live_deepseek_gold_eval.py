"""Explicit one-call-per-case evaluation of the approved Governance Gold Set."""

from __future__ import annotations

import sys
from pathlib import Path

from cityclean_agent.agent.deepseek_event_agent import (
    DeepSeekEventAgent,
    DeepSeekEventAgentError,
)
from cityclean_agent.governance_gold_evaluation import (
    DEFAULT_GOLD_JSON_PATH,
    DEFAULT_GOLD_JSONL_PATH,
    GoldIntegrityError,
    POLICY_PROFILE_ORDER,
    evaluate_governance_gold,
    load_governance_gold_cases,
    validate_governance_gold_integrity,
    write_governance_gold_evaluation_results,
)
from cityclean_agent.presentation import POLICY_PROFILE_LABELS, labeled


def main() -> int:
    """Measure the frozen Gold Set once without adapting any system component."""

    integrity = validate_governance_gold_integrity(
        DEFAULT_GOLD_JSON_PATH, DEFAULT_GOLD_JSONL_PATH
    )
    cases = load_governance_gold_cases(DEFAULT_GOLD_JSON_PATH)
    summary = evaluate_governance_gold(DeepSeekEventAgent(), cases)
    output_path = Path("artifacts/evaluations/deepseek_governance_gold_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_governance_gold_evaluation_results(output_path, summary)
    _print_summary(summary)
    return 0


def _print_summary(summary) -> None:
    print("CityClean-Agent 治理 Gold 评测")
    print(f"数据集：{summary.dataset_version}，{summary.total_cases} 个案例")
    print(
        "结构化合同："
        f"成功 {summary.successful_cases}/{summary.total_cases}，"
        f"成功率 {summary.contract_success_rate:.2%}"
    )
    print(
        f"治理策略：Accuracy {summary.policy_accuracy:.2%}，"
        f"Macro-F1 {summary.policy_macro_f1:.4f}"
    )
    print("策略混淆矩阵（行=Gold，列=预测）：")
    print("Gold \\ Pred | " + " | ".join(POLICY_PROFILE_ORDER))
    for profile, row in zip(POLICY_PROFILE_ORDER, summary.policy_confusion_matrix):
        print(f"{labeled(profile, POLICY_PROFILE_LABELS)} | " + " | ".join(map(str, row)))
    print(
        f"风险：Exact {summary.risk_exact_accuracy:.2%}，MAE {summary.risk_mae:.4f}，"
        f"±1 {summary.risk_within_one_accuracy:.2%}，"
        f"可接受范围 {summary.risk_acceptable_range_accuracy:.2%}"
    )
    print(
        "治理响应时限："
        f"可接受率 {summary.deadline_acceptable_accuracy:.2%}，"
        f"Reference MAE {summary.deadline_reference_mae:.4f}，"
        f"Gold None={summary.deadline_none_gold_cases}，"
        f"预测 None={summary.deadline_predicted_none_cases}"
    )
    print(
        f"优先目标：Precision {summary.target_precision:.2%}，"
        f"Recall {summary.target_recall:.2%}，F1 {summary.target_f1:.4f}，"
        f"Exact Set {summary.target_exact_set_accuracy:.2%}"
    )
    print(
        "Paired Context："
        f"总计 {summary.total_pairs}，双成功 {summary.both_success_pairs}，"
        f"Gold 策略变化 {summary.gold_profile_changed_pairs}，"
        f"正确策略对 {summary.correct_profile_changed_pairs}，"
        f"准确率 {summary.paired_profile_accuracy:.2%}"
    )
    _print_case_outcomes(summary)


def _print_case_outcomes(summary) -> None:
    errors = [result for result in summary.case_results if not result.contract_success]
    policy_errors = [
        result
        for result in summary.case_results
        if result.contract_success and not result.policy_correct
    ]
    if errors:
        print("合同失败案例：")
        for result in errors:
            print(f"  {result.case_id}：{result.error_type}")
    if policy_errors:
        print("策略分类错误案例：")
        for result in policy_errors:
            print(
                f"  {result.case_id}："
                f"Gold={result.gold_policy_profile}，Pred={result.predicted_policy_profile}，"
                f"Risk={result.gold_risk_level}/{result.predicted_risk_level}，"
                f"Deadline={result.gold_deadline_reference}/{result.predicted_response_deadline}"
            )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GoldIntegrityError, DeepSeekEventAgentError) as exc:
        print(f"Gold 评测未执行：{exc}", file=sys.stderr)
        raise SystemExit(1)
