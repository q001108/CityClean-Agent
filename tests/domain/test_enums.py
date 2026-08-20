from cityclean_agent.domain.enums import (
    CityEventType,
    RoadStatus,
    ServiceTaskStatus,
    VehicleStatus,
)


def test_v01_event_types_are_explicit() -> None:
    assert {event_type.value for event_type in CityEventType} == {
        "WASTE_OVERFLOW",
        "VEHICLE_BREAKDOWN",
        "ROAD_CLOSURE",
        "URGENT_TASK",
    }


def test_v01_vehicle_statuses_are_limited_to_agreed_values() -> None:
    assert {status.value for status in VehicleStatus} == {
        "AVAILABLE",
        "EN_ROUTE",
        "SERVICING",
        "BROKEN",
    }


def test_road_and_task_statuses_expose_minimum_lifecycle() -> None:
    assert {status.value for status in RoadStatus} == {"OPEN", "CLOSED"}
    assert ServiceTaskStatus.COMPLETED.value == "COMPLETED"
