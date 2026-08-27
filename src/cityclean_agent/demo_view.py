"""Pure presentation data helpers for the fixed workflow visualization demo."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cityclean_agent.demo_trace_adapter import NOT_RECORDED_IN_BASELINE
from cityclean_agent.presentation import (
    EVENT_TYPE_LABELS,
    METRIC_LABELS,
    POLICY_PROFILE_LABELS,
    STATUS_LABELS,
    labeled,
    risk_label,
)


WORKFLOW_NODE_LABELS = (
    "事件输入",
    "风险研判",
    "治理策略",
    "任务调整",
    "动态调度",
    "独立验证",
    "仿真执行",
    "指标反馈",
)


def build_demo_view(trace: Mapping[str, Any]) -> dict[str, Any]:
    """Project a DemoTrace into small, Chinese judge-facing view models.

    Missing baseline data is kept explicit in prose; this function does not
    infer optimizer outcomes or calculate new operational metrics.
    """

    timeline = _timeline_by_step(trace)
    initial = _mapping(timeline.get("initial_plan"))
    event_step = _mapping(timeline.get("event_received"))
    policy_step = _mapping(timeline.get("policy_decided"))
    tasks_step = _mapping(timeline.get("tasks_prepared"))
    replanned = _mapping(timeline.get("replanned"))
    finished = _mapping(timeline.get("simulation_finished"))

    event = _mapping(event_step.get("event"))
    policy = _mapping(policy_step.get("policy_decision"))
    task_builder = _mapping(tasks_step.get("task_builder"))
    initial_optimizer = _mapping(initial.get("optimizer"))
    replanned_optimizer = _mapping(replanned.get("optimizer"))
    final_citysim = _mapping(finished.get("citysim"))

    return {
        "scenario_title": "车辆故障动态重规划",
        "workflow_nodes": _workflow_nodes(event, policy, task_builder, replanned),
        "event": _event_view(event, event_step.get("sim_time")),
        "policy": _policy_view(policy),
        "task_adjustment": _task_adjustment_view(task_builder, tasks_step),
        "plans": {
            "before": _plan_view(initial_optimizer.get("plan")),
            "after": _plan_view(replanned_optimizer.get("plan")),
            "changes": _sequence(replanned.get("plan_changes", {}).get("changed_routes")),
        },
        "optimizer": {
            "initial": _initial_optimizer_view(initial_optimizer),
            "replanned": _replanned_optimizer_view(replanned_optimizer),
        },
        "verifier": _verifier_view(replanned.get("verifier")),
        "citysim": _citysim_view(final_citysim, finished.get("sim_time")),
        "metrics": _metrics_view(finished.get("metrics")),
    }


def _timeline_by_step(trace: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(item.get("step")): item
        for item in _sequence(trace.get("timeline"))
        if isinstance(item, Mapping) and item.get("step") is not None
    }


def _workflow_nodes(
    event: Mapping[str, Any],
    policy: Mapping[str, Any],
    task_builder: Mapping[str, Any],
    replanned: Mapping[str, Any],
) -> list[dict[str, str]]:
    event_type = _text(event.get("event_type"))
    policy_profile = _text(policy.get("policy_profile"))
    replan_status = _text(replanned.get("workflow_status"))
    verifier = _mapping(replanned.get("verifier"))
    return [
        {"label": "事件输入", "detail": _event_label(event_type)},
        {"label": "风险研判", "detail": _risk_detail(policy.get("risk_level"))},
        {"label": "治理策略", "detail": _policy_label(policy_profile)},
        {"label": "任务调整", "detail": _task_detail(task_builder)},
        {"label": "动态调度", "detail": _status_label(replan_status)},
        {"label": "独立验证", "detail": _verifier_status(verifier.get("valid"))},
        {"label": "仿真执行", "detail": "CitySim 完成执行"},
        {"label": "指标反馈", "detail": "Metrics 已生成"},
    ]


def _event_view(event: Mapping[str, Any], sim_time: Any) -> dict[str, Any]:
    event_type = _text(event.get("event_type"))
    return {
        "event_type": _event_label(event_type),
        "severity": event.get("severity"),
        "location": event.get("location"),
        "description": event.get("description"),
        "deadline": _deadline_text(event.get("deadline")),
        "sim_time": sim_time,
    }


def _policy_view(policy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "risk": _risk_detail(policy.get("risk_level")),
        "reasoning_summary": _display_or_baseline(policy.get("reasoning_summary")),
        "response_deadline": _deadline_text(policy.get("response_deadline")),
        "priority_targets": _join_or_none(policy.get("priority_targets")),
        "policy_profile": _policy_label(_text(policy.get("policy_profile"))),
        "constraints": _join_or_none(policy.get("constraints")),
    }


def _task_adjustment_view(
    task_builder: Mapping[str, Any], tasks_step: Mapping[str, Any]
) -> dict[str, Any]:
    created_tasks = task_builder.get("created_tasks")
    updated_tasks = task_builder.get("updated_tasks")
    return {
        "created_count": _count_or_baseline(created_tasks),
        "updated_count": _count_or_baseline(updated_tasks),
        "released_task_ids": _join_or_none(tasks_step.get("released_task_ids")),
        "result": "未新建服务任务；释放待执行任务后进入动态重规划"
        if task_builder.get("message") == "no new tasks created"
        else _display_or_baseline(task_builder.get("message")),
    }


def _plan_view(plan: Any) -> dict[str, Any]:
    plan_data = _mapping(plan)
    return {
        "plan_id": plan_data.get("plan_id"),
        "routes": [
            {
                "vehicle_id": route.get("vehicle_id"),
                "task_sequence": _route_text(route.get("task_sequence")),
                "planned_arrivals": _arrival_text(route.get("planned_arrivals")),
            }
            for route in _sequence(plan_data.get("vehicle_routes"))
            if isinstance(route, Mapping)
        ],
        "unassigned_tasks": _join_or_none(plan_data.get("unassigned_tasks")),
    }


def _initial_optimizer_view(optimizer: Mapping[str, Any]) -> dict[str, str]:
    has_plan = bool(_mapping(optimizer.get("plan")))
    status = optimizer.get("status")
    if status == NOT_RECORDED_IN_BASELINE:
        return {
            "plan_status": "初始调度方案：已生成" if has_plan else "初始调度方案：baseline 未记录",
            "solver_status": "求解状态：baseline 未单独记录",
            "reason": "求解原因：baseline 未单独记录",
        }
    return {
        "plan_status": "初始调度方案：已生成" if has_plan else "初始调度方案：未生成",
        "solver_status": f"求解状态：{_status_label(_text(status))}",
        "reason": f"求解原因：{_display_or_baseline(optimizer.get('reason'))}",
    }


def _replanned_optimizer_view(optimizer: Mapping[str, Any]) -> dict[str, str]:
    return {
        "solver_status": f"重规划状态：{_status_label(_text(optimizer.get('status')))}",
        "reason": f"求解原因：{_display_or_none(optimizer.get('reason'))}",
        "unassigned_tasks": _plan_view(optimizer.get("plan"))["unassigned_tasks"],
    }


def _verifier_view(verifier: Any) -> dict[str, Any]:
    verifier_data = _mapping(verifier)
    valid = verifier_data.get("valid")
    violations = verifier_data.get("violations")
    return {
        "status": _verifier_status(valid),
        "valid": valid,
        "violation_count": len(violations) if isinstance(violations, list) else None,
        "violations": violations if isinstance(violations, list) else [],
    }


def _citysim_view(citysim: Mapping[str, Any], sim_time: Any) -> dict[str, Any]:
    return {
        "current_time": citysim.get("current_time", sim_time),
        "vehicles": _sequence(citysim.get("vehicles")),
        "tasks": _sequence(citysim.get("tasks")),
        "waste_points": _sequence(citysim.get("waste_points")),
        "vehicle_status_counts": _mapping(citysim.get("vehicle_status_counts")),
        "task_status_counts": _mapping(citysim.get("task_status_counts")),
    }


def _metrics_view(metrics: Any) -> list[dict[str, str]]:
    metrics_data = _mapping(metrics)
    formats = {
        "task_completion_rate": lambda value: f"{float(value):.0%}",
        "urgent_task_completion_rate": lambda value: f"{float(value):.0%}",
        "average_response_time": lambda value: f"{float(value):.1f} 分钟",
        "overflow_count": lambda value: str(value),
        "total_distance": lambda value: f"{float(value):.1f}",
    }
    return [
        {
            "label": METRIC_LABELS[key],
            "value": formats[key](metrics_data[key])
            if key in metrics_data and metrics_data[key] is not None
            else "baseline 未记录",
        }
        for key in METRIC_LABELS
    ]


def _event_label(code: str | None) -> str:
    return labeled(code, EVENT_TYPE_LABELS) if code else "baseline 未记录"


def _policy_label(code: str | None) -> str:
    return labeled(code, POLICY_PROFILE_LABELS) if code else "baseline 未记录"


def _status_label(code: str | None) -> str:
    if code == NOT_RECORDED_IN_BASELINE:
        return "baseline 未单独记录"
    return labeled(code, STATUS_LABELS) if code else "baseline 未记录"


def _risk_detail(value: Any) -> str:
    return risk_label(value) if isinstance(value, int) else "baseline 未记录"


def _task_detail(task_builder: Mapping[str, Any]) -> str:
    if task_builder.get("message") == "no new tasks created":
        return "释放未执行任务"
    return "baseline 未记录"


def _verifier_status(valid: Any) -> str:
    if valid is True:
        return "PASS"
    if valid is False:
        return "未通过"
    return "baseline 未记录"


def _deadline_text(value: Any) -> str:
    return "未设置" if value is None else f"模拟分钟 {value}"


def _route_text(task_ids: Any) -> str:
    values = _sequence(task_ids)
    return " → ".join(str(item) for item in values) if values else "—"


def _arrival_text(arrivals: Any) -> str:
    return "、".join(
        f"{item.get('task_id')} @ {item.get('arrival_time')}"
        for item in _sequence(arrivals)
        if isinstance(item, Mapping)
    ) or "未记录"


def _join_or_none(values: Any) -> str:
    items = _sequence(values)
    return "、".join(str(item) for item in items) if items else "无"


def _count_or_baseline(value: Any) -> str:
    return str(len(value)) if isinstance(value, list) else "baseline 未记录"


def _display_or_baseline(value: Any) -> str:
    return "baseline 未记录" if value in (None, NOT_RECORDED_IN_BASELINE) else str(value)


def _display_or_none(value: Any) -> str:
    return "无" if value is None else _display_or_baseline(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, (list, tuple)) else ()


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None
