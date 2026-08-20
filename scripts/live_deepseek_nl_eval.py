"""Explicit opt-in natural-language governance evaluation using DeepSeek."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from cityclean_agent.agent.deepseek_event_agent import DeepSeekEventAgent, DeepSeekEventAgentError
from cityclean_agent.benchmark.natural_language_evaluation import (
    evaluation_summary,
    run_natural_language_evaluation,
    write_natural_language_evaluation_results,
)


def main() -> int:
    """Run the fixed live cases once and persist only final contract results."""

    load_dotenv()
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY is not configured.", file=sys.stderr)
        return 1

    results = run_natural_language_evaluation(DeepSeekEventAgent())
    summary = evaluation_summary(results)
    write_natural_language_evaluation_results(
        Path("deepseek_nl_eval_results.json"), results
    )
    print(f"Cases: {summary['total_cases']}")
    print(f"Success: {summary['successful_cases']}")
    print(f"Contract success: {summary['contract_success_rate']:.2%}")
    for result in results:
        print(
            f"{result.case_id}: {result.event_type} | "
            f"profile={result.policy_profile} | risk={result.risk_level} | "
            f"deadline={result.response_deadline}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DeepSeekEventAgentError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
