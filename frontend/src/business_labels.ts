import type { CityEventType, WorkflowRun } from "./runtime_api";

const event_labels: Record<CityEventType, string> = {
  WASTE_OVERFLOW: "垃圾点满溢",
  VEHICLE_BREAKDOWN: "车辆故障",
  ROAD_CLOSURE: "道路封闭",
  URGENT_TASK: "紧急清运",
};

const task_status_labels: Record<string, string> = {
  PENDING: "待调度",
  ASSIGNED: "已分配",
  IN_PROGRESS: "执行中",
  COMPLETED: "已完成",
};

const vehicle_status_labels: Record<string, string> = {
  AVAILABLE: "可调度",
  EN_ROUTE: "行驶中",
  SERVICING: "作业中",
  BROKEN: "故障",
};

const workflow_status_labels: Record<WorkflowRun["status"], string> = {
  SUCCESS: "调度方案已生成",
  INFEASIBLE: "暂无可行方案",
  VERIFICATION_FAILED: "方案校验未通过",
  IGNORED: "重复事件已忽略",
};

const policy_labels: Record<string, string> = {
  BALANCED: "综合均衡",
  URGENT_RESPONSE: "紧急响应",
  OVERFLOW_CONTROL: "满溢治理",
  MINIMAL_RESCHEDULE: "最小扰动重排",
};

export const event_label = (value: CityEventType) => event_labels[value];
export const task_status_label = (value: string) => task_status_labels[value] ?? value;
export const vehicle_status_label = (value: string) => vehicle_status_labels[value] ?? value;
export const workflow_status_label = (value: WorkflowRun["status"]) => workflow_status_labels[value];
export const policy_label = (value: string | undefined) => value ? policy_labels[value] ?? value : "—";
