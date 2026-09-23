"""Batch planning for selected risks from a deterministic synthetic network."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from cityclean_agent.agent.deepseek_event_agent import validate_policy_decision
from cityclean_agent.agent.mock_event_agent import MockEventAgent
from cityclean_agent.domain.enums import CityEventType, VehicleStatus
from cityclean_agent.domain.models import (
    DEFAULT_SERVICE_DURATION_MIN,
    CityEvent,
    CityState,
    Road,
    Vehicle,
    WastePoint,
)
from cityclean_agent.domain.road_network import GeoCoordinate, RoadNetwork
from cityclean_agent.domain.task_builder import build_task_changes
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.optimizer.results import OptimizationStatus
from cityclean_agent.policy.mapper import map_policy_parameters
from cityclean_agent.policy.models import PolicyDecision
from cityclean_agent.simulator.city_sim import CitySim
from cityclean_agent.simulator.synthetic_network import (
    RiskLevel,
    SandboxContract,
    SyntheticBin,
    SyntheticNetwork,
    generate_synthetic_network,
)
from cityclean_agent.verifier.plan_verifier import PlanVerifier


class SyntheticDispatchRequest(SandboxContract):
    seed: int = Field(default=20260922, ge=0, le=2_147_483_647)
    selected_bin_count: int = Field(default=18, ge=5, le=30)
    vehicle_count: int = Field(default=8, ge=2, le=12)
    vehicle_capacity_liters: float = Field(default=2200, ge=100, le=10_000)
    service_target_budget: int | None = Field(default=None, ge=1, le=30)
    policy_decision: PolicyDecision | None = None

    @model_validator(mode="after")
    def validate_target_budget(self) -> SyntheticDispatchRequest:
        if (
            self.service_target_budget is not None
            and self.service_target_budget > self.selected_bin_count
        ):
            raise ValueError("service_target_budget must not exceed selected_bin_count")
        return self


class DispatchCoordinate(SandboxContract):
    longitude: float
    latitude: float


class SyntheticDispatchTask(SandboxContract):
    task_id: str
    bin_id: str
    site_name: str
    risk_score: float
    risk_level: RiskLevel
    demand_liters: float
    deadline_minute: int
    assigned_vehicle_id: str | None
    planned_arrival_minute: int | None


class SyntheticDispatchRoute(SandboxContract):
    vehicle_id: str
    vehicle_capacity_liters: float
    assigned_load_liters: float
    bin_sequence: tuple[str, ...]
    planned_arrivals: dict[str, int]
    total_distance_km: float
    total_travel_minutes: int
    path: tuple[DispatchCoordinate, ...]


class SyntheticDispatchSummary(SandboxContract):
    selected_task_count: int
    assigned_task_count: int
    route_count: int
    vehicle_count: int
    fleet_capacity_liters: float
    selected_load_liters: float
    total_route_distance_km: float
    max_route_load_liters: float
    deadline_violation_count: int


class SyntheticDispatchResponse(SandboxContract):
    scenario_id: str
    data_mode: Literal["synthetic"] = "synthetic"
    status: Literal["SUCCESS", "INFEASIBLE", "VERIFICATION_FAILED"]
    reason: str | None
    selection_rule: str = "按风险分数降序选择，分数相同时按垃圾桶编号排序"
    verification_valid: bool
    policy_decision: PolicyDecision
    tasks: tuple[SyntheticDispatchTask, ...]
    routes: tuple[SyntheticDispatchRoute, ...]
    unassigned_bin_ids: tuple[str, ...]
    summary: SyntheticDispatchSummary


@dataclass(slots=True)
class SyntheticPlanningContext:
    """Mutable CitySim plus immutable inputs for one isolated sandbox run."""

    network: SyntheticNetwork
    selected_bins: list[SyntheticBin]
    request: SyntheticDispatchRequest
    sim: CitySim
    policy_decision: PolicyDecision


def plan_synthetic_dispatch(
    request: SyntheticDispatchRequest,
) -> SyntheticDispatchResponse:
    """Select risk hotspots and run the existing optimizer and verifier once."""

    return plan_synthetic_context(prepare_synthetic_planning_context(request))


def prepare_synthetic_planning_context(
    request: SyntheticDispatchRequest,
) -> SyntheticPlanningContext:
    """Build one isolated CitySim and convert selected risks into pending tasks."""

    network = generate_synthetic_network(seed=request.seed)
    candidate_bins = sorted(
        network.bins,
        key=lambda item: (-item.risk_score, item.bin_id),
    )[: request.selected_bin_count]
    state = build_synthetic_state(network, candidate_bins, request)
    aggregate_event = build_synthetic_batch_event(
        request.seed,
        candidate_bins,
        state.current_time,
        service_target_budget=request.service_target_budget,
    )
    decision = (
        build_rule_policy_decision(
            aggregate_event,
            state,
            service_target_budget=request.service_target_budget,
        )
        if request.policy_decision is None
        else validate_policy_decision(request.policy_decision, aggregate_event, state)
    )
    if (
        request.service_target_budget is not None
        and len(decision.priority_targets) > request.service_target_budget
    ):
        raise ValueError("治理研判选择的优先目标超过本轮资源预算")
    selected_target_ids = set(decision.priority_targets)
    if not selected_target_ids:
        raise ValueError("治理研判至少需要选择一个优先目标")
    selected_bins = [
        item for item in candidate_bins if item.bin_id in selected_target_ids
    ]
    sim = CitySim(state)

    for selected_bin in selected_bins:
        event = _event_for_bin(
            request.seed,
            selected_bin,
            state.current_time,
            response_deadline=decision.response_deadline,
        )
        if not sim.inject_event(event):
            raise RuntimeError(f"duplicate synthetic event: {event.event_id}")
        changes = build_task_changes(event, sim.get_state())
        sim.apply_task_changes(changes)

    return SyntheticPlanningContext(
        network=network,
        selected_bins=selected_bins,
        request=request,
        sim=sim,
        policy_decision=decision,
    )


def plan_synthetic_context(
    context: SyntheticPlanningContext,
) -> SyntheticDispatchResponse:
    """Optimize and install a plan into a prepared synthetic context."""

    network = context.network
    selected_bins = context.selected_bins
    request = context.request
    sim = context.sim
    planning_state = sim.get_state()
    decision = context.policy_decision

    optimization = ORToolsOptimizer().optimize(
        planning_state,
        map_policy_parameters(decision),
    )
    if optimization.status is OptimizationStatus.INFEASIBLE or optimization.plan is None:
        return _response_without_plan(
            network,
            selected_bins,
            planning_state,
            request,
            reason=optimization.reason or "OPTIMIZATION_FAILED",
        )

    verification = PlanVerifier().verify(planning_state, optimization.plan)
    if not verification.valid:
        return _response_without_plan(
            network,
            selected_bins,
            planning_state,
            request,
            reason="PLAN_VERIFICATION_FAILED",
            status="VERIFICATION_FAILED",
        )

    sim.install_plan(optimization.plan)
    routes = build_synthetic_dispatch_routes(
        planning_state,
        optimization.plan.vehicle_routes,
        request,
    )
    assignment_by_task = {
        task_id: (route.vehicle_id, route.planned_arrivals[task_id])
        for route in optimization.plan.vehicle_routes
        for task_id in route.task_sequence
    }
    tasks = _task_responses(selected_bins, planning_state, assignment_by_task)
    unassigned_bin_ids = tuple(
        planning_state.tasks[task_id].target_id
        for task_id in optimization.plan.unassigned_tasks
    )
    return SyntheticDispatchResponse(
        scenario_id=network.scenario_id,
        status="SUCCESS",
        reason=None,
        verification_valid=True,
        policy_decision=decision,
        tasks=tasks,
        routes=routes,
        unassigned_bin_ids=unassigned_bin_ids,
        summary=_summary(tasks, routes, request),
    )


def build_synthetic_state(
    network: SyntheticNetwork,
    selected_bins: list[SyntheticBin],
    request: SyntheticDispatchRequest,
) -> CityState:
    coordinates = {
        node.node_id: GeoCoordinate(node.longitude, node.latitude)
        for node in network.nodes
    }
    roads = []
    for edge in network.edges:
        roads.extend((
            Road(
                f"{edge.edge_id}-F",
                edge.from_node,
                edge.to_node,
                edge.distance_km,
                edge.travel_minutes,
            ),
            Road(
                f"{edge.edge_id}-R",
                edge.to_node,
                edge.from_node,
                edge.distance_km,
                edge.travel_minutes,
            ),
        ))
    node_count = len(network.nodes)
    vehicles = {
        f"SIM-V{index + 1:02d}": Vehicle(
            id=f"SIM-V{index + 1:02d}",
            current_node_id=network.nodes[(index * node_count) // request.vehicle_count].node_id,
            capacity=request.vehicle_capacity_liters,
            current_load=0,
            status=VehicleStatus.AVAILABLE,
            speed=30,
        )
        for index in range(request.vehicle_count)
    }
    waste_points = {
        item.bin_id: WastePoint(
            id=item.bin_id,
            node_id=item.node_id,
            capacity=item.capacity_liters,
            current_load=item.current_load_liters,
            generation_rate=item.hourly_generation_liters / 60,
            waste_type=item.waste_type,
            zone_type=item.site_type.value,
            priority=10 if item.risk_level is RiskLevel.CRITICAL else 8,
        )
        for item in selected_bins
    }
    return CityState(
        current_time=480,
        waste_points=waste_points,
        vehicles=vehicles,
        transfer_stations={},
        road_network=RoadNetwork(roads, node_coordinates=coordinates),
    )


def build_synthetic_batch_event(
    seed: int,
    bins: list[SyntheticBin],
    current_time: int,
    *,
    service_target_budget: int | None = None,
) -> CityEvent:
    return CityEvent(
        event_id=f"simulation-batch-{seed}",
        event_type=CityEventType.URGENT_TASK,
        timestamp=current_time,
        location="synthetic-map-area",
        affected_entities=[item.bin_id for item in bins],
        severity=5,
        deadline=current_time + 240,
        metadata={
            "service_target_budget": service_target_budget or len(bins),
            "candidate_target_count": len(bins),
            "candidate_facts": [
                {
                    "target_id": item.bin_id,
                    "site_type": item.site_type.value,
                    "site_name": item.site_name,
                    "fill_ratio": item.fill_ratio,
                    "risk_score": item.risk_score,
                    "risk_level": item.risk_level.value,
                    "forecast_hours_to_overflow": item.forecast_hours_to_overflow,
                    "sensitivity": item.sensitivity,
                    "service_window": item.service_window,
                    "access_constraint": item.access_constraint,
                    "sensor_confidence": item.sensor_confidence,
                    "risk_reasons": list(item.risk_reasons),
                }
                for item in bins
            ]
        },
        description="仿真风险批次，请基于候选点事实选择优先治理目标。",
    )


def build_rule_policy_decision(
    event: CityEvent,
    state: CityState,
    *,
    service_target_budget: int | None,
) -> PolicyDecision:
    """Apply the deterministic risk-order baseline within a target budget."""

    decision = MockEventAgent().decide(event, state)
    if service_target_budget is None:
        return decision
    return decision.model_copy(
        update={"priority_targets": decision.priority_targets[:service_target_budget]}
    )


def _event_for_bin(
    seed: int,
    item: SyntheticBin,
    current_time: int,
    *,
    response_deadline: int | None,
) -> CityEvent:
    risk_deadline = current_time + (
        120 if item.risk_level is RiskLevel.CRITICAL else 240
    )
    deadline = (
        risk_deadline
        if response_deadline is None
        else min(risk_deadline, response_deadline)
    )
    return CityEvent(
        event_id=f"simulation-{seed}-{item.bin_id}",
        event_type=CityEventType.URGENT_TASK,
        timestamp=current_time,
        location=item.node_id,
        affected_entities=[item.bin_id],
        severity=5 if item.risk_level is RiskLevel.CRITICAL else 4,
        deadline=deadline,
        metadata={"demand": item.current_load_liters},
        description=f"{item.site_name}风险分数 {item.risk_score}",
    )


def build_synthetic_dispatch_routes(
    planning_state,
    vehicle_routes,
    request,
) -> tuple[SyntheticDispatchRoute, ...]:
    routes = []
    for route in vehicle_routes:
        current_node_id = planning_state.vehicles[route.vehicle_id].current_node_id
        path_coordinates = [_coordinate(planning_state, current_node_id)]
        total_distance = 0.0
        total_travel_minutes = 0
        bin_sequence = []
        assigned_load = 0.0
        for task_id in route.task_sequence:
            task = planning_state.tasks[task_id]
            target = planning_state.waste_points[task.target_id]
            path = planning_state.road_network.shortest_path(current_node_id, target.node_id)
            if path is None:
                raise RuntimeError("verified route became unreachable")
            total_distance += path.total_distance
            total_travel_minutes += path.total_travel_time + task.service_duration_min
            for road_id in path.road_ids:
                path_coordinates.append(
                    _coordinate(
                        planning_state,
                        planning_state.road_network.get_road(road_id).to_node,
                    )
                )
            assigned_load += task.demand
            bin_sequence.append(task.target_id)
            current_node_id = target.node_id
        routes.append(SyntheticDispatchRoute(
            vehicle_id=route.vehicle_id,
            vehicle_capacity_liters=request.vehicle_capacity_liters,
            assigned_load_liters=round(assigned_load, 1),
            bin_sequence=tuple(bin_sequence),
            planned_arrivals={
                planning_state.tasks[task_id].target_id: arrival
                for task_id, arrival in route.planned_arrivals.items()
            },
            total_distance_km=round(total_distance, 3),
            total_travel_minutes=total_travel_minutes,
            path=tuple(path_coordinates),
        ))
    return tuple(routes)


def _coordinate(state, node_id: str) -> DispatchCoordinate:
    coordinate = state.road_network.get_node_coordinate(node_id)
    if coordinate is None:
        raise RuntimeError(f"missing synthetic coordinate: {node_id}")
    return DispatchCoordinate(
        longitude=coordinate.longitude,
        latitude=coordinate.latitude,
    )


def _task_responses(
    selected_bins: list[SyntheticBin],
    state,
    assignment_by_task: dict[str, tuple[str, int]],
) -> tuple[SyntheticDispatchTask, ...]:
    bins_by_id = {item.bin_id: item for item in selected_bins}
    responses = []
    for task in sorted(state.tasks.values(), key=lambda item: item.task_id):
        selected_bin = bins_by_id[task.target_id]
        assignment = assignment_by_task.get(task.task_id)
        responses.append(SyntheticDispatchTask(
            task_id=task.task_id,
            bin_id=task.target_id,
            site_name=selected_bin.site_name,
            risk_score=selected_bin.risk_score,
            risk_level=selected_bin.risk_level,
            demand_liters=round(task.demand, 1),
            deadline_minute=task.deadline or 0,
            assigned_vehicle_id=assignment[0] if assignment else None,
            planned_arrival_minute=assignment[1] if assignment else None,
        ))
    return tuple(responses)


def _summary(
    tasks: tuple[SyntheticDispatchTask, ...],
    routes: tuple[SyntheticDispatchRoute, ...],
    request: SyntheticDispatchRequest,
) -> SyntheticDispatchSummary:
    return SyntheticDispatchSummary(
        selected_task_count=len(tasks),
        assigned_task_count=sum(item.assigned_vehicle_id is not None for item in tasks),
        route_count=len(routes),
        vehicle_count=request.vehicle_count,
        fleet_capacity_liters=request.vehicle_count * request.vehicle_capacity_liters,
        selected_load_liters=round(sum(item.demand_liters for item in tasks), 1),
        total_route_distance_km=round(sum(item.total_distance_km for item in routes), 3),
        max_route_load_liters=max((item.assigned_load_liters for item in routes), default=0),
        deadline_violation_count=sum(
            item.planned_arrival_minute is not None
            and item.planned_arrival_minute + DEFAULT_SERVICE_DURATION_MIN
            > item.deadline_minute
            for item in tasks
        ),
    )


def _response_without_plan(
    network: SyntheticNetwork,
    selected_bins: list[SyntheticBin],
    state,
    request: SyntheticDispatchRequest,
    *,
    reason: str,
    status: Literal["INFEASIBLE", "VERIFICATION_FAILED"] = "INFEASIBLE",
) -> SyntheticDispatchResponse:
    tasks = _task_responses(selected_bins, state, {})
    return SyntheticDispatchResponse(
        scenario_id=network.scenario_id,
        status=status,
        reason=reason,
        verification_valid=False,
        policy_decision=(
            request.policy_decision
            if request.policy_decision is not None
            else MockEventAgent().decide(
                build_synthetic_batch_event(
                    request.seed,
                    selected_bins,
                    state.current_time,
                ),
                state,
            )
        ),
        tasks=tasks,
        routes=(),
        unassigned_bin_ids=tuple(item.bin_id for item in selected_bins),
        summary=_summary(tasks, (), request),
    )
