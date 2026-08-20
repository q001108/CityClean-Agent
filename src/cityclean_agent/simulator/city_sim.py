"""A minimal deterministic discrete-time simulation for CityClean-Agent."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Iterable

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
    ServiceTask,
    Vehicle,
)
from cityclean_agent.domain.task_builder import TaskBuildResult


@dataclass(slots=True)
class _VehicleProgress:
    """Private execution detail; no in-road position is exposed in CityState."""

    task_id: str
    mode: str
    remaining_min: int
    road_ids: tuple[str, ...] = ()
    road_index: int = 0


@dataclass(frozen=True, slots=True)
class RuntimeStats:
    """Minimal counters measured from actual CitySim execution."""

    total_distance: float
    overflow_count: int


class CitySim:
    """Own and advance one mutable CityState in fixed simulation ticks."""

    def __init__(self, initial_state: CityState, tick_minutes: int = 5) -> None:
        if tick_minutes <= 0:
            raise ValueError("tick_minutes must be positive")
        self.tick_minutes = tick_minutes
        self._initial_state = deepcopy(initial_state)
        self.reset()

    def reset(self) -> None:
        """Restore the initial city state and discard injected-event history."""

        self._state = deepcopy(self._initial_state)
        self._pending_events: dict[str, CityEvent] = {}
        self._processed_event_ids: set[str] = set(self._state.active_events)
        self._vehicle_progress: dict[str, _VehicleProgress] = {}
        self._total_distance = 0.0
        self._overflow_count = 0
        self._overflowing_waste_point_ids = {
            point.id
            for point in self._state.waste_points.values()
            if point.current_load >= point.capacity
        }

    def get_state(self) -> CityState:
        """Return an isolated snapshot that cannot mutate simulation truth."""

        return deepcopy(self._state)

    def get_runtime_stats(self) -> RuntimeStats:
        """Return actual-execution counters without exposing mutable state."""

        return RuntimeStats(
            total_distance=self._total_distance,
            overflow_count=self._overflow_count,
        )

    def apply_task_changes(self, changes: TaskBuildResult) -> None:
        """Apply TaskBuilder output while retaining CityState write ownership."""

        self._add_tasks(changes.created_tasks)
        self._update_tasks(changes.updated_tasks)

    def release_unstarted_tasks(self) -> tuple[str, ...]:
        """Return ASSIGNED tasks to PENDING before a replacement plan is solved.

        COMPLETED and IN_PROGRESS tasks remain untouched.  Clearing the old
        plan prevents a stale route from being executed when replanning fails.
        IN_PROGRESS work continues through the vehicle's existing assignment.
        """

        released_task_ids = sorted(
            task.task_id
            for task in self._state.tasks.values()
            if task.status is ServiceTaskStatus.ASSIGNED
        )
        released_task_id_set = set(released_task_ids)
        for task_id in released_task_ids:
            self._state.tasks[task_id].status = ServiceTaskStatus.PENDING
        for vehicle in self._state.vehicles.values():
            vehicle.assigned_tasks[:] = [
                task_id
                for task_id in vehicle.assigned_tasks
                if task_id not in released_task_id_set
                and self._state.tasks.get(task_id) is not None
                and self._state.tasks[task_id].status is ServiceTaskStatus.IN_PROGRESS
            ]
        self._state.active_plan = None
        return tuple(released_task_ids)

    def install_plan(self, plan: DispatchPlan) -> None:
        """Install a previously verified plan without resetting city state."""

        plan_copy = deepcopy(plan)
        assigned_task_ids: set[str] = set()
        for route in plan_copy.vehicle_routes:
            vehicle = self._state.vehicles.get(route.vehicle_id)
            if vehicle is None:
                raise ValueError(f"plan references an unknown vehicle: {route.vehicle_id}")
            if vehicle.status is not VehicleStatus.AVAILABLE:
                raise ValueError(f"plan vehicle is not AVAILABLE: {route.vehicle_id}")
            for task_id in route.task_sequence:
                if task_id in assigned_task_ids:
                    raise ValueError(f"plan assigns task more than once: {task_id}")
                task = self._state.tasks.get(task_id)
                if task is None:
                    raise ValueError(f"plan references an unknown task: {task_id}")
                if task.status is not ServiceTaskStatus.PENDING:
                    raise ValueError(f"plan task is not PENDING: {task_id}")
                assigned_task_ids.add(task_id)

        self._state.active_plan = plan_copy
        for route in plan_copy.vehicle_routes:
            vehicle = self._state.vehicles[route.vehicle_id]
            for task_id in route.task_sequence:
                self._state.tasks[task_id].status = ServiceTaskStatus.ASSIGNED
                if task_id not in vehicle.assigned_tasks:
                    vehicle.assigned_tasks.append(task_id)

    def inject_event(self, event: CityEvent) -> bool:
        """Queue or apply an event once; duplicate IDs have no further effect.

        Events dated at or before the current simulation minute take effect
        immediately. Future events are processed at the beginning of the first
        tick whose current time reaches their timestamp.
        """

        if event.event_id in self._processed_event_ids:
            return False
        if event.event_id in self._pending_events:
            return False

        event_copy = deepcopy(event)
        if event_copy.timestamp <= self._state.current_time:
            self._apply_event(event_copy)
        else:
            self._pending_events[event_copy.event_id] = event_copy
        return True

    def step(self) -> None:
        """Advance the city by one deterministic tick."""

        self._apply_due_events()
        self._advance_existing_routes()
        self._generate_waste()
        self._state.current_time += self.tick_minutes

    def calculate_metrics(self) -> dict[str, int | float]:
        """Return only metrics whose values CitySim can currently measure."""

        tasks = tuple(self._state.tasks.values())
        return {
            "current_time": self._state.current_time,
            "task_count": len(tasks),
            "completed_task_count": sum(
                task.status is ServiceTaskStatus.COMPLETED for task in tasks
            ),
            "overflow_count": self._overflow_count,
            "broken_vehicle_count": sum(
                vehicle.status is VehicleStatus.BROKEN
                for vehicle in self._state.vehicles.values()
            ),
        }

    def _apply_due_events(self) -> None:
        due_events = sorted(
            (
                event
                for event in self._pending_events.values()
                if event.timestamp <= self._state.current_time
            ),
            key=lambda event: (event.timestamp, event.event_id),
        )
        for event in due_events:
            del self._pending_events[event.event_id]
            self._apply_event(event)

    def _add_tasks(self, tasks: Iterable[ServiceTask]) -> None:
        for task in tasks:
            self._require_existing_waste_point(task)
            existing_task = self._state.tasks.get(task.task_id)
            if existing_task is None:
                self._state.tasks[task.task_id] = deepcopy(task)
            elif existing_task != task:
                raise ValueError(f"task ID already exists: {task.task_id}")

    def _update_tasks(self, tasks: Iterable[ServiceTask]) -> None:
        for task in tasks:
            self._require_existing_waste_point(task)
            existing_task = self._state.tasks.get(task.task_id)
            if existing_task is None:
                raise ValueError(f"cannot update unknown task ID: {task.task_id}")
            if existing_task.status is ServiceTaskStatus.COMPLETED:
                raise ValueError("completed tasks must not be updated")
            self._state.tasks[task.task_id] = deepcopy(task)

    def _require_existing_waste_point(self, task: ServiceTask) -> None:
        if task.target_id not in self._state.waste_points:
            raise ValueError(f"task target is not an existing WastePoint: {task.target_id}")

    def _apply_event(self, event: CityEvent) -> None:
        if event.event_id in self._processed_event_ids:
            return

        if event.event_type is CityEventType.VEHICLE_BREAKDOWN:
            for vehicle_id in event.affected_entities:
                vehicle = self._state.vehicles.get(vehicle_id)
                if vehicle is not None:
                    self._break_down_vehicle(vehicle)
        elif event.event_type is CityEventType.ROAD_CLOSURE:
            for road_id in event.affected_entities:
                if road_id in {road.id for road in self._state.road_network.roads}:
                    self._state.road_network.set_road_status(
                        road_id, RoadStatus.CLOSED
                    )
        elif event.event_type is CityEventType.WASTE_OVERFLOW:
            for waste_point_id in event.affected_entities:
                waste_point = self._state.waste_points.get(waste_point_id)
                if waste_point is not None:
                    previous_load = waste_point.current_load
                    waste_point.current_load = max(
                        waste_point.current_load, waste_point.capacity
                    )
                    self._record_overflow_transition(waste_point, previous_load)
        elif event.event_type is CityEventType.URGENT_TASK:
            # Task creation belongs to the later TaskBuilder phase.
            pass

        self._processed_event_ids.add(event.event_id)
        self._state.active_events[event.event_id] = deepcopy(event)

    def _break_down_vehicle(self, vehicle: Vehicle) -> None:
        vehicle.status = VehicleStatus.BROKEN
        task_ids = set(vehicle.assigned_tasks)
        route = self._route_for_vehicle(vehicle.id)
        if route is not None:
            task_ids.update(route.task_sequence)

        for task_id in task_ids:
            task = self._state.tasks.get(task_id)
            if task is not None and task.status is ServiceTaskStatus.ASSIGNED:
                task.status = ServiceTaskStatus.PENDING
        vehicle.assigned_tasks[:] = [
            task_id
            for task_id in vehicle.assigned_tasks
            if self._state.tasks.get(task_id) is not None
            and self._state.tasks[task_id].status is ServiceTaskStatus.IN_PROGRESS
        ]
        self._vehicle_progress.pop(vehicle.id, None)

    def _advance_existing_routes(self) -> None:
        for vehicle in self._state.vehicles.values():
            if vehicle.status is VehicleStatus.BROKEN:
                continue
            self._advance_vehicle(vehicle)

    def _advance_vehicle(self, vehicle: Vehicle) -> None:
        remaining_tick_min = self.tick_minutes
        elapsed_tick_min = 0

        while remaining_tick_min > 0:
            progress = self._vehicle_progress.get(vehicle.id)
            task = self._next_task_for_vehicle(vehicle)
            if task is None:
                vehicle.status = VehicleStatus.AVAILABLE
                return

            if progress is None:
                if not self._prepare_task(vehicle, task):
                    return
                progress = self._vehicle_progress[vehicle.id]

            if progress.task_id != task.task_id:
                self._vehicle_progress.pop(vehicle.id, None)
                continue

            if progress.mode == "TRAVEL":
                consumed = self._advance_travel(vehicle, task, progress, remaining_tick_min)
            else:
                consumed = self._advance_service(
                    vehicle,
                    task,
                    progress,
                    remaining_tick_min,
                    self._state.current_time + elapsed_tick_min,
                )

            remaining_tick_min -= consumed
            elapsed_tick_min += consumed
            if consumed == 0:
                return

    def _next_task_for_vehicle(self, vehicle: Vehicle) -> ServiceTask | None:
        route = self._route_for_vehicle(vehicle.id)
        task_ids = route.task_sequence if route is not None else vehicle.assigned_tasks
        for task_id in task_ids:
            task = self._state.tasks.get(task_id)
            if task is not None and task.status is not ServiceTaskStatus.COMPLETED:
                return task
        return None

    def _route_for_vehicle(self, vehicle_id: str):
        active_plan = self._state.active_plan
        if active_plan is None:
            return None
        return next(
            (
                route
                for route in active_plan.vehicle_routes
                if route.vehicle_id == vehicle_id
            ),
            None,
        )

    def _prepare_task(self, vehicle: Vehicle, task: ServiceTask) -> bool:
        waste_point = self._state.waste_points.get(task.target_id)
        if waste_point is None:
            self._release_task(vehicle, task)
            return False

        if task.status is ServiceTaskStatus.PENDING:
            task.status = ServiceTaskStatus.ASSIGNED
        if task.task_id not in vehicle.assigned_tasks:
            vehicle.assigned_tasks.append(task.task_id)

        if vehicle.current_node_id == waste_point.node_id:
            if task.demand > vehicle.remaining_capacity:
                self._release_task(vehicle, task)
                return False
            vehicle.status = VehicleStatus.SERVICING
            self._vehicle_progress[vehicle.id] = _VehicleProgress(
                task_id=task.task_id,
                mode="SERVICE",
                remaining_min=task.service_duration_min,
            )
            return True

        path = self._state.road_network.shortest_path(
            vehicle.current_node_id, waste_point.node_id
        )
        if path is None:
            self._release_task(vehicle, task)
            return False

        vehicle.status = VehicleStatus.EN_ROUTE
        self._vehicle_progress[vehicle.id] = _VehicleProgress(
            task_id=task.task_id,
            mode="TRAVEL",
            remaining_min=self._state.road_network.get_road(
                path.road_ids[0]
            ).travel_time,
            road_ids=path.road_ids,
        )
        return True

    def _advance_travel(
        self,
        vehicle: Vehicle,
        task: ServiceTask,
        progress: _VehicleProgress,
        available_min: int,
    ) -> int:
        road = self._state.road_network.get_road(progress.road_ids[progress.road_index])
        if progress.remaining_min == road.travel_time and road.status is RoadStatus.CLOSED:
            self._release_task(vehicle, task)
            return 0

        consumed = min(available_min, progress.remaining_min)
        progress.remaining_min -= consumed
        if progress.remaining_min > 0:
            vehicle.status = VehicleStatus.EN_ROUTE
            return consumed

        vehicle.current_node_id = road.to_node
        self._total_distance += road.distance
        progress.road_index += 1
        if progress.road_index < len(progress.road_ids):
            next_road = self._state.road_network.get_road(
                progress.road_ids[progress.road_index]
            )
            progress.remaining_min = next_road.travel_time
            vehicle.status = VehicleStatus.EN_ROUTE
            return consumed

        progress.mode = "SERVICE"
        progress.remaining_min = task.service_duration_min
        vehicle.status = VehicleStatus.SERVICING
        return consumed

    def _advance_service(
        self,
        vehicle: Vehicle,
        task: ServiceTask,
        progress: _VehicleProgress,
        available_min: int,
        service_start_time: int,
    ) -> int:
        if task.demand > vehicle.remaining_capacity:
            self._release_task(vehicle, task)
            return 0

        task.status = ServiceTaskStatus.IN_PROGRESS
        consumed = min(available_min, progress.remaining_min)
        progress.remaining_min -= consumed
        if progress.remaining_min > 0:
            vehicle.status = VehicleStatus.SERVICING
            return consumed

        waste_point = self._state.waste_points[task.target_id]
        previous_load = waste_point.current_load
        waste_point.current_load = max(0.0, waste_point.current_load - task.demand)
        self._record_overflow_transition(waste_point, previous_load)
        vehicle.current_load += task.demand
        task.status = ServiceTaskStatus.COMPLETED
        task.completed_at = service_start_time + consumed
        vehicle.assigned_tasks.remove(task.task_id)
        vehicle.status = VehicleStatus.AVAILABLE
        self._vehicle_progress.pop(vehicle.id, None)
        return consumed

    def _release_task(self, vehicle: Vehicle, task: ServiceTask) -> None:
        task.status = ServiceTaskStatus.PENDING
        if task.task_id in vehicle.assigned_tasks:
            vehicle.assigned_tasks.remove(task.task_id)
        vehicle.status = VehicleStatus.AVAILABLE
        self._vehicle_progress.pop(vehicle.id, None)

    def _generate_waste(self) -> None:
        for waste_point in self._state.waste_points.values():
            previous_load = waste_point.current_load
            waste_point.current_load += waste_point.generation_rate * self.tick_minutes
            self._record_overflow_transition(waste_point, previous_load)

    def _record_overflow_transition(
        self, waste_point, previous_load: float
    ) -> None:
        if previous_load < waste_point.capacity <= waste_point.current_load:
            if waste_point.id not in self._overflowing_waste_point_ids:
                self._overflow_count += 1
            self._overflowing_waste_point_ids.add(waste_point.id)
        elif waste_point.current_load < waste_point.capacity:
            self._overflowing_waste_point_ids.discard(waste_point.id)
        else:
            self._overflowing_waste_point_ids.add(waste_point.id)
