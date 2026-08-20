"""CLI entry point for the fixed deterministic verifier adversarial evaluation."""

from __future__ import annotations

from pathlib import Path

from cityclean_agent.verifier.evaluation import (
    evaluate_verifier_suite,
    summarize_verifier_evaluation,
    write_verifier_evaluation_results,
)


def main() -> int:
    """Evaluate fixed plans directly with PlanVerifier and print a compact report."""

    results = evaluate_verifier_suite()
    summary = summarize_verifier_evaluation(results)
    write_verifier_evaluation_results(Path("verifier_adversarial_results.json"), results)
    print(f"评测样例数：{summary.total_cases}")
    print(
        "合法对照接受数："
        f"{summary.correctly_accepted_valid}/{summary.valid_cases}"
    )
    print(
        "对抗非法方案拒绝数："
        f"{summary.correctly_rejected_invalid}/{summary.adversarial_cases}"
    )
    print(f"非法方案检测率：{summary.invalid_detection_rate:.2%}")
    print(f"合法方案接受率：{summary.valid_acceptance_rate:.2%}")
    for result in results:
        detected = ",".join(result.detected_violation_types) or "-"
        print(
            f"{result.case_id}：期望合法={result.expected_valid} | "
            f"实际合法={result.actual_valid} | 违规类型={detected}"
        )
    return 0 if all(result.passed_expectation for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
