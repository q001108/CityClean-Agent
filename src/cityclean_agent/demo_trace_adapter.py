"""Read-only presentation trace projection for the fixed v0.1 demo.

This module deliberately consumes :class:`DemoResult` rather than changing the
workflow or simulator contracts.  Its output contains only an explicit
JSON-safe whitelist of judge-facing fields.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from cityclean_agent.demo import DemoResult
from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import CityEvent, DispatchPlan, ServiceTask
from cityclean_agent.optimizer.results import OptimizationResult
from cityclean_agent.policy.models import PolicyDecision
from cityclean_agent.verifier.plan_verifier import VerificationResult


SCHEMA_VERSION = "12A.1"
SCENARIO_ID = "vehicle_breakdown_replan"
NOT_RECORDED_IN_BASELINE = "not_recorded_in_baseline"


def build_demo_trace(result: DemoResult) -> dict[str, Any]:
    """Return a stable, JSON-serializable visualization trace for ``run_demo``.

    The frozen ``DemoResult`` intentionally does not retain the initial
    ``OptimizationResult`` or TaskBuilder output.  Those unavailable values are
    marked explicitly instead of reconstructed or inferred.
    """

    event = _incident_event(result)
    replanning = result.replanning_result

    return {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": SCENARIO_ID,
        "timeline": [
            {
                "step": "initial_plan",
                "sim_time": 0,
                "optimizer": _initial_optimizer_payload(result.initial_plan),
                "verifier": _verification_payload(result.initial_verification),
            },
            {
                "step": "event_received",
                "sim_time": result.incident_time,
                "event": _event_payload(event),
            },
            {
                "step": "policy_decided",
                "sim_time": result.incident_time,
                "policy_decision": _policy_payload(replanning.policy_decision),
            },
            {
                "step": "tasks_prepared",
                "sim_time": result.incident_time,
                "task_builder": _task_builder_payload(event),
                "released_task_ids": list(result.released_task_ids),
            },
            {
                "step": "replanned",
                "sim_time": result.incident_time,
                "workflow_status": replanning.status.value,
                "optimizer": _optimization_payload(
                    replanning.optimization_result, replanning.plan
                ),
                "verifier": _verification_payload(replanning.verification_result),
                "plan_changes": _plan_changes(result.initial_plan, replanning.plan),
            },
            {
                "step": "simulation_finished",
                "sim_time": result.final_state.current_time,
                "citysim": _citysim_payload(result),
                "metrics": _metrics_payload(result),
            },
        ],
    }


def _incident_event(result: DemoResult) -> CityEvent | None:
    """Locate the exact injected demo event retained in the final snapshot."""

    matching_events = [
        event
        for event in result.final_state.active_events.values()
        if event.timestamp == result.incident_time
    ]
    return min(matching_events, key=lambda event: event.event_id, default=None)


def _initial_optimizer_payload(plan: DispatchPlan) -> dict[str, Any]:
    """Represent the initial plan without inventing discarded optimizer data."""

    return {
        "status": NOT_RECORDED_IN_BASELINE,
        "reason": NOT_RECORDED_IN_BASELINE,
        "plan": _plan_payload(plan),
    }


def _optimization_payload(
    result: OptimizationResult | None, plan: DispatchPlan | None
) -> dict[str, Any]:
    if result is None:
        return {
            "status": NOT_RECORDED_IN_BASELINE,
            "reason": NOT_RECORDED_IN_BASELINE,
            "plan": _plan_payload(plan),
        }
    return {
        "status": result.status.value,
        "reason": result.reason,
        "plan": _plan_payload(result.plan if result.plan is not None else plan),
    }


def _plan_payload(plan: DispatchPlan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "plan_id": plan.plan_id,
        "vehicle_routes": [
            {
                "vehicle_id": route.vehicle_id,
                "task_sequence": list(route.task_sequence),
                "planned_arrivals": [
                    {
                        "task_id": task_id,
                        "arrival_time": route.planned_arrivals[task_id],
                    }
                    for task_id in route.task_sequence
                    if task_id in route.planned_arrivals
                ],
            }
            for route in sorted(plan.vehicle_routes, key=lambda route: route.vehicle_id)
        ],
        "unassigned_tasks": sorted(plan.unassigned_tasks),
    }


def _verification_payload(
    result: VerificationResult | None,
) -> dict[str, Any]:
    if result is None:
        return {
            "valid": None,
            "violations": NOT_RECORDED_IN_BASELINE,
        }
    return {
        "valid": result.valid,
        "violations": [
            {
                "violation_type": violation.violation_type,
                "message": violation.message,
                "vehicle_id": violation.vehicle_id,
                "task_id": violation.task_id,
            }
            for violation in result.violations
        ],
    }


def _event_payload(event: CityEvent | None) -> dict[str, Any]:
    if event is None:
        return {
            "event_id": None,
            "event_type": None,
            "timestamp": None,
            "location": None,
            "description": None,
            "severity": None,
            "deadline": None,
        }
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp,
        "location": event.location,
        "description": event.description,
        "severity": event.severity,
        "deadline": event.deadline,
    }


def _policy_payload(decision: PolicyDecision | None) -> dict[str, Any]:
    if decision is None:
        return {
            "risk_level": None,
            "reasoning_summary": None,
            "response_deadline": None,
            "priority_targets": None,
            "policy_profile": None,
            "constraints": None,
        }
    return {
        "risk_level": decision.risk_level,
        "reasoning_summary": decision.reasoning_summary,
        "response_deadline": decision.response_deadline,
        "priority_targets": list(decision.priority_targets),
        "policy_profile": decision.policy_profile.value,
        "constraints": list(decision.constraints),
    }


def _task_builder_payload(event: CityEvent | None) -> dict[str, Any]:
    """Describe only the TaskBuilder output guaranteed by this fixed scenario."""

    if event is not None and event.event_type is CityEventType.VEHICLE_BREAKDOWN:
        return {
            "created_tasks": [],
            "updated_tasks": [],
            "message": "no new tasks created",
        }
    return {
        "created_tasks": NOT_RECORDED_IN_BASELINE,
        "updated_tasks": NOT_RECORDED_IN_BASELINE,
        "message": NOT_RECORDED_IN_BASELINE,
    }


def _plan_changes(
    initial_plan: DispatchPlan, replanned_plan: DispatchPlan | None
) -> dict[str, Any]:
    before = _route_map(initial_plan)
    after = _route_map(replanned_plan)
    changed_vehicle_ids = sorted(
        vehicle_id
        for vehicle_id in set(before) | set(after)
        if before.get(vehicle_id) != after.get(vehicle_id)
    )
    return {
        "previous_plan_id": initial_plan.plan_id,
        "new_plan_id": replanned_plan.plan_id if replanned_plan is not None else None,
        "changed_routes": [
            {
                "vehicle_id": vehicle_id,
                "before_task_sequence": before.get(vehicle_id, []),
                "after_task_sequence": after.get(vehicle_id, []),
            }
            for vehicle_id in changed_vehicle_ids
        ],
    }


def _route_map(plan: DispatchPlan | None) -> dict[str, list[str]]:
    if plan is None:
        return {}
    return {
        route.vehicle_id: list(route.task_sequence)
        for route in plan.vehicle_routes
    }


def _citysim_payload(result: DemoResult) -> dict[str, Any]:
    state = result.final_state
    vehicle_status_counts = Counter(vehicle.status.value for vehicle in state.vehicles.values())
    task_status_counts = Counter(task.status.value for task in state.tasks.values())
    return {
        "current_time": state.current_time,
        "vehicles": [
            {
                "vehicle_id": vehicle.id,
                "current_node_id": vehicle.current_node_id,
                "current_load": vehicle.current_load,
                "capacity": vehicle.capacity,
                "status": vehicle.status.value,
                "assigned_tasks": list(vehicle.assigned_tasks),
            }
            for vehicle in sorted(state.vehicles.values(), key=lambda vehicle: vehicle.id)
        ],
        "vehicle_status_counts": _status_counts(VehicleStatus, vehicle_status_counts),
        "tasks": [
            _task_payload(task)
            for task in sorted(state.tasks.values(), key=lambda task: task.task_id)
        ],
        "task_status_counts": _status_counts(ServiceTaskStatus, task_status_counts),
        "waste_points": [
            {
                "waste_point_id": point.id,
                "node_id": point.node_id,
                "current_load": point.current_load,
                "capacity": point.capacity,
            }
            for point in sorted(state.waste_points.values(), key=lambda point: point.id)
        ],
        "active_event_ids": sorted(state.active_events),
        "active_plan": _plan_payload(state.active_plan),
    }


def _status_counts(enum_type: type[VehicleStatus] | type[ServiceTaskStatus], counts: Counter[str]) -> dict[str, int]:
    return {status.value: counts[status.value] for status in enum_type}


def _task_payload(task: ServiceTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "source_event_id": task.source_event_id,
        "target_id": task.target_id,
        "demand": task.demand,
        "priority": task.priority,
        "deadline": task.deadline,
        "status": task.status.value,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
    }


def _metrics_payload(result: DemoResult) -> dict[str, Any]:
    metrics = result.final_metrics
    return {
        "task_completion_rate": metrics.task_completion_rate,
        "urgent_task_completion_rate": metrics.urgent_task_completion_rate,
        "average_response_time": metrics.average_response_time,
        "overflow_count": metrics.overflow_count,
        "total_distance": metrics.total_distance,
    }
