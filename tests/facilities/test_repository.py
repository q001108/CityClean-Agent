from pathlib import Path

import pytest

from cityclean_agent.facilities.models import FacilityCreate, FacilityType
from cityclean_agent.facilities.repository import (
    FacilityAlreadyExistsError,
    SqliteFacilityRepository,
)


def make_facility() -> FacilityCreate:
    return FacilityCreate(
        facility_id="XP-001",
        name="东方红大道收运点",
        facility_type=FacilityType.COLLECTION_POINT,
        address="浉河区东方红大道",
        longitude=114.0913,
        latitude=32.147,
        capacity=12,
    )


def test_facility_persists_across_repository_instances(tmp_path: Path) -> None:
    database_path = tmp_path / "facilities.db"
    repository = SqliteFacilityRepository(database_path)

    created = repository.create_facility(make_facility())
    reopened = SqliteFacilityRepository(database_path)

    assert created.facility_id == "XP-001"
    assert created.coordinate_system == "CGCS2000"
    assert reopened.list_facilities() == (created,)


def test_duplicate_facility_id_is_rejected(tmp_path: Path) -> None:
    repository = SqliteFacilityRepository(tmp_path / "facilities.db")
    repository.create_facility(make_facility())

    with pytest.raises(FacilityAlreadyExistsError, match="already exists"):
        repository.create_facility(make_facility())
