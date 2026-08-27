import { Badge, Card, Space, Tag, Typography } from "antd";
import type { BadgeProps } from "antd";
import type { Verifier } from "../types";

const { Text } = Typography;

interface VerifierPanelProps {
  verifier: Verifier;
  retained_from_replanned: boolean;
}

const badge_status_by_state: Record<string, BadgeProps["status"]> = {
  PASS: "success",
  FAIL: "error",
  NOT_REACHED: "default",
};

function tag_color(state: string): string {
  if (state === "PASS") {
    return "success";
  }

  if (state === "FAIL") {
    return "error";
  }

  return "default";
}

export function VerifierPanel({ verifier, retained_from_replanned }: VerifierPanelProps) {
  const is_pass = verifier.state === "PASS";
  const violation_count = verifier.violations === null ? "暂无数据" : verifier.violations.length;

  return (
    <Card
      className={`agent-panel verifier-panel${is_pass ? " verifier-pass" : ""}`}
      title={retained_from_replanned ? "最近一次已验证方案" : "独立验证"}
    >
      <Space orientation="vertical" size="small" className="full-width">
        {retained_from_replanned && <Text className="retained-kicker">保留自动态重规划</Text>}
        <Badge
          status={badge_status_by_state[verifier.state] ?? "default"}
          text={<Tag color={tag_color(verifier.state)}>{verifier.state}</Tag>}
        />
        <div className="panel-detail">
          <Text type="secondary">违规数量</Text>
          <strong>{violation_count}</strong>
        </div>
      </Space>
    </Card>
  );
}
