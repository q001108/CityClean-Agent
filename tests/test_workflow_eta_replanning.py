from __future__ import annotations

from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import CityEvent, CityState, Road, ServiceTask, Vehicle, WastePoint
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.optimizer.results import OptimizationStatus
from cityclean_agent.policy.mapper import POLICY_PARAMETERS_BY_PROFILE
from cityclean_agent.policy.models import PolicyProfile
from cityclean_agent.simulator.city_sim import CitySim
from cityclean_agent.verifier.plan_verifier import PlanVerifier
from cityclean_agent.workflow import WorkflowStatus, process_event


def test_urgent_replan_with_multiple_existing_tasks_has_verifier_consistent_etas() -> None:
    sim = CitySim(
        CityState(
            current_time=0,
            waste_points={
                "W1": WastePoint("W1", "B", 20, 4, 0, "mixed", "residential", 1),
                "W2": WastePoint("W2", "C", 20, 4, 0, "mixed", "school", 1),
                "W3": WastePoint("W3", "D", 20, 4, 0, "mixed", "market", 1),
                "WU": WastePoint("WU", "E", 20, 2, 0, "mixed", "park", 1),
            },
            vehicles={
                "V1": Vehicle("V1", "A", 6, 0, VehicleStatus.AVAILABLE, 30),
                "V2": Vehicle("V2", "Z", 6, 0, VehicleStatus.AVAILABLE, 30),
            },
            transfer_stations={},
            road_network=RoadNetwork(
                [
                    Road("AB", "A", "B", 1, 5),
                    Road("BC", "B", "C", 1, 5),
                    Road("CD", "C", "D", 1, 5),
                    Road("DE", "D", "E", 1, 5),
                    Road("ZC", "Z", "C", 20, 5),
                ]
            ),
            tasks={
                "T1": ServiceTask("T1", "E0", "W1", 2, 1, None),
                "T2": ServiceTask("T2", "E0", "W2", 2, 1, None),
                "T3": ServiceTask("T3", "E0", "W3", 2, 1, None),
            },
        )
    )
    initial_result = ORToolsOptimizer().optimize(
        sim.get_state(), POLICY_PARAMETERS_BY_PROFILE[PolicyProfile.BALANCED]
    )
    assert initial_result.status is OptimizationStatus.FEASIBLE
    assert initial_result.plan is not None
    assert PlanVerifier().verify(sim.get_state(), initial_result.plan).valid
    sim.install_plan(initial_result.plan)
    sim.step()
    sim.step()
    assert sim.get_state().current_time == 10
    assert sim.get_state().tasks["T1"].status is ServiceTaskStatus.COMPLETED

    result = process_event(
        sim,
        CityEvent(
            "E-urgent",
            CityEventType.URGENT_TASK,
            10,
            "E",
            ["WU"],
            10,
            50,
            description="urgent cleanup",
        ),
    )

    assert result.status is WorkflowStatus.SUCCESS
    assert result.plan is not None
    assert result.verification_result is not None
    assert result.verification_result.valid
    assert {route.vehicle_id for route in result.plan.vehicle_routes}.issubset({"V1", "V2"})
    assert any(len(route.task_sequence) >= 2 for route in result.plan.vehicle_routes)
    assert all(
        arrival >= 10
        for route in result.plan.vehicle_routes
        for arrival in route.planned_arrivals.values()
    )
    assert sim.get_state().tasks["task-E-urgent-WU"].status is ServiceTaskStatus.ASSIGNED
