"""FastAPI dependency functions for runtime availability."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from cityclean_agent.runtime.service import CityRuntime
from cityclean_agent.facilities.repository import SqliteFacilityRepository


def require_runtime(request: Request) -> CityRuntime:
    runtime: CityRuntime | None = request.app.state.runtime
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "RUNTIME_UNAVAILABLE",
                "message": "尚未配置权威城市状态源。",
            },
        )
    return runtime


RuntimeDependency = Annotated[CityRuntime, Depends(require_runtime)]


def require_facility_repository(request: Request) -> SqliteFacilityRepository:
    repository: SqliteFacilityRepository | None = request.app.state.facility_repository
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "FACILITY_REGISTRY_UNAVAILABLE",
                "message": "设施台账存储尚未配置。",
            },
        )
    return repository


FacilityRepositoryDependency = Annotated[
    SqliteFacilityRepository,
    Depends(require_facility_repository),
]
