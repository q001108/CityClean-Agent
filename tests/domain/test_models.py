import pytest

from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import (
    DEFAULT_SERVICE_DURATION_MIN,
    CityEvent,
    DispatchPlan,
    ServiceTask,
    Vehicle,
    VehicleRoute,
    WastePoint,
)


def test_waste_point_permits_overflow_for_incident_modelling() -> None:
    waste_point = WastePoint(
        id="W17",
        node_id="N17",
        capacity=100,
        current_load=125,
        generation_rate=2,
        waste_type="mixed",
        zone_type="school",
        priority=3,
    )

    assert waste_point.current_load > waste_point.capacity


def test_vehicle_exposes_remaining_capacity() -> None:
    vehicle = Vehicle(
        id="V1",
        current_node_id="N1",
        capacity=100,
        current_load=25,
        status=VehicleStatus.AVAILABLE,
        speed=30,
    )

    assert vehicle.remaining_capacity == 75


def test_vehicle_rejects_load_above_capacity() -> None:
    with pytest.raises(ValueError, match="current_load"):
        Vehicle(
            id="V1",
            current_node_id="N1",
            capacity=100,
            current_load=101,
            status=VehicleStatus.AVAILABLE,
            speed=30,
        )


def test_city_event_validates_deadline_against_timestamp() -> None:
    with pytest.raises(ValueError, match="deadline"):
        CityEvent(
            event_id="E1",
            event_type=CityEventType.URGENT_TASK,
            timestamp=20,
            location="N17",
            description="urgent collection",
            affected_entities=["W17"],
            severity=2,
            deadline=19,
        )


def test_city_event_description_is_optional_without_relaxing_required_fields() -> None:
    event = CityEvent(
        "E1",
        CityEventType.URGENT_TASK,
        20,
        "N17",
        ["W17"],
        2,
        30,
    )
    described_event = CityEvent(
        "E2",
        CityEventType.URGENT_TASK,
        20,
        "N17",
        ["W17"],
        2,
        30,
        description="urgent collection",
    )
    explicit_none_event = CityEvent(
        "E3",
        CityEventType.URGENT_TASK,
        20,
        "N17",
        ["W17"],
        2,
        30,
        description=None,
    )

    assert event.description is None
    assert described_event.description == "urgent collection"
    assert explicit_none_event.description is None

    with pytest.raises(TypeError):
        CityEvent("E4", CityEventType.URGENT_TASK, 20, "N17")


def test_service_task_uses_fixed_v01_service_duration() -> None:
    task = ServiceTask(
        task_id="T1",
        source_event_id="E1",
        target_id="W17",
        demand=20,
        priority=3,
        deadline=30,
    )

    assert task.status is ServiceTaskStatus.PENDING
    assert task.service_duration_min == DEFAULT_SERVICE_DURATION_MIN

    with pytest.raises(ValueError, match="fixed service duration"):
        ServiceTask(
            task_id="T2",
            source_event_id="E1",
            target_id="W17",
            demand=20,
            priority=3,
            deadline=30,
            service_duration_min=10,
        )


def test_vehicle_route_rejects_duplicate_tasks_and_unknown_etas() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        VehicleRoute(vehicle_id="V1", task_sequence=["T1", "T1"])

    with pytest.raises(ValueError, match="planned_arrivals"):
        VehicleRoute(
            vehicle_id="V1",
            task_sequence=["T1"],
            planned_arrivals={"T2": 10},
        )


def test_dispatch_plan_rejects_multiple_routes_for_one_vehicle() -> None:
    with pytest.raises(ValueError, match="one route"):
        DispatchPlan(
            plan_id="P1",
            vehicle_routes=[
                VehicleRoute(vehicle_id="V1", task_sequence=["T1"]),
                VehicleRoute(vehicle_id="V1", task_sequence=["T2"]),
            ],
        )
