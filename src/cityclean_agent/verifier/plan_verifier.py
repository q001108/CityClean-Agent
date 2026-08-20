"""Independent, deterministic validation of a proposed DispatchPlan."""

from __future__ import annotations

from dataclasses import dataclass

from cityclean_agent.domain.constants import MUST_SERVE_PRIORITY_THRESHOLD
from cityclean_agent.domain.enums import ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import CityState, DispatchPlan, ServiceTask


@dataclass(frozen=True, slots=True)
class Violation:
    """One independently observed plan-constraint violation."""

    violation_type: str
    message: str
    vehicle_id: str | None = None
    task_id: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """The non-mutating result of validating one DispatchPlan."""

    valid: bool
    violations: tuple[Violation, ...]


class PlanVerifier:
    """Audit routes against current CityState without repairing the plan."""

    def verify(self, state: CityState, plan: DispatchPlan) -> VerificationResult:
        """Independently recompute route feasibility and return all violations."""

        violations: list[Violation] = []
        assigned_task_ids: set[str] = set()

        for route in plan.vehicle_routes:
            vehicle = state.vehicles.get(route.vehicle_id)
            if vehicle is None:
                violations.append(
                    Violation(
                        "vehicle_exists",
                        "route references an unknown vehicle",
                        vehicle_id=route.vehicle_id,
                    )
                )
            elif vehicle.status is not VehicleStatus.AVAILABLE:
                violations.append(
                    Violation(
                        "vehicle_available",
                        "route vehicle is not AVAILABLE",
                        vehicle_id=route.vehicle_id,
                    )
                )

            route_task_ids: set[str] = set()
            current_node_id = vehicle.current_node_id if vehicle is not None else None
            completion_time = state.current_time
            accumulated_load = vehicle.current_load if vehicle is not None else 0.0

            for task_id in route.task_sequence:
                if task_id in route_task_ids:
                    violations.append(
                        Violation(
                            "duplicate_assignment",
                            "task appears more than once in one vehicle route",
                            vehicle_id=route.vehicle_id,
                            task_id=task_id,
                        )
                    )
                elif task_id in assigned_task_ids:
                    violations.append(
                        Violation(
                            "duplicate_assignment",
                            "task is assigned to more than one vehicle route",
                            vehicle_id=route.vehicle_id,
                            task_id=task_id,
                        )
                    )
                route_task_ids.add(task_id)
                assigned_task_ids.add(task_id)

                task = state.tasks.get(task_id)
                if task is None:
                    violations.append(
                        Violation(
                            "task_exists",
                            "route references an unknown task",
                            vehicle_id=route.vehicle_id,
                            task_id=task_id,
                        )
                    )
                    continue
                if task.status is not ServiceTaskStatus.PENDING:
                    violations.append(
                        Violation(
                            "task_status_valid",
                            "only PENDING tasks may enter a new route",
                            vehicle_id=route.vehicle_id,
                            task_id=task_id,
                        )
                    )
                if current_node_id is None:
                    continue

                target = state.waste_points.get(task.target_id)
                if target is None:
                    violations.append(
                        Violation(
                            "task_target_exists",
                            "task target is not an existing WastePoint",
                            vehicle_id=route.vehicle_id,
                            task_id=task_id,
                        )
                    )
                    continue

                path = state.road_network.shortest_path(current_node_id, target.node_id)
                if path is None:
                    violations.append(
                        Violation(
                            "road_accessible",
                            "task target is unreachable on the current road network",
                            vehicle_id=route.vehicle_id,
                            task_id=task_id,
                        )
                    )
                    continue

                arrival_time = completion_time + path.total_travel_time
                completion_time = arrival_time + task.service_duration_min
                accumulated_load += task.demand
                if vehicle is not None and accumulated_load > vehicle.capacity:
                    violations.append(
                        Violation(
                            "capacity_valid",
                            "route demand exceeds vehicle remaining capacity",
                            vehicle_id=route.vehicle_id,
                            task_id=task_id,
                        )
                    )
                if (
                    task.priority >= MUST_SERVE_PRIORITY_THRESHOLD
                    and task.deadline is not None
                    and completion_time > task.deadline
                ):
                    violations.append(
                        Violation(
                            "deadline_valid",
                            "required task service completion exceeds its deadline",
                            vehicle_id=route.vehicle_id,
                            task_id=task_id,
                        )
                    )
                if task_id in route.planned_arrivals and (
                    route.planned_arrivals[task_id] != arrival_time
                ):
                    violations.append(
                        Violation(
                            "planned_arrivals_consistent",
                            "planned arrival does not match independently computed arrival ETA",
                            vehicle_id=route.vehicle_id,
                            task_id=task_id,
                        )
                    )
                current_node_id = target.node_id

        self._verify_unassigned_tasks(
            state, plan, assigned_task_ids, violations
        )
        self._verify_required_tasks_are_present(state, assigned_task_ids, violations)
        return VerificationResult(valid=not violations, violations=tuple(violations))

    def _verify_unassigned_tasks(
        self,
        state: CityState,
        plan: DispatchPlan,
        assigned_task_ids: set[str],
        violations: list[Violation],
    ) -> None:
        for task_id in plan.unassigned_tasks:
            task = state.tasks.get(task_id)
            if task is None:
                violations.append(
                    Violation(
                        "task_exists",
                        "unassigned task list references an unknown task",
                        task_id=task_id,
                    )
                )
                continue
            if task_id in assigned_task_ids:
                violations.append(
                    Violation(
                        "assignment_unassigned_conflict",
                        "task cannot be both assigned and unassigned",
                        task_id=task_id,
                    )
                )
            if task.priority >= MUST_SERVE_PRIORITY_THRESHOLD:
                violations.append(
                    Violation(
                        "must_serve_unassigned",
                        "required task cannot be left unassigned",
                        task_id=task_id,
                    )
                )

    def _verify_required_tasks_are_present(
        self,
        state: CityState,
        assigned_task_ids: set[str],
        violations: list[Violation],
    ) -> None:
        for task in sorted(state.tasks.values(), key=lambda item: item.task_id):
            if (
                task.status is ServiceTaskStatus.PENDING
                and task.priority >= MUST_SERVE_PRIORITY_THRESHOLD
                and task.task_id not in assigned_task_ids
            ):
                violations.append(
                    Violation(
                        "must_serve_missing",
                        "required pending task is absent from all routes",
                        task_id=task.task_id,
                    )
                )
