"""Small fixed scenarios shared by all future benchmark baselines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from cityclean_agent.domain.enums import CityEventType, VehicleStatus
from cityclean_agent.domain.models import (
    CityEvent,
    CityState,
    Road,
    ServiceTask,
    TransferStation,
    Vehicle,
    WastePoint,
)
from cityclean_agent.domain.road_network import RoadNetwork


@dataclass(frozen=True, slots=True)
class BenchmarkScenario:
    """One reproducible episode definition with a fresh-state constructor."""

    scenario_id: str
    category: str
    build_initial_state: Callable[[], CityState]
    scheduled_events: tuple[CityEvent, ...]
    max_simulation_time: int


def scenario_bank() -> tuple[BenchmarkScenario, ...]:
    """Return the complete, stably ordered v0.1 deterministic scenario bank."""

    return (
        BenchmarkScenario("normal_control", "NORMAL", _base_state, (), 100),
        BenchmarkScenario(
            "vehicle_breakdown",
            "NORMAL",
            _base_state,
            (_event("E-breakdown", CityEventType.VEHICLE_BREAKDOWN, 10, ["V01"]),),
            100,
        ),
        BenchmarkScenario(
            "road_closure_detour",
            "NORMAL",
            _base_state,
            (_event("E-closure", CityEventType.ROAD_CLOSURE, 10, ["CD"]),),
            100,
        ),
        BenchmarkScenario(
            "urgent_task",
            "NORMAL",
            _base_state,
            (
                _event(
                    "E-urgent",
                    CityEventType.URGENT_TASK,
                    10,
                    ["W05"],
                    severity=10,
                    deadline=50,
                ),
            ),
            100,
        ),
        BenchmarkScenario(
            "waste_overflow",
            "NORMAL",
            _base_state,
            (_event("E-overflow", CityEventType.WASTE_OVERFLOW, 10, ["W05"]),),
            100,
        ),
        BenchmarkScenario(
            "breakdown_capacity_tight",
            "STRESS",
            _capacity_tight_state,
            (_event("E-tight-breakdown", CityEventType.VEHICLE_BREAKDOWN, 10, ["V01"]),),
            35,
        ),
        BenchmarkScenario(
            "urgent_infeasible",
            "STRESS",
            _urgent_infeasible_state,
            (
                _event(
                    "E-infeasible-urgent",
                    CityEventType.URGENT_TASK,
                    0,
                    ["W05"],
                    severity=10,
                    deadline=30,
                ),
            ),
            30,
        ),
        BenchmarkScenario(
            "urgent_timing_tradeoff",
            "POLICY_STRESS",
            _urgent_timing_tradeoff_state,
            (
                _event(
                    "E-policy-urgent",
                    CityEventType.URGENT_TASK,
                    10,
                    ["WU"],
                    severity=10,
                    deadline=40,
                ),
            ),
            60,
        ),
        BenchmarkScenario(
            "overflow_service_tradeoff",
            "POLICY_STRESS",
            _overflow_service_tradeoff_state,
            (
                _event(
                    "E-policy-overflow",
                    CityEventType.WASTE_OVERFLOW,
                    10,
                    ["WO"],
                    severity=3,
                ),
            ),
            60,
        ),
    )


def _base_state() -> CityState:
    return CityState(
        current_time=0,
        waste_points={
            "W01": WastePoint("W01", "B", 20, 6, 0, "mixed", "residential", 1),
            "W02": WastePoint("W02", "C", 20, 7, 0, "mixed", "school", 1),
            "W03": WastePoint("W03", "D", 20, 5, 0, "mixed", "market", 1),
            "W04": WastePoint("W04", "E", 20, 4, 0, "mixed", "industrial", 1),
            "W05": WastePoint("W05", "F", 4, 3, 0, "mixed", "park", 1),
        },
        vehicles={
            "V01": Vehicle("V01", "A", 12, 0, VehicleStatus.AVAILABLE, 30),
            "V02": Vehicle("V02", "Z", 12, 0, VehicleStatus.AVAILABLE, 30),
            "V03": Vehicle("V03", "G", 12, 0, VehicleStatus.AVAILABLE, 30),
        },
        transfer_stations={"TS01": TransferStation("TS01", "F", 100)},
        road_network=RoadNetwork(
            [
                Road("AB", "A", "B", 1, 5),
                Road("BC", "B", "C", 1, 5),
                Road("CD", "C", "D", 1, 5),
                Road("DE", "D", "E", 1, 5),
                Road("EF", "E", "F", 1, 5),
                Road("CX", "C", "X", 2, 3),
                Road("XD", "X", "D", 2, 3),
                Road("ZC", "Z", "C", 20, 5),
                Road("GF", "G", "F", 20, 5),
            ]
        ),
        tasks={
            "T01": _task("T01", "W01"),
            "T02": _task("T02", "W02"),
            "T03": _task("T03", "W03"),
            "T04": _task("T04", "W04"),
            "T05": _task("T05", "W04"),
            "T06": _task("T06", "W04"),
        },
    )


def _capacity_tight_state() -> CityState:
    state = _base_state()
    state.vehicles["V02"].capacity = 8
    state.vehicles["V02"].current_load = 8
    state.vehicles["V03"].status = VehicleStatus.BROKEN
    return state


def _urgent_infeasible_state() -> CityState:
    state = _base_state()
    state.tasks.clear()
    for vehicle in state.vehicles.values():
        vehicle.status = VehicleStatus.BROKEN
    return state


def _urgent_timing_tradeoff_state() -> CityState:
    """Leave a normal task at B when the urgent event arrives at minute 10."""

    return CityState(
        current_time=0,
        waste_points={
            "WN": WastePoint("WN", "B", 20, 4, 0, "mixed", "residential", 1),
            "WU": WastePoint("WU", "C", 20, 1, 0, "mixed", "school", 1),
        },
        vehicles={
            "V1": Vehicle("V1", "A", 3, 0, VehicleStatus.AVAILABLE, 30),
            "V2": Vehicle("V2", "Z", 1, 0, VehicleStatus.AVAILABLE, 30),
        },
        transfer_stations={},
        road_network=RoadNetwork(
            [
                Road("AB", "A", "B", 1, 5),
                Road("BC", "B", "C", 1, 5),
                Road("ZC", "Z", "C", 50, 5),
            ]
        ),
        tasks={
            "T01": ServiceTask("T01", "benchmark-initial", "WN", 1, 1, None, created_at=0),
            "T02": ServiceTask("T02", "benchmark-initial", "WN", 1, 1, None, created_at=0),
        },
    )


def _overflow_service_tradeoff_state() -> CityState:
    """Leave a normal task at B when a priority-four overflow occurs at minute 10."""

    return CityState(
        current_time=0,
        waste_points={
            "WN": WastePoint("WN", "B", 20, 4, 0, "mixed", "residential", 1),
            "WO": WastePoint("WO", "F", 4, 3, 0, "mixed", "park", 4),
        },
        vehicles={
            "V1": Vehicle("V1", "A", 3, 0, VehicleStatus.AVAILABLE, 30),
            "V2": Vehicle("V2", "Z", 4, 0, VehicleStatus.AVAILABLE, 30),
        },
        transfer_stations={},
        road_network=RoadNetwork(
            [
                Road("AB", "A", "B", 1, 5),
                Road("ZF", "Z", "F", 500, 20),
            ]
        ),
        tasks={
            "T01": ServiceTask("T01", "benchmark-initial", "WN", 1, 1, None, created_at=0),
            "T02": ServiceTask("T02", "benchmark-initial", "WN", 1, 1, None, created_at=0),
        },
    )


def _task(task_id: str, target_id: str) -> ServiceTask:
    return ServiceTask(
        task_id=task_id,
        source_event_id="benchmark-initial",
        target_id=target_id,
        demand=2,
        priority=1,
        deadline=None,
        created_at=0,
    )


def _event(
    event_id: str,
    event_type: CityEventType,
    timestamp: int,
    affected_entities: list[str],
    *,
    severity: int = 3,
    deadline: int | None = None,
) -> CityEvent:
    return CityEvent(
        event_id=event_id,
        event_type=event_type,
        timestamp=timestamp,
        location="benchmark",
        description=f"Benchmark event: {event_type.value}",
        affected_entities=affected_entities,
        severity=severity,
        deadline=deadline,
    )
