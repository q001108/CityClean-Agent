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
from cityclean_agent.presentation import (
    EVENT_TYPE_LABELS,
    METRIC_LABELS,
    POLICY_PROFILE_LABELS,
    STATUS_LABELS,
    labeled,
    risk_label,
)
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

    output.write("\n=== 仿真执行 ===\n")
    _advance_and_report(sim, output, tick_count=2)
    pre_incident_state = sim.get_state()
    completed_before_incident = _completed_task_ids(pre_incident_state)
    released_task_ids = tuple(pre_incident_state.vehicles["V01"].assigned_tasks)
    if not completed_before_incident or not released_task_ids:
        raise RuntimeError("演示场景未达到预期的事件前状态")

    output.write("\n=== 突发事件 ===\n")
    output.write(
        f"{labeled(CityEventType.VEHICLE_BREAKDOWN, EVENT_TYPE_LABELS)}："
        f"V01，模拟分钟={pre_incident_state.current_time}\n"
    )
    output.write(f"为重规划释放的未开始任务：{', '.join(released_task_ids)}\n")
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
        raise RuntimeError(f"演示重规划失败：{replanning_result.reason}")
    if replanning_result.plan is None or replanning_result.policy_decision is None:
        raise RuntimeError("成功的演示重规划未返回计划和治理策略")

    _write_policy(output, replanning_result)
    _write_replanning(output, replanning_result, sim.get_state())

    output.write("\n=== 继续仿真 ===\n")
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
        raise RuntimeError(f"演示初始调度不可行：{result.reason}")
    verification = PlanVerifier().verify(sim.get_state(), result.plan)
    if not verification.valid:
        raise RuntimeError("演示初始调度未通过独立验证")
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
            output.write(f"任务完成：{task_id}，模拟分钟={task.completed_at}\n")


def _write_initial_state(output: TextIO, state: CityState) -> None:
    output.write("=== 初始城市状态 ===\n")
    output.write(f"当前模拟时间：{state.current_time}\n")
    output.write("车辆：\n")
    for vehicle in sorted(state.vehicles.values(), key=lambda item: item.id):
        output.write(
            f"  {vehicle.id}：节点={vehicle.current_node_id}，载荷={vehicle.current_load}，"
            f"状态={labeled(vehicle.status, STATUS_LABELS)}\n"
        )
    output.write("垃圾点：\n")
    for point in sorted(state.waste_points.values(), key=lambda item: item.id):
        output.write(f"  {point.id}：载荷={point.current_load}/{point.capacity}\n")
    output.write("任务：\n")
    for task in sorted(state.tasks.values(), key=lambda item: item.task_id):
        output.write(
            f"  {task.task_id}：目标={task.target_id}，"
            f"状态={labeled(task.status, STATUS_LABELS)}\n"
        )


def _write_initial_dispatch(
    output: TextIO, plan: DispatchPlan, verification: VerificationResult
) -> None:
    output.write("\n=== 初始调度 ===\n")
    _write_plan(output, plan)
    output.write(f"独立验证：{'通过' if verification.valid else '失败'}\n")


def _write_policy(output: TextIO, result: WorkflowResult) -> None:
    decision = result.policy_decision
    assert decision is not None
    output.write("\n=== 治理策略 ===\n")
    output.write(f"风险等级：{risk_label(decision.risk_level)}\n")
    output.write(f"治理策略：{labeled(decision.policy_profile, POLICY_PROFILE_LABELS)}\n")
    output.write(
        "治理响应时限（response_deadline）："
        f"{decision.response_deadline if decision.response_deadline is not None else '无'}\n"
    )
    output.write(f"优先目标：{', '.join(decision.priority_targets) or '无'}\n")
    output.write(f"治理理由：{decision.reasoning_summary}\n")


def _write_replanning(
    output: TextIO, result: WorkflowResult, state: CityState
) -> None:
    output.write("\n=== 重规划 ===\n")
    output.write(f"V01 状态：{labeled(state.vehicles['V01'].status, STATUS_LABELS)}\n")
    assert result.plan is not None
    _write_plan(output, result.plan)
    output.write(f"未分配任务：{', '.join(result.plan.unassigned_tasks) or '无'}\n")
    verification = result.verification_result
    output.write(
        f"独立验证：{'通过' if verification is not None and verification.valid else '失败'}\n"
    )


def _write_plan(output: TextIO, plan: DispatchPlan) -> None:
    for route in plan.vehicle_routes:
        tasks = ", ".join(route.task_sequence)
        arrivals = ", ".join(
            f"{task_id}@{arrival}"
            for task_id, arrival in route.planned_arrivals.items()
        )
        output.write(
            f"  {route.vehicle_id}：任务序列=[{tasks}]，计划到达时刻=[{arrivals}]\n"
        )


def _write_final_metrics(output: TextIO, metrics: Metrics) -> None:
    output.write("\n=== 最终指标 ===\n")
    output.write(f"{METRIC_LABELS['task_completion_rate']}（task_completion_rate）：{metrics.task_completion_rate:.2f}\n")
    output.write(f"{METRIC_LABELS['urgent_task_completion_rate']}（urgent_task_completion_rate）：{metrics.urgent_task_completion_rate:.2f}\n")
    output.write(f"{METRIC_LABELS['average_response_time']}（average_response_time）：{metrics.average_response_time:.2f}\n")
    output.write(f"{METRIC_LABELS['overflow_count']}（overflow_count）：{metrics.overflow_count}\n")
    output.write(f"{METRIC_LABELS['total_distance']}（total_distance）：{metrics.total_distance:.2f}\n")


def _completed_task_ids(state: CityState) -> tuple[str, ...]:
    return tuple(
        sorted(
            task.task_id
            for task in state.tasks.values()
            if task.status is ServiceTaskStatus.COMPLETED
        )
    )
