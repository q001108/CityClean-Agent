"""Streamlit entry point for the fixed CityClean workflow visualization demo."""

from __future__ import annotations

import html
import io
from collections.abc import Iterable, Mapping
from typing import Any

import streamlit as st

from cityclean_agent.demo import run_demo
from cityclean_agent.demo_trace_adapter import build_demo_trace
from cityclean_agent.demo_view import build_demo_view


def main() -> None:
    """Render the fixed, reproducible vehicle-breakdown demonstration."""

    st.set_page_config(
        page_title="CityClean-Agent｜动态重规划演示",
        page_icon="♻️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_styles()
    _render_hero()

    run_requested = st.button("运行固定演示", type="primary", use_container_width=False)
    result = run_demo(output=io.StringIO())
    view = build_demo_view(build_demo_trace(result))

    if run_requested:
        st.success(
            "固定演示已重新执行：V01 故障后，待执行任务已转交 V02 并通过独立验证。"
        )
    else:
        st.caption("页面已载入固定演示；点击按钮可重新执行同一可复现场景。")

    _render_workflow(view["workflow_nodes"])
    st.divider()
    _render_event_and_policy(view)
    _render_task_adjustment(view["task_adjustment"])
    _render_plans(view["plans"])
    _render_optimizer_and_verifier(view)
    _render_citysim(view["citysim"])
    _render_metrics(view["metrics"])


def _render_hero() -> None:
    st.title("CityClean-Agent")
    st.subheader("面向城市突发环卫事件的自主研判与动态调度智能体")
    st.markdown(
        "<span class='scenario-badge'>车辆故障动态重规划 · 固定答辩场景 · 可复现运行</span>",
        unsafe_allow_html=True,
    )
    st.info(
        "当前演示采用确定性事件研判模式，保证比赛现场结果可复现；"
        "系统 Event Agent 接口支持接入 DeepSeek。"
    )


def _render_workflow(nodes: Iterable[Mapping[str, str]]) -> None:
    node_list = list(nodes)
    st.markdown("### 自主治理闭环")
    for row_index, row_nodes in enumerate((node_list[:4], node_list[4:])):
        columns = st.columns(7)
        for index, node in enumerate(row_nodes):
            step_number = row_index * 4 + index + 1
            with columns[index * 2]:
                st.markdown(
                    "<div class='workflow-node'>"
                    f"<div class='node-title'>{step_number}. {html.escape(node['label'])}</div>"
                    f"<div class='node-detail'>{html.escape(node['detail'])}</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )
            if index < len(row_nodes) - 1:
                columns[index * 2 + 1].markdown(
                    "<div class='workflow-arrow'>→</div>", unsafe_allow_html=True
                )
        if row_index == 0:
            st.markdown(
                "<div class='workflow-down'>↓ 进入重规划与执行阶段</div>",
                unsafe_allow_html=True,
            )


def _render_event_and_policy(view: Mapping[str, Any]) -> None:
    event, policy = view["event"], view["policy"]
    left, right = st.columns((1, 1.35), gap="large")
    with left:
        st.markdown("### 事件输入")
        st.markdown(f"**事件类型**：{event['event_type']}")
        st.markdown(f"**严重程度**：{event['severity']}")
        st.markdown(f"**发生位置**：{event['location']}")
        st.markdown(f"**仿真时间**：{event['sim_time']}")
        st.markdown(f"**截止时间**：{event['deadline']}")
        st.caption(event["description"] or "baseline 未记录事件描述")
    with right:
        st.markdown("### 事件研判（确定性演示模式）")
        st.markdown(f"**风险等级**：{policy['risk']}")
        st.markdown(f"**治理策略**：{policy['policy_profile']}")
        st.markdown(f"**响应时限**：{policy['response_deadline']}")
        st.markdown(f"**优先目标**：{policy['priority_targets']}")
        st.markdown(f"**治理理由**：{policy['reasoning_summary']}")
        st.markdown(f"**治理约束**：{policy['constraints']}")


def _render_task_adjustment(task_adjustment: Mapping[str, str]) -> None:
    st.markdown("### 任务调整")
    first, second, third = st.columns(3)
    first.metric("新建服务任务", task_adjustment["created_count"])
    second.metric("更新服务任务", task_adjustment["updated_count"])
    third.metric("释放待执行任务", task_adjustment["released_task_ids"])
    st.success(task_adjustment["result"])


def _render_plans(plans: Mapping[str, Any]) -> None:
    st.markdown("### 动态重规划：故障前 / 故障后")
    before, after = st.columns(2, gap="large")
    with before:
        st.markdown("#### 故障前计划")
        _render_routes(plans["before"]["routes"])
    with after:
        st.markdown("#### 故障后计划")
        _render_routes(plans["after"]["routes"])

    changes = plans["changes"]
    if changes:
        st.markdown("**任务重新分配**")
        st.table(
            [
                {
                    "车辆": item.get("vehicle_id"),
                    "故障前": " → ".join(item.get("before_task_sequence", [])) or "—",
                    "故障后": " → ".join(item.get("after_task_sequence", [])) or "—",
                }
                for item in changes
            ]
        )


def _render_routes(routes: Iterable[Mapping[str, Any]]) -> None:
    route_list = list(routes)
    if not route_list:
        st.caption("无分配路线")
        return
    for route in route_list:
        st.markdown(
            f"**{route['vehicle_id']}**　{route['task_sequence']}  \\n"
            f"预计到达：{route['planned_arrivals']}"
        )


def _render_optimizer_and_verifier(view: Mapping[str, Any]) -> None:
    optimizer, verifier = view["optimizer"], view["verifier"]
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("### OR-Tools 动态调度")
        st.markdown(f"**{optimizer['initial']['plan_status']}**")
        st.caption(optimizer["initial"]["solver_status"])
        st.caption(optimizer["initial"]["reason"])
        st.markdown(f"**{optimizer['replanned']['solver_status']}**")
        st.markdown(f"未分配任务：{optimizer['replanned']['unassigned_tasks']}")
    with right:
        st.markdown("### Verifier 独立验证")
        if verifier["valid"] is True:
            st.success(f"Verifier：{verifier['status']}｜约束违规：{verifier['violation_count']}")
            st.caption("方案通过独立规则验证后进入 CitySim 执行。")
        elif verifier["valid"] is False:
            st.error(f"Verifier：{verifier['status']}｜约束违规：{verifier['violation_count']}")
            st.table(verifier["violations"])
        else:
            st.warning("Verifier 结果：baseline 未记录")


def _render_citysim(citysim: Mapping[str, Any]) -> None:
    st.markdown("### CitySim 执行结果")
    st.caption(f"最终模拟时间：{citysim['current_time']}")
    vehicle_column, task_column, waste_column = st.columns(3, gap="medium")
    with vehicle_column:
        st.markdown("**车辆状态**")
        st.table(citysim["vehicles"])
    with task_column:
        st.markdown("**任务状态**")
        st.table(citysim["tasks"])
    with waste_column:
        st.markdown("**垃圾点状态**")
        st.table(citysim["waste_points"])


def _render_metrics(metrics: Iterable[Mapping[str, str]]) -> None:
    metric_list = list(metrics)
    st.markdown("### 指标反馈")
    columns = st.columns(len(metric_list))
    for column, metric in zip(columns, metric_list, strict=True):
        column.metric(metric["label"], metric["value"])


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
            .scenario-badge {
                display: inline-block; padding: 0.35rem 0.75rem; border-radius: 999px;
                color: #0b4f4a; background: #dff4ef; font-weight: 600;
            }
            .workflow-node {
                min-height: 94px; padding: 0.75rem 0.45rem; border: 1px solid #c9d8e8;
                border-radius: 10px; background: #f7fbff; text-align: center;
            }
            .node-title { color: #12395b; font-weight: 700; font-size: 1rem; }
            .node-detail { color: #54708a; margin-top: 0.4rem; font-size: 0.78rem; }
            .workflow-arrow { margin-top: 30px; color: #2c6da4; font-size: 1.7rem; text-align: center; }
            .workflow-down {
                color: #2c6da4; font-size: 0.9rem; line-height: 1.5rem;
                text-align: right; padding-right: 0.75rem; font-weight: 600;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
