"""Small SQLite repository for a personal-project facility registry."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from cityclean_agent.facilities.models import FacilityCreate, FacilityRecord


class FacilityAlreadyExistsError(ValueError):
    """Raised when a stable facility identifier is already registered."""


class SqliteFacilityRepository:
    """Persist validated facilities without introducing an ORM dependency."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def list_facilities(self) -> Sequence[FacilityRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM facilities ORDER BY created_at, facility_id"
            ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def create_facility(self, facility: FacilityCreate) -> FacilityRecord:
        now = datetime.now(timezone.utc)
        values = facility.model_dump(mode="json")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO facilities (
                        facility_id, name, facility_type, address,
                        longitude, latitude, coordinate_system, capacity,
                        status, source, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values["facility_id"],
                        values["name"],
                        values["facility_type"],
                        values["address"],
                        values["longitude"],
                        values["latitude"],
                        values["coordinate_system"],
                        values["capacity"],
                        values["status"],
                        values["source"],
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise FacilityAlreadyExistsError(
                f"facility ID already exists: {facility.facility_id}"
            ) from exc
        return FacilityRecord(**facility.model_dump(), created_at=now, updated_at=now)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS facilities (
                    facility_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    facility_type TEXT NOT NULL,
                    address TEXT,
                    longitude REAL NOT NULL,
                    latitude REAL NOT NULL,
                    coordinate_system TEXT NOT NULL,
                    capacity REAL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> FacilityRecord:
        return FacilityRecord.model_validate(dict(row))
