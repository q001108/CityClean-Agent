"""Minimal deterministic open-route CVRP solver backed by OR-Tools."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from cityclean_agent.domain.enums import ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.constants import MUST_SERVE_PRIORITY_THRESHOLD
from cityclean_agent.domain.models import (
    CityState,
    DispatchPlan,
    ServiceTask,
    Vehicle,
    VehicleRoute,
)
from cityclean_agent.policy.models import PolicyParameters
from cityclean_agent.optimizer.results import OptimizationResult, OptimizationStatus


_CAPACITY_SCALE = 1_000
_UNREACHABLE_COST = 10**8
_MAX_ROUTE_TIME = 10**9


@dataclass(frozen=True, slots=True)
class _RoutingNode:
    """A task, vehicle start, or dummy route end in the OR-Tools model."""

    location_id: str | None
    task: ServiceTask | None = None
    is_end: bool = False


class ORToolsOptimizer:
    """Solve pending tasks without mutating the supplied CityState snapshot."""

    def optimize(
        self,
        state: CityState,
        parameters: PolicyParameters,
        previous_plan: DispatchPlan | None = None,
    ) -> OptimizationResult:
        """Return an open-route DispatchPlan or an explicit infeasible result."""

        del previous_plan  # Reassignment cost belongs to the later replanning phase.

        pending_tasks = sorted(
            (
                task
                for task in state.tasks.values()
                if task.status is ServiceTaskStatus.PENDING
            ),
            key=lambda task: task.task_id,
        )
        available_vehicles = sorted(
            (
                vehicle
                for vehicle in state.vehicles.values()
                if vehicle.status is VehicleStatus.AVAILABLE
            ),
            key=lambda vehicle: vehicle.id,
        )
        if not pending_tasks:
            return self._feasible_plan([])

        eligible_tasks, unassigned_tasks, infeasible = self._screen_tasks(
            state, pending_tasks, available_vehicles
        )
        if infeasible is not None:
            return self._infeasible(infeasible)
        if not eligible_tasks:
            return self._feasible_plan([], unassigned_tasks)

        nodes, starts, ends = self._build_nodes(eligible_tasks, available_vehicles)
        manager = pywrapcp.RoutingIndexManager(
            len(nodes), len(available_vehicles), starts, ends
        )
        routing = pywrapcp.RoutingModel(manager)

        distance_transit = self._distance_callback(manager, nodes, state, parameters)
        distance_callback_index = routing.RegisterTransitCallback(distance_transit)
        routing.SetArcCostEvaluatorOfAllVehicles(distance_callback_index)

        demand_callback = routing.RegisterUnaryTransitCallback(
            self._demand_callback(manager, nodes)
        )
        routing.AddDimensionWithVehicleCapacity(
            demand_callback,
            0,
            [_scaled(vehicle.remaining_capacity) for vehicle in available_vehicles],
            True,
            "Capacity",
        )

        time_transit = self._time_callback(manager, nodes, state)
        time_callback_index = routing.RegisterTransitCallback(time_transit)
        routing.AddDimension(time_callback_index, 0, _MAX_ROUTE_TIME, True, "Time")
        time_dimension = routing.GetDimensionOrDie("Time")

        task_node_indices = {
            task.task_id: node_index
            for node_index, node in enumerate(nodes)
            if node.task is not None
            for task in (node.task,)
        }
        for task in eligible_tasks:
            routing_index = manager.NodeToIndex(task_node_indices[task.task_id])
            if _is_required(task):
                if task.deadline is not None:
                    time_dimension.CumulVar(routing_index).SetMax(
                        max(0, task.deadline - state.current_time)
                    )
                time_dimension.SetCumulVarSoftUpperBound(
                    routing_index,
                    0,
                    parameters.lateness_weight,
                )
            else:
                priority_factor = _priority_factor(task)
                routing.AddDisjunction(
                    [routing_index],
                    parameters.unserved_task_penalty * priority_factor,
                )
                if task.deadline is not None:
                    time_dimension.SetCumulVarSoftUpperBound(
                        routing_index,
                        max(0, task.deadline - state.current_time),
                        parameters.lateness_weight * priority_factor,
                    )

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.use_full_propagation = True
        solution = routing.SolveWithParameters(search_parameters)
        if solution is None:
            return self._infeasible("REQUIRED_TASKS_UNASSIGNABLE")

        return self._build_result(
            state,
            routing,
            manager,
            solution,
            time_dimension,
            nodes,
            available_vehicles,
            eligible_tasks,
            unassigned_tasks,
        )

    def _screen_tasks(
        self,
        state: CityState,
        tasks: list[ServiceTask],
        vehicles: list[Vehicle],
    ) -> tuple[list[ServiceTask], list[str], str | None]:
        eligible_tasks: list[ServiceTask] = []
        unassigned_tasks: list[str] = []
        for task in tasks:
            reachable_vehicles = [
                vehicle
                for vehicle in vehicles
                if vehicle.remaining_capacity >= task.demand
                and state.road_network.shortest_path(
                    vehicle.current_node_id,
                    state.waste_points[task.target_id].node_id,
                )
                is not None
            ]
            if not reachable_vehicles:
                if _is_required(task):
                    if not vehicles:
                        return [], [], "REQUIRED_TASK_NO_AVAILABLE_VEHICLE"
                    if not any(
                        vehicle.remaining_capacity >= task.demand for vehicle in vehicles
                    ):
                        return [], [], "REQUIRED_TASK_CAPACITY_EXCEEDED"
                    return [], [], "REQUIRED_TASK_UNREACHABLE"
                unassigned_tasks.append(task.task_id)
                continue

            if task.deadline is not None and _is_required(task):
                earliest_completion = min(
                    state.current_time
                    + state.road_network.shortest_path(
                        vehicle.current_node_id,
                        state.waste_points[task.target_id].node_id,
                    ).total_travel_time
                    + task.service_duration_min
                    for vehicle in reachable_vehicles
                )
                if earliest_completion > task.deadline:
                    return [], [], "REQUIRED_TASK_DEADLINE_UNACHIEVABLE"
            eligible_tasks.append(task)
        return eligible_tasks, unassigned_tasks, None

    def _build_nodes(
        self, tasks: list[ServiceTask], vehicles: list[Vehicle]
    ) -> tuple[list[_RoutingNode], list[int], list[int]]:
        nodes = [
            _RoutingNode(location_id=None, task=task)
            for task in tasks
        ]
        starts = []
        ends = []
        for vehicle in vehicles:
            starts.append(len(nodes))
            nodes.append(_RoutingNode(location_id=vehicle.current_node_id))
        for _ in vehicles:
            ends.append(len(nodes))
            nodes.append(_RoutingNode(location_id=None, is_end=True))
        return nodes, starts, ends

    def _distance_callback(
        self,
        manager: pywrapcp.RoutingIndexManager,
        nodes: list[_RoutingNode],
        state: CityState,
        parameters: PolicyParameters,
    ):
        @lru_cache(maxsize=None)
        def distance_between(from_location: str, to_location: str) -> int:
            path = state.road_network.shortest_path(from_location, to_location)
            if path is None:
                return _UNREACHABLE_COST
            if path.total_distance == 0:
                return 0
            return max(1, int(round(path.total_distance))) * parameters.distance_weight

        def callback(from_index: int, to_index: int) -> int:
            from_node = nodes[manager.IndexToNode(from_index)]
            to_node = nodes[manager.IndexToNode(to_index)]
            if from_node.is_end or to_node.is_end:
                return 0
            return distance_between(
                _node_location(from_node, state), _node_location(to_node, state)
            )

        return callback

    def _time_callback(
        self,
        manager: pywrapcp.RoutingIndexManager,
        nodes: list[_RoutingNode],
        state: CityState,
    ):
        @lru_cache(maxsize=None)
        def travel_time_between(from_location: str, to_location: str) -> int:
            path = state.road_network.shortest_path(from_location, to_location)
            return _UNREACHABLE_COST if path is None else path.total_travel_time

        def callback(from_index: int, to_index: int) -> int:
            from_node = nodes[manager.IndexToNode(from_index)]
            to_node = nodes[manager.IndexToNode(to_index)]
            if from_node.is_end or to_node.is_end:
                return 0
            service_time = to_node.task.service_duration_min if to_node.task else 0
            return travel_time_between(
                _node_location(from_node, state), _node_location(to_node, state)
            ) + service_time

        return callback

    def _demand_callback(
        self,
        manager: pywrapcp.RoutingIndexManager,
        nodes: list[_RoutingNode],
    ):
        def callback(index: int) -> int:
            task = nodes[manager.IndexToNode(index)].task
            return 0 if task is None else _scaled(task.demand)

        return callback

    def _build_result(
        self,
        state: CityState,
        routing: pywrapcp.RoutingModel,
        manager: pywrapcp.RoutingIndexManager,
        solution: pywrapcp.Assignment,
        time_dimension: pywrapcp.RoutingDimension,
        nodes: list[_RoutingNode],
        vehicles: list[Vehicle],
        tasks: list[ServiceTask],
        pre_unassigned_task_ids: list[str],
    ) -> OptimizationResult:
        task_node_indices = {
            node.task.task_id: node_index
            for node_index, node in enumerate(nodes)
            if node.task is not None
        }
        dropped_task_ids = {
            task.task_id
            for task in tasks
            if solution.Value(
                routing.NextVar(manager.NodeToIndex(task_node_indices[task.task_id]))
            )
            == manager.NodeToIndex(task_node_indices[task.task_id])
        }
        if any(_is_required(task) and task.task_id in dropped_task_ids for task in tasks):
            return self._infeasible("REQUIRED_TASKS_UNASSIGNABLE")

        routes: list[VehicleRoute] = []
        assigned_task_ids: set[str] = set()
        for vehicle_index, vehicle in enumerate(vehicles):
            index = routing.Start(vehicle_index)
            task_sequence: list[str] = []
            planned_arrivals: dict[str, int] = {}
            while not routing.IsEnd(index):
                next_index = solution.Value(routing.NextVar(index))
                if routing.IsEnd(next_index):
                    break
                from_node = nodes[manager.IndexToNode(index)]
                to_node = nodes[manager.IndexToNode(next_index)]
                if (
                    state.road_network.shortest_path(
                        _node_location(from_node, state),
                        _node_location(to_node, state),
                    )
                    is None
                ):
                    return self._infeasible("ROUTING_USED_UNREACHABLE_ROAD")
                task = to_node.task
                if task is not None:
                    task_sequence.append(task.task_id)
                    assigned_task_ids.add(task.task_id)
                    planned_arrivals[task.task_id] = (
                        state.current_time
                        + solution.Value(time_dimension.CumulVar(next_index))
                        - task.service_duration_min
                    )
                index = next_index
            if task_sequence:
                routes.append(
                    VehicleRoute(
                        vehicle_id=vehicle.id,
                        task_sequence=task_sequence,
                        planned_arrivals=planned_arrivals,
                    )
                )

        missing_required = [
            task.task_id
            for task in tasks
            if _is_required(task) and task.task_id not in assigned_task_ids
        ]
        if missing_required:
            return self._infeasible("REQUIRED_TASKS_UNASSIGNABLE")

        return self._feasible_plan(
            routes,
            sorted(set(pre_unassigned_task_ids) | dropped_task_ids),
        )

    def _feasible_plan(
        self,
        routes: list[VehicleRoute],
        unassigned_tasks: list[str] | None = None,
    ) -> OptimizationResult:
        return OptimizationResult(
            status=OptimizationStatus.FEASIBLE,
            plan=DispatchPlan(
                plan_id="dispatch-plan",
                vehicle_routes=routes,
                unassigned_tasks=unassigned_tasks or [],
            ),
        )

    def _infeasible(self, reason: str) -> OptimizationResult:
        return OptimizationResult(status=OptimizationStatus.INFEASIBLE, reason=reason)


def _node_location(node: _RoutingNode, state: CityState) -> str:
    if node.location_id is not None:
        return node.location_id
    assert node.task is not None
    return state.waste_points[node.task.target_id].node_id


def _is_required(task: ServiceTask) -> bool:
    return task.priority >= MUST_SERVE_PRIORITY_THRESHOLD


def _priority_factor(task: ServiceTask) -> int:
    """Keep zero-priority tasks subject to the profile's base soft costs."""

    return max(1, task.priority)


def _scaled(value: float) -> int:
    return int(round(value * _CAPACITY_SCALE))
