"""Real DeepSeek-backed event assessment with strict structured output."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
from pydantic import ValidationError

from cityclean_agent.domain.constants import MUST_SERVE_PRIORITY_THRESHOLD
from cityclean_agent.domain.enums import ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import CityEvent, CityState
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile


DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
_MAX_REASONING_SUMMARY_LENGTH = 500
_FORBIDDEN_OPTIMIZATION_FIELDS = frozenset(
    {
        "distance_weight",
        "lateness_weight",
        "unserved_task_penalty",
        "rescheduling_weight",
    }
)

_SYSTEM_PROMPT = """你是 CityClean 的城市环卫事件治理研判助手。
请严格只输出符合以下 JSON 结构的 PolicyDecision，用于判断治理紧迫性、
风险等级、有效优先目标、治理响应时限、既有治理策略、简短中文治理理由和少量治理约束。

JSON 必须且只能包含以下英文机器字段，不能新增或改名：
- event_type：必须原样使用输入的 event_type。
- risk_level：1 到 5 的整数，不能使用 HIGH 等文字。
- reasoning_summary：简短、非空的中文治理理由。
- response_deadline：绝对模拟分钟，必须不早于 current_time；未知时为 null。
- priority_targets：数组，元素必须是当前有效 WastePoint ID。
- policy_profile：只能是 BALANCED、URGENT_RESPONSE、OVERFLOW_CONTROL 或 MINIMAL_RESCHEDULE。
- constraints：包含少量简短中文治理约束的数组。
不得输出 governance_urgency、valid_priority_targets 等额外字段。

event_type、timestamp、location 和 affected_entities 是系统确定性事实。
若存在 natural_language_description，只能将其与 severity 和城市摘要结合为额外治理语境；
不得覆盖这些事实，也不得虚构新的事件类型或目标。

不得进行车辆分配、路线生成、最短路径计算、容量计算、ETA 计算、任务序列生成、
距离计算、OR-Tools 目标计算或优化权重生成。
确定性路径与调度由独立 Optimizer 负责。"""


class DeepSeekEventAgentError(RuntimeError):
    """Raised when a real-model output cannot satisfy the CityClean contract."""


class DeepSeekEventAgent:
    """Assess a structured CityEvent with DeepSeek and return PolicyDecision."""

    def __init__(self, model: Any | None = None) -> None:
        self._model = model if model is not None else self._create_structured_model()

    def decide(self, event: CityEvent, state: CityState) -> PolicyDecision:
        """Return a validated policy decision without mutating the supplied state."""

        messages = [
            ("system", _SYSTEM_PROMPT),
            (
                "human",
                json.dumps(
                    build_governance_state_summary(event, state),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
            ),
        ]
        try:
            output = self._model.invoke(messages)
        except Exception as exc:
            raise DeepSeekEventAgentError(
                f"DeepSeek 模型调用失败：{exc}"
            ) from exc

        decision = _validate_structured_output(output)
        _validate_cross_object_contract(decision, event, state)
        return decision

    def _create_structured_model(self) -> Any:
        load_dotenv()
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise DeepSeekEventAgentError("DEEPSEEK_API_KEY 未配置")
        try:
            chat_model = ChatDeepSeek(
                model=DEFAULT_DEEPSEEK_MODEL,
                api_key=api_key,
                temperature=0,
                max_retries=2,
            )
            return chat_model.with_structured_output(
                PolicyDecision,
                method="json_mode",
            )
        except Exception as exc:
            raise DeepSeekEventAgentError(
                f"DeepSeek 结构化输出模型配置失败：{exc}"
            ) from exc


def build_governance_state_summary(
    event: CityEvent, state: CityState
) -> dict[str, object]:
    """Build the compact deterministic governance context sent to the model."""

    affected_targets = []
    for target_id in sorted(set(event.affected_entities)):
        point = state.waste_points.get(target_id)
        if point is not None:
            affected_targets.append(
                {
                    "id": point.id,
                    "current_load": point.current_load,
                    "capacity": point.capacity,
                    "priority": point.priority,
                    "is_overflow": point.current_load >= point.capacity,
                }
            )

    unfinished_tasks = [
        task
        for task in state.tasks.values()
        if task.status is not ServiceTaskStatus.COMPLETED
    ]
    high_priority_tasks = [
        {
            "task_id": task.task_id,
            "target_id": task.target_id,
            "priority": task.priority,
            "status": task.status.value,
            "deadline": task.deadline,
        }
        for task in sorted(unfinished_tasks, key=lambda task: task.task_id)
        if task.priority >= MUST_SERVE_PRIORITY_THRESHOLD
    ]
    return {
        "current_time": state.current_time,
        "event": {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "timestamp": event.timestamp,
            "severity": event.severity,
            "affected_entities": list(event.affected_entities),
            "metadata": {key: event.metadata[key] for key in sorted(event.metadata)},
            **(
                {"natural_language_description": event.description}
                if event.description is not None
                else {}
            ),
        },
        "affected_targets": affected_targets,
        "vehicle_summary": {
            "total": len(state.vehicles),
            "available": sum(
                vehicle.status is VehicleStatus.AVAILABLE
                for vehicle in state.vehicles.values()
            ),
            "broken": sum(
                vehicle.status is VehicleStatus.BROKEN
                for vehicle in state.vehicles.values()
            ),
            "en_route": sum(
                vehicle.status is VehicleStatus.EN_ROUTE
                for vehicle in state.vehicles.values()
            ),
            "servicing": sum(
                vehicle.status is VehicleStatus.SERVICING
                for vehicle in state.vehicles.values()
            ),
        },
        "task_summary": {
            "unfinished_task_count": len(unfinished_tasks),
            "must_serve_task_count": len(high_priority_tasks),
            "high_priority_tasks": high_priority_tasks,
        },
    }


def _validate_structured_output(output: Any) -> PolicyDecision:
    if isinstance(output, PolicyDecision):
        return output
    if not isinstance(output, Mapping):
        raise DeepSeekEventAgentError("DeepSeek 未返回结构化 PolicyDecision")
    forbidden_fields = _FORBIDDEN_OPTIMIZATION_FIELDS.intersection(output)
    if forbidden_fields:
        raise DeepSeekEventAgentError(
            "DeepSeek 输出不得包含 Optimizer 权重字段"
        )
    try:
        return PolicyDecision.model_validate(dict(output))
    except ValidationError as exc:
        raise DeepSeekEventAgentError("DeepSeek 返回了无效的 PolicyDecision") from exc


def _validate_cross_object_contract(
    decision: PolicyDecision, event: CityEvent, state: CityState
) -> None:
    if decision.event_type is not event.event_type:
        raise DeepSeekEventAgentError("PolicyDecision 的 event_type 与 CityEvent 不一致")
    invalid_targets = set(decision.priority_targets).difference(state.waste_points)
    if invalid_targets:
        raise DeepSeekEventAgentError("PolicyDecision 包含未知的 priority target")
    if not isinstance(decision.policy_profile, PolicyProfile):
        raise DeepSeekEventAgentError("PolicyDecision 包含无效的 policy_profile")
    if (
        not decision.reasoning_summary.strip()
        or len(decision.reasoning_summary) > _MAX_REASONING_SUMMARY_LENGTH
    ):
        raise DeepSeekEventAgentError("PolicyDecision 的 reasoning_summary 无效")
    if (
        decision.response_deadline is not None
        and decision.response_deadline < state.current_time
    ):
        raise DeepSeekEventAgentError("PolicyDecision 的 response_deadline 早于当前模拟时间")
