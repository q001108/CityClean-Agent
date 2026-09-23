"""Versioned transport contracts for the product runtime."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cityclean_agent.domain.enums import (
    CityEventType,
    RoadStatus,
    ServiceTaskStatus,
    VehicleStatus,
)
from cityclean_agent.domain.models import (
    CityEvent,
    CityState,
    DispatchPlan,
    VehicleRoute,
)
from cityclean_agent.policy.models import PolicyDecision
from cityclean_agent.verifier.plan_verifier import VerificationResult
from cityclean_agent.workflow import WorkflowResult, WorkflowStatus


class StrictContract(BaseModel):
    """Reject undeclared fields at the external API boundary."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictContract):
    status: str = "ok"
    service: str = "cityclean-agent-runtime"
    api_version: str = "v1"


class RuntimeStatusResponse(StrictContract):
    status: str
    detail: str
    capabilities: tuple[str, ...]
    source_name: str | None
    data_mode: Literal["test", "production"] | None


class GeoCoordinateResponse(StrictContract):
    longitude: float
    latitude: float


class CityEventRequest(StrictContract):
    event_id: str = Field(min_length=1)
    event_type: CityEventType
    timestamp: int = Field(ge=0)
    location: str = Field(min_length=1)
    affected_entities: list[str] = Field(min_length=1)
    severity: int = Field(ge=0)
    deadline: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None

    @model_validator(mode="after")
    def validate_event(self) -> CityEventRequest:
        if self.deadline is not None and self.deadline < self.timestamp:
            raise ValueError("deadline must not be before timestamp")
        if any(not entity_id.strip() for entity_id in self.affected_entities):
            raise ValueError("affected_entities must not contain empty identifiers")
        if self.event_type in {
            CityEventType.WASTE_OVERFLOW,
            CityEventType.URGENT_TASK,
        } and "demand" in self.metadata:
            demand = self.metadata["demand"]
            if isinstance(demand, bool) or not isinstance(demand, (int, float)) or demand <= 0:
                raise ValueError("metadata.demand must be a positive number")
        return self

    def to_domain(self) -> CityEvent:
        return CityEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            timestamp=self.timestamp,
            location=self.location,
            affected_entities=list(dict.fromkeys(self.affected_entities)),
            severity=self.severity,
            deadline=self.deadline,
            metadata=dict(self.metadata),
            description=self.description,
        )


class WastePointResponse(StrictContract):
    id: str
    node_id: str
    capacity: float
    current_load: float
    generation_rate: float
    waste_type: str
    zone_type: str
    priority: int
    coordinate: GeoCoordinateResponse | None


class VehicleResponse(StrictContract):
    id: str
    current_node_id: str
    capacity: float
    current_load: float
    status: VehicleStatus
    speed: float
    assigned_tasks: tuple[str, ...]
    coordinate: GeoCoordinateResponse | None


class TransferStationResponse(StrictContract):
    id: str
    node_id: str
    capacity: float
    coordinate: GeoCoordinateResponse | None


class RoadResponse(StrictContract):
    id: str
    from_node: str
    to_node: str
    distance: float
    travel_time: int
    status: RoadStatus
    from_coordinate: GeoCoordinateResponse | None
    to_coordinate: GeoCoordinateResponse | None


class ServiceTaskResponse(StrictContract):
    task_id: str
    source_event_id: str
    target_id: str
    demand: float
    priority: int
    deadline: int | None
    status: ServiceTaskStatus
    service_duration_min: int
    created_at: int
    completed_at: int | None


class EventResponse(StrictContract):
    event_id: str
    event_type: CityEventType
    timestamp: int
    location: str
    affected_entities: tuple[str, ...]
    severity: int
    deadline: int | None
    metadata: dict[str, Any]
    description: str | None


class VehicleRouteResponse(StrictContract):
    vehicle_id: str
    task_sequence: tuple[str, ...]
    planned_arrivals: dict[str, int]
    path: tuple[GeoCoordinateResponse, ...] = ()


class DispatchPlanResponse(StrictContract):
    plan_id: str
    vehicle_routes: tuple[VehicleRouteResponse, ...]
    unassigned_tasks: tuple[str, ...]


class CitySnapshotResponse(StrictContract):
    current_time: int
    waste_points: tuple[WastePointResponse, ...]
    vehicles: tuple[VehicleResponse, ...]
    transfer_stations: tuple[TransferStationResponse, ...]
    roads: tuple[RoadResponse, ...]
    active_events: tuple[EventResponse, ...]
    tasks: tuple[ServiceTaskResponse, ...]
    active_plan: DispatchPlanResponse | None


class ViolationResponse(StrictContract):
    violation_type: str
    message: str
    vehicle_id: str | None
    task_id: str | None


class VerificationResponse(StrictContract):
    valid: bool
    violations: tuple[ViolationResponse, ...]


class WorkflowRunResponse(StrictContract):
    event_id: str
    status: WorkflowStatus
    reason: str | None
    policy_decision: PolicyDecision | None
    plan: DispatchPlanResponse | None
    verification: VerificationResponse | None


