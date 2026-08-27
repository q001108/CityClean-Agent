import { Card, Space, Tag, Typography } from "antd";
import type { Optimizer } from "../types";

const { Text } = Typography;

interface OptimizerPanelProps {
  optimizer: Optimizer | null;
  retained_from_replanned: boolean;
}

export function OptimizerPanel({ optimizer, retained_from_replanned }: OptimizerPanelProps) {
  if (optimizer === null) {
    return <Card className="agent-panel" title="调度优化"><Text type="secondary">暂无数据</Text></Card>;
  }

  return (
    <Card className="agent-panel" title={retained_from_replanned ? "最近一次重规划调度" : "调度优化"}>
      <Space orientation="vertical" size="small" className="full-width">
        {retained_from_replanned && <Text className="retained-kicker">任务序列，不代表实际道路轨迹</Text>}
        <div className="panel-tags">
          <Tag color="cyan">{optimizer.status}</Tag>
        </div>
        <div className="panel-detail">
          <Text type="secondary">任务执行顺序</Text>
          <div className="panel-tags">
            {optimizer.vehicle_routes.map((route) => (
              <Tag key={route.vehicle_id} color="blue">
                {route.vehicle_id} → {route.task_sequence.join(", ")}
              </Tag>
            ))}
          </div>
        </div>
        <div className="panel-detail">
          <Text type="secondary">未分配任务</Text>
          <strong>{optimizer.unassigned_tasks.length}</strong>
        </div>
      </Space>
    </Card>
  );
}
