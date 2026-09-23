export type RuntimeStatus = {
  status: "ready" | "unavailable";
  detail: string;
  capabilities: string[];
  source_name: string | null;
  data_mode: "test" | "production" | null;
};

export type CitySnapshot = {
  current_time: number;
  waste_points: Array<{ id: string; node_id: string; current_load: number; capacity: number; coordinate: GeoCoordinate | null }>;
  vehicles: Array<{ id: string; current_node_id: string; status: string; coordinate: GeoCoordinate | null }>;
  transfer_stations: Array<{ id: string; node_id: string; coordinate: GeoCoordinate | null }>;
  roads: Array<{
    id: string;
    from_node: string;
    to_node: string;
    status: string;
    from_coordinate: GeoCoordinate | null;
    to_coordinate: GeoCoordinate | null;
  }>;
  active_events: Array<{
    event_id: string;
    event_type: CityEventType;
    affected_entities: string[];
    severity: number;
  }>;
  tasks: Array<{
    task_id: string;
    source_event_id: string;
    target_id: string;
    status: string;
    priority: number;
  }>;
  active_plan: {
    plan_id: string;
    vehicle_routes: Array<{ vehicle_id: string; task_sequence: string[]; path: GeoCoordinate[] }>;
    unassigned_tasks: string[];
  } | null;
};

export type GeoCoordinate = {
  longitude: number;
  latitude: number;
};

export type FacilityType = "COLLECTION_POINT" | "TRANSFER_STATION" | "DEPOT" | "DISPOSAL_SITE";

export type FacilityRecord = {
  facility_id: string;
  name: string;
  facility_type: FacilityType;
  address: string | null;
  longitude: number;
  latitude: number;
  coordinate_system: "CGCS2000";
  capacity: number | null;
  status: "ACTIVE" | "INACTIVE";
  source: "manual_map";
  created_at: string;
  updated_at: string;
};

export type FacilityCreatePayload = Omit<FacilityRecord, "created_at" | "updated_at">;

export type SyntheticSiteType = "SCHOOL" | "HOSPITAL" | "RESIDENTIAL" | "COMMERCIAL" | "TRANSIT" | "PUBLIC_SPACE";
export type SyntheticRiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type PolicyDecision = {
  event_type: CityEventType;
  risk_level: number;
  reasoning_summary: string;
  response_deadline: number | null;
  priority_targets: string[];
  policy_profile: string;
  constraints: string[];
};

export type SyntheticNetwork = {
  scenario_id: string;
  seed: number;
  data_mode: "synthetic";
  disclaimer: string;
  center_longitude: number;
  center_latitude: number;
  nodes: Array<{ node_id: string; longitude: number; latitude: number }>;
  edges: Array<{
    edge_id: string;
    from_node: string;
    to_node: string;
    distance_km: number;
    travel_minutes: number;
    congestion_level: number;
  }>;
  bins: Array<{
    bin_id: string;
    node_id: string;
    site_type: SyntheticSiteType;
    site_name: string;
    longitude: number;
    latitude: number;
    capacity_liters: number;
    current_load_liters: number;
    fill_ratio: number;
    hourly_generation_liters: number;
    waste_type: string;
    priority: number;
    sensitivity: string;
    service_window: string;
    access_constraint: string;
    last_collected_minutes_ago: number;
    sensor_confidence: number;
    forecast_hours_to_overflow: number;
    risk_score: number;
    risk_level: SyntheticRiskLevel;
    risk_reasons: string[];
  }>;
  analysis: {
    road_node_count: number;
    road_edge_count: number;
    bin_count: number;
    critical_bin_count: number;
    high_risk_bin_count: number;
    projected_overflow_4h_count: number;
    sensitive_site_high_risk_count: number;
    average_fill_ratio: number;
    total_capacity_liters: number;
    disconnected_node_count: number;
  };
};

export type SyntheticDispatch = {
  scenario_id: string;
  data_mode: "synthetic";
  status: "SUCCESS" | "INFEASIBLE" | "VERIFICATION_FAILED";
  reason: string | null;
  selection_rule: string;
  verification_valid: boolean;
  policy_decision: PolicyDecision;
  tasks: Array<{
    task_id: string;
    bin_id: string;
    site_name: string;
    risk_score: number;
    risk_level: SyntheticRiskLevel;
    demand_liters: number;
    deadline_minute: number;
    assigned_vehicle_id: string | null;
    planned_arrival_minute: number | null;
  }>;
  routes: Array<{
    vehicle_id: string;
    vehicle_capacity_liters: number;
    assigned_load_liters: number;
    bin_sequence: string[];
    planned_arrivals: Record<string, number>;
    total_distance_km: number;
    total_travel_minutes: number;
    path: GeoCoordinate[];
  }>;
  unassigned_bin_ids: string[];
  summary: {
    selected_task_count: number;
    assigned_task_count: number;
    route_count: number;
    vehicle_count: number;
    fleet_capacity_liters: number;
    selected_load_liters: number;
    total_route_distance_km: number;
    max_route_load_liters: number;
    deadline_violation_count: number;
  };
};

export type SyntheticDispatchRequest = {
  seed: number;
  selected_bin_count: number;
  vehicle_count: number;
  vehicle_capacity_liters: number;
  service_target_budget?: number;
  policy_decision?: PolicyDecision;
};

export type SyntheticAssessmentMode = "RULE" | "DEEPSEEK";

