export interface Scenario {
  scenario_id: string;
  scenario_title: string;
  demo_mode: string;
  frame_count: number;
}

export interface Timeline {
  id: string;
  label: string;
  order: number;
  sim_time: number;
}

export interface CityNode {
  node_id: string;
}

export interface Road {
  road_id: string;
  from_node: string;
  to_node: string;
  distance: number;
  travel_time: number;
  status: string;
}

export interface CityTask {
  task_id: string;
  target_id: string;
  node_id: string;
  priority: number;
  status: string;
}

export interface Vehicle {
  vehicle_id: string;
  node_id: string;
  load: number;
  status: string;
}

export interface WastePoint {
  waste_point_id: string;
  node_id: string;
  current_load: number;
  capacity: number;
}

export interface City {
  nodes: CityNode[];
  roads: Road[];
  tasks: CityTask[];
  vehicles: Vehicle[];
  waste_points: WastePoint[];
}

export interface Event {
  event_type: string;
  location: string;
  severity: number;
  description: string;
}

export interface Decision {
  policy_profile: string;
  priority_targets: string[];
  risk_level: number;
  response_deadline: number | null;
  reasoning_summary: string;
}

export interface VehicleAssignment {
  vehicle_id: string;
  task_sequence: string[];
}

export interface Assignment {
  before_assignments: VehicleAssignment[] | null;
  after_assignments: VehicleAssignment[] | null;
  released_task_ids: string[] | null;
}

export interface Optimizer {
  status: string;
  vehicle_routes: VehicleAssignment[];
  unassigned_tasks: string[];
  reason: string | null;
}

export interface Verifier {
  state: string;
  valid: boolean | null;
  violations: string[] | null;
}

export interface Metrics {
  total_distance: number;
  average_response_time: number;
  task_completion_rate: number;
  urgent_task_completion_rate: number;
  overflow_count: number;
}

export interface Frame {
  id: string;
  label: string;
  phase_status: string;
  sim_time: number;
  city: City;
  event: Event | null;
  decision: Decision | null;
  assignment: Assignment;
  optimizer: Optimizer | null;
  verifier: Verifier;
  metrics: Metrics | null;
}

export interface Summary {
  final_phase_status: string;
  final_sim_time: number;
}

export interface FrontendFixture {
  schema_version: string;
  scenario: Scenario;
  timeline: Timeline[];
  frames: Frame[];
  summary: Summary;
}

export interface V2Ablation {
  mode: string;
  label: string;
  availability: string;
  reason: string | null;
  metrics: Metrics | null;
  optimizer_status: string | null;
  verifier_passed: boolean | null;
  completed: boolean | null;
  policy_decision?: Decision | null;
}

export interface V2ExperienceFixture {
  schema_version: string;
  experience: {
    title: string;
    selected_case: boolean;
    availability: string;
    selected_case_disclosure: string;
  };
  provenance: {
    trace_source: string;
    model_id: string | null;
  };
  complaint_session: {
    messages: Array<{ content: string; role: string; source: string }>;
    intake_result: {
      status: string;
      complaint_summary: string | null;
      candidate_event_type: string | null;
      affected_entity_mentions: string[];
    };
  };
  city_event: Event;
  policy_decision: Decision | null;
  policy_notice: string;
  execution_frames: Array<{ module: string; status: string }>;
  final_metrics: Metrics;
  final_summary: {
    headline: string;
    citizen_reply: string;
    source: string;
  };
  ablation_comparison: V2Ablation[];
  experiment_summary: {
    gold_cases: number;
    successful_calls: number;
    contract_success_rate: number;
    policy_accuracy: number;
    macro_f1: number;
    paired_context_accuracy: number;
    provider_failures: number;
  };
}
