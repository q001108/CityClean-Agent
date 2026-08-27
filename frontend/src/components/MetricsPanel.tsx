import { Card, Tag, Typography } from "antd";
import type { Metrics } from "../types";

const { Text } = Typography;

interface MetricsPanelProps {
  metrics: Metrics;
  phase_status: string;
}

function format_percentage(value: number): string {
  const percentage = value * 100;
  return `${Number.isInteger(percentage) ? percentage : percentage.toFixed(1)}%`;
}

export function MetricsPanel({ metrics, phase_status }: MetricsPanelProps) {
  return (
    <Card className="console-card final-metrics-panel" title="执行完成 · 核心指标">
      <div className="metrics-heading">
        <Tag color="success">{phase_status}</Tag>
        <Text type="secondary">最终环境反馈</Text>
      </div>
      <div className="metrics-grid">
        <div>
          <Text type="secondary">任务完成率</Text>
          <strong>{format_percentage(metrics.task_completion_rate)}</strong>
        </div>
        <div>
          <Text type="secondary">平均响应时间</Text>
          <strong>{metrics.average_response_time.toFixed(2)}</strong>
        </div>
        <div>
          <Text type="secondary">总距离</Text>
          <strong>{metrics.total_distance}</strong>
        </div>
        <div>
          <Text type="secondary">溢出数量</Text>
          <strong>{metrics.overflow_count}</strong>
        </div>
      </div>
    </Card>
  );
}
