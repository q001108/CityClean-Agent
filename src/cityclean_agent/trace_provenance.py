"""Validation for the deliberately small v0.2 trace provenance contract."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TraceSource(str, Enum):
    RECORDED_REAL_API = "RECORDED_REAL_API"
    LIVE_API = "LIVE_API"
    DETERMINISTIC = "DETERMINISTIC"


class TraceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str = Field(min_length=1)
    trace_source: TraceSource
    model_id: str | None = None
    captured_at: str
    scenario_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    seed: int
    complaint_contract_version: str = Field(min_length=1)
    policy_contract_version: str = Field(min_length=1)
    frontend_contract_version: str = Field(min_length=1)
    input_hash: str = Field(min_length=16)
    success: bool
    error_type: str | None = None

    @model_validator(mode="after")
    def _validate_source_fields(self) -> "TraceProvenance":
        if self.trace_source is TraceSource.DETERMINISTIC and self.model_id is not None:
            raise ValueError("deterministic traces must not claim a model_id")
        if self.trace_source is not TraceSource.DETERMINISTIC and not self.model_id:
            raise ValueError("API traces require the actually invoked model_id")
        if self.success and self.error_type is not None:
            raise ValueError("successful traces must not have an error_type")
        if not self.success and not self.error_type:
            raise ValueError("failed traces require an error_type")
        if self.trace_source is not TraceSource.DETERMINISTIC:
            try:
                captured_at = datetime.fromisoformat(self.captured_at)
            except ValueError as exc:
                raise ValueError("API traces require an ISO-8601 captured_at") from exc
            if captured_at.tzinfo is None:
                raise ValueError("API traces require a timezone-aware captured_at")
        if not re.fullmatch(r"[0-9a-f]{64}", self.input_hash):
            raise ValueError("input_hash must be a SHA-256 hex digest")
        return self


def deterministic_provenance(*, scenario_id: str, input_hash: str) -> TraceProvenance:
    return TraceProvenance(
        trace_id=f"deterministic-{scenario_id}",
        trace_source=TraceSource.DETERMINISTIC,
        model_id=None,
        captured_at="offline-fixture",
        scenario_id=scenario_id,
        dataset_version="v0.2-offline-fixture",
        seed=0,
        complaint_contract_version="2.0",
        policy_contract_version="1.0",
        frontend_contract_version="2.0",
        input_hash=input_hash,
        success=True,
    )
