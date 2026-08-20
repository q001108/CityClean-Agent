"""Enumerations shared by CityClean-Agent domain models."""

from enum import Enum


class CityEventType(str, Enum):
    """Supported v0.1 external incident types."""

    WASTE_OVERFLOW = "WASTE_OVERFLOW"
    VEHICLE_BREAKDOWN = "VEHICLE_BREAKDOWN"
    ROAD_CLOSURE = "ROAD_CLOSURE"
    URGENT_TASK = "URGENT_TASK"


class RoadStatus(str, Enum):
    """Whether a road can currently be entered."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class VehicleStatus(str, Enum):
    """The complete v0.1 vehicle lifecycle."""

    AVAILABLE = "AVAILABLE"
    EN_ROUTE = "EN_ROUTE"
    SERVICING = "SERVICING"
    BROKEN = "BROKEN"


class ServiceTaskStatus(str, Enum):
    """Lifecycle states for a vehicle service task."""

    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
