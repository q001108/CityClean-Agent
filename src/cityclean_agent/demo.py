"""Deterministic command-line demonstration of the existing closed loop."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TextIO

from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import (
    CityEvent,
    CityState,
    DispatchPlan,
    Road,
    ServiceTask,
    TransferStation,
    Vehicle,
    WastePoint,
)
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.metrics.calculator import Metrics, MetricsCalculator
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.optimizer.results import OptimizationResult, OptimizationStatus
from cityclean_agent.policy.mapper import POLICY_PARAMETERS_BY_PROFILE
from cityclean_agent.policy.models import PolicyProfile
from cityclean_agent.simulator.city_sim import CitySim
from cityclean_agent.verifier.plan_verifier import PlanVerifier, VerificationResult
from cityclean_agent.workflow import WorkflowResult, WorkflowStatus, process_event


@dataclass(frozen=True, slots=True)
class DemoResult:
    """Business results exposed for deterministic demo tests."""

    initial_plan: DispatchPlan
    initial_verification: VerificationResult
    replanning_result: WorkflowResult
    incident_time: int
    released_task_ids: tuple[str, ...]
    completed_before_incident: tuple[str, ...]
    final_state: CityState
    final_metrics: Metrics


def run_demo(output: TextIO | None = None) -> DemoResult:
    """Run the fixed vehicle-breakdown scenario without external dependencies."""

    output = output or sys.stdout
    sim = CitySim(build_demo_state())
    _write_initial_state(output, sim.get_state())

    initial_result, initial_verification = _install_initial_plan(sim)
    assert initial_result.plan is not None
    _write_initial_dispatch(output, initial_result.plan, initial_verification)

    output.write("\n=== Simulation ===\n")
    _advance_and_report(sim, output, tick_count=2)
    pre_incident_state = sim.get_state()
    completed_before_incident = _completed_task_ids(pre_incident_state)
    released_task_ids = tuple(pre_incident_state.vehicles["V01"].assigned_tasks)
    if not completed_before_incident or not released_task_ids:
        raise RuntimeError("demo scenario did not reach the required pre-incident state")

    output.write("\n=== Incident ===\n")
    output.write(f"VEHICLE_BREAKDOWN: V01 at t={pre_incident_state.current_time}\n")
    output.write(f"Unstarted tasks released for replanning: {', '.join(released_task_ids)}\n")
    incident = CityEvent(
        event_id="demo-breakdown-v01",
        event_type=CityEventType.VEHICLE_BREAKDOWN,
        timestamp=pre_incident_state.current_time,
        location=pre_incident_state.vehicles["V01"].current_node_id,
        description="Demo vehicle breakdown after the first collection task.",
        affected_entities=["V01"],
        severity=3,
        deadline=None,
    )
    replanning_result = process_event(sim, incident)
    if replanning_result.status is not WorkflowStatus.SUCCESS:
        raise RuntimeError(f"demo replanning failed: {replanning_result.reason}")
    if replanning_result.plan is None or replanning_result.policy_decision is None:
        raise RuntimeError("successful demo replanning did not return its plan and policy")

    _write_policy(output, replanning_result)
    _write_replanning(output, replanning_result, sim.get_state())

    output.write("\n=== Continued Simulation ===\n")
    _advance_and_report(sim, output, tick_count=4)
    final_state = sim.get_state()
    final_metrics = MetricsCalculator().calculate(final_state, sim.get_runtime_stats())
    _write_final_metrics(output, final_metrics)

    return DemoResult(
        initial_plan=initial_result.plan,
        initial_verification=initial_verification,
        replanning_result=replanning_result,
        incident_time=pre_incident_state.current_time,
        released_task_ids=released_task_ids,
        completed_before_incident=completed_before_incident,
        final_state=final_state,
        final_metrics=final_metrics,
    )


def build_demo_state() -> CityState:
    """Build a small fixed city where V01 initially owns all service tasks."""

    waste_points = {
        "W01": WastePoint("W01", "B", 20, 6, 0, "mixed", "residential", 1),
        "W02": WastePoint("W02", "C", 20, 7, 0, "mixed", "school", 1),
        "W03": WastePoint("W03", "D", 20, 5, 0, "mixed", "market", 1),
    }
    tasks = {
        "T01": ServiceTask("T01", "demo-initial", "W01", 2, 1, None, created_at=0),
        "T02": ServiceTask("T02", "demo-initial", "W02", 2, 1, None, created_at=0),
        "T03": ServiceTask("T03", "demo-initial", "W03", 2, 1, None, created_at=0),
    }
    return CityState(
        current_time=0,
        waste_points=waste_points,
        vehicles={
            "V01": Vehicle("V01", "A", 8, 0, VehicleStatus.AVAILABLE, 30),
            "V02": Vehicle("V02", "Z", 8, 0, VehicleStatus.AVAILABLE, 30),
        },
        transfer_stations={
            "TS01": TransferStation("TS01", "D", 100),
        },
        road_network=RoadNetwork(
            [
                Road("AB", "A", "B", 1, 5),
                Road("BC", "B", "C", 1, 5),
                Road("CD", "C", "D", 1, 5),
                Road("ZC", "Z", "C", 20, 5),
            ]
        ),
        tasks=tasks,
    )


def _install_initial_plan(
    sim: CitySim,
) -> tuple[OptimizationResult, VerificationResult]:
    optimizer = ORToolsOptimizer()
    result = optimizer.optimize(
        sim.get_state(), POLICY_PARAMETERS_BY_PROFILE[PolicyProfile.BALANCED]
    )
    if result.status is not OptimizationStatus.FEASIBLE or result.plan is None:
        raise RuntimeError(f"demo initial dispatch is infeasible: {result.reason}")
    verification = PlanVerifier().verify(sim.get_state(), result.plan)
    if not verification.valid:
        raise RuntimeError("demo initial dispatch failed verification")
    sim.install_plan(result.plan)
    return result, verification


def _advance_and_report(sim: CitySim, output: TextIO, tick_count: int) -> None:
    for _ in range(tick_count):
        completed_before = set(_completed_task_ids(sim.get_state()))
        sim.step()
        state = sim.get_state()
        newly_completed = [
            task_id
            for task_id in _completed_task_ids(state)
            if task_id not in completed_before
        ]
        for task_id in newly_completed:
            task = state.tasks[task_id]
            output.write(f"Completed: {task_id} at t={task.completed_at}\n")


def _write_initial_state(output: TextIO, state: CityState) -> None:
    output.write("=== Initial City State ===\n")
    output.write(f"current_time: {state.current_time}\n")
    output.write("vehicles:\n")
    for vehicle in sorted(state.vehicles.values(), key=lambda item: item.id):
        output.write(
            f"  {vehicle.id}: node={vehicle.current_node_id}, load={vehicle.current_load}, "
            f"status={vehicle.status.value}\n"
        )
    output.write("waste points:\n")
    for point in sorted(state.waste_points.values(), key=lambda item: item.id):
        output.write(f"  {point.id}: load={point.current_load}/{point.capacity}\n")
    output.write("tasks:\n")
    for task in sorted(state.tasks.values(), key=lambda item: item.task_id):
        output.write(f"  {task.task_id}: target={task.target_id}, status={task.status.value}\n")


def _write_initial_dispatch(
    output: TextIO, plan: DispatchPlan, verification: VerificationResult
) -> None:
    output.write("\n=== Initial Dispatch ===\n")
    _write_plan(output, plan)
    output.write(f"Verifier: {'PASS' if verification.valid else 'FAIL'}\n")


def _write_policy(output: TextIO, result: WorkflowResult) -> None:
    decision = result.policy_decision
    assert decision is not None
    output.write("\n=== Policy ===\n")
    output.write(f"risk_level: {decision.risk_level}\n")
    output.write(f"policy_profile: {decision.policy_profile.value}\n")
    output.write(f"priority_targets: {', '.join(decision.priority_targets) or 'none'}\n")
    output.write(f"reasoning: {decision.reasoning_summary}\n")


def _write_replanning(
    output: TextIO, result: WorkflowResult, state: CityState
) -> None:
    output.write("\n=== Replanning ===\n")
    output.write(f"V01 status: {state.vehicles['V01'].status.value}\n")
    assert result.plan is not None
    _write_plan(output, result.plan)
    output.write(f"unassigned tasks: {', '.join(result.plan.unassigned_tasks) or 'none'}\n")
    verification = result.verification_result
    output.write(f"Verifier: {'PASS' if verification is not None and verification.valid else 'FAIL'}\n")


def _write_plan(output: TextIO, plan: DispatchPlan) -> None:
    for route in plan.vehicle_routes:
        tasks = ", ".join(route.task_sequence)
        arrivals = ", ".join(
            f"{task_id}@{arrival}"
            for task_id, arrival in route.planned_arrivals.items()
        )
        output.write(
            f"  {route.vehicle_id}: tasks=[{tasks}], planned_arrivals=[{arrivals}]\n"
        )


def _write_final_metrics(output: TextIO, metrics: Metrics) -> None:
    output.write("\n=== Final Metrics ===\n")
    output.write(f"task_completion_rate: {metrics.task_completion_rate:.2f}\n")
    output.write(f"urgent_task_completion_rate: {metrics.urgent_task_completion_rate:.2f}\n")
    output.write(f"average_response_time: {metrics.average_response_time:.2f}\n")
    output.write(f"overflow_count: {metrics.overflow_count}\n")
    output.write(f"total_distance: {metrics.total_distance:.2f}\n")


def _completed_task_ids(state: CityState) -> tuple[str, ...]:
    return tuple(
        sorted(
            task.task_id
            for task in state.tasks.values()
            if task.status is ServiceTaskStatus.COMPLETED
        )
    )
