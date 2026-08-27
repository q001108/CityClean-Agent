"""Deterministic measurement of the frozen CityClean governance Gold Set."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from cityclean_agent.agent.deepseek_event_agent import DeepSeekEventAgentError
from cityclean_agent.domain.constants import MUST_SERVE_PRIORITY_THRESHOLD
from cityclean_agent.domain.enums import CityEventType, ServiceTaskStatus, VehicleStatus
from cityclean_agent.domain.models import (
    CityEvent,
    CityState,
    DispatchPlan,
    Road,
    ServiceTask,
    Vehicle,
    VehicleRoute,
    WastePoint,
)
from cityclean_agent.domain.road_network import RoadNetwork
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD_JSON_PATH = _PROJECT_ROOT / "data" / "cityclean_governance_gold_v0.1.json"
DEFAULT_GOLD_JSONL_PATH = _PROJECT_ROOT / "data" / "cityclean_governance_gold_v0.1.jsonl"
POLICY_PROFILE_ORDER = (
    PolicyProfile.BALANCED.value,
    PolicyProfile.URGENT_RESPONSE.value,
    PolicyProfile.OVERFLOW_CONTROL.value,
    PolicyProfile.MINIMAL_RESCHEDULE.value,
)
_EXPECTED_EVENT_COUNTS = {
    CityEventType.WASTE_OVERFLOW.value: 10,
    CityEventType.URGENT_TASK.value: 10,
    CityEventType.VEHICLE_BREAKDOWN.value: 10,
    CityEventType.ROAD_CLOSURE.value: 10,
}
_EXPECTED_POLICY_COUNTS = {
    PolicyProfile.BALANCED.value: 7,
    PolicyProfile.URGENT_RESPONSE.value: 20,
    PolicyProfile.OVERFLOW_CONTROL.value: 5,
    PolicyProfile.MINIMAL_RESCHEDULE.value: 8,
}
_EXPECTED_RISK_COUNTS = {1: 4, 2: 11, 3: 7, 4: 13, 5: 5}


class GoldIntegrityError(ValueError):
    """Raised when the frozen Gold files do not match their declared contract."""


@dataclass(frozen=True, slots=True)
class GovernanceGoldCase:
    """One frozen Gold record, with labels retained only for post-call scoring."""

    case_id: str
    pair_id: str
    event_type: str
    dataset_version: str
    event_data: dict[str, Any]
    state_context: dict[str, Any]
    gold: dict[str, Any]
    annotation: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GoldIntegritySummary:
    """Mechanical facts proving the approved v0.1 data contract."""

    total_cases: int
    paired_groups: int
    event_type_counts: dict[str, int]
    policy_profile_counts: dict[str, int]
    risk_level_counts: dict[int, int]
    all_approved: bool
    jsonl_consistent: bool


@dataclass(frozen=True, slots=True)
class GovernanceGoldCaseResult:
    """One contract result and its post-call comparison against Gold labels."""

    case_id: str
    pair_id: str
    event_type: str
    contract_success: bool
    error_type: str | None
    error_message: str | None
    gold_policy_profile: str
    gold_risk_level: int
    gold_risk_range: tuple[int, int]
    gold_deadline_reference: int | None
    gold_deadline_range: tuple[int, int] | None
    gold_priority_targets: tuple[str, ...]
    predicted_policy_profile: str | None
    predicted_risk_level: int | None
    predicted_response_deadline: int | None
    predicted_priority_targets: tuple[str, ...]
    reasoning_summary: str | None
    policy_correct: bool | None
    risk_exact_correct: bool | None
    risk_abs_error: int | None
    risk_within_one: bool | None
    risk_in_acceptable_range: bool | None
    deadline_acceptable: bool | None
    deadline_abs_error: int | None
    target_exact: bool | None

    def to_dict(self) -> dict[str, object]:
        """Return machine-readable case data without Gold rationales or credentials."""

        return {
            "case_id": self.case_id,
            "pair_id": self.pair_id,
            "event_type": self.event_type,
            "contract_success": self.contract_success,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "gold_policy_profile": self.gold_policy_profile,
            "gold_risk_level": self.gold_risk_level,
            "gold_risk_range": list(self.gold_risk_range),
            "gold_deadline_reference": self.gold_deadline_reference,
            "gold_deadline_range": (
                list(self.gold_deadline_range)
                if self.gold_deadline_range is not None
                else None
            ),
            "gold_priority_targets": list(self.gold_priority_targets),
            "predicted_policy_profile": self.predicted_policy_profile,
            "predicted_risk_level": self.predicted_risk_level,
            "predicted_response_deadline": self.predicted_response_deadline,
            "predicted_priority_targets": list(self.predicted_priority_targets),
            "reasoning_summary": self.reasoning_summary,
            "policy_correct": self.policy_correct,
            "risk_exact_correct": self.risk_exact_correct,
            "risk_abs_error": self.risk_abs_error,
            "risk_within_one": self.risk_within_one,
            "risk_in_acceptable_range": self.risk_in_acceptable_range,
            "deadline_acceptable": self.deadline_acceptable,
            "deadline_abs_error": self.deadline_abs_error,
            "target_exact": self.target_exact,
        }


@dataclass(frozen=True, slots=True)
class PairContextResult:
    """Observed description-context changes for one fixed Gold pair."""

    pair_id: str
    both_contract_success: bool
    gold_profile_changed: bool
    predicted_profile_changed: bool | None
    gold_risk_changed: bool
    predicted_risk_changed: bool | None
    gold_deadline_changed: bool
    predicted_deadline_changed: bool | None
    profile_pair_correct: bool | None

    def to_dict(self) -> dict[str, object]:
        return {
            "pair_id": self.pair_id,
            "both_contract_success": self.both_contract_success,
            "gold_profile_changed": self.gold_profile_changed,
            "predicted_profile_changed": self.predicted_profile_changed,
            "gold_risk_changed": self.gold_risk_changed,
            "predicted_risk_changed": self.predicted_risk_changed,
            "gold_deadline_changed": self.gold_deadline_changed,
            "predicted_deadline_changed": self.predicted_deadline_changed,
            "profile_pair_correct": self.profile_pair_correct,
        }


@dataclass(frozen=True, slots=True)
class GovernanceGoldEvaluationSummary:
    """Aggregate governance-quality measures over contract-successful calls."""

    dataset_version: str
    total_cases: int
    successful_cases: int
    failed_cases: int
    contract_success_rate: float
    policy_accuracy: float
    policy_macro_f1: float
    policy_per_class_precision: dict[str, float]
    policy_per_class_recall: dict[str, float]
    policy_per_class_f1: dict[str, float]
    policy_confusion_matrix: tuple[tuple[int, ...], ...]
    risk_exact_accuracy: float
    risk_mae: float
    risk_within_one_accuracy: float
    risk_acceptable_range_accuracy: float
    deadline_acceptable_accuracy: float
    deadline_reference_mae: float
    deadline_numeric_evaluable_cases: int
    deadline_none_gold_cases: int
    deadline_predicted_none_cases: int
    target_precision: float
    target_recall: float
    target_f1: float
    target_exact_set_accuracy: float
    total_pairs: int
    both_success_pairs: int
    gold_profile_changed_pairs: int
    correct_profile_changed_pairs: int
    paired_profile_accuracy: float
    case_results: tuple[GovernanceGoldCaseResult, ...]
    pair_results: tuple[PairContextResult, ...]

    def to_dict(self) -> dict[str, object]:
        """Return stable JSON-compatible evaluation output."""

        return {
            "dataset_version": self.dataset_version,
            "total_cases": self.total_cases,
            "successful_cases": self.successful_cases,
            "failed_cases": self.failed_cases,
            "contract_success_rate": self.contract_success_rate,
            "policy": {
                "accuracy": self.policy_accuracy,
                "macro_f1": self.policy_macro_f1,
                "per_class_precision": self.policy_per_class_precision,
                "per_class_recall": self.policy_per_class_recall,
                "per_class_f1": self.policy_per_class_f1,
                "confusion_matrix_order": list(POLICY_PROFILE_ORDER),
                "confusion_matrix": [list(row) for row in self.policy_confusion_matrix],
            },
            "risk": {
                "exact_accuracy": self.risk_exact_accuracy,
                "mae": self.risk_mae,
                "within_one_accuracy": self.risk_within_one_accuracy,
                "acceptable_range_accuracy": self.risk_acceptable_range_accuracy,
            },
            "deadline": {
                "acceptable_accuracy": self.deadline_acceptable_accuracy,
                "reference_mae": self.deadline_reference_mae,
                "numeric_evaluable_cases": self.deadline_numeric_evaluable_cases,
                "none_gold_cases": self.deadline_none_gold_cases,
                "predicted_none_cases": self.deadline_predicted_none_cases,
            },
            "targets": {
                "precision": self.target_precision,
                "recall": self.target_recall,
                "f1": self.target_f1,
                "exact_set_accuracy": self.target_exact_set_accuracy,
            },
            "pairs": {
                "total_pairs": self.total_pairs,
                "both_success_pairs": self.both_success_pairs,
                "gold_profile_changed_pairs": self.gold_profile_changed_pairs,
                "correct_profile_changed_pairs": self.correct_profile_changed_pairs,
                "paired_profile_accuracy": self.paired_profile_accuracy,
            },
            "case_results": [result.to_dict() for result in self.case_results],
            "pair_results": [result.to_dict() for result in self.pair_results],
        }


def load_governance_gold_cases(
    path: Path = DEFAULT_GOLD_JSON_PATH,
) -> tuple[GovernanceGoldCase, ...]:
    """Load the frozen JSON Gold file without embedding cases in code."""

    records = _read_json_records(path)
    return tuple(_case_from_record(record) for record in records)


def validate_governance_gold_integrity(
    json_path: Path = DEFAULT_GOLD_JSON_PATH,
    jsonl_path: Path = DEFAULT_GOLD_JSONL_PATH,
) -> GoldIntegritySummary:
    """Fail closed when the two frozen Gold serializations are inconsistent."""

    json_records = _read_json_records(json_path)
    jsonl_records = _read_jsonl_records(jsonl_path)
    if json_records != jsonl_records:
        raise GoldIntegrityError("Gold JSON and JSONL records differ")

    cases = tuple(_case_from_record(record) for record in json_records)
    case_ids = [case.case_id for case in cases]
    pair_counts = Counter(case.pair_id for case in cases)
    event_counts = dict(Counter(case.event_type for case in cases))
    policy_counts = dict(Counter(case.gold["policy_profile"] for case in cases))
    risk_counts = dict(Counter(case.gold["risk_level"] for case in cases))
    approved = all(case.annotation.get("review_status") == "approved" for case in cases)

    if len(cases) != 40:
        raise GoldIntegrityError("Gold Set must contain exactly 40 cases")
    if len(set(case_ids)) != 40:
        raise GoldIntegrityError("Gold case_id values must be unique")
    if len(pair_counts) != 20 or set(pair_counts.values()) != {2}:
        raise GoldIntegrityError("Gold Set must contain 20 pairs with two cases each")
    if event_counts != _EXPECTED_EVENT_COUNTS:
        raise GoldIntegrityError("Gold event-type distribution differs from v0.1")
    if policy_counts != _EXPECTED_POLICY_COUNTS:
        raise GoldIntegrityError("Gold policy-profile distribution differs from v0.1")
    if risk_counts != _EXPECTED_RISK_COUNTS:
        raise GoldIntegrityError("Gold risk-level distribution differs from v0.1")
    if not approved:
        raise GoldIntegrityError("all Gold cases must be approved")

    return GoldIntegritySummary(
        total_cases=len(cases),
        paired_groups=len(pair_counts),
        event_type_counts=dict(sorted(event_counts.items())),
        policy_profile_counts=dict(sorted(policy_counts.items())),
        risk_level_counts=dict(sorted(risk_counts.items())),
        all_approved=True,
        jsonl_consistent=True,
    )


def build_gold_case_agent_input(case: GovernanceGoldCase) -> tuple[CityEvent, CityState]:
    """Build only the formal Agent input; Gold labels remain outside this boundary."""

    return build_gold_case_event(case), build_gold_case_state(case)


def build_gold_case_event(case: GovernanceGoldCase) -> CityEvent:
    """Create CityEvent directly from the frozen event payload."""

    event = case.event_data
    return CityEvent(
        event_id=event["event_id"],
        event_type=CityEventType(event["event_type"]),
        timestamp=event["timestamp"],
        location=event["location"],
        affected_entities=list(event["affected_entities"]),
        severity=event["severity"],
        deadline=event["deadline"],
        metadata=dict(event["metadata"]),
        description=event["description"],
    )


def build_gold_case_state(case: GovernanceGoldCase) -> CityState:
    """Map allowed state context facts to the smallest semantically matching CityState."""

    context = case.state_context
    points = {
        point["id"]: WastePoint(
            id=point["id"],
            node_id=f"gold-{case.case_id}-point-{point['id']}",
            capacity=point["capacity"],
            current_load=point["current_load"],
            generation_rate=0,
            waste_type="mixed",
            zone_type="gold-evaluation",
            priority=point["priority"],
        )
        for point in context["relevant_waste_points"]
    }
    primary_target_id = context.get("primary_target_id", next(iter(points), None))
    if primary_target_id not in points:
        raise GoldIntegrityError("Gold primary target must be a relevant WastePoint")

    event = build_gold_case_event(case)
    tasks, assigned_task_ids = _build_tasks(case, primary_target_id)
    vehicles = _build_vehicles(case, assigned_task_ids)
    road_network = _build_minimal_road_network(case, primary_target_id, points)
    active_plan = _build_active_plan(case, vehicles, assigned_task_ids)
    return CityState(
        current_time=context["current_time"],
        waste_points=points,
        vehicles=vehicles,
        transfer_stations={},
        road_network=road_network,
        tasks=tasks,
        active_plan=active_plan,
    )


def evaluate_governance_gold(
    agent: Any,
    cases: Iterable[GovernanceGoldCase],
) -> GovernanceGoldEvaluationSummary:
    """Call an Agent once per case, then measure only returned PolicyDecision values."""

    selected_cases = tuple(cases)
    results = tuple(_evaluate_case(agent, case) for case in selected_cases)
    return _summarize(selected_cases, results)


def write_governance_gold_evaluation_results(
    path: Path,
    summary: GovernanceGoldEvaluationSummary,
) -> None:
    """Write the generated live result without modifying frozen Gold data."""

    path.write_text(
        json.dumps(summary.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_json_records(path: Path) -> list[dict[str, Any]]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise GoldIntegrityError("Gold JSON must contain a list of cases")
    return records


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _case_from_record(record: Mapping[str, Any]) -> GovernanceGoldCase:
    return GovernanceGoldCase(
        case_id=record["case_id"],
        pair_id=record["pair_id"],
        event_type=record["event_type"],
        dataset_version=record["dataset_version"],
        event_data=dict(record["event"]),
        state_context=dict(record["state_context"]),
        gold=dict(record["gold"]),
        annotation=dict(record["annotation"]),
    )


def _build_tasks(
    case: GovernanceGoldCase, primary_target_id: str
) -> tuple[dict[str, ServiceTask], tuple[str, ...]]:
    summary = case.state_context["task_summary"]
    unfinished = summary["unfinished"]
    assigned = summary["assigned"]
    must_serve = summary["must_serve"]
    if not 0 <= assigned <= unfinished or not 0 <= must_serve <= unfinished:
        raise GoldIntegrityError("Gold task summary is internally inconsistent")

    task_ids = tuple(f"gold-{case.case_id}-task-{index:02d}" for index in range(unfinished))
    tasks = {
        task_id: ServiceTask(
            task_id=task_id,
            source_event_id=case.event_data["event_id"],
            target_id=primary_target_id,
            demand=1,
            priority=(MUST_SERVE_PRIORITY_THRESHOLD if index < must_serve else 1),
            deadline=case.event_data["deadline"],
            status=(
                ServiceTaskStatus.ASSIGNED
                if index < assigned
                else ServiceTaskStatus.PENDING
            ),
            created_at=case.state_context["current_time"],
        )
        for index, task_id in enumerate(task_ids)
    }
    return tasks, task_ids[:assigned]


def _build_vehicles(
    case: GovernanceGoldCase, assigned_task_ids: tuple[str, ...]
) -> dict[str, Vehicle]:
    summary = case.state_context["vehicle_summary"]
    counts = {
        VehicleStatus.AVAILABLE: summary["available"],
        VehicleStatus.BROKEN: summary["broken"],
        VehicleStatus.EN_ROUTE: summary["en_route"],
        VehicleStatus.SERVICING: summary["servicing"],
    }
    if sum(counts.values()) != summary["total"]:
        raise GoldIntegrityError("Gold vehicle summary is internally inconsistent")

    preferred_broken_id = case.event_data["metadata"].get("vehicle_id")
    vehicles: dict[str, Vehicle] = {}
    for status in (
        VehicleStatus.AVAILABLE,
        VehicleStatus.BROKEN,
        VehicleStatus.EN_ROUTE,
        VehicleStatus.SERVICING,
    ):
        for index in range(counts[status]):
            vehicle_id = _vehicle_id(case, status, index, preferred_broken_id)
            if vehicle_id in vehicles:
                raise GoldIntegrityError("Gold vehicle IDs must be constructible uniquely")
            vehicles[vehicle_id] = Vehicle(
                id=vehicle_id,
                current_node_id=f"gold-{case.case_id}-hub",
                capacity=100,
                current_load=0,
                status=status,
                speed=30,
            )

    if assigned_task_ids:
        owner = next(
            (vehicle for vehicle in vehicles.values() if vehicle.status is not VehicleStatus.BROKEN),
            None,
        )
        if owner is None:
            raise GoldIntegrityError("assigned tasks require at least one non-broken vehicle")
        owner.assigned_tasks.extend(assigned_task_ids)
    return vehicles


def _vehicle_id(
    case: GovernanceGoldCase,
    status: VehicleStatus,
    index: int,
    preferred_broken_id: object,
) -> str:
    if status is VehicleStatus.BROKEN and index == 0 and isinstance(preferred_broken_id, str):
        return preferred_broken_id
    return f"gold-{case.case_id}-{status.value.lower()}-{index:02d}"


def _build_minimal_road_network(
    case: GovernanceGoldCase,
    primary_target_id: str,
    points: Mapping[str, WastePoint],
) -> RoadNetwork:
    hub = f"gold-{case.case_id}-hub"
    target = points[primary_target_id].node_id
    requested_road_id = case.event_data["metadata"].get("road_id")
    forward_id = (
        requested_road_id
        if isinstance(requested_road_id, str)
        else f"gold-{case.case_id}-hub-target"
    )
    return RoadNetwork(
        (
            Road(forward_id, hub, target, 1, 1),
            Road(f"{forward_id}-return", target, hub, 1, 1),
        )
    )


def _build_active_plan(
    case: GovernanceGoldCase,
    vehicles: Mapping[str, Vehicle],
    assigned_task_ids: tuple[str, ...],
) -> DispatchPlan | None:
    if not case.state_context["active_plan_exists"]:
        return None
    owner = next(
        vehicle for vehicle in vehicles.values() if vehicle.assigned_tasks == list(assigned_task_ids)
    )
    return DispatchPlan(
        plan_id=f"gold-{case.case_id}-active-plan",
        vehicle_routes=[VehicleRoute(owner.id, list(assigned_task_ids))],
    )


def _evaluate_case(agent: Any, case: GovernanceGoldCase) -> GovernanceGoldCaseResult:
    event, state = build_gold_case_agent_input(case)
    try:
        decision = agent.decide(event, state)
        if not isinstance(decision, PolicyDecision):
            raise TypeError("Agent did not return PolicyDecision")
    except DeepSeekEventAgentError as exc:
        return _failed_case_result(case, _classify_agent_error(exc), str(exc))
    except Exception as exc:
        return _failed_case_result(case, "unexpected_error", str(exc))
    return _successful_case_result(case, decision)


def _classify_agent_error(error: DeepSeekEventAgentError) -> str:
    message = str(error)
    if "模型调用失败" in message:
        return "provider_error"
    if "未返回结构化" in message:
        return "structured_output_error"
    if "无效的 PolicyDecision" in message:
        return "schema_error"
    return "cross_validation_error"


def _failed_case_result(
    case: GovernanceGoldCase, error_type: str, error_message: str
) -> GovernanceGoldCaseResult:
    gold = case.gold
    return GovernanceGoldCaseResult(
        case_id=case.case_id,
        pair_id=case.pair_id,
        event_type=case.event_type,
        contract_success=False,
        error_type=error_type,
        error_message=error_message,
        gold_policy_profile=gold["policy_profile"],
        gold_risk_level=gold["risk_level"],
        gold_risk_range=tuple(gold["acceptable_risk_range"]),
        gold_deadline_reference=gold["response_deadline_reference"],
        gold_deadline_range=_deadline_range(gold),
        gold_priority_targets=tuple(gold["priority_targets"]),
        predicted_policy_profile=None,
        predicted_risk_level=None,
        predicted_response_deadline=None,
        predicted_priority_targets=(),
        reasoning_summary=None,
        policy_correct=None,
        risk_exact_correct=None,
        risk_abs_error=None,
        risk_within_one=None,
        risk_in_acceptable_range=None,
        deadline_acceptable=None,
        deadline_abs_error=None,
        target_exact=None,
    )


def _successful_case_result(
    case: GovernanceGoldCase, decision: PolicyDecision
) -> GovernanceGoldCaseResult:
    gold = case.gold
    risk_error = abs(decision.risk_level - gold["risk_level"])
    deadline_range = _deadline_range(gold)
    deadline_acceptable = _deadline_is_acceptable(
        decision.response_deadline,
        gold["response_deadline_reference"],
        deadline_range,
    )
    deadline_error = (
        abs(decision.response_deadline - gold["response_deadline_reference"])
        if decision.response_deadline is not None
        and gold["response_deadline_reference"] is not None
        else None
    )
    predicted_targets = tuple(decision.priority_targets)
    gold_targets = tuple(gold["priority_targets"])
    return GovernanceGoldCaseResult(
        case_id=case.case_id,
        pair_id=case.pair_id,
        event_type=case.event_type,
        contract_success=True,
        error_type=None,
        error_message=None,
        gold_policy_profile=gold["policy_profile"],
        gold_risk_level=gold["risk_level"],
        gold_risk_range=tuple(gold["acceptable_risk_range"]),
        gold_deadline_reference=gold["response_deadline_reference"],
        gold_deadline_range=deadline_range,
        gold_priority_targets=gold_targets,
        predicted_policy_profile=decision.policy_profile.value,
        predicted_risk_level=decision.risk_level,
        predicted_response_deadline=decision.response_deadline,
        predicted_priority_targets=predicted_targets,
        reasoning_summary=decision.reasoning_summary,
        policy_correct=decision.policy_profile.value == gold["policy_profile"],
        risk_exact_correct=risk_error == 0,
        risk_abs_error=risk_error,
        risk_within_one=risk_error <= 1,
        risk_in_acceptable_range=(
            gold["acceptable_risk_range"][0]
            <= decision.risk_level
            <= gold["acceptable_risk_range"][1]
        ),
        deadline_acceptable=deadline_acceptable,
        deadline_abs_error=deadline_error,
        target_exact=set(predicted_targets) == set(gold_targets),
    )


def _deadline_range(gold: Mapping[str, Any]) -> tuple[int, int] | None:
    value = gold["response_deadline_range"]
    return tuple(value) if value is not None else None


def _deadline_is_acceptable(
    predicted: int | None, reference: int | None, acceptable_range: tuple[int, int] | None
) -> bool:
    if reference is None:
        return predicted is None
    return predicted is not None and acceptable_range is not None and (
        acceptable_range[0] <= predicted <= acceptable_range[1]
    )


def _summarize(
    cases: tuple[GovernanceGoldCase, ...],
    results: tuple[GovernanceGoldCaseResult, ...],
) -> GovernanceGoldEvaluationSummary:
    successful = tuple(result for result in results if result.contract_success)
    policy_matrix = _policy_confusion_matrix(successful)
    precision, recall, f1 = _per_class_policy_metrics(policy_matrix)
    target_tp, target_fp, target_fn = _target_counts(successful)
    pair_results = _pair_results(results)
    both_success = tuple(result for result in pair_results if result.both_contract_success)
    profile_changed = tuple(result for result in both_success if result.gold_profile_changed)
    numeric_deadline_errors = tuple(
        result.deadline_abs_error
        for result in successful
        if result.deadline_abs_error is not None
    )
    return GovernanceGoldEvaluationSummary(
        dataset_version=_dataset_version(cases),
        total_cases=len(results),
        successful_cases=len(successful),
        failed_cases=len(results) - len(successful),
        contract_success_rate=_ratio(len(successful), len(results)),
        policy_accuracy=_ratio(
            sum(result.policy_correct is True for result in successful), len(successful)
        ),
        policy_macro_f1=sum(f1.values()) / len(POLICY_PROFILE_ORDER),
        policy_per_class_precision=precision,
        policy_per_class_recall=recall,
        policy_per_class_f1=f1,
        policy_confusion_matrix=policy_matrix,
        risk_exact_accuracy=_ratio(
            sum(result.risk_exact_correct is True for result in successful), len(successful)
        ),
        risk_mae=_mean(
            tuple(result.risk_abs_error for result in successful if result.risk_abs_error is not None)
        ),
        risk_within_one_accuracy=_ratio(
            sum(result.risk_within_one is True for result in successful), len(successful)
        ),
        risk_acceptable_range_accuracy=_ratio(
            sum(result.risk_in_acceptable_range is True for result in successful),
            len(successful),
        ),
        deadline_acceptable_accuracy=_ratio(
            sum(result.deadline_acceptable is True for result in successful), len(successful)
        ),
        deadline_reference_mae=_mean(numeric_deadline_errors),
        deadline_numeric_evaluable_cases=len(numeric_deadline_errors),
        deadline_none_gold_cases=sum(
            result.gold_deadline_reference is None for result in successful
        ),
        deadline_predicted_none_cases=sum(
            result.predicted_response_deadline is None for result in successful
        ),
        target_precision=_ratio(target_tp, target_tp + target_fp),
        target_recall=_ratio(target_tp, target_tp + target_fn),
        target_f1=_f1(
            _ratio(target_tp, target_tp + target_fp),
            _ratio(target_tp, target_tp + target_fn),
        ),
        target_exact_set_accuracy=_ratio(
            sum(result.target_exact is True for result in successful), len(successful)
        ),
        total_pairs=len(pair_results),
        both_success_pairs=len(both_success),
        gold_profile_changed_pairs=len(profile_changed),
        correct_profile_changed_pairs=sum(
            result.profile_pair_correct is True for result in profile_changed
        ),
        paired_profile_accuracy=_ratio(
            sum(result.profile_pair_correct is True for result in profile_changed),
            len(profile_changed),
        ),
        case_results=results,
        pair_results=pair_results,
    )


def _dataset_version(cases: tuple[GovernanceGoldCase, ...]) -> str:
    versions = {case.dataset_version for case in cases}
    if len(versions) > 1:
        raise GoldIntegrityError("evaluation cases must use one dataset version")
    return next(iter(versions), "unknown")


def _policy_confusion_matrix(
    results: tuple[GovernanceGoldCaseResult, ...],
) -> tuple[tuple[int, ...], ...]:
    matrix = [[0 for _ in POLICY_PROFILE_ORDER] for _ in POLICY_PROFILE_ORDER]
    indexes = {profile: index for index, profile in enumerate(POLICY_PROFILE_ORDER)}
    for result in results:
        matrix[indexes[result.gold_policy_profile]][indexes[result.predicted_policy_profile]] += 1
    return tuple(tuple(row) for row in matrix)


def _per_class_policy_metrics(
    matrix: tuple[tuple[int, ...], ...],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    precision: dict[str, float] = {}
    recall: dict[str, float] = {}
    f1: dict[str, float] = {}
    for index, profile in enumerate(POLICY_PROFILE_ORDER):
        true_positive = matrix[index][index]
        predicted_total = sum(row[index] for row in matrix)
        gold_total = sum(matrix[index])
        precision[profile] = _ratio(true_positive, predicted_total)
        recall[profile] = _ratio(true_positive, gold_total)
        f1[profile] = _f1(precision[profile], recall[profile])
    return precision, recall, f1


def _target_counts(
    results: tuple[GovernanceGoldCaseResult, ...],
) -> tuple[int, int, int]:
    true_positive = false_positive = false_negative = 0
    for result in results:
        gold_targets = set(result.gold_priority_targets)
        predicted_targets = set(result.predicted_priority_targets)
        true_positive += len(gold_targets.intersection(predicted_targets))
        false_positive += len(predicted_targets.difference(gold_targets))
        false_negative += len(gold_targets.difference(predicted_targets))
    return true_positive, false_positive, false_negative


def _pair_results(
    results: tuple[GovernanceGoldCaseResult, ...],
) -> tuple[PairContextResult, ...]:
    grouped: dict[str, list[GovernanceGoldCaseResult]] = {}
    for result in results:
        grouped.setdefault(result.pair_id, []).append(result)
    pair_results = []
    for pair_id in sorted(grouped):
        paired_results = sorted(grouped[pair_id], key=lambda result: result.case_id)
        if len(paired_results) != 2:
            continue
        first, second = paired_results
        both_success = first.contract_success and second.contract_success
        gold_profile_changed = first.gold_policy_profile != second.gold_policy_profile
        gold_risk_changed = first.gold_risk_level != second.gold_risk_level
        gold_deadline_changed = (
            first.gold_deadline_reference != second.gold_deadline_reference
        )
        pair_results.append(
            PairContextResult(
                pair_id=pair_id,
                both_contract_success=both_success,
                gold_profile_changed=gold_profile_changed,
                predicted_profile_changed=(
                    first.predicted_policy_profile != second.predicted_policy_profile
                    if both_success
                    else None
                ),
                gold_risk_changed=gold_risk_changed,
                predicted_risk_changed=(
                    first.predicted_risk_level != second.predicted_risk_level
                    if both_success
                    else None
                ),
                gold_deadline_changed=gold_deadline_changed,
                predicted_deadline_changed=(
                    first.predicted_response_deadline
                    != second.predicted_response_deadline
                    if both_success
                    else None
                ),
                profile_pair_correct=(
                    first.predicted_policy_profile == first.gold_policy_profile
                    and second.predicted_policy_profile == second.gold_policy_profile
                    if both_success and gold_profile_changed
                    else None
                ),
            )
        )
    return tuple(pair_results)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _mean(values: tuple[int, ...]) -> float:
    return sum(values) / len(values) if values else 0.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0
