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


def main() -> int:
    """Run exactly one real governance call per fixed closed-loop smoke case."""

    load_dotenv()
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY is not configured.", file=sys.stderr)
        return 1

    agent = DeepSeekEventAgent()
    results = tuple(run_live_e2e_case(agent, case) for case in live_e2e_cases())
    write_live_e2e_results(Path("deepseek_e2e_smoke_results.json"), results)
    for result in results:
        decision = result.policy_decision or {}
        target = result.target_task_outcome or {}
        print(
            f"{result.case_id}: success={result.success} | "
            f"workflow={result.workflow_status} | verifier={result.verification_valid} | "
            f"profile={decision.get('policy_profile')} | risk={decision.get('risk_level')} | "
            f"deadline={decision.get('response_deadline')} | "
            f"target={target.get('status')} | response_time={target.get('response_time')}"
        )
    return 0 if all(result.success for result in results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DeepSeekEventAgentError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
