from __future__ import annotations

import pytest

from cityclean_agent.agent.mock_event_agent import MockEventAgent
from cityclean_agent.domain.enums import CityEventType, VehicleStatus
from cityclean_agent.domain.models import CityEvent, CityState, Road, Vehicle, WastePoint
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile


def make_state() -> CityState:
    waste_point = WastePoint(
        id="W1",
        node_id="N1",
        capacity=20,
        current_load=8,
        generation_rate=1,
        waste_type="mixed",
        zone_type="school",
        priority=2,
    )
    vehicle = Vehicle(
        id="V1",
        current_node_id="N1",
        capacity=30,
        current_load=0,
        status=VehicleStatus.AVAILABLE,
        speed=30,
    )
    return CityState(
        current_time=0,
        waste_points={"W1": waste_point},
        vehicles={"V1": vehicle},
        transfer_stations={},
        road_network=RoadNetwork([Road("R1", "N1", "N2", 1, 5)]),
    )


def make_event(event_type: CityEventType) -> CityEvent:
    affected_entity = {
        CityEventType.WASTE_OVERFLOW: "W1",
        CityEventType.URGENT_TASK: "W1",
        CityEventType.VEHICLE_BREAKDOWN: "V1",
        CityEventType.ROAD_CLOSURE: "R1",
    }[event_type]
    return CityEvent(
        event_id=f"E-{event_type.value}",
        event_type=event_type,
        timestamp=0,
        location="N1",
        description="test event",
        affected_entities=[affected_entity],
        severity=3,
        deadline=20,
    )


@pytest.mark.parametrize("event_type", list(CityEventType))
def test_every_event_type_produces_a_valid_policy_decision(
    event_type: CityEventType,
) -> None:
    decision = MockEventAgent().decide(make_event(event_type), make_state())

    assert isinstance(decision, PolicyDecision)
    assert decision.event_type is event_type
    assert 1 <= decision.risk_level <= 5


def test_same_input_produces_same_policy_decision() -> None:
    agent = MockEventAgent()
    event = make_event(CityEventType.WASTE_OVERFLOW)

    assert agent.decide(event, make_state()) == agent.decide(event, make_state())


@pytest.mark.parametrize(
    ("event_type", "profile"),
    [
        (CityEventType.WASTE_OVERFLOW, PolicyProfile.OVERFLOW_CONTROL),
        (CityEventType.URGENT_TASK, PolicyProfile.URGENT_RESPONSE),
        (CityEventType.VEHICLE_BREAKDOWN, PolicyProfile.MINIMAL_RESCHEDULE),
        (CityEventType.ROAD_CLOSURE, PolicyProfile.MINIMAL_RESCHEDULE),
    ],
)
def test_mock_event_profiles_are_fixed(
    event_type: CityEventType, profile: PolicyProfile
) -> None:
    assert MockEventAgent().decide(make_event(event_type), make_state()).policy_profile is profile


def test_priority_targets_reference_affected_waste_points_only() -> None:
    agent = MockEventAgent()

    overflow = agent.decide(make_event(CityEventType.WASTE_OVERFLOW), make_state())
    urgent = agent.decide(make_event(CityEventType.URGENT_TASK), make_state())
    breakdown = agent.decide(make_event(CityEventType.VEHICLE_BREAKDOWN), make_state())

    assert overflow.priority_targets == ("W1",)
    assert urgent.priority_targets == ("W1",)
    assert breakdown.priority_targets == ()
