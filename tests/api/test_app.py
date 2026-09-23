from fastapi.testclient import TestClient
from pathlib import Path

from cityclean_agent.agent.mock_event_agent import MockEventAgent
from cityclean_agent.api.app import create_app
from cityclean_agent.domain.enums import VehicleStatus
from cityclean_agent.domain.models import CityState, Road, Vehicle, WastePoint
from cityclean_agent.domain.road_network import GeoCoordinate, RoadNetwork
from cityclean_agent.facilities.repository import SqliteFacilityRepository
from cityclean_agent.runtime.service import CityRuntime
from cityclean_agent.policy.models import PolicyDecision, PolicyProfile
from cityclean_agent.simulator.city_sim import CitySim


def make_client() -> TestClient:
    state = CityState(
        current_time=10,
        waste_points={
            "W1": WastePoint("W1", "B", 20, 8, 0, "mixed", "residential", 2)
        },
        vehicles={
            "V1": Vehicle("V1", "A", 20, 0, VehicleStatus.AVAILABLE, 30)
        },
        transfer_stations={},
        road_network=RoadNetwork(
            [Road("AB", "A", "B", 1, 5)],
            node_coordinates={
                "A": GeoCoordinate(114.0913, 32.147),
                "B": GeoCoordinate(114.105, 32.155),
            },
        ),
    )
    runtime = CityRuntime(
        CitySim(state),
        event_agent=MockEventAgent(),
        source_name="api-test",
        data_mode="test",
    )
    return TestClient(create_app(runtime))


def event_payload(**overrides):
    payload = {
        "event_id": "E1",
        "event_type": "URGENT_TASK",
        "timestamp": 10,
        "location": "B",
        "affected_entities": ["W1"],
        "severity": 4,
        "deadline": 30,
        "metadata": {"demand": 5},
        "description": "urgent collection",
    }
    payload.update(overrides)
    return payload


def test_default_app_is_healthy_but_runtime_is_explicitly_unavailable() -> None:
    client = TestClient(create_app())

    assert client.get("/api/v1/health").json()["status"] == "ok"
    status_response = client.get("/api/v1/runtime/status")
    snapshot_response = client.get("/api/v1/runtime/snapshot")

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "unavailable"
    assert snapshot_response.status_code == 503
    assert snapshot_response.json()["detail"]["code"] == "RUNTIME_UNAVAILABLE"


def test_ready_runtime_exposes_snapshot_and_runs_structured_event() -> None:
    client = make_client()

    assert client.get("/api/v1/runtime/status").json()["status"] == "ready"
    assert client.get("/api/v1/runtime/status").json()["data_mode"] == "test"
    before = client.get("/api/v1/runtime/snapshot").json()
    response = client.post("/api/v1/runtime/events", json=event_payload())
    after = client.get("/api/v1/runtime/snapshot").json()

    assert before["active_events"] == []
    assert before["vehicles"][0]["coordinate"]["longitude"] == 114.0913
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    assert response.json()["plan"] is not None
    assert after["active_events"][0]["event_id"] == "E1"
    assert after["tasks"][0]["source_event_id"] == "E1"
    assert len(after["active_plan"]["vehicle_routes"][0]["path"]) == 2


