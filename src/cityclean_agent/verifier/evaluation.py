"""Fixed adversarial evaluation for the existing independent plan verifier."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

from cityclean_agent.domain.enums import RoadStatus, ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import CityState, DispatchPlan, Road, ServiceTask, Vehicle, VehicleRoute, WastePoint
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.verifier.plan_verifier import PlanVerifier


@dataclass(frozen=True, slots=True)
class VerifierEvaluationCase:
    """One fixed valid control or directly submitted adversarial dispatch plan."""

    case_id: str
    expected_valid: bool
    expected_violation_types: tuple[str, ...]
    build_state: Callable[[], CityState]
    build_plan: Callable[[], DispatchPlan]


@dataclass(frozen=True, slots=True)
class VerifierEvaluationCaseResult:
    """Observed verifier facts for one fixed evaluation case."""

    case_id: str
    expected_valid: bool
    actual_valid: bool
    expected_violation_types: tuple[str, ...]
    detected_violation_types: tuple[str, ...]
    passed_expectation: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VerifierEvaluationSummary:
    """Small report-ready aggregate of fixed-suite verifier behavior."""

    total_cases: int
    valid_cases: int
    adversarial_cases: int
    correctly_accepted_valid: int
    correctly_rejected_invalid: int
    invalid_detection_rate: float
    valid_acceptance_rate: float
    detected_violation_type_coverage: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def verifier_evaluation_suite() -> tuple[VerifierEvaluationCase, ...]:
    """Return two controls and thirteen manually specified adversarial plans."""

    return (
        VerifierEvaluationCase(
            "valid_single_vehicle",
            True,
            (),
            _base_state,
            lambda: _plan("valid-single", [VehicleRoute("V1", ["T1"], {"T1": 5})]),
        ),
        VerifierEvaluationCase(
            "valid_multi_vehicle",
            True,
            (),
            _base_state,
            lambda: _plan(
                "valid-multi",
                [
                    VehicleRoute("V1", ["T1"], {"T1": 5}),
                    VehicleRoute("V2", ["T2"], {"T2": 9}),
                ],
            ),
        ),
        VerifierEvaluationCase(
            "unknown_vehicle",
            False,
            ("vehicle_exists",),
            _base_state,
            lambda: _plan("unknown-vehicle", [VehicleRoute("UNKNOWN", ["T1"])]),
        ),
        VerifierEvaluationCase(
            "unavailable_vehicle",
            False,
            ("vehicle_available",),
            _broken_vehicle_state,
            lambda: _plan("broken-vehicle", [VehicleRoute("V1", ["T1"])]),
        ),
        VerifierEvaluationCase(
            "unknown_task",
            False,
            ("task_exists",),
            _base_state,
            lambda: _plan("unknown-task", [VehicleRoute("V1", ["UNKNOWN"])]),
        ),
        VerifierEvaluationCase(
            "invalid_task_status",
            False,
            ("task_status_valid",),
            _completed_task_state,
            lambda: _plan("completed-task", [VehicleRoute("V1", ["T1"])]),
        ),
        VerifierEvaluationCase(
            "duplicate_same_route",
            False,
            ("duplicate_assignment",),
            _base_state,
            _duplicate_same_route_plan,
        ),
        VerifierEvaluationCase(
            "duplicate_cross_vehicle",
            False,
            ("duplicate_assignment",),
            _base_state,
            lambda: _plan(
                "duplicate-cross",
                [VehicleRoute("V1", ["T1"]), VehicleRoute("V2", ["T1"])],
            ),
        ),
        VerifierEvaluationCase(
            "capacity_exceeded",
            False,
            ("capacity_valid",),
            _capacity_state,
            lambda: _plan("capacity", [VehicleRoute("V1", ["T1", "T2"])]),
        ),
        VerifierEvaluationCase(
            "unreachable_route",
            False,
            ("road_accessible",),
            _unreachable_state,
            lambda: _plan("unreachable", [VehicleRoute("V1", ["T1"])]),
        ),
        VerifierEvaluationCase(
            "closed_road_effect",
            False,
            ("road_accessible",),
            _closed_road_state,
            lambda: _plan("closed-road", [VehicleRoute("V1", ["T1"])]),
        ),
        VerifierEvaluationCase(
            "hard_deadline_violation",
            False,
            ("deadline_valid",),
            _deadline_state,
            lambda: _plan("deadline", [VehicleRoute("V1", ["T1"])]),
        ),
        VerifierEvaluationCase(
            "falsified_planned_arrival",
            False,
            ("planned_arrivals_consistent",),
            _base_state,
            lambda: _plan("false-eta", [VehicleRoute("V1", ["T1"], {"T1": 4})]),
        ),
        VerifierEvaluationCase(
            "must_serve_unassigned",
            False,
            ("must_serve_unassigned",),
            _base_state,
            lambda: _plan("must-unassigned", [], ["T1"]),
        ),
        VerifierEvaluationCase(
            "assigned_and_unassigned",
            False,
            ("assignment_unassigned_conflict",),
            _normal_task_state,
            lambda: _plan("assignment-conflict", [VehicleRoute("V1", ["T1"])], ["T1"]),
        ),
    )


def evaluate_verifier_suite(
    cases: Iterable[VerifierEvaluationCase] | None = None,
) -> tuple[VerifierEvaluationCaseResult, ...]:
    """Submit every fixed plan directly to PlanVerifier without repair or replanning."""

    selected_cases = verifier_evaluation_suite() if cases is None else tuple(cases)
    verifier = PlanVerifier()
    results: list[VerifierEvaluationCaseResult] = []
    for case in selected_cases:
        verification = verifier.verify(case.build_state(), case.build_plan())
        detected = tuple(
            sorted({violation.violation_type for violation in verification.violations})
        )
        expected = set(case.expected_violation_types)
        passed_expectation = (
            verification.valid and not verification.violations
            if case.expected_valid
            else not verification.valid and expected.issubset(detected)
        )
        results.append(
            VerifierEvaluationCaseResult(
                case_id=case.case_id,
                expected_valid=case.expected_valid,
                actual_valid=verification.valid,
                expected_violation_types=case.expected_violation_types,
                detected_violation_types=detected,
                passed_expectation=passed_expectation,
            )
        )
    return tuple(results)


def summarize_verifier_evaluation(
    results: Iterable[VerifierEvaluationCaseResult],
) -> VerifierEvaluationSummary:
    """Summarize controls, adversarial detection, and stable violation coverage."""

    result_list = tuple(results)
    valid_results = tuple(result for result in result_list if result.expected_valid)
    adversarial_results = tuple(result for result in result_list if not result.expected_valid)
    correctly_accepted_valid = sum(result.passed_expectation for result in valid_results)
    correctly_rejected_invalid = sum(
        result.passed_expectation for result in adversarial_results
    )
    return VerifierEvaluationSummary(
        total_cases=len(result_list),
        valid_cases=len(valid_results),
        adversarial_cases=len(adversarial_results),
        correctly_accepted_valid=correctly_accepted_valid,
        correctly_rejected_invalid=correctly_rejected_invalid,
        invalid_detection_rate=(
            correctly_rejected_invalid / len(adversarial_results)
            if adversarial_results
            else 0.0
        ),
        valid_acceptance_rate=(
            correctly_accepted_valid / len(valid_results) if valid_results else 0.0
        ),
        detected_violation_type_coverage=tuple(
            sorted(
                {
                    violation_type
                    for result in result_list
                    for violation_type in result.detected_violation_types
                }
            )
        ),
    )


def write_verifier_evaluation_results(
    path: Path, results: Iterable[VerifierEvaluationCaseResult]
) -> None:
    """Write the deterministic suite result and summary as machine-readable JSON."""

    result_list = tuple(results)
    path.write_text(
        json.dumps(
            {
                "summary": summarize_verifier_evaluation(result_list).to_dict(),
                "cases": [result.to_dict() for result in result_list],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _base_state() -> CityState:
    return CityState(
        current_time=0,
        waste_points={
            "W1": WastePoint("W1", "B", 100, 10, 0, "mixed", "residential", 1),
            "W2": WastePoint("W2", "C", 100, 10, 0, "mixed", "school", 1),
        },
        vehicles={
            "V1": Vehicle("V1", "A", 5, 0, VehicleStatus.AVAILABLE, 30),
            "V2": Vehicle("V2", "A", 5, 0, VehicleStatus.AVAILABLE, 30),
        },
        transfer_stations={},
        road_network=RoadNetwork([Road("AB", "A", "B", 2, 5), Road("BC", "B", "C", 1, 4)]),
        tasks={
            "T1": _task("T1", "W1", priority=10, deadline=10),
            "T2": _task("T2", "W2", priority=1, deadline=None),
        },
    )


def _broken_vehicle_state() -> CityState:
    state = _base_state()
    state.vehicles["V1"].status = VehicleStatus.BROKEN
    return state


def _completed_task_state() -> CityState:
    state = _base_state()
    state.tasks["T1"].status = ServiceTaskStatus.COMPLETED
    return state


def _capacity_state() -> CityState:
    state = _base_state()
    state.tasks["T1"] = _task("T1", "W1", demand=3, priority=1, deadline=None)
    state.tasks["T2"] = _task("T2", "W2", demand=3, priority=1, deadline=None)
    return state


def _unreachable_state() -> CityState:
    state = _base_state()
    state.road_network = RoadNetwork([])
    return state


def _closed_road_state() -> CityState:
    state = _base_state()
    state.road_network.get_road("AB").status = RoadStatus.CLOSED
    return state


def _deadline_state() -> CityState:
    state = _base_state()
    state.tasks["T1"] = _task("T1", "W1", priority=10, deadline=9)
    return state


def _normal_task_state() -> CityState:
    state = _base_state()
    state.tasks["T1"] = _task("T1", "W1", priority=1, deadline=None)
    return state


def _task(
    task_id: str,
    target_id: str,
    *,
    demand: float = 2,
    priority: int,
    deadline: int | None,
) -> ServiceTask:
    return ServiceTask(task_id, f"E-{task_id}", target_id, demand, priority, deadline)


def _plan(
    plan_id: str,
    routes: list[VehicleRoute],
    unassigned_tasks: list[str] | None = None,
) -> DispatchPlan:
    return DispatchPlan(plan_id, routes, unassigned_tasks or [])


def _duplicate_same_route_plan() -> DispatchPlan:
    plan = _plan("duplicate-same", [VehicleRoute("V1", ["T1"])])
    plan.vehicle_routes[0].task_sequence.append("T1")
    return plan
