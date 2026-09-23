from cityclean_agent.agent.mock_event_agent import MockEventAgent
from cityclean_agent.domain.enums import CityEventType, VehicleStatus
from cityclean_agent.domain.models import CityEvent, CityState, Road, Vehicle, WastePoint
from cityclean_agent.domain.road_network import GeoCoordinate, RoadNetwork
from cityclean_agent.runtime.service import CityRuntime
from cityclean_agent.simulator.city_sim import CitySim
from cityclean_agent.workflow import WorkflowStatus


def make_runtime() -> CityRuntime:
    state = CityState(
        current_time=10,
        waste_points={
            "W1": WastePoint("W1", "B", 20, 8, 0, "mixed", "residential", 2)
        },
        vehicles={
            "V1": Vehicle("V1", "A", 20, 0, VehicleStatus.AVAILABLE, 30)
        },
        transfer_stations={},
        road_network=RoadNetwork(
            [Road("AB", "A", "B", 1, 5)],
            node_coordinates={
                "A": GeoCoordinate(114.0913, 32.147),
                "B": GeoCoordinate(114.105, 32.155),
            },
        ),
    )
    return CityRuntime(
        CitySim(state),
        event_agent=MockEventAgent(),
        source_name="runtime-test",
        data_mode="test",
    )


def make_event(event_id: str = "E1") -> CityEvent:
    return CityEvent(
        event_id=event_id,
        event_type=CityEventType.URGENT_TASK,
        timestamp=10,
        location="B",
        affected_entities=["W1"],
        severity=4,
        deadline=30,
        metadata={"demand": 5},
        description="urgent collection",
    )


def test_snapshot_is_deterministic_and_isolated_from_citysim() -> None:
    runtime = make_runtime()

    snapshot = runtime.snapshot()
    snapshot.waste_points[0].current_load = 99

    assert runtime.snapshot().waste_points[0].current_load == 8
    assert snapshot.current_time == 10
    assert snapshot.vehicles[0].id == "V1"
    assert snapshot.vehicles[0].coordinate is not None
    assert snapshot.vehicles[0].coordinate.longitude == 114.0913
    assert snapshot.waste_points[0].coordinate is not None
    assert snapshot.roads[0].id == "AB"


def test_process_uses_real_workflow_and_reports_duplicate_event() -> None:
    runtime = make_runtime()

    first = runtime.process(make_event())
    second = runtime.process(make_event())

    assert first.status is WorkflowStatus.SUCCESS
    assert first.plan is not None
    assert first.policy_decision is not None
    assert second.status is WorkflowStatus.IGNORED
    assert second.reason == "EVENT_ALREADY_PROCESSED"
    snapshot = runtime.snapshot()
    assert snapshot.active_events[0].event_id == "E1"
    assert snapshot.tasks[0].source_event_id == "E1"
    assert snapshot.active_plan is not None
    assert len(snapshot.active_plan.vehicle_routes[0].path) == 2


def test_invalid_reference_is_rejected_before_state_changes() -> None:
    runtime = make_runtime()
    event = make_event()
    event.affected_entities = ["UNKNOWN"]

    try:
        runtime.process(event)
    except ValueError as exc:
        assert "unknown waste point IDs" in str(exc)
    else:
        raise AssertionError("unknown reference should fail")

    assert runtime.snapshot().active_events == ()
    assert runtime.snapshot().tasks == ()
