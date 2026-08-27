"""Stage-based, JSON-safe playback data for the fixed CityClean demo."""

from __future__ import annotations

from typing import Any

from cityclean_agent.agent.mock_event_agent import MockEventAgent
from cityclean_agent.demo import build_demo_state
from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus
from cityclean_agent.domain.models import CityEvent, CityState, DispatchPlan
from cityclean_agent.domain.task_builder import build_task_changes
from cityclean_agent.metrics.calculator import MetricsCalculator
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.optimizer.results import OptimizationResult, OptimizationStatus
from cityclean_agent.policy.mapper import (
    POLICY_PARAMETERS_BY_PROFILE,
    map_policy_parameters,
)
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile
from cityclean_agent.simulator.city_sim import CitySim, RuntimeStats
from cityclean_agent.verifier.plan_verifier import PlanVerifier, VerificationResult
from cityclean_agent.workflow import WorkflowStatus


SCHEMA_VERSION = "12A.3B"
SCENARIO_ID = "vehicle_breakdown_replan"


def run_demo_playback() -> dict[str, Any]:
    """Replay the fixed breakdown demo and return JSON-safe stage snapshots.

    The function uses the same public Core APIs and ordering as ``run_demo``.
    It does not alter the frozen demo or workflow contracts.
    """

    sim = CitySim(build_demo_state())
    initial_plan, initial_verification = _install_initial_plan(sim)
    frames = [
        _frame(
            "initial",
            sim,
            plan=_plan_payload(initial_plan),
            verifier=_verification_payload(initial_verification),
        )
    ]

    _advance(sim, tick_count=2)
    before_event_state = sim.get_state()
    incident = _build_breakdown_event(before_event_state)
    released_task_ids = _assigned_tasks_for_affected_vehicles(
        before_event_state, incident
    )
    frames.append(
        _frame("before_event", sim, plan=_plan_payload(before_event_state.active_plan))
    )

    if not sim.inject_event(incident):
        raise RuntimeError("fixed playback incident was unexpectedly ignored")
    frames.append(_frame("event_received", sim, event=_event_payload(incident)))

    sim.release_unstarted_tasks()
    released_state = sim.get_state()
    frames.append(
        _frame(
            "tasks_released",
            sim,
            plan=_plan_payload(released_state.active_plan),
            released_task_ids=released_task_ids,
            completed_task_ids=_completed_task_ids(released_state),
        )
    )

    replanning = _replan_after_injected_event(sim, incident)
    frames.append(
        _frame(
            "replanned",
            sim,
            workflow_status=WorkflowStatus.SUCCESS.value,
            policy_decision=_policy_payload(replanning["policy_decision"]),
            optimizer=_optimization_payload(replanning["optimization_result"]),
            verifier=_verification_payload(replanning["verification_result"]),
            plan=_plan_payload(replanning["plan"]),
            plan_changes=_plan_changes(initial_plan, replanning["plan"]),
        )
    )

    _advance(sim, tick_count=4)
    final_state = sim.get_state()
    frames.append(
        _frame(
            "final",
            sim,
            metrics=_metrics_payload(
                MetricsCalculator().calculate(final_state, sim.get_runtime_stats())
            ),
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": SCENARIO_ID,
        "frames": frames,
    }


def _install_initial_plan(sim: CitySim) -> tuple[DispatchPlan, VerificationResult]:
    result = ORToolsOptimizer().optimize(
        sim.get_state(), POLICY_PARAMETERS_BY_PROFILE[PolicyProfile.BALANCED]
    )
    if result.status is not OptimizationStatus.FEASIBLE or result.plan is None:
        raise RuntimeError(f"fixed playback initial plan is infeasible: {result.reason}")
    verification = PlanVerifier().verify(sim.get_state(), result.plan)
    if not verification.valid:
        raise RuntimeError("fixed playback initial plan failed verification")
    sim.install_plan(result.plan)
    return result.plan, verification


def _build_breakdown_event(state: CityState) -> CityEvent:
    affected_vehicle_id = "V01"
    return CityEvent(
        event_id="demo-breakdown-v01",
        event_type=CityEventType.VEHICLE_BREAKDOWN,
        timestamp=state.current_time,
        location=state.vehicles[affected_vehicle_id].current_node_id,
        description="Demo vehicle breakdown after the first collection task.",
        affected_entities=[affected_vehicle_id],
        severity=3,
        deadline=None,
    )


def _replan_after_injected_event(
    sim: CitySim, event: CityEvent
) -> dict[str, Any]:
    """Run the post-injection portion of the frozen workflow using public APIs."""

    decision = MockEventAgent().decide(event, sim.get_state())
    changes = build_task_changes(event, sim.get_state())
    sim.apply_task_changes(changes)

    optimization_result = ORToolsOptimizer().optimize(
        sim.get_state(), map_policy_parameters(decision)
    )
    if (
        optimization_result.status is not OptimizationStatus.FEASIBLE
        or optimization_result.plan is None
    ):
        raise RuntimeError(
            f"fixed playback replanning is infeasible: {optimization_result.reason}"
        )

    verification_result = PlanVerifier().verify(sim.get_state(), optimization_result.plan)
    if not verification_result.valid:
        raise RuntimeError("fixed playback replanning failed verification")
    sim.install_plan(optimization_result.plan)
    return {
        "policy_decision": decision,
        "optimization_result": optimization_result,
        "verification_result": verification_result,
        "plan": optimization_result.plan,
    }


def _advance(sim: CitySim, *, tick_count: int) -> None:
    for _ in range(tick_count):
        sim.step()


def _frame(step: str, sim: CitySim, **facts: Any) -> dict[str, Any]:
    state = sim.get_state()
    return {
        "step": step,
        "sim_time": state.current_time,
        "state": _state_payload(state),
        "runtime_stats": _runtime_stats_payload(sim.get_runtime_stats()),
        **facts,
    }


def _state_payload(state: CityState) -> dict[str, Any]:
    return {
        "current_time": state.current_time,
        "roads": [
            {
                "road_id": road.id,
                "from_node": road.from_node,
                "to_node": road.to_node,
                "distance": road.distance,
                "travel_time": road.travel_time,
                "status": road.status.value,
            }
            for road in state.road_network.roads
        ],
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
        "waste_points": [
            {
                "waste_point_id": point.id,
                "node_id": point.node_id,
                "current_load": point.current_load,
                "capacity": point.capacity,
                "generation_rate": point.generation_rate,
                "priority": point.priority,
            }
            for point in sorted(state.waste_points.values(), key=lambda point: point.id)
        ],
        "tasks": [
            {
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
            for task in sorted(state.tasks.values(), key=lambda task: task.task_id)
        ],
        "active_plan": _plan_payload(state.active_plan),
        "active_events": [
            _event_payload(event)
            for event in sorted(state.active_events.values(), key=lambda event: event.event_id)
        ],
    }


def _event_payload(event: CityEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp,
        "location": event.location,
        "description": event.description,
        "affected_entities": list(event.affected_entities),
        "severity": event.severity,
        "deadline": event.deadline,
        "metadata": dict(sorted(event.metadata.items())),
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


def _policy_payload(decision: PolicyDecision) -> dict[str, Any]:
    return {
        "risk_level": decision.risk_level,
        "reasoning_summary": decision.reasoning_summary,
        "response_deadline": decision.response_deadline,
        "priority_targets": list(decision.priority_targets),
        "policy_profile": decision.policy_profile.value,
        "constraints": list(decision.constraints),
    }


def _optimization_payload(result: OptimizationResult) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "reason": result.reason,
        "plan": _plan_payload(result.plan),
    }


def _verification_payload(result: VerificationResult) -> dict[str, Any]:
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


def _runtime_stats_payload(stats: RuntimeStats) -> dict[str, Any]:
    return {
        "total_distance": stats.total_distance,
        "overflow_count": stats.overflow_count,
    }


def _metrics_payload(metrics: Any) -> dict[str, Any]:
    return {
        "task_completion_rate": metrics.task_completion_rate,
        "urgent_task_completion_rate": metrics.urgent_task_completion_rate,
        "average_response_time": metrics.average_response_time,
        "overflow_count": metrics.overflow_count,
        "total_distance": metrics.total_distance,
    }


def _plan_changes(
    initial_plan: DispatchPlan, replanned_plan: DispatchPlan
) -> dict[str, Any]:
    before = _route_map(initial_plan)
    after = _route_map(replanned_plan)
    return {
        "previous_plan_id": initial_plan.plan_id,
        "new_plan_id": replanned_plan.plan_id,
        "changed_routes": [
            {
                "vehicle_id": vehicle_id,
                "before_task_sequence": before.get(vehicle_id, []),
                "after_task_sequence": after.get(vehicle_id, []),
            }
            for vehicle_id in sorted(set(before) | set(after))
            if before.get(vehicle_id) != after.get(vehicle_id)
        ],
    }


def _route_map(plan: DispatchPlan) -> dict[str, list[str]]:
    return {
        route.vehicle_id: list(route.task_sequence)
        for route in plan.vehicle_routes
    }


def _assigned_tasks_for_affected_vehicles(
    state: CityState, event: CityEvent
) -> list[str]:
    return sorted(
        {
            task_id
            for vehicle_id in event.affected_entities
            if vehicle_id in state.vehicles
            for task_id in state.vehicles[vehicle_id].assigned_tasks
            if task_id in state.tasks
            and state.tasks[task_id].status is ServiceTaskStatus.ASSIGNED
        }
    )


def _completed_task_ids(state: CityState) -> list[str]:
    return sorted(
        task.task_id
        for task in state.tasks.values()
        if task.status is ServiceTaskStatus.COMPLETED
    )
