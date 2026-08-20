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
from cityclean_agent.presentation import (
    EVENT_TYPE_LABELS,
    POLICY_PROFILE_LABELS,
    labeled,
    risk_label,
)


def main() -> int:
    """Run the fixed live cases once and persist only final contract results."""

    load_dotenv()
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY 未配置。", file=sys.stderr)
        return 1

    results = run_natural_language_evaluation(DeepSeekEventAgent())
    summary = evaluation_summary(results)
    write_natural_language_evaluation_results(
        Path("deepseek_nl_eval_results.json"), results
    )
    print(f"评测样例数：{summary['total_cases']}")
    print(f"通过样例数：{summary['successful_cases']}")
    print(f"合同通过率：{summary['contract_success_rate']:.2%}")
    for result in results:
        print(
            f"{result.case_id}：{labeled(result.event_type, EVENT_TYPE_LABELS)} | "
            f"治理策略={labeled(result.policy_profile, POLICY_PROFILE_LABELS) if result.policy_profile else '无'} | "
            f"风险等级={risk_label(result.risk_level) if result.risk_level is not None else '无'} | "
            "治理响应时限="
            f"{result.response_deadline if result.response_deadline is not None else '无'}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DeepSeekEventAgentError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
