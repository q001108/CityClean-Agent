import type { City } from "./types";

interface CityTopologyProps {
  city: City;
  compact: boolean;
}

interface Point {
  x: number;
  y: number;
}

const fixed_node_positions: Record<string, Point> = {
  A: { x: 100, y: 230 },
  B: { x: 270, y: 230 },
  C: { x: 450, y: 230 },
  D: { x: 630, y: 230 },
  Z: { x: 450, y: 80 },
};

function road_color(status: string): string {
  return status === "OPEN" ? "#52d9bb" : "#ff7875";
}

function vehicle_color(status: string): string {
  return status === "BROKEN" ? "#ff7875" : "#69c0ff";
}

function task_color(status: string): string {
  if (status === "COMPLETED") {
    return "#52c41a";
  }

  if (status === "PENDING") {
    return "#faad14";
  }

  return "#69c0ff";
}

function item_index_at_node<T extends { node_id: string }>(items: T[], item_index: number): number {
  const item = items[item_index];
  return items.slice(0, item_index).filter((previous_item) => previous_item.node_id === item.node_id).length;
}

export function CityTopology({ city, compact }: CityTopologyProps) {
  return (
    <svg
      viewBox="0 0 730 390"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="城市逻辑拓扑"
      className={`city-topology${compact ? " city-topology-compact" : ""}`}
    >
      <title>城市逻辑拓扑</title>
      <rect width="730" height="390" rx="12" fill="#081725" />

      <g aria-label="道路">
        {city.roads.map((road) => {
          const from_position = fixed_node_positions[road.from_node];
          const to_position = fixed_node_positions[road.to_node];

          if (from_position === undefined || to_position === undefined) {
            return null;
          }

          const label_x = (from_position.x + to_position.x) / 2;
          const label_y = (from_position.y + to_position.y) / 2 - 12;

          return (
            <g key={road.road_id}>
              <line
                x1={from_position.x}
                y1={from_position.y}
                x2={to_position.x}
                y2={to_position.y}
                stroke={road_color(road.status)}
                strokeWidth="4"
                strokeLinecap="round"
                opacity="0.85"
              />
              <text x={label_x} y={label_y} textAnchor="middle" fill="#b7d4e6" fontSize="12">
                {road.road_id} · {road.status}
              </text>
            </g>
          );
        })}
      </g>

      <g aria-label="垃圾点">
        {city.waste_points.map((waste_point, index) => {
          const position = fixed_node_positions[waste_point.node_id];

          if (position === undefined) {
            return null;
          }

          const offset = item_index_at_node(city.waste_points, index) * 24;

          return (
            <g key={waste_point.waste_point_id} transform={`translate(${position.x - 52}, ${position.y + 38 + offset})`}>
              <rect width="104" height="21" rx="5" fill="#183b55" stroke="#3b85aa" />
              <text x="52" y="15" textAnchor="middle" fill="#d8f0ff" fontSize="11">
                {waste_point.waste_point_id} {waste_point.current_load}/{waste_point.capacity}
              </text>
            </g>
          );
        })}
      </g>

      <g aria-label="任务">
        {city.tasks.map((task, index) => {
          const position = fixed_node_positions[task.node_id];

          if (position === undefined) {
            return null;
          }

          const offset = item_index_at_node(city.tasks, index) * 23;

          return (
            <text
              key={task.task_id}
              x={position.x}
              y={position.y + 80 + offset}
              textAnchor="middle"
              fill={task_color(task.status)}
              fontSize="11"
              fontWeight="600"
            >
              {task.task_id} · {task.status}
            </text>
          );
        })}
      </g>

      <g aria-label="车辆">
        {city.vehicles.map((vehicle, index) => {
          const position = fixed_node_positions[vehicle.node_id];

          if (position === undefined) {
            return null;
          }

          const offset = item_index_at_node(city.vehicles, index) * 24;
          const color = vehicle_color(vehicle.status);

          return (
            <g key={vehicle.vehicle_id} transform={`translate(${position.x - 50}, ${position.y - 70 - offset})`}>
              {vehicle.status === "BROKEN" && (
                <text x="50" y="-5" textAnchor="middle" fill="#ff7875" fontSize="10" fontWeight="700">
                  故障车辆
                </text>
              )}
              <rect
                width="100"
                height="23"
                rx="5"
                fill={vehicle.status === "BROKEN" ? "#3b171d" : "#0f263a"}
                stroke={color}
                strokeWidth={vehicle.status === "BROKEN" ? "3" : "1.5"}
              />
              <text x="50" y="16" textAnchor="middle" fill={color} fontSize="11" fontWeight="700">
                {vehicle.vehicle_id} · {vehicle.status}
              </text>
            </g>
          );
        })}
      </g>

      <g aria-label="节点">
        {city.nodes.map((node) => {
          const position = fixed_node_positions[node.node_id];

          if (position === undefined) {
            return null;
          }

          return (
            <g key={node.node_id}>
              <circle cx={position.x} cy={position.y} r="21" fill="#14334a" stroke="#7ce2ff" strokeWidth="2" />
              <text x={position.x} y={position.y + 5} textAnchor="middle" fill="#f0fbff" fontSize="14" fontWeight="700">
                {node.node_id}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}