def test_duplicate_event_is_an_explicit_ignored_result() -> None:
    client = make_client()

    client.post("/api/v1/runtime/events", json=event_payload())
    response = client.post("/api/v1/runtime/events", json=event_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "IGNORED"
    assert response.json()["reason"] == "EVENT_ALREADY_PROCESSED"


def test_unknown_entity_returns_422_without_mutating_runtime() -> None:
    client = make_client()

    response = client.post(
        "/api/v1/runtime/events",
        json=event_payload(affected_entities=["UNKNOWN"]),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_CITY_EVENT"
    assert client.get("/api/v1/runtime/snapshot").json()["active_events"] == []


def test_invalid_payload_is_rejected_by_transport_contract() -> None:
    client = make_client()

    response = client.post(
        "/api/v1/runtime/events",
        json=event_payload(metadata={"demand": -1}, unexpected=True),
    )

    assert response.status_code == 422


def test_facility_registry_persists_map_selected_facility(tmp_path: Path) -> None:
    repository = SqliteFacilityRepository(tmp_path / "facilities.db")
    client = TestClient(create_app(facility_repository=repository))
    payload = {
        "facility_id": "XP-001",
        "name": "东方红大道收运点",
        "facility_type": "COLLECTION_POINT",
        "address": "浉河区东方红大道",
        "longitude": 114.0913,
        "latitude": 32.147,
        "coordinate_system": "CGCS2000",
        "capacity": 12,
        "status": "ACTIVE",
        "source": "manual_map",
    }

    created = client.post("/api/v1/facilities", json=payload)
    listed = client.get("/api/v1/facilities")

    assert created.status_code == 201
    assert listed.status_code == 200
    assert listed.json()[0]["facility_id"] == "XP-001"
    assert listed.json()[0]["longitude"] == 114.0913


def test_facility_registry_rejects_duplicate_id(tmp_path: Path) -> None:
    repository = SqliteFacilityRepository(tmp_path / "facilities.db")
    client = TestClient(create_app(facility_repository=repository))
    payload = {
        "facility_id": "XP-001",
        "name": "测试收运点",
        "facility_type": "COLLECTION_POINT",
        "longitude": 114.0913,
        "latitude": 32.147,
    }

    assert client.post("/api/v1/facilities", json=payload).status_code == 201
    duplicate = client.post("/api/v1/facilities", json=payload)

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "FACILITY_ALREADY_EXISTS"


def test_unconfigured_facility_registry_returns_503() -> None:
    response = TestClient(create_app()).get("/api/v1/facilities")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "FACILITY_REGISTRY_UNAVAILABLE"


def test_simulation_network_is_available_without_runtime_or_registry() -> None:
    response = TestClient(create_app()).get(
        "/api/v1/simulation/network",
        params={"seed": 9, "road_node_count": 100, "bin_count": 140},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "synthetic"
    assert body["analysis"]["road_node_count"] == 100
    assert body["analysis"]["bin_count"] == 140
    assert len(body["edges"]) >= 160


def test_simulation_network_rejects_an_unrealistically_small_graph() -> None:
    response = TestClient(create_app()).get(
        "/api/v1/simulation/network",
        params={"road_node_count": 20},
    )

    assert response.status_code == 422


def test_simulation_dispatch_returns_verified_vehicle_routes() -> None:
    response = TestClient(create_app()).post(
        "/api/v1/simulation/dispatch",
        json={"seed": 42, "selected_bin_count": 12, "vehicle_count": 6},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["verification_valid"] is True
    assert body["summary"]["assigned_task_count"] == 12
    assert body["routes"]


def test_rule_assessment_exposes_auditable_facts_and_policy_mapping() -> None:
    response = TestClient(create_app()).post(
        "/api/v1/simulation/assessments",
        json={
            "seed": 42,
            "selected_bin_count": 12,
            "vehicle_count": 6,
            "vehicle_capacity_liters": 2200,
            "agent_mode": "RULE",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agent_mode"] == "RULE"
    assert body["model_call_status"] == "NOT_REQUESTED"
    assert body["model_name"] is None
    assert body["validated"] is True
    assert body["input_facts"]["candidate_count"] == 12
    assert len(body["policy_decision"]["priority_targets"]) == 12
    assert body["optimization_parameters"]["lateness_weight"] == 10


def test_rule_assessment_respects_resource_target_budget() -> None:
    response = TestClient(create_app()).post(
        "/api/v1/simulation/assessments",
        json={
            "seed": 42,
            "selected_bin_count": 30,
            "service_target_budget": 10,
            "vehicle_count": 4,
            "vehicle_capacity_liters": 1600,
            "agent_mode": "RULE",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["input_facts"]["candidate_count"] == 30
    assert body["input_facts"]["service_target_budget"] == 10
    assert len(body["policy_decision"]["priority_targets"]) == 10
    assert any(
        candidate["site_type"] == "HOSPITAL"
        and candidate["service_window_open"] is True
        for candidate in body["input_facts"]["candidates"]
    )
    assert any(
        candidate["site_type"] == "TRANSIT"
        and candidate["service_window_open"] is False
        for candidate in body["input_facts"]["candidates"]
    )


class _SubsetAssessmentAgent:
    def decide(self, event, state) -> PolicyDecision:
        return PolicyDecision(
            event_type=event.event_type,
            risk_level=5,
            reasoning_summary="医院与学校周边风险较高，优先处理前三个目标。",
            response_deadline=state.current_time + 90,
            priority_targets=tuple(event.affected_entities[:3]),
            policy_profile=PolicyProfile.URGENT_RESPONSE,
            constraints=("避让敏感场所服务窗口",),
        )


def test_deepseek_assessment_decision_drives_selected_dispatch_targets() -> None:
    client = TestClient(create_app(deepseek_agent=_SubsetAssessmentAgent()))
    assessment = client.post(
        "/api/v1/simulation/assessments",
        json={
            "seed": 42,
            "selected_bin_count": 12,
            "service_target_budget": 3,
            "vehicle_count": 6,
            "vehicle_capacity_liters": 2200,
            "agent_mode": "DEEPSEEK",
        },
    )

    assert assessment.status_code == 200
    evidence = assessment.json()
    assert evidence["model_call_status"] == "SUCCESS"
    assert evidence["model_name"] == "deepseek-v4-flash"
    dispatch = client.post(
        "/api/v1/simulation/dispatch",
        json={
            "seed": 42,
            "selected_bin_count": 12,
            "service_target_budget": 3,
            "vehicle_count": 6,
            "vehicle_capacity_liters": 2200,
            "policy_decision": evidence["policy_decision"],
        },
    )

    assert dispatch.status_code == 200
    body = dispatch.json()
    assert body["policy_decision"] == evidence["policy_decision"]
    assert body["summary"]["selected_task_count"] == 3
    assert {task["bin_id"] for task in body["tasks"]} == set(
        evidence["policy_decision"]["priority_targets"]
    )


def test_assessment_rejects_model_targets_over_resource_budget() -> None:
    response = TestClient(create_app(deepseek_agent=_SubsetAssessmentAgent())).post(
        "/api/v1/simulation/assessments",
        json={
            "seed": 42,
            "selected_bin_count": 12,
            "service_target_budget": 2,
            "vehicle_count": 4,
            "vehicle_capacity_liters": 1600,
            "agent_mode": "DEEPSEEK",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_ASSESSMENT"


def test_simulation_run_can_advance_and_replan_after_breakdown() -> None:
    client = TestClient(create_app())
    started = client.post(
        "/api/v1/simulation/runs",
        json={"seed": 42, "selected_bin_count": 12, "vehicle_count": 6},
    )

    assert started.status_code == 201
    run_id = started.json()["run"]["run_id"]
    advanced = client.post(
        f"/api/v1/simulation/runs/{run_id}/steps",
        json={"ticks": 1},
    )
    disrupted = client.post(
        f"/api/v1/simulation/runs/{run_id}/disruptions",
        json={"disruption_type": "VEHICLE_BREAKDOWN"},
    )

    assert advanced.status_code == 200
    assert advanced.json()["current_minute"] == 485
    assert disrupted.status_code == 200
    assert disrupted.json()["broken_vehicle_count"] == 1
    assert disrupted.json()["last_replan_status"] == "SUCCESS"


def test_unknown_simulation_run_returns_404() -> None:
    response = TestClient(create_app()).get(
        "/api/v1/simulation/runs/missing-run"
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SYNTHETIC_RUN_NOT_FOUND"
