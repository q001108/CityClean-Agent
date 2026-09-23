"""Explicit opt-in capture of one real v0.2 DeepSeek policy trajectory."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from cityclean_agent.agent.deepseek_event_agent import DEFAULT_DEEPSEEK_MODEL, DeepSeekEventAgent
from cityclean_agent.complaint_intake import (
    ComplaintMessage,
    ComplaintRole,
    MessageSource,
    urgent_timing_tradeoff_resolver,
)
from cityclean_agent.live_e2e import live_e2e_cases, run_live_e2e_case
from cityclean_agent.trace_provenance import TraceProvenance, TraceSource
from cityclean_agent.v2_experience import write_v2_fixture
from cityclean_agent.v2_trace import TRACE_SCHEMA_VERSION, TraceCityEvent, trace_input_hash


COMPLAINT = "大型活动刚结束，出口处人流密集，需要尽快完成临时清运任务，以保障疏散通行和环境卫生。"


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture one opt-in v0.2 real policy trace.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--fixture-output",
        type=Path,
        default=Path("knowledge_base/demo/fixtures/complaint_urgent_v2.json"),
        help="offline fixture updated only after a successful capture",
    )
    args = parser.parse_args()
    case = next(case for case in live_e2e_cases() if case.case_id == "urgent_timing_tradeoff_live")
    message = ComplaintMessage("complaint-urgent-001", ComplaintRole.USER, COMPLAINT, 0, MessageSource.USER_AUTHORED)
    session = urgent_timing_tradeoff_resolver(case.event).intake(message)
    if session.resolved_event is None:
        raise RuntimeError("selected complaint did not resolve")
    result = run_live_e2e_case(DeepSeekEventAgent(), case)
    if not result.success or result.policy_decision is None:
        print(result.error or "real v0.2 policy trace capture failed")
        return 1
    city_event = TraceCityEvent(
        event_id=session.resolved_event.event_id,
        event_type=session.resolved_event.event_type,
        timestamp=session.resolved_event.timestamp,
        location=session.resolved_event.location,
        affected_entities=tuple(session.resolved_event.affected_entities),
        severity=session.resolved_event.severity,
        deadline=session.resolved_event.deadline,
        description=session.resolved_event.description,
    )
    captured_at = datetime.now(UTC).isoformat()
    provenance = TraceProvenance(
        trace_id=f"recorded-{case.case_id}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        trace_source=TraceSource.RECORDED_REAL_API,
        model_id=DEFAULT_DEEPSEEK_MODEL,
        captured_at=captured_at,
        scenario_id=case.case_id,
        dataset_version="v0.2",
        seed=0,
        complaint_contract_version="2.0",
        policy_contract_version="1.0",
        frontend_contract_version="2.0",
        input_hash=trace_input_hash(COMPLAINT, city_event),
        success=True,
        error_type=None,
    )
    payload = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "provenance": provenance.model_dump(mode="json"),
        "complaint": {"content": COMPLAINT, "source": MessageSource.USER_AUTHORED.value},
        "city_event": city_event.model_dump(mode="json"),
        "policy_decision": result.policy_decision,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_v2_fixture(args.fixture_output, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
