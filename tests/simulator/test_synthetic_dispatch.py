from cityclean_agent.simulator.synthetic_dispatch import (
    SyntheticDispatchRequest,
    plan_synthetic_dispatch,
)


def test_synthetic_risks_are_converted_into_verified_routes() -> None:
    response = plan_synthetic_dispatch(SyntheticDispatchRequest(seed=42))

    assert response.status == "SUCCESS"
    assert response.verification_valid
    assert response.summary.selected_task_count == 18
    assert response.summary.assigned_task_count == 18
    assert response.summary.deadline_violation_count == 0
    assert response.routes
    assert not response.unassigned_bin_ids
    assert all(route.path for route in response.routes)
    assert all(
        route.assigned_load_liters <= route.vehicle_capacity_liters
        for route in response.routes
    )


def test_dispatch_is_deterministic_for_the_same_request() -> None:
    request = SyntheticDispatchRequest(seed=17, selected_bin_count=12, vehicle_count=6)

    assert plan_synthetic_dispatch(request) == plan_synthetic_dispatch(request)


def test_dispatch_reports_capacity_infeasibility_without_installing_a_plan() -> None:
    response = plan_synthetic_dispatch(SyntheticDispatchRequest(
        seed=42,
        selected_bin_count=5,
        vehicle_count=2,
        vehicle_capacity_liters=100,
    ))

    assert response.status == "INFEASIBLE"
    assert response.reason == "REQUIRED_TASK_CAPACITY_EXCEEDED"
    assert not response.verification_valid
    assert response.routes == ()
