"""Read-only v2 frontend contract built from validated domain facts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cityclean_agent.complaint_intake import (
    ComplaintMessage,
    ComplaintRole,
    MessageSource,
    urgent_timing_tradeoff_resolver,
)
from cityclean_agent.final_summary import deterministic_final_summary
from cityclean_agent.live_e2e import live_e2e_cases
from cityclean_agent.trace_provenance import deterministic_provenance
from cityclean_agent.v2_contract import validate_v2_contract
from cityclean_agent.v2_trace import (
    RecordedV2Trace,
    SELECTED_CASE_ID,
    TraceCityEvent,
    load_recorded_v2_trace,
    run_fair_ablation,
    trace_input_hash,
)


EXPERIENCE_SCHEMA_VERSION = "2.0"
_COMPLAINT = "大型活动刚结束，出口处人流密集，需要尽快完成临时清运任务，以保障疏散通行和环境卫生。"


def build_v2_experience(
    recorded_trace_path: str | Path | None = None,
) -> dict[str, Any]:
    """Project either a validated real trace or the explicit offline fallback.

    No historical result is upgraded to real provenance implicitly.  Passing a
    path is an intentional developer operation and the trace is validated
    before its saved policy can reach the optimizer boundary.
    """

    case = next(case for case in live_e2e_cases() if case.case_id == SELECTED_CASE_ID)
    session = urgent_timing_tradeoff_resolver(case.event).intake(
        ComplaintMessage(
            message_id="complaint-urgent-001",
            role=ComplaintRole.USER,
            content=_COMPLAINT,
            created_at=0,
            source=MessageSource.USER_AUTHORED,
        )
    )
    if session.resolved_event is None:
        raise RuntimeError("selected complaint failed deterministic resolution")
    trace = load_recorded_v2_trace(recorded_trace_path) if recorded_trace_path else None
    if trace is not None:
        _validate_trace_matches_session(trace, session.resolved_event)
    comparison = run_fair_ablation(trace)
    full = comparison[0]
    selected_result = full if full["availability"] == "READY" else comparison[1]
    final_summary = deterministic_final_summary(
        complaint_summary=session.intake_result.complaint_summary or _COMPLAINT,
        policy_profile=(
            selected_result["policy_decision"]["policy_profile"]
            if selected_result["policy_decision"] else None
        ),
        optimizer_status=str(selected_result["optimizer_status"]),
        verifier_passed=bool(selected_result["verifier_passed"]),
        completed=bool(selected_result["completed"]),
    )
    provenance = trace.provenance if trace else deterministic_provenance(
        scenario_id=SELECTED_CASE_ID,
        input_hash=trace_input_hash(_COMPLAINT, _city_event_model(session.resolved_event)),
    )
    payload = {
        "schema_version": EXPERIENCE_SCHEMA_VERSION,
        "experience": {
            "experience_id": "v02-urgent-timing-offline" if trace is None else trace.provenance.trace_id,
            "title": "投诉闭环：活动出口临时清运",
            "scenario_id": SELECTED_CASE_ID,
            "selected_case": True,
            "mode": "FULL_LLM_POLICY_REPLAN",
            "availability": "READY" if trace else "PROVENANCE_REQUIRED",
            "selected_case_disclosure": "精选展示案例；全量冻结评测与不利结果见实验说明。",
        },
        "provenance": provenance.model_dump(mode="json"),
        "complaint_session": _session_payload(session),
        "city_event": _event_payload(session.resolved_event),
        "policy_decision": full["policy_decision"],
        "policy_notice": (
            "已加载真实 DeepSeek 冻结 PolicyDecision；离线回放不再访问 Provider。"
            if trace else "当前仓库的历史闭环结果缺少逐轨迹 provenance，未作为真实 DeepSeek 决策回放。"
        ),
        "execution_frames": _execution_frames(trace is not None),
        "final_metrics": selected_result["metrics"],
        "final_summary": {
            **final_summary.model_dump(mode="json"),
            "source": "DETERMINISTIC_TEMPLATE",
        },
        "ablation_comparison": comparison,
        "experiment_summary": {
            "gold_cases": 40,
            "successful_calls": 38,
            "contract_success_rate": 0.95,
            "policy_accuracy": 0.6053,
            "macro_f1": 0.5216,
            "paired_context_accuracy": 0.3125,
            "provider_failures": 2,
        },
    }
    return validate_v2_contract(payload)


def write_v2_fixture(
    path: str | Path, recorded_trace_path: str | Path | None = None
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            build_v2_experience(recorded_trace_path),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return destination


def _validate_trace_matches_session(trace: RecordedV2Trace, event: Any) -> None:
    expected = _city_event_model(event)
    if trace.city_event != expected:
        raise ValueError("recorded trace CityEvent does not match the selected scenario")
    if trace.complaint.content != _COMPLAINT:
        raise ValueError("recorded trace complaint does not match the selected scenario")


def _city_event_model(event: Any) -> TraceCityEvent:
    return TraceCityEvent(
        event_id=event.event_id,
        event_type=event.event_type,
        timestamp=event.timestamp,
        location=event.location,
        affected_entities=tuple(event.affected_entities),
        severity=event.severity,
        deadline=event.deadline,
        description=event.description,
    )


def _session_payload(session: Any) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "scenario_id": session.scenario_id,
        "messages": [
            {
                "message_id": message.message_id,
                "role": message.role.value,
                "content": message.content,
                "created_at": message.created_at,
                "source": message.source.value,
            }
            for message in session.messages
        ],
        "intake_result": {
            "status": session.intake_result.status.value,
            "complaint_summary": session.intake_result.complaint_summary,
            "candidate_event_type": (
                session.intake_result.candidate_event_type.value
                if session.intake_result.candidate_event_type else None
            ),
            "location_text": session.intake_result.location_text,
            "affected_entity_mentions": list(session.intake_result.affected_entity_mentions),
            "missing_fields": list(session.intake_result.missing_fields),
            "rejection_reason": session.intake_result.rejection_reason,
        },
        "clarification_prompt": session.clarification_prompt,
    }


def _event_payload(event: Any) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp,
        "location": event.location,
        "affected_entities": list(event.affected_entities),
        "severity": event.severity,
        "deadline": event.deadline,
        "description": event.description,
    }


def _execution_frames(has_full_trace: bool) -> list[dict[str, str]]:
    return [
        {"module": "投诉接入", "status": "SUCCESS"},
        {"module": "CityEvent", "status": "SUCCESS"},
        {"module": "DeepSeek 研判", "status": "SUCCESS" if has_full_trace else "NOT_REACHED"},
        {"module": "TaskBuilder", "status": "SUCCESS" if has_full_trace else "NOT_REACHED"},
        {"module": "OR-Tools", "status": "SUCCESS" if has_full_trace else "NOT_REACHED"},
        {"module": "Verifier", "status": "SUCCESS" if has_full_trace else "NOT_REACHED"},
        {"module": "CitySim", "status": "SUCCESS" if has_full_trace else "NOT_REACHED"},
        {"module": "最终总结", "status": "SUCCESS"},
    ]
