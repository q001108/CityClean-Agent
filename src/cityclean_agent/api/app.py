"""FastAPI application factory for the versioned product API."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, status
from fastapi import Query

from cityclean_agent.agent.deepseek_event_agent import DeepSeekEventAgentError
from cityclean_agent.agent.protocols import EventDecisionAgent
from cityclean_agent.api.dependencies import (
    FacilityRepositoryDependency,
    RuntimeDependency,
)
from cityclean_agent.facilities.models import FacilityCreate, FacilityRecord
from cityclean_agent.facilities.repository import (
    FacilityAlreadyExistsError,
    SqliteFacilityRepository,
)
from cityclean_agent.runtime.contracts import (
    CityEventRequest,
    CitySnapshotResponse,
    HealthResponse,
    RuntimeStatusResponse,
    WorkflowRunResponse,
)
from cityclean_agent.runtime.service import CityRuntime, InvalidCityEventError
from cityclean_agent.simulator.synthetic_network import (
    SyntheticNetwork,
    generate_synthetic_network,
)
from cityclean_agent.simulator.synthetic_dispatch import (
    SyntheticDispatchRequest,
    SyntheticDispatchResponse,
    plan_synthetic_dispatch,
)
from cityclean_agent.simulator.synthetic_assessment import (
    SyntheticAssessmentRequest,
    SyntheticAssessmentResponse,
    assess_synthetic_scenario,
)
from cityclean_agent.simulator.synthetic_run import (
    SyntheticDisruptionRequest,
    SyntheticRunNotFoundError,
    SyntheticRunRegistry,
    SyntheticRunSnapshot,
    SyntheticRunStartResponse,
    SyntheticStepRequest,
)


def create_app(
    runtime: CityRuntime | None = None,
    facility_repository: SqliteFacilityRepository | None = None,
    deepseek_agent: EventDecisionAgent | None = None,
) -> FastAPI:
    app = FastAPI(
        title="CityClean Agent Runtime API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.runtime = runtime
    app.state.facility_repository = facility_repository
    app.state.deepseek_agent = deepseek_agent
    app.state.synthetic_runs = SyntheticRunRegistry()

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/api/v1/runtime/status", response_model=RuntimeStatusResponse)
    def runtime_status() -> RuntimeStatusResponse:
        if app.state.runtime is None:
            return RuntimeStatusResponse(
                status="unavailable",
                detail="尚未配置权威城市状态源。",
                capabilities=(),
                source_name=None,
                data_mode=None,
            )
        return app.state.runtime.status()

    @app.get("/api/v1/runtime/snapshot", response_model=CitySnapshotResponse)
    def city_snapshot(runtime_service: RuntimeDependency) -> CitySnapshotResponse:
        return runtime_service.snapshot()

    @app.post("/api/v1/runtime/events", response_model=WorkflowRunResponse)
    def process_city_event(
        request: CityEventRequest,
        runtime_service: RuntimeDependency,
    ) -> WorkflowRunResponse:
        try:
            return runtime_service.process(request.to_domain())
        except InvalidCityEventError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "INVALID_CITY_EVENT", "message": str(exc)},
            ) from exc

    @app.get("/api/v1/facilities", response_model=list[FacilityRecord])
    def list_facilities(
        repository: FacilityRepositoryDependency,
    ) -> list[FacilityRecord]:
        return list(repository.list_facilities())

    @app.post(
        "/api/v1/facilities",
        response_model=FacilityRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def create_facility(
        request: FacilityCreate,
        repository: FacilityRepositoryDependency,
    ) -> FacilityRecord:
        try:
            return repository.create_facility(request)
        except FacilityAlreadyExistsError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "FACILITY_ALREADY_EXISTS", "message": str(exc)},
            ) from exc

    @app.get("/api/v1/simulation/network", response_model=SyntheticNetwork)
    def simulation_network(
        center_longitude: float = Query(default=114.0913, ge=-180, le=180),
        center_latitude: float = Query(default=32.147, ge=-90, le=90),
        seed: int = Query(default=20260922, ge=0, le=2_147_483_647),
        road_node_count: int = Query(default=120, ge=64, le=225),
        bin_count: int = Query(default=180, ge=80, le=400),
    ) -> SyntheticNetwork:
        return generate_synthetic_network(
            center_longitude=center_longitude,
            center_latitude=center_latitude,
            seed=seed,
            road_node_count=road_node_count,
            bin_count=bin_count,
        )

    @app.post(
        "/api/v1/simulation/assessments",
        response_model=SyntheticAssessmentResponse,
    )
    def simulation_assessment(
        request: SyntheticAssessmentRequest,
    ) -> SyntheticAssessmentResponse:
        try:
            return assess_synthetic_scenario(
                request,
                deepseek_agent=app.state.deepseek_agent,
            )
        except DeepSeekEventAgentError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "MODEL_ASSESSMENT_FAILED", "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "INVALID_ASSESSMENT", "message": str(exc)},
            ) from exc

    @app.post(
        "/api/v1/simulation/dispatch",
        response_model=SyntheticDispatchResponse,
    )
    def simulation_dispatch(
        request: SyntheticDispatchRequest,
    ) -> SyntheticDispatchResponse:
        try:
            return plan_synthetic_dispatch(request)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "INVALID_POLICY_DECISION", "message": str(exc)},
            ) from exc

    @app.post(
        "/api/v1/simulation/runs",
        response_model=SyntheticRunStartResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def start_simulation_run(
        request: SyntheticDispatchRequest,
    ) -> SyntheticRunStartResponse:
        return app.state.synthetic_runs.create(request)

    @app.get(
        "/api/v1/simulation/runs/{run_id}",
        response_model=SyntheticRunSnapshot,
    )
    def get_simulation_run(run_id: str) -> SyntheticRunSnapshot:
        return _run_or_404(lambda: app.state.synthetic_runs.get(run_id))

    @app.post(
        "/api/v1/simulation/runs/{run_id}/steps",
        response_model=SyntheticRunSnapshot,
    )
    def step_simulation_run(
        run_id: str,
        request: SyntheticStepRequest,
    ) -> SyntheticRunSnapshot:
        return _run_or_404(
            lambda: app.state.synthetic_runs.step(run_id, request.ticks)
        )

    @app.post(
        "/api/v1/simulation/runs/{run_id}/disruptions",
        response_model=SyntheticRunSnapshot,
    )
    def disrupt_simulation_run(
        run_id: str,
        request: SyntheticDisruptionRequest,
    ) -> SyntheticRunSnapshot:
        try:
            return _run_or_404(
                lambda: app.state.synthetic_runs.disrupt(run_id, request)
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "NO_DISRUPTION_TARGET", "message": str(exc)},
            ) from exc

    return app


def _run_or_404(operation):
    try:
        return operation()
    except SyntheticRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SYNTHETIC_RUN_NOT_FOUND", "message": "仿真运行会话不存在或服务已重启。"},
        ) from exc


app = create_app()
