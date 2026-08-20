"""Explicit opt-in DeepSeek end-to-end CityClean closed-loop smoke test."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from cityclean_agent.agent.deepseek_event_agent import DeepSeekEventAgent, DeepSeekEventAgentError
from cityclean_agent.live_e2e import (
    live_e2e_cases,
    run_live_e2e_case,
    write_live_e2e_results,
)
from cityclean_agent.presentation import (
    POLICY_PROFILE_LABELS,
    STATUS_LABELS,
    labeled,
    risk_label,
)


def main() -> int:
    """Run exactly one real governance call per fixed closed-loop smoke case."""

    load_dotenv()
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY 未配置。", file=sys.stderr)
        return 1

    agent = DeepSeekEventAgent()
    results = tuple(run_live_e2e_case(agent, case) for case in live_e2e_cases())
    write_live_e2e_results(Path("deepseek_e2e_smoke_results.json"), results)
    for result in results:
        decision = result.policy_decision or {}
        target = result.target_task_outcome or {}
        print(
            f"{result.case_id}：闭环={'成功' if result.success else '失败'} | "
            f"工作流={labeled(result.workflow_status, STATUS_LABELS) if result.workflow_status else '无'} | "
            f"独立验证={'通过' if result.verification_valid else '失败'} | "
            f"治理策略={labeled(decision.get('policy_profile'), POLICY_PROFILE_LABELS) if decision.get('policy_profile') else '无'} | "
            f"风险等级={risk_label(decision['risk_level']) if decision.get('risk_level') is not None else '无'} | "
            "治理响应时限="
            f"{decision.get('response_deadline') if decision.get('response_deadline') is not None else '无'} | "
            f"目标任务={labeled(target.get('status'), STATUS_LABELS) if target.get('status') else '无'} | "
            "响应时间="
            f"{target.get('response_time') if target.get('response_time') is not None else '无'}"
        )
    return 0 if all(result.success for result in results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DeepSeekEventAgentError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
