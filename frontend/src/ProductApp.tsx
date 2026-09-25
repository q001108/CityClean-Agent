import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  ConfigProvider,
  Descriptions,
  Input,
  InputNumber,
  Layout,
  Modal,
  Select,
  Space,
  Tag,
  Typography,
  theme,
} from "antd";
import { TiandituProductMap } from "./TiandituProductMap";
import {
  event_label,
  policy_label,
  task_status_label,
  vehicle_status_label,
} from "./business_labels";
import {
  create_facility,
  fetch_city_snapshot,
  fetch_facilities,
  fetch_runtime_status,
  fetch_synthetic_network,
  disrupt_synthetic_run,
  start_synthetic_run,
  step_synthetic_run,
  submit_synthetic_assessment,
  submit_synthetic_dispatch,
} from "./runtime_api";
import type {
  CitySnapshot,
  FacilityRecord,
  FacilityType,
  GeoCoordinate,
  RuntimeStatus,
  SyntheticDispatch,
  SyntheticAssessment,
  SyntheticAssessmentMode,
  SyntheticNetwork,
  SyntheticRunSnapshot,
} from "./runtime_api";
import "./product.css";

const { Header, Content } = Layout;
const { Paragraph, Text, Title } = Typography;

const facility_type_options: Array<{ value: FacilityType; label: string }> = [
  { value: "COLLECTION_POINT", label: "收运点" },
  { value: "TRANSFER_STATION", label: "中转站" },
  { value: "DEPOT", label: "车辆基地" },
  { value: "DISPOSAL_SITE", label: "处置场" },
];

const simulation_site_labels = {
  SCHOOL: "学校片区",
  HOSPITAL: "医院片区",
  RESIDENTIAL: "居民片区",
  COMMERCIAL: "商业片区",
  TRANSIT: "交通站点",
  PUBLIC_SPACE: "公共空间",
} as const;

function facility_type_label(value: FacilityType): string {
  return facility_type_options.find((option) => option.value === value)?.label ?? value;
}

