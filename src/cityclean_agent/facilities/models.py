"""Validated records for manually maintained sanitation facilities."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FacilityType(str, Enum):
    COLLECTION_POINT = "COLLECTION_POINT"
    TRANSFER_STATION = "TRANSFER_STATION"
    DEPOT = "DEPOT"
    DISPOSAL_SITE = "DISPOSAL_SITE"


class FacilityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class FacilityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facility_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    facility_type: FacilityType
    address: str | None = Field(default=None, max_length=240)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    coordinate_system: Literal["CGCS2000"] = "CGCS2000"
    capacity: float | None = Field(default=None, gt=0)
    status: FacilityStatus = FacilityStatus.ACTIVE
    source: Literal["manual_map"] = "manual_map"

    @field_validator("facility_id", "name", "address")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class FacilityRecord(FacilityCreate):
    created_at: datetime
    updated_at: datetime
