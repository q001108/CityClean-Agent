from __future__ import annotations

import io

from cityclean_agent.demo import run_demo
from cityclean_agent.demo_trace_adapter import build_demo_trace
from cityclean_agent.demo_view import WORKFLOW_NODE_LABELS, build_demo_view


def test_demo_trace_builds_complete_chinese_workflow_view() -> None:
    view = build_demo_view(build_demo_trace(run_demo(io.StringIO())))

    assert tuple(node["label"] for node in view["workflow_nodes"]) == (
        WORKFLOW_NODE_LABELS
    )
    assert view["event"]["event_type"] == "车辆故障（VEHICLE_BREAKDOWN）"
    assert view["policy"]["policy_profile"] == "最小扰动重调度（MINIMAL_RESCHEDULE）"
    assert view["task_adjustment"] == {
        "created_count": "0",
        "updated_count": "0",
        "released_task_ids": "T02、T03",
        "result": "未新建服务任务；释放待执行任务后进入动态重规划",
    }


def test_demo_view_preserves_before_after_routes_and_missing_initial_status() -> None:
    view = build_demo_view(build_demo_trace(run_demo(io.StringIO())))

    assert view["plans"]["before"]["routes"] == [
        {
            "vehicle_id": "V01",
            "task_sequence": "T01 → T02 → T03",
            "planned_arrivals": "T01 @ 5、T02 @ 15、T03 @ 25",
        }
    ]
    assert view["plans"]["after"]["routes"] == [
        {
            "vehicle_id": "V02",
            "task_sequence": "T02 → T03",
            "planned_arrivals": "T02 @ 15、T03 @ 25",
        }
    ]
    assert view["plans"]["changes"][0]["vehicle_id"] == "V01"
    assert view["optimizer"]["initial"]["solver_status"] == (
        "求解状态：baseline 未单独记录"
    )
    assert view["optimizer"]["replanned"]["solver_status"] == (
        "重规划状态：可行（FEASIBLE）"
    )
