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
    print(f"Cases: {summary.total_cases}")
    print(
        "Valid controls accepted: "
        f"{summary.correctly_accepted_valid}/{summary.valid_cases}"
    )
    print(
        "Adversarial plans rejected: "
        f"{summary.correctly_rejected_invalid}/{summary.adversarial_cases}"
    )
    print(f"Detection rate: {summary.invalid_detection_rate:.2%}")
    print(f"Valid acceptance rate: {summary.valid_acceptance_rate:.2%}")
    for result in results:
        detected = ",".join(result.detected_violation_types) or "-"
        print(
            f"{result.case_id}: expected={result.expected_valid} | "
            f"actual={result.actual_valid} | violations={detected}"
        )
    return 0 if all(result.passed_expectation for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
