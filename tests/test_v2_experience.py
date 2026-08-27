from __future__ import annotations

import json
from pathlib import Path

import pytest

from cityclean_agent.complaint_intake import (
    ComplaintMessage,
    ComplaintRole,
    MessageSource,
    urgent_timing_tradeoff_resolver,
)
from cityclean_agent.final_summary import (
    FinalNarrativeSummary,
    deterministic_final_summary,
    validate_final_summary,
)
from cityclean_agent.live_e2e import live_e2e_cases
from cityclean_agent.trace_provenance import TraceProvenance, TraceSource
from cityclean_agent.v2_experience import build_v2_experience, write_v2_fixture
from cityclean_agent.v2_contract import validate_v2_contract
from cityclean_agent.v2_trace import (
    TRACE_SCHEMA_VERSION,
    RecordedV2Trace,
    TraceCityEvent,
    run_fair_ablation,
    trace_input_hash,
)
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile


def _resolver():
    case = next(case for case in live_e2e_cases() if case.case_id == "urgent_timing_tradeoff_live")
    return urgent_timing_tradeoff_resolver(case.event)


def _message(content: str) -> ComplaintMessage:
    return ComplaintMessage("m1", ComplaintRole.USER, content, 0, MessageSource.USER_AUTHORED)


def test_selected_complaint_resolves_only_predeclared_aliases() -> None:
    session = _resolver().intake(_message("活动出口人流密集，请尽快清运垃圾。"))

    assert session.intake_result.status.value == "READY"
    assert session.resolved_event is not None
    assert session.resolved_event.affected_entities == ["WU"]
    assert len(session.messages) == 1


def test_unknown_location_requires_clarification_without_creating_event() -> None:
    session = _resolver().intake(_message("东门人流密集，请尽快清运。"))

    assert session.intake_result.status.value == "NEEDS_CLARIFICATION"
    assert session.resolved_event is None
    assert session.clarification_prompt is not None


def test_provenance_rejects_claimed_model_for_deterministic_trace() -> None:
    with pytest.raises(ValueError, match="deterministic"):
        TraceProvenance(
            trace_id="x", trace_source=TraceSource.DETERMINISTIC, model_id="deepseek-v4-flash",
            captured_at="x", scenario_id="x", dataset_version="x", seed=0,
            complaint_contract_version="2", policy_contract_version="1", frontend_contract_version="2",
            input_hash="0" * 16, success=True,
        )


def test_final_summary_rejects_unknown_fact_and_has_template_fallback() -> None:
    summary = deterministic_final_summary(
        complaint_summary="投诉", policy_profile="BALANCED", optimizer_status="FEASIBLE",
        verifier_passed=True, completed=True,
    )
    assert validate_final_summary(summary, allowed_fact_refs={"complaint", "policy", "optimizer", "verifier", "outcome"}, verifier_passed=True, optimizer_status="FEASIBLE") == summary
    invalid = FinalNarrativeSummary(**{**summary.model_dump(), "fact_refs": ("invented",)})
    with pytest.raises(ValueError, match="whitelist"):
        validate_final_summary(invalid, allowed_fact_refs=set(), verifier_passed=True, optimizer_status="FEASIBLE")


def test_v2_fixture_is_deterministic_and_does_not_mislabel_historical_decision(tmp_path) -> None:
    experience = build_v2_experience()

    assert json.loads(json.dumps(experience, ensure_ascii=False)) == experience
    assert experience["schema_version"] == "2.0"
    assert experience["experience"]["selected_case"] is True
    assert experience["provenance"]["trace_source"] == "DETERMINISTIC"
    assert experience["provenance"]["model_id"] is None
    full = experience["ablation_comparison"][0]
    assert full["mode"] == "FULL_LLM_POLICY_REPLAN"
    assert full["availability"] == "PROVENANCE_REQUIRED"
    output = write_v2_fixture(tmp_path / "v2.json")
    assert json.loads(output.read_text(encoding="utf-8")) == experience
    committed_fixture = Path("frontend/fixtures/complaint_urgent_v2.json")
    committed_payload = json.loads(committed_fixture.read_text(encoding="utf-8"))
    assert validate_v2_contract(committed_payload) == committed_payload
    if committed_payload["provenance"]["trace_source"] == "DETERMINISTIC":
        assert committed_payload == experience
    else:
        trace_path = Path("data/v02_urgent_timing_trace.json")
        assert trace_path.is_file()
        assert committed_payload == build_v2_experience(trace_path)


def _recorded_trace() -> RecordedV2Trace:
    case = next(case for case in live_e2e_cases() if case.case_id == "urgent_timing_tradeoff_live")
    event = TraceCityEvent(
        event_id=case.event.event_id,
        event_type=case.event.event_type,
        timestamp=case.event.timestamp,
        location=case.event.location,
        affected_entities=tuple(case.event.affected_entities),
        severity=case.event.severity,
        deadline=case.event.deadline,
        description=case.event.description,
    )
    complaint = "大型活动刚结束，出口处人流密集，需要尽快完成临时清运任务，以保障疏散通行和环境卫生。"
    return RecordedV2Trace(
        schema_version=TRACE_SCHEMA_VERSION,
        provenance=TraceProvenance(
            trace_id="recorded-test", trace_source=TraceSource.RECORDED_REAL_API,
            model_id="deepseek-v4-flash", captured_at="2026-08-26T00:00:00+00:00",
            scenario_id="urgent_timing_tradeoff_live", dataset_version="v0.2", seed=0,
            complaint_contract_version="2.0", policy_contract_version="1.0",
            frontend_contract_version="2.0", input_hash=trace_input_hash(complaint, event),
            success=True,
        ),
        complaint={"content": complaint, "source": "USER_AUTHORED"},
        city_event=event,
        policy_decision=PolicyDecision(
            event_type=case.event.event_type, risk_level=5,
            reasoning_summary="活动出口人流密集，需要优先完成临时清运。",
            response_deadline=15, priority_targets=("WU",),
            policy_profile=PolicyProfile.URGENT_RESPONSE,
            constraints=("优先保障出口通行。",),
        ),
    )


def test_recorded_real_policy_runs_full_mode_with_fair_shared_inputs(tmp_path: Path, monkeypatch) -> None:
    trace = _recorded_trace()

    monkeypatch.setattr(
        "socket.create_connection",
        lambda *args, **kwargs: pytest.fail("frozen Full replay must not access the network"),
    )

    comparison = run_fair_ablation(trace)

    assert [item["mode"] for item in comparison] == [
        "FULL_LLM_POLICY_REPLAN", "FIXED_BALANCED_REPLAN", "STATIC_NO_REPLAN"
    ]
    assert all(item["shared_inputs"] == comparison[0]["shared_inputs"] for item in comparison)
    assert comparison[0]["availability"] == "READY"
    assert comparison[0]["policy_decision"] == trace.policy_decision.model_dump(mode="json")
    assert comparison[0]["verifier_passed"] is True
    trace_path = tmp_path / "recorded.json"
    trace_path.write_text(trace.model_dump_json(), encoding="utf-8")
    experience = build_v2_experience(trace_path)
    assert experience["experience"]["availability"] == "READY"
    assert experience["provenance"]["trace_source"] == "RECORDED_REAL_API"
    assert experience["policy_decision"] == trace.policy_decision.model_dump(mode="json")
