from cityclean_agent.domain.enums import CityEventType
from cityclean_agent.presentation import (
    BENCHMARK_MODE_LABELS,
    EVENT_TYPE_LABELS,
    METRIC_LABELS,
    POLICY_PROFILE_LABELS,
    RISK_LEVEL_LABELS,
    STATUS_LABELS,
    labeled,
    risk_label,
)
from cityclean_agent.policy.models import PolicyProfile


def test_event_and_policy_labels_keep_stable_machine_codes() -> None:
    assert labeled(CityEventType.WASTE_OVERFLOW, EVENT_TYPE_LABELS) == (
        "垃圾满溢（WASTE_OVERFLOW）"
    )
    assert labeled(PolicyProfile.URGENT_RESPONSE, POLICY_PROFILE_LABELS) == (
        "紧急响应（URGENT_RESPONSE）"
    )


def test_fixed_judge_facing_labels_cover_metrics_modes_risks_and_statuses() -> None:
    assert METRIC_LABELS == {
        "task_completion_rate": "任务完成率",
        "urgent_task_completion_rate": "紧急任务完成率",
        "average_response_time": "平均响应时间",
        "overflow_count": "满溢次数",
        "total_distance": "总行驶距离",
    }
    assert BENCHMARK_MODE_LABELS["STATIC_NO_REPLAN"] == "静态不重规划"
    assert BENCHMARK_MODE_LABELS["FIXED_BALANCED_REPLAN"] == "固定均衡策略重规划"
    assert BENCHMARK_MODE_LABELS["EVENT_POLICY_REPLAN"] == "事件治理策略重规划"
    assert RISK_LEVEL_LABELS[4] == "较高风险"
    assert risk_label(5) == "5（严重风险）"
    assert labeled("SUCCESS", STATUS_LABELS) == "成功（SUCCESS）"
    assert labeled("FEASIBLE", STATUS_LABELS) == "可行（FEASIBLE）"
