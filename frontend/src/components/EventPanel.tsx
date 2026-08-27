import { Card, Space, Tag, Typography } from "antd";
import type { Event } from "../types";

const { Text } = Typography;

interface EventPanelProps {
  event: Event | null;
  released_task_ids: string[] | null;
  release_pending: boolean;
}

export function EventPanel({ event, released_task_ids, release_pending }: EventPanelProps) {
  if (event === null) {
    return <Card className="agent-panel" title="事件研判"><Text type="secondary">暂无数据</Text></Card>;
  }

  return (
    <Card className="agent-panel" title="事件研判">
      <Space orientation="vertical" size="small" className="full-width">
        <div className="panel-tags">
          <Tag color="orange">{event.event_type}</Tag>
          <Tag color="volcano">严重等级 {event.severity}</Tag>
          <Tag>{event.location}</Tag>
        </div>
        <p>{event.description}</p>
        {release_pending && released_task_ids !== null && (
          <div className="release-callout">
            <Text className="release-kicker">任务已释放</Text>
            <div className="panel-tags">
              {released_task_ids.map((task_id) => <Tag key={task_id} color="gold">{task_id} · 已释放</Tag>)}
            </div>
            <strong>等待重新分配</strong>
          </div>
        )}
      </Space>
    </Card>
  );
}
