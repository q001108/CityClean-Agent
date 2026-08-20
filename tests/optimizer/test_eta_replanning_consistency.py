from __future__ import annotations

from cityclean_agent.domain.enums import ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import CityState, Road, ServiceTask, Vehicle, WastePoint
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.optimizer.results import OptimizationStatus
from cityclean_agent.policy.models import PolicyParameters
from cityclean_agent.verifier.plan_verifier import PlanVerifier


PARAMETERS = PolicyParameters(
    distance_weight=1,
    lateness_weight=10,
    unserved_task_penalty=1_000,
    rescheduling_weight=0,
)


def test_multitask_replanning_eta_matches_arrival_and_completion_semantics() -> None:
    state = CityState(
        current_time=20,
        waste_points={
            "W1": WastePoint("W1", "B", 20, 4, 0, "mixed", "residential", 1),
            "WU": WastePoint("WU", "C", 20, 4, 0, "mixed", "school", 1),
            "W2": WastePoint("W2", "D", 20, 4, 0, "mixed", "market", 1),
        },
        vehicles={
            "V1": Vehicle("V1", "A", 10, 0, VehicleStatus.AVAILABLE, 30),
            "V2": Vehicle("V2", "Z", 10, 0, VehicleStatus.AVAILABLE, 30),
        },
        transfer_stations={},
        road_network=RoadNetwork(
            [
                Road("AB", "A", "B", 1, 4),
                Road("BC", "B", "C", 1, 3),
                Road("CD", "C", "D", 1, 3),
                Road("ZC", "Z", "C", 20, 20),
            ]
        ),
        tasks={
            "T1": ServiceTask("T1", "E1", "W1", 1, 1, 29),
            "TU": ServiceTask("TU", "E2", "WU", 1, 10, 37),
            "T2": ServiceTask("T2", "E3", "W2", 1, 1, None),
        },
    )

    result = ORToolsOptimizer().optimize(state, PARAMETERS)

    assert result.status is OptimizationStatus.FEASIBLE
    assert result.plan is not None
    route = result.plan.vehicle_routes[0]
    assert route.task_sequence == ["T1", "TU", "T2"]
    assert route.planned_arrivals == {"T1": 24, "TU": 32, "T2": 40}
    assert PlanVerifier().verify(state, result.plan).valid


def test_high_priority_deadline_uses_completion_not_arrival() -> None:
    state = CityState(
        current_time=0,
        waste_points={
            "W1": WastePoint("W1", "B", 20, 4, 0, "mixed", "residential", 1)
        },
        vehicles={
            "V1": Vehicle("V1", "A", 10, 0, VehicleStatus.AVAILABLE, 30)
        },
        transfer_stations={},
        road_network=RoadNetwork([Road("AB", "A", "B", 1, 10)]),
        tasks={
            "T1": ServiceTask("T1", "E1", "W1", 1, 10, 14),
        },
    )

    result = ORToolsOptimizer().optimize(state, PARAMETERS)

    assert result.status is OptimizationStatus.INFEASIBLE
    assert result.reason == "REQUIRED_TASK_DEADLINE_UNACHIEVABLE"


def test_high_priority_deadline_equal_to_completion_is_feasible() -> None:
    state = CityState(
        current_time=0,
        waste_points={
            "W1": WastePoint("W1", "B", 20, 4, 0, "mixed", "residential", 1)
        },
        vehicles={
            "V1": Vehicle("V1", "A", 10, 0, VehicleStatus.AVAILABLE, 30)
        },
        transfer_stations={},
        road_network=RoadNetwork([Road("AB", "A", "B", 1, 10)]),
        tasks={
            "T1": ServiceTask("T1", "E1", "W1", 1, 10, 15),
        },
    )

    result = ORToolsOptimizer().optimize(state, PARAMETERS)

    assert result.status is OptimizationStatus.FEASIBLE
    assert result.plan is not None
    assert result.plan.vehicle_routes[0].planned_arrivals == {"T1": 10}
    assert PlanVerifier().verify(state, result.plan).valid