def snapshot_response(state: CityState) -> CitySnapshotResponse:
    """Convert an isolated CityState copy into deterministic JSON data."""

    return CitySnapshotResponse(
        current_time=state.current_time,
        waste_points=tuple(
            WastePointResponse(
                id=point.id,
                node_id=point.node_id,
                capacity=point.capacity,
                current_load=point.current_load,
                generation_rate=point.generation_rate,
                waste_type=point.waste_type,
                zone_type=point.zone_type,
                priority=point.priority,
                coordinate=_coordinate_response(state, point.node_id),
            )
            for point in sorted(state.waste_points.values(), key=lambda item: item.id)
        ),
        vehicles=tuple(
            VehicleResponse(
                id=vehicle.id,
                current_node_id=vehicle.current_node_id,
                capacity=vehicle.capacity,
                current_load=vehicle.current_load,
                status=vehicle.status,
                speed=vehicle.speed,
                assigned_tasks=tuple(vehicle.assigned_tasks),
                coordinate=_coordinate_response(state, vehicle.current_node_id),
            )
            for vehicle in sorted(state.vehicles.values(), key=lambda item: item.id)
        ),
        transfer_stations=tuple(
            TransferStationResponse(
                id=station.id,
                node_id=station.node_id,
                capacity=station.capacity,
                coordinate=_coordinate_response(state, station.node_id),
            )
            for station in sorted(
                state.transfer_stations.values(), key=lambda item: item.id
            )
        ),
        roads=tuple(
            RoadResponse(
                id=road.id,
                from_node=road.from_node,
                to_node=road.to_node,
                distance=road.distance,
                travel_time=road.travel_time,
                status=road.status,
                from_coordinate=_coordinate_response(state, road.from_node),
                to_coordinate=_coordinate_response(state, road.to_node),
            )
            for road in state.road_network.roads
        ),
        active_events=tuple(
            _event_response(event)
            for event in sorted(state.active_events.values(), key=lambda item: item.event_id)
        ),
        tasks=tuple(
            ServiceTaskResponse.model_validate(task, from_attributes=True)
            for task in sorted(state.tasks.values(), key=lambda item: item.task_id)
        ),
        active_plan=_plan_response(state.active_plan, state),
    )


def workflow_response(event_id: str, result: WorkflowResult) -> WorkflowRunResponse:
    return WorkflowRunResponse(
        event_id=event_id,
        status=result.status,
        reason=result.reason,
        policy_decision=result.policy_decision,
        plan=_plan_response(result.plan),
        verification=_verification_response(result.verification_result),
    )


def _event_response(event: CityEvent) -> EventResponse:
    return EventResponse(
        event_id=event.event_id,
        event_type=event.event_type,
        timestamp=event.timestamp,
        location=event.location,
        affected_entities=tuple(event.affected_entities),
        severity=event.severity,
        deadline=event.deadline,
        metadata=dict(event.metadata),
        description=event.description,
    )


def _plan_response(
    plan: DispatchPlan | None,
    state: CityState | None = None,
) -> DispatchPlanResponse | None:
    if plan is None:
        return None
    return DispatchPlanResponse(
        plan_id=plan.plan_id,
        vehicle_routes=tuple(
            VehicleRouteResponse(
                vehicle_id=route.vehicle_id,
                task_sequence=tuple(route.task_sequence),
                planned_arrivals=dict(route.planned_arrivals),
                path=_route_path_response(state, route),
            )
            for route in plan.vehicle_routes
        ),
        unassigned_tasks=tuple(plan.unassigned_tasks),
    )


def _coordinate_response(
    state: CityState,
    node_id: str,
) -> GeoCoordinateResponse | None:
    coordinate = state.road_network.get_node_coordinate(node_id)
    if coordinate is None:
        return None
    return GeoCoordinateResponse(
        longitude=coordinate.longitude,
        latitude=coordinate.latitude,
    )


def _route_path_response(
    state: CityState | None,
    route: VehicleRoute,
) -> tuple[GeoCoordinateResponse, ...]:
    if state is None:
        return ()
    vehicle = state.vehicles.get(route.vehicle_id)
    if vehicle is None:
        return ()

    node_ids = [vehicle.current_node_id]
    current_node_id = vehicle.current_node_id
    for task_id in route.task_sequence:
        task = state.tasks.get(task_id)
        target = state.waste_points.get(task.target_id) if task is not None else None
        if target is None:
            return ()
        path = state.road_network.shortest_path(current_node_id, target.node_id)
        if path is None:
            return ()
        node_ids.extend(
            state.road_network.get_road(road_id).to_node for road_id in path.road_ids
        )
        current_node_id = target.node_id

    coordinates = []
    for node_id in node_ids:
        coordinate = _coordinate_response(state, node_id)
        if coordinate is None:
            return ()
        coordinates.append(coordinate)
    return tuple(coordinates)


def _verification_response(
    verification: VerificationResult | None,
) -> VerificationResponse | None:
    if verification is None:
        return None
    return VerificationResponse(
        valid=verification.valid,
        violations=tuple(
            ViolationResponse.model_validate(violation, from_attributes=True)
            for violation in verification.violations
        ),
    )
