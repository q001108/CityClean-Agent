"""Stable Chinese labels for judge-facing CityClean command-line output."""

from __future__ import annotations

from enum import Enum


EVENT_TYPE_LABELS = {
    "WASTE_OVERFLOW": "垃圾满溢",
    "URGENT_TASK": "紧急清运任务",
    "VEHICLE_BREAKDOWN": "车辆故障",
    "ROAD_CLOSURE": "道路封闭",
}

POLICY_PROFILE_LABELS = {
    "BALANCED": "均衡治理",
    "URGENT_RESPONSE": "紧急响应",
    "OVERFLOW_CONTROL": "满溢治理",
    "MINIMAL_RESCHEDULE": "最小扰动重调度",
}

RISK_LEVEL_LABELS = {
    1: "轻微",
    2: "局部影响",
    3: "明显影响",
    4: "较高风险",
    5: "严重风险",
}

METRIC_LABELS = {
    "task_completion_rate": "任务完成率",
    "urgent_task_completion_rate": "紧急任务完成率",
    "average_response_time": "平均响应时间",
    "overflow_count": "满溢次数",
    "total_distance": "总行驶距离",
}

BENCHMARK_MODE_LABELS = {
    "STATIC_NO_REPLAN": "静态不重规划",
    "FIXED_BALANCED_REPLAN": "固定均衡策略重规划",
    "EVENT_POLICY_REPLAN": "事件治理策略重规划",
}

STATUS_LABELS = {
    "SUCCESS": "成功",
    "INFEASIBLE": "不可行",
    "VERIFICATION_FAILED": "验证失败",
    "MAX_SIMULATION_TIME": "达到最大仿真时间",
    "FEASIBLE": "可行",
    "AVAILABLE": "可用",
    "EN_ROUTE": "行驶中",
    "SERVICING": "服务中",
    "BROKEN": "故障",
    "PENDING": "待处理",
    "ASSIGNED": "已分配",
    "IN_PROGRESS": "执行中",
    "COMPLETED": "已完成",
}


def labeled(value: str | Enum, labels: dict[str, str]) -> str:
    """Return a Chinese judge-facing label while preserving the stable code."""

    code = value.value if isinstance(value, Enum) else value
    return f"{labels.get(code, code)}（{code}）"


def risk_label(risk_level: int) -> str:
    """Return a Chinese risk label while retaining its stable numeric value."""

    return f"{risk_level}（{RISK_LEVEL_LABELS.get(risk_level, '未知')}）"
