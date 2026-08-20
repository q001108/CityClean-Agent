"""Minimal domain entities for the v0.1 CityClean-Agent scope."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cityclean_agent.domain.enums import (
    CityEventType,
    RoadStatus,
    ServiceTaskStatus,
    VehicleStatus,
)

if TYPE_CHECKING:
    from cityclean_agent.domain.road_network import RoadNetwork


DEFAULT_SERVICE_DURATION_MIN = 5


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must not be empty")


@dataclass(slots=True)
class WastePoint:
    """A waste-collection location and its current accumulated waste."""

    id: str
    node_id: str
    capacity: float
    current_load: float
    generation_rate: float
    waste_type: str
    zone_type: str
    priority: int

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "id")
        _require_non_empty(self.node_id, "node_id")
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if self.current_load < 0:
            raise ValueError("current_load must not be negative")
        if self.generation_rate < 0:
            raise ValueError("generation_rate must not be negative")
        if self.priority < 0:
            raise ValueError("priority must not be negative")


@dataclass(slots=True)
class Vehicle:
    """A sanitation vehicle with its true current location and load."""

    id: str
    current_node_id: str
    capacity: float
    current_load: float
    status: VehicleStatus
    speed: float
    assigned_tasks: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "id")
        _require_non_empty(self.current_node_id, "current_node_id")
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if not 0 <= self.current_load <= self.capacity:
            raise ValueError("current_load must be between zero and capacity")
        if self.speed <= 0:
            raise ValueError("speed must be positive")

    @property
    def remaining_capacity(self) -> float:
        """Return capacity still available for collection in this route."""

        return self.capacity - self.current_load


@dataclass(slots=True)
class TransferStation:
    """A transfer station retained for the v0.1 city-state model."""

    id: str
    node_id: str
    capacity: float

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "id")
        _require_non_empty(self.node_id, "node_id")
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")


@dataclass(slots=True)
class Road:
    """A directed road edge used for all routing distance and time queries."""

    id: str
    from_node: str
    to_node: str
    distance: float
    travel_time: int
    status: RoadStatus = RoadStatus.OPEN

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "id")
        _require_non_empty(self.from_node, "from_node")
        _require_non_empty(self.to_node, "to_node")
        if self.distance <= 0:
            raise ValueError("distance must be positive")
        if self.travel_time <= 0:
            raise ValueError("travel_time must be positive")


@dataclass(slots=True)
class CityEvent:
    """A fact about an external city incident, separate from service work."""

    event_id: str
    event_type: CityEventType
    timestamp: int
    location: str
    affected_entities: list[str]
    severity: int
    deadline: int | None
    metadata: dict[str, Any] = field(default_factory=dict)
    description: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.event_id, "event_id")
        _require_non_empty(self.location, "location")
        if self.timestamp < 0:
            raise ValueError("timestamp must not be negative")
        if self.severity < 0:
            raise ValueError("severity must not be negative")
        if self.deadline is not None and self.deadline < self.timestamp:
            raise ValueError("deadline must not be before timestamp")


@dataclass(slots=True)
class ServiceTask:
    """A concrete waste-point service operation for a vehicle to perform."""

    task_id: str
    source_event_id: str
    target_id: str
    demand: float
    priority: int
    deadline: int | None
    status: ServiceTaskStatus = ServiceTaskStatus.PENDING
    service_duration_min: int = DEFAULT_SERVICE_DURATION_MIN
    created_at: int = 0
    completed_at: int | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.task_id, "task_id")
        _require_non_empty(self.source_event_id, "source_event_id")
        _require_non_empty(self.target_id, "target_id")
        if self.demand <= 0:
            raise ValueError("demand must be positive")
        if self.priority < 0:
            raise ValueError("priority must not be negative")
        if self.deadline is not None and self.deadline < 0:
            raise ValueError("deadline must not be negative")
        if self.service_duration_min != DEFAULT_SERVICE_DURATION_MIN:
            raise ValueError(
                "service_duration_min must use the v0.1 fixed service duration"
            )
        if self.created_at < 0:
            raise ValueError("created_at must not be negative")
        if self.completed_at is not None and self.completed_at < self.created_at:
            raise ValueError("completed_at must not be before created_at")


@dataclass(slots=True)
class VehicleRoute:
    """The ordered tasks assigned to one vehicle in a dispatch plan.

    ``planned_arrivals`` records absolute target-node arrival minutes and
    excludes the task's own service duration.
    """

    vehicle_id: str
    task_sequence: list[str]
    planned_arrivals: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty(self.vehicle_id, "vehicle_id")
        if len(self.task_sequence) != len(set(self.task_sequence)):
            raise ValueError("task_sequence must not contain duplicate task IDs")
        if not set(self.planned_arrivals).issubset(self.task_sequence):
            raise ValueError("planned_arrivals may only reference route tasks")
        if any(arrival < 0 for arrival in self.planned_arrivals.values()):
            raise ValueError("planned arrival times must not be negative")


@dataclass(slots=True)
class DispatchPlan:
    """A structured proposed assignment of service tasks to vehicle routes."""

    plan_id: str
    vehicle_routes: list[VehicleRoute]
    unassigned_tasks: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_non_empty(self.plan_id, "plan_id")
        route_vehicle_ids = [route.vehicle_id for route in self.vehicle_routes]
        if len(route_vehicle_ids) != len(set(route_vehicle_ids)):
            raise ValueError("a dispatch plan may contain only one route per vehicle")


@dataclass(slots=True)
class CityState:
    """The mutable aggregate state owned by CitySim."""

    current_time: int
    waste_points: dict[str, WastePoint]
    vehicles: dict[str, Vehicle]
    transfer_stations: dict[str, TransferStation]
    road_network: RoadNetwork
    active_events: dict[str, CityEvent] = field(default_factory=dict)
    tasks: dict[str, ServiceTask] = field(default_factory=dict)
    active_plan: DispatchPlan | None = None

    def __post_init__(self) -> None:
        if self.current_time < 0:
            raise ValueError("current_time must not be negative")
