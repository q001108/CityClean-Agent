import { Button, Card, ConfigProvider, Layout, Space, Steps, Tag, Typography, theme } from "antd";
import { useState } from "react";
import { CityTopology } from "./CityTopology";
import { DecisionPanel } from "./components/DecisionPanel";
import { EventPanel } from "./components/EventPanel";
import { MetricsPanel } from "./components/MetricsPanel";
import { OptimizerPanel } from "./components/OptimizerPanel";
import { VerifierPanel } from "./components/VerifierPanel";
import { load_demo_scenario, load_v2_experience } from "./demo_data";
import type { Frame, V2Ablation } from "./types";
import "./app.css";

const { Header, Content, Footer } = Layout;
const { Text, Title, Paragraph } = Typography;
type Page = "video" | "ablation" | "evidence" | "breakdown";
const page_labels: Array<[Page, string]> = [["video", "视频演示"], ["ablation", "消融对照"], ["evidence", "实验说明"], ["breakdown", "车辆故障 Demo"]];
const replay_modules = ["投诉接入", "CityEvent", "DeepSeek 研判", "TaskBuilder", "OR-Tools", "Verifier", "CitySim", "最终总结"];
const mismatch_message = "当前输入不匹配已验证的真实冻结轨迹。请选择主演示样例；自由输入实时研判将在后续目标中实现。";

function Percent({ value, digits = 0 }: { value: number; digits?: number }) { return <>{(value * 100).toFixed(digits)}%</>; }
function is_full_ready(item: V2Ablation | undefined, source: string, has_policy: boolean) {
  return item !== undefined && source === "RECORDED_REAL_API" && item.availability === "READY" && has_policy && item.metrics !== null && item.verifier_passed === true;
}
function AblationCard({ item, source, has_policy }: { item: V2Ablation; source: string; has_policy: boolean }) {
  const full_ready = item.mode === "FULL_LLM_POLICY_REPLAN" && is_full_ready(item, source, has_policy);
  const label = full_ready ? "真实 DeepSeek API 冻结轨迹 · 已通过 Verifier" : item.mode === "FIXED_BALANCED_REPLAN" ? "固定策略消融 · 保留确定性重规划" : "无重规划消融 · CitySim 继续执行";
  return <Card className="ablation-card" title={item.label} extra={<Tag color={full_ready ? "cyan" : "blue"}>{item.availability}</Tag>}>
    <Paragraph className={full_ready ? "source-copy" : "secondary-copy"}>{label}</Paragraph>
    <Text type="secondary">优化器：{item.optimizer_status ?? "—"} · Verifier：{item.verifier_passed === null ? "—" : item.verifier_passed ? "PASS" : "FAIL"}</Text>
    {item.metrics ? <div className="metric-strip"><span>完成率<strong><Percent value={item.metrics.task_completion_rate} digits={2} /></strong></span><span>紧急完成<strong><Percent value={item.metrics.urgent_task_completion_rate} digits={2} /></strong></span><span>平均响应<strong>{item.metrics.average_response_time.toFixed(2)} 分</strong></span><span>总距离<strong>{item.metrics.total_distance.toFixed(0)}</strong></span></div> : <Paragraph className="warning-copy">{item.reason}</Paragraph>}
  </Card>;
}
function workflow_status(index: number, stage: number) { return stage > replay_modules.length - 1 || index < stage ? "SUCCESS" : index === stage ? "RUNNING" : "NOT_REACHED"; }
function current_breakdown(frames: Frame[], index: number) {
  const current = frames[index];
  const final = current.metrics !== null;
  const replanned = final ? [...frames.slice(0, index)].reverse().find((frame) => frame.decision !== null || frame.optimizer !== null) : undefined;
  return { current, decision: final ? replanned?.decision ?? null : current.decision, optimizer: final ? replanned?.optimizer ?? null : current.optimizer, retained: final && replanned !== undefined, release_pending: current.assignment.released_task_ids !== null && current.assignment.after_assignments === null };
}

