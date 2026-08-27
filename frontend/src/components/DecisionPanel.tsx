import { Card, Space, Tag, Typography } from "antd";
import type { Decision } from "../types";

const { Text } = Typography;

interface DecisionPanelProps {
  decision: Decision | null;
  retained_from_replanned: boolean;
}

export function DecisionPanel({ decision, retained_from_replanned }: DecisionPanelProps) {
  if (decision === null) {
    return <Card className="agent-panel" title="治理策略"><Text type="secondary">暂无数据</Text></Card>;
  }

  return (
    <Card className="agent-panel" title={retained_from_replanned ? "最近一次重规划策略" : "治理策略"}>
      <Space orientation="vertical" size="small" className="full-width">
        {retained_from_replanned && <Text className="retained-kicker">保留自动态重规划</Text>}
        <div className="panel-tags">
          <Tag color="purple">{decision.policy_profile}</Tag>
          <Tag color="gold">风险等级 {decision.risk_level}</Tag>
        </div>
        <div className="panel-detail">
          <Text type="secondary">响应时限</Text>
          <strong>{decision.response_deadline ?? "暂无数据"}</strong>
        </div>
        <div className="panel-detail">
          <Text type="secondary">优先目标</Text>
          <div className="panel-tags">
            {decision.priority_targets.length === 0
              ? <Text type="secondary">暂无数据</Text>
              : decision.priority_targets.map((target) => <Tag key={target}>{target}</Tag>)}
          </div>
        </div>
        <p>{decision.reasoning_summary}</p>
      </Space>
    </Card>
  );
}