export type SyntheticAssessment = {
  scenario_id: string;
  data_mode: "synthetic";
  agent_mode: SyntheticAssessmentMode;
  agent_name: string;
  model_name: string | null;
  model_call_status: "NOT_REQUESTED" | "SUCCESS";
  validated: boolean;
  latency_ms: number;
  input_facts: {
    current_minute: number;
    candidate_count: number;
    service_target_budget: number;
    vehicle_count: number;
    fleet_capacity_liters: number;
    candidate_load_liters: number;
    critical_target_count: number;
    sensitive_target_count: number;
    candidates: Array<{
      target_id: string;
      site_type: SyntheticSiteType;
      site_name: string;
      fill_ratio: number;
      risk_score: number;
      risk_level: SyntheticRiskLevel;
      forecast_hours_to_overflow: number;
      sensitivity: string;
      service_window: string;
      service_window_open: boolean;
      access_constraint: string;
      sensor_confidence: number;
      risk_reasons: string[];
    }>;
  };
  policy_decision: PolicyDecision;
  optimization_parameters: {
    distance_weight: number;
    lateness_weight: number;
    unserved_task_penalty: number;
    rescheduling_weight: number;
  };
};

export type SyntheticAssessmentRequest = Omit<SyntheticDispatchRequest, "policy_decision"> & {
  agent_mode: SyntheticAssessmentMode;
};

export type SyntheticRunSnapshot = {
  run_id: string;
  scenario_id: string;
  data_mode: "synthetic";
  status: "RUNNING" | "COMPLETED" | "NEEDS_ATTENTION";
  current_minute: number;
  elapsed_minutes: number;
  tick_minutes: number;
  task_count: number;
  completed_task_count: number;
  overflow_count: number;
  broken_vehicle_count: number;
  last_event: string | null;
  last_replan_status: string;
  vehicles: Array<{
    vehicle_id: string;
    status: string;
    current_node_id: string;
    coordinate: GeoCoordinate;
    current_load_liters: number;
    capacity_liters: number;
    assigned_task_ids: string[];
  }>;
  bins: Array<{
    bin_id: string;
    site_name: string;
    coordinate: GeoCoordinate;
    current_load_liters: number;
    capacity_liters: number;
    fill_ratio: number;
    generation_liters_per_hour: number;
    task_status: string;
  }>;
  routes: SyntheticDispatch["routes"];
  available_road_disruptions: string[];
  available_vehicle_disruptions: string[];
};

export type SyntheticRunStart = {
  dispatch: SyntheticDispatch;
  run: SyntheticRunSnapshot;
};

export type CityEventType =
  | "WASTE_OVERFLOW"
  | "VEHICLE_BREAKDOWN"
  | "ROAD_CLOSURE"
  | "URGENT_TASK";

export type CityEventPayload = {
  event_id: string;
  event_type: CityEventType;
  timestamp: number;
  location: string;
  affected_entities: string[];
  severity: number;
  deadline: number | null;
  metadata: Record<string, unknown>;
  description: string | null;
};

export type WorkflowRun = {
  event_id: string;
  status: "SUCCESS" | "INFEASIBLE" | "VERIFICATION_FAILED" | "IGNORED";
  reason: string | null;
  policy_decision: { policy_profile: string; reasoning_summary: string } | null;
  plan: {
    plan_id: string;
    vehicle_routes: Array<{ vehicle_id: string; task_sequence: string[]; path: GeoCoordinate[] }>;
    unassigned_tasks: string[];
  } | null;
  verification: { valid: boolean } | null;
};

const api_base = (import.meta.env.VITE_RUNTIME_API_BASE_URL?.trim() ?? "").replace(/\/$/, "");

async function request_json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${api_base}${path}`, init);
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body
      ? (body as { detail: unknown }).detail
      : null;
    const message = detail && typeof detail === "object" && "message" in detail
      ? String((detail as { message: unknown }).message)
      : `运行服务请求失败（HTTP ${response.status}）`;
    throw new Error(message);
  }
  return body as T;
}

export function fetch_runtime_status(): Promise<RuntimeStatus> {
  return request_json("/api/v1/runtime/status");
}

export function fetch_city_snapshot(): Promise<CitySnapshot> {
  return request_json("/api/v1/runtime/snapshot");
}

export function submit_city_event(payload: CityEventPayload): Promise<WorkflowRun> {
  return request_json("/api/v1/runtime/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetch_facilities(): Promise<FacilityRecord[]> {
  return request_json("/api/v1/facilities");
}

export function create_facility(payload: FacilityCreatePayload): Promise<FacilityRecord> {
  return request_json("/api/v1/facilities", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetch_synthetic_network(seed = 20260922): Promise<SyntheticNetwork> {
  const search = new URLSearchParams({
    seed: String(seed),
    road_node_count: "120",
    bin_count: "180",
  });
  return request_json(`/api/v1/simulation/network?${search.toString()}`);
}

export function submit_synthetic_dispatch(payload: SyntheticDispatchRequest): Promise<SyntheticDispatch> {
  return request_json("/api/v1/simulation/dispatch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function submit_synthetic_assessment(payload: SyntheticAssessmentRequest): Promise<SyntheticAssessment> {
  return request_json("/api/v1/simulation/assessments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function start_synthetic_run(payload: SyntheticDispatchRequest): Promise<SyntheticRunStart> {
  return request_json("/api/v1/simulation/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function step_synthetic_run(run_id: string, ticks: number): Promise<SyntheticRunSnapshot> {
  return request_json(`/api/v1/simulation/runs/${encodeURIComponent(run_id)}/steps`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticks }),
  });
}

export function disrupt_synthetic_run(
  run_id: string,
  disruption_type: "ROAD_CLOSURE" | "VEHICLE_BREAKDOWN",
): Promise<SyntheticRunSnapshot> {
  return request_json(`/api/v1/simulation/runs/${encodeURIComponent(run_id)}/disruptions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ disruption_type }),
  });
}
