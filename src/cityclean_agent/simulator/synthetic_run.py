"""In-memory execution sessions for the isolated synthetic dispatch sandbox."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Literal

from pydantic import Field

from cityclean_agent.agent.mock_event_agent import MockEventAgent
from cityclean_agent.domain.enums import CityEventType, RoadStatus, ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import CityEvent
from cityclean_agent.simulator.synthetic_dispatch import (
    DispatchCoordinate,
    SyntheticDispatchRequest,
    SyntheticDispatchResponse,
    SyntheticDispatchRoute,
    SyntheticPlanningContext,
    build_synthetic_dispatch_routes,
    plan_synthetic_context,
    prepare_synthetic_planning_context,
)
from cityclean_agent.simulator.synthetic_network import SandboxContract
from cityclean_agent.workflow import WorkflowStatus, process_event


class SyntheticDisruptionType(str, Enum):
    ROAD_CLOSURE = "ROAD_CLOSURE"
    VEHICLE_BREAKDOWN = "VEHICLE_BREAKDOWN"
    WASTE_OVERFLOW = "WASTE_OVERFLOW"
    URGENT_TASK = "URGENT_TASK"


class SyntheticStepRequest(SandboxContract):
    ticks: int = Field(default=1, ge=1, le=12)


class SyntheticDisruptionRequest(SandboxContract):
    disruption_type: SyntheticDisruptionType
    target_id: str | None = None


class SyntheticRunVehicle(SandboxContract):
    vehicle_id: str
    status: VehicleStatus
    current_node_id: str
    coordinate: DispatchCoordinate
    current_load_liters: float
    capacity_liters: float
    assigned_task_ids: tuple[str, ...]


class SyntheticRunBin(SandboxContract):
    bin_id: str
    site_name: str
    coordinate: DispatchCoordinate
    current_load_liters: float
    capacity_liters: float
    fill_ratio: float
    generation_liters_per_hour: float
    task_status: ServiceTaskStatus | None


class SyntheticTimelineVehicle(SandboxContract):
    vehicle_id: str
    status: VehicleStatus
    current_node_id: str
    current_load_liters: float
    active_task_id: str | None


class SyntheticTimelineEntry(SandboxContract):
    sequence: int
    current_minute: int
    kind: Literal["RUN_STARTED", "TIME_ADVANCED", "DISRUPTION", "RUN_COMPLETED"]
    summary: str
    completed_task_count: int
    route_count: int
    replan_status: str
    vehicles: tuple[SyntheticTimelineVehicle, ...]


class SyntheticRunSnapshot(SandboxContract):
    run_id: str
    scenario_id: str
    data_mode: Literal["synthetic"] = "synthetic"
    status: Literal["RUNNING", "COMPLETED", "NEEDS_ATTENTION"]
    current_minute: int
    elapsed_minutes: int
    tick_minutes: int
    task_count: int
    completed_task_count: int
    overflow_count: int
    broken_vehicle_count: int
    last_event: str | None
    last_replan_status: str
    vehicles: tuple[SyntheticRunVehicle, ...]
    bins: tuple[SyntheticRunBin, ...]
    routes: tuple[SyntheticDispatchRoute, ...]
    available_road_disruptions: tuple[str, ...]
    available_vehicle_disruptions: tuple[str, ...]
    available_bin_disruptions: tuple[str, ...]
    closed_road_ids: tuple[str, ...]
    timeline: tuple[SyntheticTimelineEntry, ...]


class SyntheticRunStartResponse(SandboxContract):
    dispatch: SyntheticDispatchResponse
    run: SyntheticRunSnapshot


class SyntheticRunNotFoundError(KeyError):
    """Raised when an in-memory sandbox run no longer exists."""


@dataclass(slots=True)
class _SyntheticRunRecord:
    context: SyntheticPlanningContext
    initial_minute: int
    initial_dispatch: SyntheticDispatchResponse
    last_event: str | None = None
    last_replan_status: str = "NOT_RUN"
    needs_attention: bool = False
    disruption_sequence: int = 0
    timeline: list[SyntheticTimelineEntry] = field(default_factory=list)


class SyntheticRunRegistry:
    """Own isolated CitySim sessions; state disappears when the API restarts."""

    def __init__(self) -> None:
        self._records: dict[str, _SyntheticRunRecord] = {}
        self._sequence = 0
        self._lock = Lock()

    def create(self, request: SyntheticDispatchRequest) -> SyntheticRunStartResponse:
        with self._lock:
            context = prepare_synthetic_planning_context(request)
            dispatch = plan_synthetic_context(context)
            self._sequence += 1
            run_id = f"synthetic-run-{self._sequence:04d}"
            record = _SyntheticRunRecord(
                context=context,
                initial_minute=context.sim.get_state().current_time,
                initial_dispatch=dispatch,
                needs_attention=dispatch.status != "SUCCESS",
                last_replan_status=dispatch.status,
            )
            self._records[run_id] = record
            self._append_timeline(
                record,
                kind="RUN_STARTED",
                summary="已安装通过独立校验的初始调度方案。",
            )
            return SyntheticRunStartResponse(
                dispatch=dispatch,
                run=self._snapshot(run_id, record),
            )

    def get(self, run_id: str) -> SyntheticRunSnapshot:
        with self._lock:
            record = self._require(run_id)
            return self._snapshot(run_id, record)

    def step(self, run_id: str, ticks: int) -> SyntheticRunSnapshot:
        with self._lock:
            record = self._require(run_id)
            if not record.needs_attention and not self._is_complete(record):
                for _ in range(ticks):
                    record.context.sim.step()
                    completed = self._is_complete(record)
                    self._append_timeline(
                        record,
                        kind="RUN_COMPLETED" if completed else "TIME_ADVANCED",
                        summary=(
                            "全部任务执行完成。"
                            if completed
                            else f"仿真时钟推进 {record.context.sim.tick_minutes} 分钟。"
                        ),
                    )
                    if completed:
                        break
            return self._snapshot(run_id, record)

    def disrupt(
        self,
        run_id: str,
        request: SyntheticDisruptionRequest,
    ) -> SyntheticRunSnapshot:
        with self._lock:
            record = self._require(run_id)
            state = record.context.sim.get_state()
            target_id = request.target_id or self._default_disruption_target(
                state,
                request.disruption_type,
            )
            record.disruption_sequence += 1
            event = CityEvent(
                event_id=f"{run_id}-disruption-{record.disruption_sequence:03d}",
                event_type=CityEventType(request.disruption_type.value),
                timestamp=state.current_time,
                location=target_id,
                affected_entities=[target_id],
                severity=5,
                deadline=(
                    state.current_time + 60
                    if request.disruption_type is SyntheticDisruptionType.URGENT_TASK
                    else None
                ),
                metadata=(
                    {"demand": state.waste_points[target_id].current_load}
                    if request.disruption_type is SyntheticDisruptionType.URGENT_TASK
                    else {}
                ),
                description="仿真运行中的可复现受控扰动。",
            )
            result = process_event(
                record.context.sim,
                event,
                event_agent=MockEventAgent(),
            )
            record.last_replan_status = result.status.value
            record.needs_attention = result.status is not WorkflowStatus.SUCCESS
            kind_label = {
                SyntheticDisruptionType.ROAD_CLOSURE: "道路封闭",
                SyntheticDisruptionType.VEHICLE_BREAKDOWN: "车辆故障",
                SyntheticDisruptionType.WASTE_OVERFLOW: "垃圾量突增",
                SyntheticDisruptionType.URGENT_TASK: "紧急清运任务",
            }[request.disruption_type]
            record.last_event = f"{kind_label}：{target_id}；重规划结果：{result.status.value}"
            self._append_timeline(
                record,
                kind="DISRUPTION",
                summary=record.last_event,
            )
            return self._snapshot(run_id, record)

    def _require(self, run_id: str) -> _SyntheticRunRecord:
        try:
            return self._records[run_id]
        except KeyError as exc:
            raise SyntheticRunNotFoundError(run_id) from exc

    @staticmethod
    def _is_complete(record: _SyntheticRunRecord) -> bool:
        state = record.context.sim.get_state()
        return bool(state.tasks) and all(
            task.status is ServiceTaskStatus.COMPLETED
            for task in state.tasks.values()
        )

    def _snapshot(
        self,
        run_id: str,
        record: _SyntheticRunRecord,
    ) -> SyntheticRunSnapshot:
        state = record.context.sim.get_state()
        metrics = record.context.sim.calculate_metrics()
        bins_by_id = {item.bin_id: item for item in record.context.network.bins}
        tasks_by_target = {
            task.target_id: task
            for task in sorted(state.tasks.values(), key=lambda item: item.task_id)
        }
        active_plan = state.active_plan
        routes = () if active_plan is None else build_synthetic_dispatch_routes(
            state,
            active_plan.vehicle_routes,
            record.context.request,
        )
        if record.needs_attention:
            run_status = "NEEDS_ATTENTION"
        elif self._is_complete(record):
            run_status = "COMPLETED"
        else:
            run_status = "RUNNING"
        return SyntheticRunSnapshot(
            run_id=run_id,
            scenario_id=record.context.network.scenario_id,
            status=run_status,
            current_minute=state.current_time,
            elapsed_minutes=state.current_time - record.initial_minute,
            tick_minutes=record.context.sim.tick_minutes,
            task_count=len(state.tasks),
            completed_task_count=metrics["completed_task_count"],
            overflow_count=metrics["overflow_count"],
            broken_vehicle_count=metrics["broken_vehicle_count"],
            last_event=record.last_event,
            last_replan_status=record.last_replan_status,
            vehicles=tuple(
                SyntheticRunVehicle(
                    vehicle_id=vehicle.id,
                    status=vehicle.status,
                    current_node_id=vehicle.current_node_id,
                    coordinate=_coordinate(state, vehicle.current_node_id),
                    current_load_liters=round(vehicle.current_load, 1),
                    capacity_liters=vehicle.capacity,
                    assigned_task_ids=tuple(vehicle.assigned_tasks),
                )
                for vehicle in sorted(state.vehicles.values(), key=lambda item: item.id)
            ),
            bins=tuple(
                SyntheticRunBin(
                    bin_id=point.id,
                    site_name=bins_by_id[point.id].site_name,
                    coordinate=_coordinate(state, point.node_id),
                    current_load_liters=round(point.current_load, 1),
                    capacity_liters=point.capacity,
                    fill_ratio=round(point.current_load / point.capacity, 3),
                    generation_liters_per_hour=round(point.generation_rate * 60, 1),
                    task_status=(
                        tasks_by_target[point.id].status
                        if point.id in tasks_by_target
                        else None
                    ),
                )
                for point in sorted(state.waste_points.values(), key=lambda item: item.id)
            ),
            routes=routes,
            available_road_disruptions=self._route_road_ids(state),
            available_vehicle_disruptions=tuple(
                vehicle.id
                for vehicle in sorted(state.vehicles.values(), key=lambda item: item.id)
                if vehicle.status is not VehicleStatus.BROKEN
            ),
            available_bin_disruptions=tuple(
                point.id
                for point in sorted(
                    state.waste_points.values(),
                    key=lambda item: (-item.current_load / item.capacity, item.id),
                )
            ),
            closed_road_ids=tuple(
                road.id
                for road in state.road_network.roads
                if road.status is RoadStatus.CLOSED
            ),
            timeline=tuple(record.timeline[-48:]),
        )

    @staticmethod
    def _append_timeline(
        record: _SyntheticRunRecord,
        *,
        kind: Literal["RUN_STARTED", "TIME_ADVANCED", "DISRUPTION", "RUN_COMPLETED"],
        summary: str,
    ) -> None:
        state = record.context.sim.get_state()
        active_plan = state.active_plan
        completed_task_count = sum(
            task.status is ServiceTaskStatus.COMPLETED
            for task in state.tasks.values()
        )
        record.timeline.append(SyntheticTimelineEntry(
            sequence=len(record.timeline) + 1,
            current_minute=state.current_time,
            kind=kind,
            summary=summary,
            completed_task_count=completed_task_count,
            route_count=len(active_plan.vehicle_routes) if active_plan is not None else 0,
            replan_status=record.last_replan_status,
            vehicles=tuple(
                SyntheticTimelineVehicle(
                    vehicle_id=vehicle.id,
                    status=vehicle.status,
                    current_node_id=vehicle.current_node_id,
                    current_load_liters=round(vehicle.current_load, 1),
                    active_task_id=(
                        vehicle.assigned_tasks[0]
                        if vehicle.assigned_tasks
                        else None
                    ),
                )
                for vehicle in sorted(state.vehicles.values(), key=lambda item: item.id)
            ),
        ))

    @staticmethod
    def _route_road_ids(state) -> tuple[str, ...]:
        active_plan = state.active_plan
        if active_plan is None:
            return ()
        road_ids = []
        for route in active_plan.vehicle_routes:
            current_node_id = state.vehicles[route.vehicle_id].current_node_id
            for task_id in route.task_sequence:
                task = state.tasks[task_id]
                if task.status is ServiceTaskStatus.COMPLETED:
                    continue
                target_node_id = state.waste_points[task.target_id].node_id
                path = state.road_network.shortest_path(current_node_id, target_node_id)
                if path is not None:
                    road_ids.extend(
                        road_id
                        for road_id in path.road_ids
                        if state.road_network.get_road(road_id).status is RoadStatus.OPEN
                    )
                    current_node_id = target_node_id
        return tuple(dict.fromkeys(road_ids))

    def _default_disruption_target(self, state, disruption_type: SyntheticDisruptionType) -> str:
        if disruption_type is SyntheticDisruptionType.ROAD_CLOSURE:
            candidates = self._route_road_ids(state)
        elif disruption_type is SyntheticDisruptionType.VEHICLE_BREAKDOWN:
            candidates = tuple(
                route.vehicle_id
                for route in (state.active_plan.vehicle_routes if state.active_plan else ())
                if state.vehicles[route.vehicle_id].status is not VehicleStatus.BROKEN
            )
        elif disruption_type is SyntheticDisruptionType.WASTE_OVERFLOW:
            candidates = tuple(
                point.id
                for point in sorted(
                    state.waste_points.values(),
                    key=lambda item: (-item.current_load / item.capacity, item.id),
                )
                if point.current_load < point.capacity
            )
        else:
            candidates = tuple(
                point.id
                for point in sorted(
                    state.waste_points.values(),
                    key=lambda item: (-item.current_load / item.capacity, item.id),
                )
            )
        if not candidates:
            raise ValueError("当前运行态没有可注入的扰动目标。")
        return candidates[0]


def _coordinate(state, node_id: str) -> DispatchCoordinate:
    coordinate = state.road_network.get_node_coordinate(node_id)
    if coordinate is None:
        raise RuntimeError(f"missing synthetic coordinate: {node_id}")
    return DispatchCoordinate(
        longitude=coordinate.longitude,
        latitude=coordinate.latitude,
    )
