"""Thread-safe product runtime around the existing deterministic workflow."""

from __future__ import annotations

from threading import Lock
from typing import Literal

from cityclean_agent.agent.protocols import EventDecisionAgent
from cityclean_agent.domain.enums import CityEventType
from cityclean_agent.domain.models import CityEvent
from cityclean_agent.optimizer.ortools_optimizer import ORToolsOptimizer
from cityclean_agent.runtime.contracts import (
    CitySnapshotResponse,
    RuntimeStatusResponse,
    WorkflowRunResponse,
    snapshot_response,
    workflow_response,
)
from cityclean_agent.simulator.city_sim import CitySim
from cityclean_agent.verifier.plan_verifier import PlanVerifier
from cityclean_agent.workflow import process_event


class InvalidCityEventError(ValueError):
    """Raised before workflow execution when event facts are invalid."""


class CityRuntime:
    """Serialize access to one authoritative CitySim instance."""

    def __init__(
        self,
        sim: CitySim,
        *,
        event_agent: EventDecisionAgent,
        source_name: str,
        data_mode: Literal["test", "production"],
        optimizer: ORToolsOptimizer | None = None,
        verifier: PlanVerifier | None = None,
    ) -> None:
        self._sim = sim
        self._event_agent = event_agent
        self._source_name = source_name
        self._data_mode = data_mode
        self._optimizer = optimizer
        self._verifier = verifier
        self._lock = Lock()

    def status(self) -> RuntimeStatusResponse:
        return RuntimeStatusResponse(
            status="ready",
            detail=(
                "生产城市状态源已连接。"
                if self._data_mode == "production"
                else "本地测试状态源已连接。"
            ),
            capabilities=("city_snapshot", "policy_agent", "structured_event_workflow"),
            source_name=self._source_name,
            data_mode=self._data_mode,
        )

    def snapshot(self) -> CitySnapshotResponse:
        with self._lock:
            return snapshot_response(self._sim.get_state())

    def process(self, event: CityEvent) -> WorkflowRunResponse:
        with self._lock:
            state = self._sim.get_state()
            self._validate_event_references(event, state)
            result = process_event(
                self._sim,
                event,
                event_agent=self._event_agent,
                optimizer=self._optimizer,
                verifier=self._verifier,
            )
            return workflow_response(event.event_id, result)

    @staticmethod
    def _validate_event_references(event: CityEvent, state) -> None:
        if event.timestamp > state.current_time:
            raise InvalidCityEventError(
                "event timestamp must be due at the current runtime time"
            )

        if event.event_type is CityEventType.VEHICLE_BREAKDOWN:
            known_ids = set(state.vehicles)
            entity_name = "vehicle"
        elif event.event_type is CityEventType.ROAD_CLOSURE:
            known_ids = {road.id for road in state.road_network.roads}
            entity_name = "road"
        else:
            known_ids = set(state.waste_points)
            entity_name = "waste point"

        unknown_ids = sorted(set(event.affected_entities) - known_ids)
        if unknown_ids:
            raise InvalidCityEventError(
                f"event references unknown {entity_name} IDs: {', '.join(unknown_ids)}"
            )
