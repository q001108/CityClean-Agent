"""Explicit opt-in smoke test for the real DeepSeek event agent."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from cityclean_agent.agent.deepseek_event_agent import (
    DeepSeekEventAgent,
    DeepSeekEventAgentError,
)
from cityclean_agent.domain.enums import CityEventType, VehicleStatus
from cityclean_agent.domain.models import CityEvent, CityState, Road, Vehicle, WastePoint
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.presentation import (
    EVENT_TYPE_LABELS,
    POLICY_PROFILE_LABELS,
    labeled,
    risk_label,
)


def main() -> int:
    """Run one live structured-output call for each supported event type."""

    load_dotenv()
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY 未配置。", file=sys.stderr)
        return 1

    agent = DeepSeekEventAgent()
    state = _state()
    for event in _events():
        decision = agent.decide(event, state)
        print(f"事件：{labeled(event.event_type, EVENT_TYPE_LABELS)}")
        print(f"风险等级：{risk_label(decision.risk_level)}")
        print(f"治理策略：{labeled(decision.policy_profile, POLICY_PROFILE_LABELS)}")
        print(
            "治理响应时限（response_deadline）："
            f"{decision.response_deadline if decision.response_deadline is not None else '无'}"
        )
        print(f"优先目标：{', '.join(decision.priority_targets) or '无'}")
        print(f"治理理由：{decision.reasoning_summary}")
    return 0


def _state() -> CityState:
    return CityState(
        current_time=10,
        waste_points={
            "W1": WastePoint("W1", "B", 10, 10, 0, "mixed", "residential", 4)
        },
        vehicles={
            "V1": Vehicle("V1", "A", 5, 0, VehicleStatus.AVAILABLE, 30),
            "V2": Vehicle("V2", "C", 5, 0, VehicleStatus.BROKEN, 30),
        },
        transfer_stations={},
        road_network=RoadNetwork([Road("AB", "A", "B", 1, 5)]),
        tasks={},
    )


def _events() -> tuple[CityEvent, ...]:
    return (
        CityEvent(
            "E-overflow", CityEventType.WASTE_OVERFLOW, 10, "B", ["W1"], 4, 30,
            description="居民区垃圾点发生垃圾满溢。",
        ),
        CityEvent(
            "E-urgent", CityEventType.URGENT_TASK, 10, "B", ["W1"], 10, 30,
            description="居民区需要紧急清运。",
        ),
        CityEvent(
            "E-breakdown", CityEventType.VEHICLE_BREAKDOWN, 10, "C", ["V2"], 4, None,
            description="执行中的清运车辆发生故障。",
        ),
        CityEvent(
            "E-closure", CityEventType.ROAD_CLOSURE, 10, "A-B", ["AB"], 3, None,
            description="道路因突发情况封闭。",
        ),
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DeepSeekEventAgentError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
