import { useEffect, useRef, useState } from "react";
import { Alert, Tag } from "antd";
import { CityTopology } from "./CityTopology";
import { load_tianditu } from "./tianditu_sdk";
import type { TiandituMapInstance, TiandituNamespace } from "./tianditu_sdk";
import type { City, VehicleAssignment } from "./types";

interface TiandituCityMapProps {
  city: City;
  assignments: VehicleAssignment[] | null;
  compact: boolean;
}

interface DemoCoordinate {
  lng: number;
  lat: number;
}

type MapStatus = "loading" | "ready" | "error" | "missing-token";

// 信阳市范围内的演示投影，仅用于把逻辑节点放到底图上，不代表真实设施位置。
const xinyang_demo_coordinates: Record<string, DemoCoordinate> = {
  A: { lng: 114.056, lat: 32.137 },
  B: { lng: 114.079, lat: 32.145 },
  C: { lng: 114.104, lat: 32.151 },
  D: { lng: 114.132, lat: 32.159 },
  Z: { lng: 114.101, lat: 32.179 },
};

function coordinate_for(node_id: string, index = 0): DemoCoordinate | undefined {
  const coordinate = xinyang_demo_coordinates[node_id];
  if (coordinate === undefined) {
    return undefined;
  }
  const angle = (index % 6) * (Math.PI / 3);
  const radius = index === 0 ? 0 : 0.0032;
  return {
    lng: coordinate.lng + Math.cos(angle) * radius,
    lat: coordinate.lat + Math.sin(angle) * radius,
  };
}

function add_label(
  api: TiandituNamespace,
  map: TiandituMapInstance,
  coordinate: DemoCoordinate,
  text: string,
  colors: { background: string; border: string; foreground: string },
  on_select: () => void,
) {
  const label = new api.Label({ text, position: new api.LngLat(coordinate.lng, coordinate.lat) });
  label.setBackgroundColor(colors.background);
  label.setBorderColor(colors.border);
  label.setBorderLine(2);
  label.setFontColor(colors.foreground);
  label.setFontSize(12);
  label.addEventListener("click", on_select);
  map.addOverLay(label);
}

export function TiandituCityMap({ city, assignments, compact }: TiandituCityMapProps) {
  const container_ref = useRef<HTMLDivElement>(null);
  const api_key = import.meta.env.VITE_TIANDITU_KEY?.trim() ?? "";
  const [status, set_status] = useState<MapStatus>(api_key === "" ? "missing-token" : "loading");
  const [error_message, set_error_message] = useState("");
  const [selected, set_selected] = useState("点击地图中的车辆或任务点查看详情");

  useEffect(() => {
    if (api_key === "" || container_ref.current === null) {
      return;
    }

    let active = true;
    let map: TiandituMapInstance | null = null;
    set_status("loading");
    set_error_message("");

    load_tianditu(api_key)
      .then((api) => {
        if (!active || container_ref.current === null) {
          return;
        }
        container_ref.current.replaceChildren();
        map = new api.Map(container_ref.current);
        map.centerAndZoom(new api.LngLat(114.095, 32.153), 12);
        map.enableScrollWheelZoom();
        map.setStyle("indigo");

        city.roads.forEach((road) => {
          const from = xinyang_demo_coordinates[road.from_node];
          const to = xinyang_demo_coordinates[road.to_node];
          if (from === undefined || to === undefined || map === null) {
            return;
          }
          map.addOverLay(new api.Polyline(
            [new api.LngLat(from.lng, from.lat), new api.LngLat(to.lng, to.lat)],
            { color: road.status === "OPEN" ? "#52d9bb" : "#ff7875", opacity: 0.72, weight: 4 },
          ));
        });

        assignments?.forEach((assignment, route_index) => {
          const vehicle = city.vehicles.find((item) => item.vehicle_id === assignment.vehicle_id);
          const route_nodes = [
            vehicle?.node_id,
            ...assignment.task_sequence.map((task_id) => city.tasks.find((task) => task.task_id === task_id)?.node_id),
          ].filter((node_id): node_id is string => node_id !== undefined);
          const points = route_nodes
            .map((node_id) => xinyang_demo_coordinates[node_id])
            .filter((coordinate): coordinate is DemoCoordinate => coordinate !== undefined)
            .map((coordinate) => new api.LngLat(coordinate.lng, coordinate.lat));
          if (points.length >= 2 && map !== null) {
            map.addOverLay(new api.Polyline(points, {
              color: route_index % 2 === 0 ? "#722ed1" : "#fa8c16",
              lineStyle: "dashed",
              opacity: 0.95,
              weight: 7,
            }));
          }
        });

        city.tasks.forEach((task, index) => {
          const coordinate = coordinate_for(task.node_id, index + 1);
          if (coordinate === undefined || map === null) {
            return;
          }
          add_label(
            api,
            map,
            coordinate,
            `任务 ${task.task_id}`,
            { background: "#4a3500", border: "#faad14", foreground: "#fff1b8" },
            () => set_selected(`任务 ${task.task_id} · 状态 ${task.status} · 逻辑节点 ${task.node_id} · 优先级 ${task.priority}`),
          );
        });

        city.vehicles.forEach((vehicle, index) => {
          const coordinate = coordinate_for(vehicle.node_id, index + 4);
          if (coordinate === undefined || map === null) {
            return;
          }
          const broken = vehicle.status === "BROKEN";
          add_label(
            api,
            map,
            coordinate,
            `${broken ? "故障" : "车辆"} ${vehicle.vehicle_id}`,
            broken
              ? { background: "#4b171d", border: "#ff7875", foreground: "#fff1f0" }
              : { background: "#0f3652", border: "#69c0ff", foreground: "#e6f7ff" },
            () => set_selected(`车辆 ${vehicle.vehicle_id} · 状态 ${vehicle.status} · 逻辑节点 ${vehicle.node_id} · 载荷 ${vehicle.load}`),
          );
        });

        set_status("ready");
      })
      .catch((error: unknown) => {
        if (!active) {
          return;
        }
        set_error_message(error instanceof Error ? error.message : "天地图初始化失败");
        set_status("error");
      });

    return () => {
      active = false;
      map?.clearOverLays();
    };
  }, [api_key, assignments, city]);

  if (status === "missing-token" || status === "error") {
    return <div className="map-fallback">
      <Alert
        type={status === "error" ? "warning" : "info"}
        showIcon
        title={status === "error" ? "天地图暂不可用，已回退逻辑拓扑" : "未配置天地图 Key，当前显示逻辑拓扑"}
        description={status === "error" ? error_message : "请在 frontend/.env.local 中设置 VITE_TIANDITU_KEY，然后重启前端。"}
      />
      <CityTopology city={city} compact={compact} />
    </div>;
  }

  return <div className={`tianditu-shell${compact ? " tianditu-shell-compact" : ""}`}>
    <div ref={container_ref} className="tianditu-map" role="application" aria-label="天地图真实地图场景" />
    <div className="tianditu-map-badges">
      <Tag color="blue">天地图</Tag>
      <Tag color="gold">演示映射，非真实设施位置</Tag>
      <Tag>{status === "ready" ? "地图已加载" : "地图加载中"}</Tag>
    </div>
    <div className="tianditu-map-detail" aria-live="polite">{selected}</div>
    <div className="tianditu-map-legend">
      <span><i className="legend-vehicle" />车辆</span>
      <span><i className="legend-task" />任务点</span>
      <span><i className="legend-route" />逻辑任务序列</span>
    </div>
  </div>;
}
