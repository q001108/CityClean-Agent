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
    assert disrupted.routes
