"""Generate the deterministic Governance Gold Error Analysis Report."""

from __future__ import annotations

from cityclean_agent.governance_error_analysis import (
    DEFAULT_EVALUATION_RESULTS_PATH,
    DEFAULT_GOLD_JSONL_PATH,
    DEFAULT_GOLD_JSON_PATH,
    DEFAULT_REPORT_PATH,
    GovernanceAnalysisError,
    analyze_governance_errors,
    load_approved_gold_records,
    load_evaluation_results,
    write_governance_error_analysis_report,
)


def main() -> int:
    """Read frozen inputs and render analysis without changing evaluation or Gold data."""

    evaluation = load_evaluation_results(DEFAULT_EVALUATION_RESULTS_PATH)
    gold = load_approved_gold_records(DEFAULT_GOLD_JSON_PATH, DEFAULT_GOLD_JSONL_PATH)
    analysis = analyze_governance_errors(evaluation, gold)
    write_governance_error_analysis_report(DEFAULT_REPORT_PATH, analysis)
    print(f"已生成治理误差分析报告：{DEFAULT_REPORT_PATH}")
    print(f"Policy 误分类：{len(analysis['policy']['errors'])}")
    print(f"Deadline 未命中：{len(analysis['deadline']['misses'])}")
    print(f"Provider failure：{len(analysis['contract_failures'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GovernanceAnalysisError, FileNotFoundError) as exc:
        print(f"无法生成治理误差分析报告：{exc}")
        raise SystemExit(1)