function format_simulation_time(minute: number): string {
  const hour = Math.floor(minute / 60) % 24;
  const minutes = minute % 60;
  return `${String(hour).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function run_status_label(status: SyntheticRunSnapshot["status"]): string {
  if (status === "COMPLETED") return "执行完成";
  if (status === "NEEDS_ATTENTION") return "需要人工处理";
  return "执行中";
}

function replan_status_label(status: string): string {
  if (status === "SUCCESS") return "重规划成功";
  if (status === "NOT_RUN") return "尚未重规划";
  return status === "VERIFICATION_FAILED" ? "独立校验未通过" : "重规划需要处理";
}

function initial_plan_status_label(status: string): string {
  if (status === "SUCCESS") return "已校验通过";
  if (status === "NOT_RUN") return "尚未校验";
  return status === "VERIFICATION_FAILED" ? "校验未通过" : "方案需要处理";
}

function disruption_result_label(status: string): string {
  if (status === "SUCCESS") return "已生成可执行方案，并通过独立校验。";
  if (status === "INFEASIBLE") return "未生成可执行方案，需要人工处理。";
  if (status === "VERIFICATION_FAILED") return "新方案未通过独立校验，需要人工处理。";
  return "重规划未完成，需要人工核查。";
}

function event_summary_label(summary: string): string {
  return summary
    .replace("重规划结果：SUCCESS", "重规划结果：重规划成功")
    .replace("重规划结果：NOT_RUN", "重规划结果：尚未重规划")
    .replace("重规划结果：VERIFICATION_FAILED", "重规划结果：独立校验未通过");
}

type SyntheticDisruptionType = "ROAD_CLOSURE" | "VEHICLE_BREAKDOWN" | "WASTE_OVERFLOW" | "URGENT_TASK";

function dispatch_score(dispatch: SyntheticDispatch, assessment: SyntheticAssessment) {
  const selected_ids = new Set(dispatch.tasks.map((task) => task.bin_id));
  const selected_bins = assessment.input_facts.candidates.filter((bin) => selected_ids.has(bin.target_id));
  const sensitive_types = new Set(["SCHOOL", "HOSPITAL", "TRANSIT"]);
  return {
    selected_ids,
    assigned_count: dispatch.summary.assigned_task_count,
    critical_count: selected_bins.filter((bin) => bin.risk_level === "CRITICAL").length,
    sensitive_count: selected_bins.filter((bin) => sensitive_types.has(bin.site_type)).length,
    open_window_count: selected_bins.filter((bin) => bin.service_window_open).length,
    average_risk: selected_bins.length === 0
      ? 0
      : selected_bins.reduce((total, bin) => total + bin.risk_score, 0) / selected_bins.length,
    distance_km: dispatch.summary.total_route_distance_km,
    deadline_violations: dispatch.summary.deadline_violation_count,
  };
}

function ProductWorkbench() {
  const [runtime_status, set_runtime_status] = useState<RuntimeStatus | null>(null);
  const [snapshot, set_snapshot] = useState<CitySnapshot | null>(null);
  const [runtime_error, set_runtime_error] = useState("");
  const [facilities, set_facilities] = useState<FacilityRecord[]>([]);
  const [facility_registry_error, set_facility_registry_error] = useState("");
  const [pending_coordinate, set_pending_coordinate] = useState<GeoCoordinate | null>(null);
  const [facility_id, set_facility_id] = useState("");
  const [facility_name, set_facility_name] = useState("");
  const [facility_type, set_facility_type] = useState<FacilityType>("COLLECTION_POINT");
  const [facility_address, set_facility_address] = useState("");
  const [facility_capacity, set_facility_capacity] = useState<number | null>(null);
  const [facility_saving, set_facility_saving] = useState(false);
  const [facility_save_error, set_facility_save_error] = useState("");
  const [simulation, set_simulation] = useState<SyntheticNetwork | null>(null);
  const [simulation_seed, set_simulation_seed] = useState(20260922);
  const [simulation_loading, set_simulation_loading] = useState(false);
  const [simulation_error, set_simulation_error] = useState("");
  const [simulation_dispatch, set_simulation_dispatch] = useState<SyntheticDispatch | null>(null);
  const [dispatch_task_count, set_dispatch_task_count] = useState(30);
  const [dispatch_vehicle_count, set_dispatch_vehicle_count] = useState(4);
  const [dispatch_vehicle_capacity, set_dispatch_vehicle_capacity] = useState(1600);
  const [service_target_budget, set_service_target_budget] = useState(10);
  const [dispatch_loading, set_dispatch_loading] = useState(false);
  const [dispatch_error, set_dispatch_error] = useState("");
  const [assessment_loading, set_assessment_loading] = useState<SyntheticAssessmentMode | null>(null);
  const [assessment_error, set_assessment_error] = useState("");
  const [assessments, set_assessments] = useState<Partial<Record<SyntheticAssessmentMode, SyntheticAssessment>>>({});
  const [dispatch_results, set_dispatch_results] = useState<Partial<Record<SyntheticAssessmentMode, SyntheticDispatch>>>({});
  const [active_assessment_mode, set_active_assessment_mode] = useState<SyntheticAssessmentMode | null>(null);
  const [simulation_run, set_simulation_run] = useState<SyntheticRunSnapshot | null>(null);
  // The API retains only 48 timeline entries, so keep the first disruption boundary locally.
  const [first_disruption, set_first_disruption] = useState<{ run_id: string; sequence: number } | null>(null);
  const [latest_disruption_seen, set_latest_disruption_seen] = useState<{ run_id: string; sequence: number; current_minute: number; route_count: number } | null>(null);
  const [run_loading, set_run_loading] = useState(false);
  const [run_error, set_run_error] = useState("");
  const [run_auto_play, set_run_auto_play] = useState(false);
  const refresh_runtime = useCallback(async () => {
    set_runtime_error("");
    try {
      const status = await fetch_runtime_status();
      set_runtime_status(status);
      if (status.status === "ready") {
        set_snapshot(await fetch_city_snapshot());
      } else {
        set_snapshot(null);
      }
    } catch (error: unknown) {
      set_runtime_status(null);
      set_snapshot(null);
      set_runtime_error(error instanceof Error ? error.message : "Runtime API 连接失败");
    }
  }, []);

  const refresh_facilities = useCallback(async () => {
    set_facility_registry_error("");
    try {
      set_facilities(await fetch_facilities());
    } catch (error: unknown) {
      set_facilities([]);
      set_facility_registry_error(error instanceof Error ? error.message : "设施台账连接失败");
    }
  }, []);

  const load_simulation = useCallback(async (requested_seed: number) => {
    set_simulation_loading(true);
    set_simulation_error("");
    set_simulation_dispatch(null);
    set_simulation_run(null);
    set_first_disruption(null);
    set_latest_disruption_seen(null);
    set_run_auto_play(false);
    set_dispatch_error("");
    set_assessments({});
    set_dispatch_results({});
    set_active_assessment_mode(null);
    set_assessment_error("");
    try {
      set_simulation(await fetch_synthetic_network(requested_seed));
    } catch (error: unknown) {
      set_simulation(null);
      set_simulation_error(error instanceof Error ? error.message : "仿真网络生成失败");
    } finally {
      set_simulation_loading(false);
    }
  }, []);

  async function handle_simulation_dispatch() {
    const dispatch_mode = active_assessment_mode;
    const active_assessment = dispatch_mode === null ? null : assessments[dispatch_mode];
    if (!active_assessment || dispatch_mode === null) {
      set_dispatch_error("请先完成规则或 DeepSeek 治理研判，再确认进入调度优化。");
      return;
    }
    set_dispatch_loading(true);
    set_dispatch_error("");
    set_simulation_dispatch(null);
    set_simulation_run(null);
    set_run_auto_play(false);
    try {
      const result = await submit_synthetic_dispatch({
        seed: simulation_seed,
        selected_bin_count: dispatch_task_count,
        vehicle_count: dispatch_vehicle_count,
        vehicle_capacity_liters: dispatch_vehicle_capacity,
        service_target_budget,
        policy_decision: active_assessment.policy_decision,
      });
      set_simulation_dispatch(result);
      set_dispatch_results((current) => ({ ...current, [dispatch_mode]: result }));
      if (result.status !== "SUCCESS") {
        set_dispatch_error(`当前约束下无可安装方案：${result.reason ?? result.status}`);
      }
    } catch (error: unknown) {
      set_dispatch_error(error instanceof Error ? error.message : "仿真调度失败");
    } finally {
      set_dispatch_loading(false);
    }
  }

  function current_dispatch_request() {
    const active_assessment = active_assessment_mode === null ? null : assessments[active_assessment_mode];
    return {
      seed: simulation_seed,
      selected_bin_count: dispatch_task_count,
      vehicle_count: dispatch_vehicle_count,
      vehicle_capacity_liters: dispatch_vehicle_capacity,
      service_target_budget,
      ...(active_assessment ? { policy_decision: active_assessment.policy_decision } : {}),
    };
  }

  function reset_assessment_results() {
    set_assessments({});
    set_dispatch_results({});
    set_active_assessment_mode(null);
    set_assessment_error("");
    set_simulation_dispatch(null);
    set_simulation_run(null);
    set_run_auto_play(false);
  }

  async function handle_assessment(agent_mode: SyntheticAssessmentMode) {
    set_assessment_loading(agent_mode);
    set_assessment_error("");
    set_dispatch_error("");
    set_simulation_dispatch(null);
    set_simulation_run(null);
    set_run_auto_play(false);
    try {
      const result = await submit_synthetic_assessment({
        seed: simulation_seed,
        selected_bin_count: dispatch_task_count,
        vehicle_count: dispatch_vehicle_count,
        vehicle_capacity_liters: dispatch_vehicle_capacity,
        service_target_budget,
        agent_mode,
      });
      set_assessments((current) => ({ ...current, [agent_mode]: result }));
      set_dispatch_results((current) => {
        const next = { ...current };
        delete next[agent_mode];
        return next;
      });
      set_active_assessment_mode(agent_mode);
    } catch (error: unknown) {
      set_assessment_error(error instanceof Error ? error.message : "治理研判失败");
    } finally {
      set_assessment_loading(null);
    }
  }

  async function handle_start_run() {
    set_run_loading(true);
    set_run_error("");
    try {
      const started = await start_synthetic_run(current_dispatch_request());
      set_simulation_dispatch(started.dispatch);
      set_simulation_run(started.run);
      set_first_disruption(null);
      set_latest_disruption_seen(null);
      set_run_auto_play(false);
    } catch (error: unknown) {
      set_run_error(error instanceof Error ? error.message : "执行仿真启动失败");
    } finally {
      set_run_loading(false);
    }
  }

  async function handle_step_run(ticks: number) {
    if (simulation_run === null) {
      return;
    }
    set_run_loading(true);
    set_run_error("");
    try {
      const advanced = await step_synthetic_run(simulation_run.run_id, ticks);
      set_simulation_run(advanced);
      if (advanced.status !== "RUNNING") {
        set_run_auto_play(false);
      }
    } catch (error: unknown) {
      set_run_error(error instanceof Error ? error.message : "仿真时间推进失败");
      set_run_auto_play(false);
    } finally {
      set_run_loading(false);
    }
  }

  async function handle_disruption(disruption_type: SyntheticDisruptionType) {
    if (simulation_run === null) {
      return;
    }
    set_run_loading(true);
    set_run_error("");
    set_run_auto_play(false);
    try {
      const updated_run = await disrupt_synthetic_run(simulation_run.run_id, disruption_type);
      const first_disruption_entry = updated_run.timeline.find((entry) => entry.kind === "DISRUPTION");
      if (first_disruption_entry) {
        set_first_disruption((current) => current?.run_id === updated_run.run_id
          ? current
          : { run_id: updated_run.run_id, sequence: first_disruption_entry.sequence });
      }
      const latest_disruption_entry = updated_run.timeline[updated_run.timeline.length - 1];
      if (latest_disruption_entry?.kind === "DISRUPTION") {
        set_latest_disruption_seen({ run_id: updated_run.run_id, sequence: latest_disruption_entry.sequence, current_minute: latest_disruption_entry.current_minute, route_count: latest_disruption_entry.route_count });
      }
      set_simulation_run(updated_run);
    } catch (error: unknown) {
      set_run_error(error instanceof Error ? error.message : "扰动注入失败");
    } finally {
      set_run_loading(false);
    }
  }

  useEffect(() => {
    if (!run_auto_play || run_loading || simulation_run?.status !== "RUNNING") {
      return;
    }
    const timer = window.setTimeout(() => {
      void handle_step_run(1);
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [run_auto_play, run_loading, simulation_run]);

  useEffect(() => {
    void refresh_runtime();
    void refresh_facilities();
    void load_simulation(20260922);
  }, [load_simulation, refresh_facilities, refresh_runtime]);

  function handle_map_select(coordinate: GeoCoordinate) {
    set_pending_coordinate(coordinate);
    set_facility_id("");
    set_facility_name("");
    set_facility_type("COLLECTION_POINT");
    set_facility_address("");
    set_facility_capacity(null);
    set_facility_save_error("");
  }

  function close_facility_editor() {
    if (!facility_saving) {
      set_pending_coordinate(null);
      set_facility_save_error("");
    }
  }

  async function handle_facility_save() {
    if (pending_coordinate === null || facility_id.trim() === "" || facility_name.trim() === "") {
      set_facility_save_error("请填写设施编号和设施名称。");
      return;
    }
    if (!/^[A-Za-z0-9_-]+$/.test(facility_id.trim())) {
      set_facility_save_error("设施编号仅支持英文字母、数字、短横线和下划线。");
      return;
    }
    set_facility_saving(true);
    set_facility_save_error("");
    try {
      await create_facility({
        facility_id: facility_id.trim(),
        name: facility_name.trim(),
        facility_type,
        address: facility_address.trim() || null,
        longitude: pending_coordinate.longitude,
        latitude: pending_coordinate.latitude,
        coordinate_system: "CGCS2000",
        capacity: facility_capacity,
        status: "ACTIVE",
        source: "manual_map",
      });
      await refresh_facilities();
      set_pending_coordinate(null);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "设施保存失败";
      set_facility_save_error(message.includes("already exists") ? "设施编号已存在，请使用唯一编号。" : message);
    } finally {
      set_facility_saving(false);
    }
  }

  const runtime_ready = runtime_status?.status === "ready" && snapshot !== null;
  const latest_event = snapshot && snapshot.active_events.length > 0
    ? snapshot.active_events[snapshot.active_events.length - 1]
    : null;
  const latest_task = latest_event
    ? snapshot?.tasks.find((task) => task.source_event_id === latest_event.event_id)
      ?? snapshot?.tasks.find((task) => latest_event.affected_entities.includes(task.target_id))
      ?? null
    : null;
  const active_route = latest_task
    ? snapshot?.active_plan?.vehicle_routes.find((route) => route.task_sequence.includes(latest_task.task_id)) ?? null
    : null;
  const runtime_summary = latest_event ? {
    event: `${event_label(latest_event.event_type)} · ${latest_event.affected_entities.join("、")}`,
    task: latest_task ? `${latest_task.target_id} · ${task_status_label(latest_task.status)}` : "未生成服务任务",
    route: active_route ? `${active_route.vehicle_id} → ${latest_task?.target_id}` : "当前无车辆路线",
  } : null;
  const runtime_tag = runtime_ready
    ? <Tag color="success">运行服务已连接</Tag>
    : <Tag color="warning">运行服务未就绪</Tag>;
  const rule_score = assessments.RULE && dispatch_results.RULE?.status === "SUCCESS"
    ? dispatch_score(dispatch_results.RULE, assessments.RULE)
    : null;
  const deepseek_score = assessments.DEEPSEEK && dispatch_results.DEEPSEEK?.status === "SUCCESS"
    ? dispatch_score(dispatch_results.DEEPSEEK, assessments.DEEPSEEK)
    : null;
  const shared_target_count = rule_score && deepseek_score
    ? [...rule_score.selected_ids].filter((target_id) => deepseek_score.selected_ids.has(target_id)).length
    : null;
  const scenario_ready = simulation !== null;
  const assessment_ready = active_assessment_mode !== null;
  const dispatch_ready = simulation_dispatch?.status === "SUCCESS";
  const run_ready = simulation_run !== null;
  const disruption_ready = Boolean(simulation_run?.last_event);
  const disruption_skipped = simulation_run?.status === "COMPLETED" && !simulation_run.last_event;
  const result_ready = simulation_run?.status === "COMPLETED"
    || Boolean(simulation_run?.last_event && simulation_run.last_replan_status !== "NOT_RUN");
  const first_disruption_sequence = first_disruption !== null && first_disruption.run_id === simulation_run?.run_id
    ? first_disruption.sequence
    : simulation_run?.timeline.find((entry) => entry.kind === "DISRUPTION")?.sequence;
  const latest_disruption = [...(simulation_run?.timeline ?? [])].reverse().find((entry) => entry.kind === "DISRUPTION")
    ?? (latest_disruption_seen !== null && latest_disruption_seen.run_id === simulation_run?.run_id ? latest_disruption_seen : undefined);
  const before_latest_disruption = latest_disruption && simulation_run?.timeline.find((entry) => entry.sequence === latest_disruption.sequence - 1);
  const latest_event_parts = simulation_run?.last_event?.match(/^(.+?)：(.+?)；重规划结果：/);
  const current_route_count = simulation_run?.routes.length ?? 0;
  const route_change_label = before_latest_disruption && latest_disruption
    ? before_latest_disruption.route_count === latest_disruption.route_count
      ? `路线数保持 ${latest_disruption.route_count} 条${latest_disruption.route_count === current_route_count ? "（当前）" : `；当前 ${current_route_count} 条`}`
      : latest_disruption.route_count === current_route_count
        ? `路线 ${before_latest_disruption.route_count} → ${current_route_count} 条（当前）`
        : `扰动时路线 ${before_latest_disruption.route_count} → ${latest_disruption.route_count} 条；当前 ${current_route_count} 条`
    : `当前路线 ${current_route_count} 条；扰动前数据不在当前时间线中`;
  const workflow_steps = [
    { label: "场景准备", complete: scenario_ready },
    { label: "治理研判", complete: assessment_ready },
    { label: "生成调度", complete: dispatch_ready },
    { label: "启动仿真", complete: run_ready },
    { label: "注入扰动", complete: disruption_ready, skipped: disruption_skipped },
    { label: "查看结果", complete: result_ready },
  ];
  const first_incomplete_step = workflow_steps.findIndex((step) => !step.complete && !step.skipped);
  const current_step_index = first_incomplete_step === -1
    ? workflow_steps.length - 1
    : first_incomplete_step;
  const next_action = !scenario_ready
    ? "SCENARIO"
    : !assessment_ready
      ? "ASSESSMENT"
      : !dispatch_ready
        ? "DISPATCH"
        : !run_ready
          ? "RUN"
          : !disruption_ready && simulation_run.status === "RUNNING"
            ? "DISRUPTION"
            : "RESULT";
  const active_assessment = active_assessment_mode === null ? null : assessments[active_assessment_mode] ?? null;
  const active_decision = active_assessment?.policy_decision ?? null;
  const current_stage_label = workflow_steps[current_step_index]?.label ?? "场景准备";

  function scroll_to(element_id: string) {
    document.getElementById(element_id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function open_experiment_details() {
    const details = document.getElementById("experiment-details");
    if (details instanceof HTMLDetailsElement) {
      details.open = true;
      details.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  return <ConfigProvider theme={{ algorithm: theme.darkAlgorithm, token: { colorPrimary: "#2dd4bf", borderRadius: 10, fontFamily: "Inter, 'Microsoft YaHei', sans-serif" } }}>
    <Layout className="product-layout">
      <Header className="product-header">
        <div>
          <Text className="product-eyebrow">城市环卫智能体</Text>
          <Title level={1}>城市环卫智能调度工作台</Title>
          <Text type="secondary">资源约束研判、确定性调度与动态重规划演示</Text>
        </div>
        <Tag className="synthetic-mode-tag" color="gold">合成仿真模式</Tag>
      </Header>

      <Content className="product-content">
        {runtime_error && <Alert className="primary-runtime-error" type="error" showIcon title="无法连接应用服务" description={`${runtime_error} 合成实验暂时无法加载，请确认后端服务已启动。`} />}

        <section className="workbench-intro" aria-labelledby="workbench-purpose">
          <div className="mode-boundary">
            <div>
              <Tag color="gold">合成仿真模式</Tag>
              <strong id="workbench-purpose">真实地图底图上的决策仿真实验</strong>
            </div>
            <p>地图底图来自天地图；车辆、垃圾桶、传感器和事件均为可复现合成数据。</p>
            <small>当前运行于合成演示模式；生产城市状态源{runtime_ready ? "已连接" : "尚未启用"}，设施台账{facility_registry_error ? "尚未启用" : "可用"}，均不影响下方仿真实验。</small>
          </div>

          <ol className="workflow-steps" aria-label="决策仿真主流程">
            {workflow_steps.map((step, index) => <li
              key={step.label}
              className={`${step.complete ? "is-complete" : ""}${step.skipped ? " is-skipped" : ""}${index === current_step_index ? " is-current" : ""}`}
              aria-current={index === current_step_index ? "step" : undefined}
            >
              <span>{step.complete ? "✓" : step.skipped ? "—" : index + 1}</span>
              <strong>{step.label}</strong>
              <small>{step.skipped ? "已跳过" : index === current_step_index ? "当前步骤" : step.complete ? "已完成" : "待进行"}</small>
            </li>)}
          </ol>

          <div className="next-action-panel" aria-live="polite">
            <div>
              <Text className="next-action-label">当前下一步</Text>
              {next_action === "SCENARIO" && <strong>正在准备可复现的合成场景，请稍候。</strong>}
              {next_action === "ASSESSMENT" && <strong>场景已准备完成，下一步选择规则或 DeepSeek 进行治理研判。</strong>}
              {next_action === "DISPATCH" && <strong>治理研判已完成，下一步生成调度方案并执行独立校验。</strong>}
              {next_action === "RUN" && <strong>调度与校验已完成，下一步启动 CitySim 执行仿真。</strong>}
              {next_action === "DISRUPTION" && <strong>车辆已经进入执行阶段，下一步选择一种扰动并观察重规划。</strong>}
              {next_action === "RESULT" && <strong>{disruption_skipped
                ? "本轮仿真已自然完成，未注入扰动。可查看基础执行结果，或重新生成场景后体验扰动重规划。"
                : "执行结果已经产生，可查看车辆状态、扰动影响和重规划结果。"}</strong>}
            </div>
            <Space wrap className="next-action-buttons">
              <Button type="primary" onClick={() => scroll_to("simulation-cockpit")}>
                {next_action === "RESULT" ? "查看执行结果" : next_action === "DISRUPTION" ? "继续当前步骤" : "进入仿真操作台"}
              </Button>
            </Space>
          </div>
        </section>

        <section id="simulation-cockpit" className="simulation-cockpit" aria-labelledby="cockpit-title">
          <Card className="product-map-card cockpit-map-card" title={<span id="cockpit-title">实时仿真地图</span>} extra={<Text type="secondary">天地图底图 · 信阳市</Text>}>
            <TiandituProductMap
              snapshot={snapshot}
              facilities={facilities}
              pending_coordinate={pending_coordinate}
              on_map_select={handle_map_select}
              simulation={simulation}
              simulation_dispatch={simulation_dispatch}
              simulation_run={simulation_run}
              runtime_summary={runtime_summary}
            />
          </Card>

          <aside className="cockpit-control" aria-label="仿真操作台" aria-live="polite">
            <div className="cockpit-heading">
              <div><Text className="cockpit-eyebrow">仿真操作台</Text><strong>当前阶段：{current_stage_label}</strong></div>
              <Tag color={simulation_run?.status === "NEEDS_ATTENTION" ? "error" : simulation_run?.status === "COMPLETED" ? "success" : "processing"}>
                {simulation_run ? run_status_label(simulation_run.status) : dispatch_ready ? "等待启动" : assessment_ready ? "研判完成" : "场景就绪"}
              </Tag>
            </div>

            {!scenario_ready && <div className="cockpit-empty"><Text>正在准备可复现合成场景…</Text><Button loading={simulation_loading} onClick={() => void load_simulation(simulation_seed)}>重新加载场景</Button></div>}

            {scenario_ready && !assessment_ready && <>
              <div className="cockpit-context-grid">
                <span><small>场景种子</small><b>{simulation_seed}</b></span>
                <span><small>候选数量</small><b>{dispatch_task_count} 个</b></span>
                <span><small>治理预算</small><b>{service_target_budget} 个</b></span>
                <span><small>车辆数量</small><b>{dispatch_vehicle_count} 辆</b></span>
              </div>
              <div className="cockpit-guidance"><Tag color="gold">合成运营数据</Tag><p>先选择一种治理研判方式。DeepSeek 只会在你主动点击后调用。</p></div>
              <div className="cockpit-primary-actions">
                <Button type="primary" loading={assessment_loading === "RULE"} onClick={() => void handle_assessment("RULE")}>运行规则研判</Button>
                <Button loading={assessment_loading === "DEEPSEEK"} onClick={() => void handle_assessment("DEEPSEEK")}>使用 DeepSeek 研判</Button>
              </div>
            </>}

            {scenario_ready && assessment_ready && !dispatch_ready && active_decision && <>
              <div className="cockpit-summary-card">
                <div><small>当前研判方式</small><strong>{active_assessment_mode === "DEEPSEEK" ? "DeepSeek 研判" : "规则基线"}</strong></div>
                <div className="cockpit-context-grid">
                  <span><small>选中目标</small><b>{active_decision.priority_targets.length} 个</b></span>
                  <span><small>风险等级</small><b>{active_decision.risk_level} / 5</b></span>
                  <span><small>治理策略</small><b>{policy_label(active_decision.policy_profile)}</b></span>
                  <span><small>资源预算</small><b>{service_target_budget} 个</b></span>
                </div>
              </div>
              <Button type="primary" block loading={dispatch_loading} onClick={() => void handle_simulation_dispatch()}>生成当前策略方案</Button>
            </>}

            {dispatch_ready && simulation_run === null && <>
              <div className="cockpit-status-line"><Tag color="success">独立校验通过</Tag><span>路线由 OR-Tools 计算，可启动 CitySim 执行。</span></div>
              <div className="cockpit-context-grid">
                <span><small>已分配任务</small><b>{simulation_dispatch.summary.assigned_task_count} 个</b></span>
                <span><small>启用车辆</small><b>{simulation_dispatch.summary.route_count} 辆</b></span>
                <span><small>总路线距离</small><b>{simulation_dispatch.summary.total_route_distance_km.toFixed(1)} 千米</b></span>
                <span><small>时限违约</small><b>{simulation_dispatch.summary.deadline_violation_count} 个</b></span>
              </div>
              <Button type="primary" block loading={run_loading} onClick={() => void handle_start_run()}>启动执行仿真</Button>
            </>}

            {simulation_run && <>
              <div className="cockpit-run-metrics">
                <span><small>仿真时刻</small><b>{format_simulation_time(simulation_run.current_minute)}</b></span>
                <span><small>已推进</small><b>{simulation_run.elapsed_minutes} 分钟</b></span>
                <span><small>完成任务</small><b>{simulation_run.completed_task_count} / {simulation_run.task_count}</b></span>
                <span><small>满溢事件</small><b>{simulation_run.overflow_count}</b></span>
                <span><small>故障车辆</small><b>{simulation_run.broken_vehicle_count}</b></span>
                <span>
                  <small>{simulation_run.last_event ? "最近重规划" : "初始方案"}</small>
                  <b>{simulation_run.last_event ? replan_status_label(simulation_run.last_replan_status) : initial_plan_status_label(simulation_run.last_replan_status)}</b>
                </span>
              </div>

              {simulation_run.status === "RUNNING" && <>
                <div className="cockpit-action-group">
                  <small>时间控制</small>
                  <div>
                    <Button type={run_auto_play ? "default" : "primary"} loading={run_loading && !run_auto_play} onClick={() => set_run_auto_play((current) => !current)}>{run_auto_play ? "暂停" : "自动运行"}</Button>
                    <Button loading={run_loading} onClick={() => void handle_step_run(1)}>推进 5 分钟</Button>
                    <Button loading={run_loading} onClick={() => void handle_step_run(6)}>推进 30 分钟</Button>
                  </div>
                </div>
                <div className="cockpit-action-group cockpit-disruptions">
                  <small>动态扰动（执行后立即重新研判、调度并校验）</small>
                  <div>
                    <Button danger loading={run_loading} disabled={simulation_run.available_road_disruptions.length === 0} onClick={() => void handle_disruption("ROAD_CLOSURE")}>道路封闭</Button>
                    <Button danger loading={run_loading} disabled={simulation_run.available_vehicle_disruptions.length === 0} onClick={() => void handle_disruption("VEHICLE_BREAKDOWN")}>车辆故障</Button>
                    <Button danger loading={run_loading} disabled={simulation_run.available_bin_disruptions.length === 0} onClick={() => void handle_disruption("WASTE_OVERFLOW")}>垃圾量突增</Button>
                    <Button danger loading={run_loading} disabled={simulation_run.available_bin_disruptions.length === 0} onClick={() => void handle_disruption("URGENT_TASK")}>紧急清运</Button>
                  </div>
                </div>
              </>}

              <div className={`cockpit-event${simulation_run.last_event ? " has-event" : ""}`}>
                {simulation_run.last_event ? <>
                  <small>最近一次扰动的因果说明</small>
                  <div className="cockpit-causal-row"><b>事件</b><span>{latest_event_parts ? `${latest_event_parts[1]} · ${latest_event_parts[2]}` : simulation_run.last_event} · {latest_disruption ? format_simulation_time(latest_disruption.current_minute) : "发生时刻未保留在当前时间线中"}</span></div>
                  <div className="cockpit-causal-row"><b>系统应对</b><span>确定性规则重新研判，OR-Tools 尝试调度；有候选方案时再独立校验。</span></div>
                  <div className="cockpit-causal-row"><b>执行结果</b><span>{disruption_result_label(simulation_run.last_replan_status)}<br />{route_change_label}</span></div>
                </> : <>
                  <small>最近事件与可执行状态</small>
                  <strong>{simulation_run.status === "COMPLETED" ? "本轮自然完成，未注入扰动。" : "尚未注入扰动"}</strong>
                  <span>剩余任务 {simulation_run.task_count - simulation_run.completed_task_count} 个 · 当前路线 {current_route_count} 条 · 初始方案{initial_plan_status_label(simulation_run.last_replan_status)}</span>
                </>}
              </div>

              {simulation_run.status === "COMPLETED" && <div className="cockpit-result-actions">
                <Button type="primary" onClick={open_experiment_details}>查看详细结果</Button>
                <Button loading={simulation_loading} onClick={() => void load_simulation(simulation_seed)}>重新生成场景</Button>
              </div>}
            </>}

            {(assessment_error || dispatch_error || run_error) && <Alert type="error" showIcon title="当前操作未完成" description={assessment_error || dispatch_error || run_error} />}
            <button type="button" className="cockpit-detail-link" onClick={open_experiment_details}>查看实验参数与完整结果</button>
          </aside>
        </section>

        <details id="experiment-details" className="experiment-details">
          <summary><span><strong>实验参数与完整结果</strong><small>场景参数、研判详情、路线和车辆时间线</small></span><Tag>专家详情</Tag></summary>
        <Card id="synthetic-experiment" className="simulation-card" title="高级实验控制与完整结果" extra={<Tag color="gold">非真实业务数据</Tag>}>
          <div className="simulation-toolbar">
            <div>
              <Text strong>确定性场景种子</Text>
              <Text type="secondary"> 相同种子会生成完全一致的路网、垃圾桶与风险状态</Text>
            </div>
            <Space>
              <InputNumber min={0} max={2147483647} precision={0} value={simulation_seed} onChange={(value) => set_simulation_seed(value ?? 0)} />
              <Button type="primary" loading={simulation_loading} onClick={() => void load_simulation(simulation_seed)}>重新生成场景</Button>
            </Space>
          </div>
          {simulation_error && <Alert className="simulation-error" type="error" showIcon title="仿真网络生成失败" description={simulation_error} />}
          {simulation && <>
            <div className="simulation-metrics">
              <div><small>道路拓扑</small><strong>{simulation.analysis.road_node_count} 节点 / {simulation.analysis.road_edge_count} 连边</strong></div>
              <div><small>模拟垃圾桶</small><strong>{simulation.analysis.bin_count} 个</strong></div>
              <div><small>高风险 / 紧急</small><strong>{simulation.analysis.high_risk_bin_count} / {simulation.analysis.critical_bin_count}</strong></div>
              <div><small>预计 4 小时内满溢</small><strong>{simulation.analysis.projected_overflow_4h_count} 个</strong></div>
              <div><small>敏感场所高风险</small><strong>{simulation.analysis.sensitive_site_high_risk_count} 个</strong></div>
              <div><small>平均装载率</small><strong>{Math.round(simulation.analysis.average_fill_ratio * 100)}%</strong></div>
            </div>
            <div className="simulation-risk-list">
              <Text strong>优先研判对象</Text>
              <div>{[...simulation.bins]
                .sort((first, second) => second.risk_score - first.risk_score)
                .slice(0, 6)
                .map((bin) => <button key={bin.bin_id} type="button">
                  <span><b>{bin.bin_id}</b>{bin.site_name}</span>
                  <small>{simulation_site_labels[bin.site_type]} · 装载率 {Math.round(bin.fill_ratio * 100)}% · 风险 {bin.risk_score}</small>
                </button>)}</div>
            </div>
            <div id="assessment-workbench" className="dispatch-builder">
              <div className="dispatch-builder-heading">
                <div><Text strong>资源约束研判实验台</Text><Text type="secondary"> 同一批候选、同一资源预算，比较规则与大模型的治理取舍</Text></div>
                <Tag color="volcano">资源不足场景</Tag>
              </div>
              <div className="dispatch-controls">
                <label><span>候选风险桶</span><InputNumber min={5} max={30} precision={0} value={dispatch_task_count} onChange={(value) => { const next = value ?? 5; set_dispatch_task_count(next); set_service_target_budget((current) => Math.min(current, next)); reset_assessment_results(); }} /></label>
                <label><span>最多治理点位</span><InputNumber min={1} max={dispatch_task_count} precision={0} value={service_target_budget} onChange={(value) => { set_service_target_budget(value ?? 1); reset_assessment_results(); }} /></label>
                <label><span>仿真车辆数</span><InputNumber min={2} max={12} precision={0} value={dispatch_vehicle_count} onChange={(value) => { set_dispatch_vehicle_count(value ?? 2); reset_assessment_results(); }} /></label>
                <label><span>单车容量（升）</span><InputNumber min={100} max={10000} precision={0} value={dispatch_vehicle_capacity} onChange={(value) => { set_dispatch_vehicle_capacity(value ?? 100); reset_assessment_results(); }} /></label>
              </div>
              <div className="assessment-actions">
                <div>
                  <Text strong>第一步：治理研判</Text>
                  <Text type="secondary"> 同一批事实可分别运行规则基线与真实模型，对比后选择进入调度的策略</Text>
                </div>
                <Space wrap>
                  <Button loading={assessment_loading === "RULE"} onClick={() => void handle_assessment("RULE")}>运行规则研判</Button>
                  <Button type="primary" loading={assessment_loading === "DEEPSEEK"} onClick={() => void handle_assessment("DEEPSEEK")}>使用 DeepSeek 研判</Button>
                </Space>
              </div>
              {assessment_error && <Alert className="dispatch-result" type="error" showIcon title="模型研判未完成" description={assessment_error} />}
              {Object.keys(assessments).length > 0 && <div className="assessment-grid">
                {(["RULE", "DEEPSEEK"] as SyntheticAssessmentMode[]).map((mode) => {
                  const assessment = assessments[mode];
                  if (!assessment) return null;
                  const decision = assessment.policy_decision;
                  const selected = active_assessment_mode === mode;
                  return <button
                    key={mode}
                    type="button"
                    className={`assessment-panel${selected ? " assessment-panel-selected" : ""}`}
                    onClick={() => { set_active_assessment_mode(mode); set_simulation_dispatch(dispatch_results[mode] ?? null); set_simulation_run(null); }}
                  >
                    <div className="assessment-panel-heading">
                      <div><strong>{assessment.agent_name}</strong><small>{assessment.model_name ?? "未调用外部模型"}</small></div>
                      <Tag color={mode === "DEEPSEEK" ? "purple" : "default"}>{assessment.model_call_status === "SUCCESS" ? "真实调用成功" : "规则基线"}</Tag>
                    </div>
                    <div className="assessment-fact-strip">
                      <span><small>输入候选</small><b>{assessment.input_facts.candidate_count}</b></span>
                      <span><small>资源预算</small><b>{assessment.input_facts.service_target_budget}</b></span>
                      <span><small>模型选中</small><b>{decision.priority_targets.length}</b></span>
                      <span><small>风险等级</small><b>{decision.risk_level} / 5</b></span>
                      <span><small>研判耗时</small><b>{assessment.latency_ms} 毫秒</b></span>
                    </div>
                    <p>{decision.reasoning_summary}</p>
                    <div className="assessment-decision-list">
                      <span><b>治理策略</b>{policy_label(decision.policy_profile)}</span>
                      <span><b>响应时限</b>{decision.response_deadline === null ? "未指定" : format_simulation_time(decision.response_deadline)}</span>
                      <span><b>优先目标</b>{decision.priority_targets.slice(0, 8).join("、")}{decision.priority_targets.length > 8 ? ` 等 ${decision.priority_targets.length} 个` : ""}</span>
                      <span><b>治理约束</b>{decision.constraints.length > 0 ? decision.constraints.join("；") : "无附加约束"}</span>
                    </div>
                    <small className="assessment-mapping">固定参数映射：迟到权重 {assessment.optimization_parameters.lateness_weight}，未服务惩罚 {assessment.optimization_parameters.unserved_task_penalty}。路线仍由 OR-Tools 计算。</small>
                  </button>;
                })}
              </div>}
              {active_assessment_mode && <div className="assessment-confirm">
                <Text>当前采用：<b>{assessments[active_assessment_mode]?.agent_name}</b>。确认后才生成任务并进入确定性优化。</Text>
                <Button type="primary" loading={dispatch_loading} onClick={() => void handle_simulation_dispatch()}>生成当前策略方案</Button>
              </div>}
              {Object.keys(dispatch_results).length > 0 && <div className="experiment-comparison">
                <div className="experiment-comparison-heading">
                  <div><Text strong>方案量化对比</Text><Text type="secondary"> 所有指标来自同一确定性场景与独立校验结果</Text></div>
                  {shared_target_count !== null && <Tag color="blue">共同选择 {shared_target_count} 个目标</Tag>}
                </div>
                <div className="experiment-score-grid">
                  {(["RULE", "DEEPSEEK"] as SyntheticAssessmentMode[]).map((mode) => {
                    const score = mode === "RULE" ? rule_score : deepseek_score;
                    const assessment = assessments[mode];
                    const result = dispatch_results[mode];
                    return <div key={mode} className="experiment-score-card">
                      <div><strong>{mode === "RULE" ? "规则基线方案" : "DeepSeek 方案"}</strong>{result && <Tag color={result.status === "SUCCESS" ? "success" : "error"}>{result.status === "SUCCESS" ? "校验通过" : "不可执行"}</Tag>}</div>
                      {score && assessment
                        ? <div className="experiment-score-metrics">
                          <span><small>已分配任务</small><b>{score.assigned_count} / {assessment.input_facts.service_target_budget}</b></span>
                          <span><small>紧急点覆盖</small><b>{score.critical_count} / {assessment.input_facts.critical_target_count}</b></span>
                          <span><small>敏感场所覆盖</small><b>{score.sensitive_count} / {assessment.input_facts.sensitive_target_count}</b></span>
                          <span><small>当前窗口可执行</small><b>{score.open_window_count} / {assessment.input_facts.candidates.filter((candidate) => candidate.service_window_open).length}</b></span>
                          <span><small>入选平均风险</small><b>{score.average_risk.toFixed(1)}</b></span>
                          <span><small>总路线距离</small><b>{score.distance_km.toFixed(1)} 千米</b></span>
                          <span><small>时限违约</small><b>{score.deadline_violations}</b></span>
                        </div>
                        : <Text type="secondary">尚未生成该策略的可执行方案</Text>}
                    </div>;
                  })}
                </div>
              </div>}
              {dispatch_error && <Alert className="dispatch-result" type="warning" showIcon title="未生成可执行方案" description={dispatch_error} />}
              {simulation_dispatch?.status === "SUCCESS" && <div className="dispatch-result">
                <Alert type="success" showIcon title="仿真调度已通过独立验证" description={`已分配 ${simulation_dispatch.summary.assigned_task_count} 个任务，生成 ${simulation_dispatch.summary.route_count} 条车辆路线，截止时限违约 ${simulation_dispatch.summary.deadline_violation_count} 个。`} />
                <div className="dispatch-summary">
                  <span><small>风险任务负荷</small><b>{Math.round(simulation_dispatch.summary.selected_load_liters)} 升</b></span>
                  <span><small>启用车辆</small><b>{simulation_dispatch.summary.route_count} / {simulation_dispatch.summary.vehicle_count}</b></span>
                  <span><small>总路线距离</small><b>{simulation_dispatch.summary.total_route_distance_km.toFixed(1)} 千米</b></span>
                  <span><small>最大单车负荷</small><b>{Math.round(simulation_dispatch.summary.max_route_load_liters)} 升</b></span>
                </div>
                <div className="dispatch-routes">{simulation_dispatch.routes.map((route) => <div key={route.vehicle_id}>
                  <strong>{route.vehicle_id}</strong>
                  <span>{route.bin_sequence.join(" → ")}</span>
                  <small>{route.assigned_load_liters.toFixed(0)} / {route.vehicle_capacity_liters.toFixed(0)} 升 · {route.total_distance_km.toFixed(1)} 千米 · 约 {route.total_travel_minutes} 分钟</small>
                </div>)}</div>
                <div id="run-console" className="run-console">
                  <div className="run-console-heading">
                    <div><Text strong>执行仿真</Text><Text type="secondary"> CitySim 以 5 分钟为步长推进</Text></div>
                    {simulation_run
                      ? <Tag color={simulation_run.status === "COMPLETED" ? "success" : simulation_run.status === "NEEDS_ATTENTION" ? "error" : "processing"}>{simulation_run.status === "COMPLETED" ? "执行完成" : simulation_run.status === "NEEDS_ATTENTION" ? "需要人工处理" : "执行中"}</Tag>
                      : <Tag>尚未启动</Tag>}
                  </div>
                  {simulation_run === null
                    ? <Button loading={run_loading} onClick={() => void handle_start_run()}>启动执行仿真</Button>
                    : <>
                      <div className="run-metrics">
                        <span><small>仿真时刻</small><b>{format_simulation_time(simulation_run.current_minute)}</b></span>
                        <span><small>已推进</small><b>{simulation_run.elapsed_minutes} 分钟</b></span>
                        <span><small>完成任务</small><b>{simulation_run.completed_task_count} / {simulation_run.task_count}</b></span>
                        <span><small>满溢事件</small><b>{simulation_run.overflow_count}</b></span>
                        <span><small>故障车辆</small><b>{simulation_run.broken_vehicle_count}</b></span>
                        <span><small>{simulation_run.last_event ? "最近重规划" : "初始方案"}</small><b>{simulation_run.last_event ? replan_status_label(simulation_run.last_replan_status) : initial_plan_status_label(simulation_run.last_replan_status)}</b></span>
                      </div>
                      <div className="run-actions">
                        <Button type={run_auto_play ? "default" : "primary"} loading={run_loading && !run_auto_play} disabled={simulation_run.status !== "RUNNING"} onClick={() => set_run_auto_play((current) => !current)}>{run_auto_play ? "暂停自动运行" : "自动运行"}</Button>
                        <Button loading={run_loading} disabled={simulation_run.status !== "RUNNING"} onClick={() => void handle_step_run(1)}>推进 5 分钟</Button>
                        <Button loading={run_loading} disabled={simulation_run.status !== "RUNNING"} onClick={() => void handle_step_run(6)}>推进 30 分钟</Button>
                        <Button danger loading={run_loading} disabled={simulation_run.status !== "RUNNING" || simulation_run.available_road_disruptions.length === 0} onClick={() => void handle_disruption("ROAD_CLOSURE")}>模拟道路封闭</Button>
                        <Button danger loading={run_loading} disabled={simulation_run.status !== "RUNNING" || simulation_run.available_vehicle_disruptions.length === 0} onClick={() => void handle_disruption("VEHICLE_BREAKDOWN")}>模拟车辆故障</Button>
                        <Button danger loading={run_loading} disabled={simulation_run.status !== "RUNNING" || simulation_run.available_bin_disruptions.length === 0} onClick={() => void handle_disruption("WASTE_OVERFLOW")}>模拟垃圾量突增</Button>
                        <Button danger loading={run_loading} disabled={simulation_run.status !== "RUNNING" || simulation_run.available_bin_disruptions.length === 0} onClick={() => void handle_disruption("URGENT_TASK")}>模拟紧急清运</Button>
                      </div>
                      {simulation_run.last_event && <Alert className="run-event" type={simulation_run.status === "NEEDS_ATTENTION" ? "warning" : "info"} showIcon title="最近扰动与重规划" description={event_summary_label(simulation_run.last_event)} />}
                      <div className="vehicle-timeline">
                        <div className="vehicle-timeline-heading">
                          <div><Text strong>车辆运行时间线</Text><Text type="secondary"> 每个节点均来自 CitySim 真值快照</Text></div>
                          <Tag color="cyan">{simulation_run.timeline.length} 个节点</Tag>
                        </div>
                        <div className="vehicle-timeline-list">
                          {[...simulation_run.timeline].reverse().map((entry) => <div key={entry.sequence} className={`vehicle-timeline-entry vehicle-timeline-${entry.kind.toLowerCase()}`}>
                            <div className="vehicle-timeline-marker"><b>{format_simulation_time(entry.current_minute)}</b><small>#{entry.sequence}</small></div>
                            <div className="vehicle-timeline-content">
                              <div><strong>{entry.kind === "DISRUPTION" ? event_summary_label(entry.summary) : entry.summary}</strong><small>完成 {entry.completed_task_count}/{simulation_run.task_count} · 路线 {entry.route_count} · {simulation_run.last_event && (first_disruption_sequence === undefined || entry.sequence >= first_disruption_sequence) ? replan_status_label(entry.replan_status) : `初始方案${initial_plan_status_label(entry.replan_status)}`}</small></div>
                              <div className="vehicle-timeline-fleet">{entry.vehicles.map((vehicle) => <span key={vehicle.vehicle_id}>
                                <b>{vehicle.vehicle_id}</b>
                                <em>{vehicle_status_label(vehicle.status)}</em>
                                <small>{Math.round(vehicle.current_load_liters)} 升{vehicle.active_task_id ? ` · ${vehicle.active_task_id}` : " · 无当前任务"}</small>
                              </span>)}</div>
                            </div>
                          </div>)}
                        </div>
                      </div>
                    </>}
                  {run_error && <Alert className="run-event" type="error" showIcon title="执行仿真失败" description={run_error} />}
                </div>
              </div>}
            </div>
            <Paragraph className="simulation-disclosure">{simulation.disclaimer} 当前沙盘用于验证研判字段、风险排序、调度约束与独立校验链路，不写入设施台账或生产 Runtime。</Paragraph>
          </>}
        </Card>
        </details>

        <details className="system-status-panel">
          <summary>
            <span><strong>系统与数据源状态</strong><small>生产接入、设施台账与历史演示</small></span>
            <Tag>次级信息</Tag>
          </summary>
          <div className="system-status-content">
            <Card title="生产运行服务" className="product-card" extra={runtime_tag}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="状态来源">{runtime_status?.source_name ?? "尚未配置"}</Descriptions.Item>
                <Descriptions.Item label="数据模式">{runtime_status?.data_mode === "production" ? "生产数据" : runtime_status?.data_mode === "test" ? "测试数据" : "未启用"}</Descriptions.Item>
                <Descriptions.Item label="车辆 / 任务">{snapshot ? `${snapshot.vehicles.length} / ${snapshot.tasks.length}` : "—"}</Descriptions.Item>
                <Descriptions.Item label="当前计划">{snapshot?.active_plan ? "已生成" : "—"}</Descriptions.Item>
              </Descriptions>
              <Paragraph className="runtime-detail">{runtime_status?.detail ?? "正在读取运行状态…"}</Paragraph>
            </Card>

            <Card title="设施台账" className="product-card" extra={<Tag color={facility_registry_error ? "default" : "purple"}>{facility_registry_error ? "未启用" : `${facilities.length} 条`}</Tag>}>
              <Paragraph className="facility-guidance">台账属于生产接入准备能力，不影响合成仿真实验。启用后可点击地图登记设施基础信息。</Paragraph>
              {facility_registry_error
                ? <Text type="secondary">当前未配置设施台账服务。</Text>
                : facilities.length === 0
                  ? <Text type="secondary">尚未登记设施</Text>
                  : <ul className="facility-list">{facilities.slice(-5).reverse().map((facility) => <li key={facility.facility_id}>
                      <div><strong>{facility.name}</strong><small>{facility.facility_id} · {facility_type_label(facility.facility_type)}</small></div>
                      <Tag color={facility.status === "ACTIVE" ? "success" : "default"}>{facility.status === "ACTIVE" ? "启用" : "停用"}</Tag>
                    </li>)}</ul>}
            </Card>

            <div className="secondary-entry-card">
              <strong>其他入口</strong>
              <p>历史比赛页面继续保留，仅用于回看既有演示，不属于当前产品主流程。</p>
              <Space wrap>
                <Button size="small" onClick={() => { void refresh_runtime(); void refresh_facilities(); }}>刷新接入状态</Button>
                <a className="demo-link" href="/demo">打开历史比赛演示</a>
              </Space>
            </div>
          </div>
        </details>

      </Content>

      <Modal
        title="登记设施台账"
        open={pending_coordinate !== null}
        okText="保存设施"
        cancelText="取消"
        confirmLoading={facility_saving}
        onOk={() => void handle_facility_save()}
        onCancel={close_facility_editor}
        destroyOnHidden
      >
        <Alert
          className="facility-coordinate-note"
          type="info"
          showIcon
          title="地图选点坐标"
          description={pending_coordinate ? `经度 ${pending_coordinate.longitude.toFixed(6)}，纬度 ${pending_coordinate.latitude.toFixed(6)}（CGCS2000）` : ""}
        />
        <div className="facility-form">
          <label><span>设施编号 *</span><Input value={facility_id} onChange={(event) => set_facility_id(event.target.value)} placeholder="例如：XP-001" maxLength={64} /></label>
          <label><span>设施名称 *</span><Input value={facility_name} onChange={(event) => set_facility_name(event.target.value)} placeholder="例如：东方红大道收运点" maxLength={120} /></label>
          <label><span>设施类型</span><Select value={facility_type} options={facility_type_options} onChange={set_facility_type} /></label>
          <label><span>设计容量</span><InputNumber min={0.01} value={facility_capacity} onChange={set_facility_capacity} placeholder="可选" /></label>
          <label className="facility-address"><span>地址描述</span><Input value={facility_address} onChange={(event) => set_facility_address(event.target.value)} placeholder="可选，填写可核验的实际地址" maxLength={240} /></label>
        </div>
        {facility_save_error && <Alert className="facility-save-error" type="error" showIcon title="保存失败" description={facility_save_error} />}
        <Paragraph className="facility-disclosure">保存后写入本地 SQLite 台账。当前只作为持久化基础事实，不会直接创建任务或改变车辆调度。</Paragraph>
      </Modal>
    </Layout>
  </ConfigProvider>;
}

export function ProductRoot() {
  return <ProductWorkbench />;
}
