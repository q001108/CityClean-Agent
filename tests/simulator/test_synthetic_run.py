from cityclean_agent.simulator.synthetic_dispatch import SyntheticDispatchRequest
from cityclean_agent.simulator.synthetic_run import (
    SyntheticDisruptionRequest,
    SyntheticDisruptionType,
    SyntheticRunRegistry,
)


def make_registry_with_run():
    registry = SyntheticRunRegistry()
    started = registry.create(SyntheticDispatchRequest(seed=42))
    return registry, started


def test_run_advances_citysim_and_exposes_execution_state() -> None:
    registry, started = make_registry_with_run()

    advanced = registry.step(started.run.run_id, 2)

    assert started.run.status == "RUNNING"
    assert advanced.current_minute == 490
    assert advanced.elapsed_minutes == 10
    assert advanced.task_count == 18
    assert advanced.routes
    assert any(vehicle.current_load_liters > 0 for vehicle in advanced.vehicles)
    assert any(item.current_load_liters != initial.current_load_liters for item, initial in zip(advanced.bins, started.run.bins, strict=True))
    assert [entry.kind for entry in advanced.timeline] == [
        "RUN_STARTED",
        "TIME_ADVANCED",
        "TIME_ADVANCED",
    ]
    assert advanced.timeline[-1].vehicles


def test_vehicle_breakdown_triggers_verified_replanning() -> None:
    registry, started = make_registry_with_run()
    target = started.run.available_vehicle_disruptions[0]

    disrupted = registry.disrupt(
        started.run.run_id,
        SyntheticDisruptionRequest(
            disruption_type=SyntheticDisruptionType.VEHICLE_BREAKDOWN,
            target_id=target,
        ),
    )

    assert disrupted.status == "RUNNING"
    assert disrupted.broken_vehicle_count == 1
    assert disrupted.last_replan_status == "SUCCESS"
    assert target not in {route.vehicle_id for route in disrupted.routes}


def test_road_closure_after_movement_releases_routes_and_replans() -> None:
    registry, started = make_registry_with_run()
    moved = registry.step(started.run.run_id, 1)
    target = moved.available_road_disruptions[0]

    disrupted = registry.disrupt(
        started.run.run_id,
        SyntheticDisruptionRequest(
            disruption_type=SyntheticDisruptionType.ROAD_CLOSURE,
            target_id=target,
        ),
    )

    assert disrupted.status == "RUNNING"
    assert disrupted.last_replan_status == "SUCCESS"
    assert target in disrupted.last_event
    assert target in disrupted.closed_road_ids
    assert disrupted.routes


def test_waste_overflow_and_urgent_task_are_recorded_on_timeline() -> None:
    registry, started = make_registry_with_run()
    overflow_target = next(
        item.bin_id
        for item in started.run.bins
        if item.current_load_liters < item.capacity_liters
    )

    overflowed = registry.disrupt(
        started.run.run_id,
        SyntheticDisruptionRequest(
            disruption_type=SyntheticDisruptionType.WASTE_OVERFLOW,
            target_id=overflow_target,
        ),
    )
    urgent = registry.disrupt(
        started.run.run_id,
        SyntheticDisruptionRequest(
            disruption_type=SyntheticDisruptionType.URGENT_TASK,
            target_id=overflow_target,
        ),
    )

    overflow_bin = next(item for item in overflowed.bins if item.bin_id == overflow_target)
    assert overflow_bin.fill_ratio >= 1
    assert overflowed.timeline[-1].kind == "DISRUPTION"
    assert "垃圾量突增" in overflowed.timeline[-1].summary
    assert urgent.timeline[-1].kind == "DISRUPTION"
    assert "紧急清运任务" in urgent.timeline[-1].summary
    assert urgent.last_replan_status == "SUCCESS"


def test_resource_budget_run_keeps_unselected_bins_available_for_disruptions() -> None:
    registry = SyntheticRunRegistry()
    started = registry.create(SyntheticDispatchRequest(
        seed=20260922,
        selected_bin_count=30,
        vehicle_count=4,
        vehicle_capacity_liters=1600,
        service_target_budget=10,
    ))

    assert started.run.task_count == 10
    assert len(started.run.bins) == 30
    assert len(started.run.available_bin_disruptions) == 30
    assert sum(item.task_status is not None for item in started.run.bins) == 10