export function App() {
  const demo = load_demo_scenario();
  const v2 = load_v2_experience();
  const frozen_complaint = v2.complaint_session.messages[0].content;
  const full = v2.ablation_comparison.find((item) => item.mode === "FULL_LLM_POLICY_REPLAN");
  const full_ready = is_full_ready(full, v2.provenance.trace_source, v2.policy_decision !== null);
  const [page, set_page] = useState<Page>("video");
  const [video_stage, set_video_stage] = useState(-1);
  const [breakdown_stage, set_breakdown_stage] = useState(0);
  const [complaint_text, set_complaint_text] = useState("");
  const [input_error, set_input_error] = useState<string | null>(null);
  const breakdown = current_breakdown(demo.frames, breakdown_stage);
  const video_final = replay_modules.length;
  const breakdown_final = demo.frames.length - 1;

  const select_page = (next: Page) => { set_page(next); set_video_stage(-1); set_breakdown_stage(0); set_complaint_text(""); set_input_error(null); };
  const fill_demo = () => { set_complaint_text(frozen_complaint); set_input_error(null); };
  const start_replay = () => {
    if (complaint_text.trim() !== frozen_complaint.trim()) { set_input_error(mismatch_message); return; }
    set_input_error(null); set_video_stage(0);
  };
  const reset = () => {
    if (page === "video") { set_video_stage(-1); set_complaint_text(""); set_input_error(null); }
    if (page === "breakdown") set_breakdown_stage(0);
  };
  const previous = () => { if (page === "video") set_video_stage((value) => Math.max(0, value - 1)); if (page === "breakdown") set_breakdown_stage((value) => Math.max(0, value - 1)); };
  const next = () => { if (page === "video") set_video_stage((value) => Math.min(video_final, value + 1)); if (page === "breakdown") set_breakdown_stage((value) => Math.min(breakdown_final, value + 1)); };
  const previous_disabled = page === "video" ? video_stage <= 0 : page !== "breakdown" || breakdown_stage === 0;
  const reset_disabled = page === "video" ? video_stage < 0 && complaint_text.length === 0 : page !== "breakdown" || breakdown_stage === 0;
  const next_disabled = page === "video" ? video_stage < 0 || video_stage >= video_final : page !== "breakdown" || breakdown_stage >= breakdown_final;

  return <ConfigProvider theme={{ algorithm: theme.darkAlgorithm, token: { colorPrimary: "#31d1ff", borderRadius: 8, fontFamily: "Inter, 'Microsoft YaHei', sans-serif", fontSize: 16 } }}>
    <Layout className="showcase-layout">
      <Header className="showcase-header"><div><Text className="eyebrow">CITYCLEAN · V0.2</Text><Title level={1}>城市环卫投诉闭环</Title><Text className="subtitle">LLM 治理研判与确定性调度验证分离</Text></div><Space wrap className="primary-nav">{page_labels.map(([key, label]) => <Button key={key} type={page === key ? "primary" : "default"} onClick={() => select_page(key)}>{label}</Button>)}</Space></Header>
      <Content className="v2-content">
        {page === "video" && <section className="video-shell">
          <div className="v2-tags"><Tag color="gold">精选展示案例</Tag><Tag color="cyan">真实 DeepSeek API 冻结轨迹</Tag><Tag color="blue">确定性稳定回放</Tag><Tag>当前不是实时 Provider 调用</Tag></div>
          <Steps className="replay-steps" current={Math.max(0, Math.min(video_stage, replay_modules.length - 1))} responsive={false} items={replay_modules.map((module, index) => { const status = workflow_status(index, video_stage); return { title: <>{module}<Tag color={status === "SUCCESS" ? "success" : status === "RUNNING" ? "processing" : undefined}>{status}</Tag></>, status: status === "SUCCESS" ? "finish" : status === "RUNNING" ? "process" : "wait" }; })} />
          {video_stage < 0 && <Card className="phase-card intake-card" title="输入并验证主演示投诉"><div className="input-layout"><div><Text className="section-kicker">仅支持 urgent_timing_tradeoff_live 冻结样例</Text><Paragraph>输入会去除首尾空格后与已验证的真实冻结轨迹精确匹配；浏览器不会发起 API 调用。</Paragraph><textarea aria-label="投诉内容" value={complaint_text} onChange={(event) => { set_complaint_text(event.target.value); set_input_error(null); }} placeholder="输入或填入主演示投诉" rows={4} />{input_error && <Paragraph className="input-error">{input_error}</Paragraph>}</div><Space className="input-actions"><Button onClick={fill_demo}>填入主演示样例</Button><Button type="primary" onClick={start_replay}>开始冻结回放</Button></Space></div></Card>}
          {video_stage >= 0 && <div className="phase-card-grid">
            <Card className="phase-card" title={`当前阶段 · ${video_stage < replay_modules.length ? replay_modules[video_stage] : "回放完成"}`}>
              {video_stage === 0 && <><Tag color="processing">RUNNING</Tag><div className="chat-bubble"><Text type="secondary">用户 · {v2.complaint_session.messages[0].source}</Text><Paragraph>{frozen_complaint}</Paragraph></div><Paragraph>正在按冻结契约确认投诉文本与预声明实体别名。</Paragraph></>}
              {video_stage === 1 && <><Tag color="success">CityEvent 已确认</Tag><Paragraph>类型：{v2.city_event.event_type} · 位置：{v2.city_event.location} · 严重度：{v2.city_event.severity}</Paragraph><Paragraph>{v2.city_event.description}</Paragraph></>}
              {video_stage === 2 && v2.policy_decision && <><Tag color="cyan">真实 DeepSeek API 冻结 PolicyDecision</Tag><Paragraph>模型：{v2.provenance.model_id} · 策略：{v2.policy_decision.policy_profile} · 风险等级：{v2.policy_decision.risk_level}</Paragraph><Paragraph>优先目标：{v2.policy_decision.priority_targets.join("、")}</Paragraph><Paragraph>{v2.policy_decision.reasoning_summary}</Paragraph></>}
              {video_stage === 3 && <><Tag color="blue">确定性策略映射</Tag><Paragraph>TaskBuilder 根据已验证的 PolicyDecision 构造任务变化；不由模型计算路线、距离或容量。</Paragraph></>}
              {video_stage === 4 && <><Tag color="blue">OR-Tools</Tag><Paragraph>已接收确定性任务变化并完成求解：{full?.optimizer_status ?? "—"}。任务序列不代表实际道路轨迹。</Paragraph></>}
              {video_stage === 5 && <><Tag color="success">Verifier PASS</Tag><Paragraph>独立硬约束检查：{full?.verifier_passed ? "通过" : "未通过"}。仅通过后才允许 CitySim 安装方案。</Paragraph></>}
              {video_stage === 6 && <><Tag color="success">CitySim</Tag><Paragraph>CitySim 正在以冻结 seed 推进经过验证的调度方案；环境状态和指标仍以确定性模块为准。</Paragraph></>}
              {video_stage >= 7 && <><Tag>DETERMINISTIC_TEMPLATE</Tag><Title level={4}>{v2.final_summary.headline}</Title><Paragraph>{v2.final_summary.citizen_reply}</Paragraph><Text type="secondary">这是基于已验证事实的确定性模板，不是实时模型回复。</Text></>}
            </Card>
            <Card className="phase-card truth-card" title="轨迹真实性与边界"><Tag color={full_ready ? "cyan" : "gold"}>{v2.provenance.trace_source}</Tag><Paragraph>模型标识：{v2.provenance.model_id ?? "未调用模型"}</Paragraph><Paragraph>{full_ready ? "Full 条件已加载真实 PolicyDecision、确定性重规划结果与 Verifier 通过记录。" : "该条件未达到真实冻结轨迹的展示要求。"}</Paragraph><Paragraph className="secondary-copy">无 token 流、无隐藏思维链、无实时 Provider 调用；浏览器不读取 API Key。</Paragraph></Card>
          </div>}
          {video_stage === video_final && <MetricsPanel metrics={v2.final_metrics} phase_status="COMPLETED" />}
        </section>}
        {page === "ablation" && <section className="page-shell"><div className="v2-tags"><Tag color="gold">精选展示案例</Tag><Tag>相同初始状态、事件、tick、时长与 Metrics</Tag></div><Title level={3}>公平消融对照</Title><Paragraph>{full_ready ? "Full 条件使用真实 DeepSeek API 冻结 PolicyDecision；三种条件共享输入，差异仅来自策略选择与是否重规划。" : "当前没有可用的真实 Full 轨迹，因此不会将固定策略冒充为 DeepSeek。"}</Paragraph><div className="ablation-grid">{v2.ablation_comparison.map((item) => <AblationCard item={item} source={v2.provenance.trace_source} has_policy={v2.policy_decision !== null} key={item.mode} />)}</div></section>}
        {page === "evidence" && <section className="page-shell"><Card title="实验说明与数据真实性" className="evidence-card"><Tag color="gold">精选展示案例</Tag><Paragraph>{v2.experience.selected_case_disclosure}</Paragraph><div className="metric-strip experiment-strip"><span>Gold cases<strong>{v2.experiment_summary.gold_cases}</strong></span><span>Successful calls<strong>{v2.experiment_summary.successful_calls}</strong></span><span>合同成功率<strong><Percent value={v2.experiment_summary.contract_success_rate} digits={2} /></strong></span><span>Policy Accuracy<strong><Percent value={v2.experiment_summary.policy_accuracy} digits={2} /></strong></span><span>Macro-F1<strong>{v2.experiment_summary.macro_f1.toFixed(4)}</strong></span><span>Paired Context<strong><Percent value={v2.experiment_summary.paired_context_accuracy} digits={2} /></strong></span><span>Provider failures<strong>{v2.experiment_summary.provider_failures}</strong></span></div><Paragraph className="secondary-copy">冻结 fixture 不含 API Key、身份信息或 Provider 私有响应字段。</Paragraph></Card></section>}
        {page === "breakdown" && <section className="breakdown-shell"><Steps current={breakdown_stage} responsive={false} items={demo.timeline.map((item) => ({ title: item.label }))} /><div className="breakdown-grid"><Card title="城市逻辑拓扑"><CityTopology city={breakdown.current.city} compact /></Card><Space orientation="vertical" className="full-width"><EventPanel event={breakdown.current.event} released_task_ids={breakdown.current.assignment.released_task_ids} release_pending={breakdown.release_pending} /><DecisionPanel decision={breakdown.decision} retained_from_replanned={breakdown.retained} /><OptimizerPanel optimizer={breakdown.optimizer} retained_from_replanned={breakdown.retained} /><VerifierPanel verifier={breakdown.current.verifier} retained_from_replanned={breakdown.retained} /></Space></div>{breakdown.current.metrics && <MetricsPanel metrics={breakdown.current.metrics} phase_status={breakdown.current.phase_status} />}</section>}
      </Content>
      <Footer className="frame-controls"><Text type="secondary">默认回放无业务网络请求；浏览器不读取 API Key。</Text><Space><Button onClick={reset} disabled={reset_disabled}>重置</Button><Button onClick={previous} disabled={previous_disabled}>上一步</Button><Button type="primary" onClick={next} disabled={next_disabled}>下一步</Button></Space></Footer>
    </Layout>
  </ConfigProvider>;
}
