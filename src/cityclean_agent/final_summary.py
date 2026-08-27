"""Validated final narrative summaries and a safe deterministic fallback."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FinalNarrativeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    headline: str = Field(min_length=1, max_length=160)
    incident_summary: str = Field(min_length=1)
    governance_summary: str = Field(min_length=1)
    dispatch_summary: str = Field(min_length=1)
    verification_summary: str = Field(min_length=1)
    outcome_summary: str = Field(min_length=1)
    citizen_reply: str = Field(min_length=1)
    fact_refs: tuple[str, ...] = Field(min_length=1)


def validate_final_summary(
    summary: FinalNarrativeSummary, *, allowed_fact_refs: set[str], verifier_passed: bool,
    optimizer_status: str,
) -> FinalNarrativeSummary:
    """Reject unknown fact references and unsupported positive claims."""

    if not set(summary.fact_refs).issubset(allowed_fact_refs):
        raise ValueError("final summary references facts outside the whitelist")
    combined = " ".join(summary.model_dump(exclude={"fact_refs"}).values()).upper()
    if (not verifier_passed or optimizer_status == "INFEASIBLE") and "验证通过" in combined:
        raise ValueError("summary must not claim verification passed")
    return summary


def deterministic_final_summary(
    *, complaint_summary: str, policy_profile: str | None, optimizer_status: str,
    verifier_passed: bool, completed: bool,
) -> FinalNarrativeSummary:
    outcome = "任务已完成" if completed else "任务尚未全部完成"
    verification = "Verifier 独立验证通过。" if verifier_passed else "Verifier 未通过或未执行。"
    policy = policy_profile or "未提供真实模型策略"
    return FinalNarrativeSummary(
        headline="确定性结果说明（非模型回复）",
        incident_summary=complaint_summary,
        governance_summary=f"治理策略：{policy}。",
        dispatch_summary=f"OR-Tools 状态：{optimizer_status}。",
        verification_summary=verification,
        outcome_summary=outcome,
        citizen_reply=f"已根据已验证的执行结果反馈：{outcome}。",
        fact_refs=("complaint", "policy", "optimizer", "verifier", "outcome"),
    )
