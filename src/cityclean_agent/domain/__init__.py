"""Core domain models and road-network utilities."""

from cityclean_agent.domain.enums import (
    CityEventType,
    RoadStatus,
    ServiceTaskStatus,
    VehicleStatus,
)
from cityclean_agent.domain.constants import MUST_SERVE_PRIORITY_THRESHOLD
from cityclean_agent.domain.models import (
    CityEvent,
    CityState,
    DispatchPlan,
    Road,
    ServiceTask,
    TransferStation,
    Vehicle,
    VehicleRoute,
    WastePoint,
)
from cityclean_agent.domain.road_network import GeoCoordinate, RoadNetwork, RoadPath
from cityclean_agent.domain.task_builder import TaskBuildResult, build_task_changes

__all__ = [
    "CityEvent",
    "CityEventType",
    "CityState",
    "DispatchPlan",
    "GeoCoordinate",
    "Road",
    "RoadNetwork",
    "RoadPath",
    "RoadStatus",
    "MUST_SERVE_PRIORITY_THRESHOLD",
    "ServiceTask",
    "ServiceTaskStatus",
    "TransferStation",
    "TaskBuildResult",
    "Vehicle",
    "VehicleRoute",
    "VehicleStatus",
    "WastePoint",
    "build_task_changes",
]
