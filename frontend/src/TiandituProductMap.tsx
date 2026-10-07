import { Tag } from "antd";
import { useEffect, useRef, useState } from "react";
import { vehicle_status_label } from "./business_labels";
import type { CitySnapshot, FacilityRecord, GeoCoordinate, SyntheticDispatch, SyntheticNetwork, SyntheticRunSnapshot } from "./runtime_api";
import { load_tianditu } from "./tianditu_sdk";
import type {
  TiandituMapInstance,
  TiandituMapClickEvent,
  TiandituNamespace,
} from "./tianditu_sdk";

type ProductMapStatus = "loading" | "ready" | "error" | "missing-key";

type TiandituProductMapProps = {
  snapshot: CitySnapshot | null;
  facilities: FacilityRecord[];
  pending_coordinate: GeoCoordinate | null;
  on_map_select: (coordinate: GeoCoordinate) => void;
  simulation: SyntheticNetwork | null;
  simulation_dispatch: SyntheticDispatch | null;
  simulation_run: SyntheticRunSnapshot | null;
  runtime_summary?: {
    event: string;
    task: string;
    route: string;
  } | null;
};

function add_label(
  api: TiandituNamespace,
  map: TiandituMapInstance,
  coordinate: GeoCoordinate,
  text: string,
  colors: { background: string; border: string; foreground: string },
  on_select: () => void,
) {
  const label = new api.Label({
    text,
    position: new api.LngLat(coordinate.longitude, coordinate.latitude),
  });
  label.setBackgroundColor(colors.background);
  label.setBorderColor(colors.border);
  label.setBorderLine(2);
  label.setFontColor(colors.foreground);
  label.setFontSize(12);
  label.addEventListener("click", on_select);
  map.addOverLay(label);
}

function path_points(api: TiandituNamespace, path: GeoCoordinate[]) {
  return path.map((point) => new api.LngLat(point.longitude, point.latitude));
}

function synthetic_edge_id_from_road_id(road_id: string): string {
  return road_id.replace(/-(F|R)$/, "");
}

function add_risk_point(
  api: TiandituNamespace,
  map: TiandituMapInstance,
  coordinate: GeoCoordinate,
  color: string,
  on_select: () => void,
) {
  const label = new api.Label({
    text: "●",
    position: new api.LngLat(coordinate.longitude, coordinate.latitude),
  });
  label.setBackgroundColor("transparent");
  label.setBorderColor("transparent");
  label.setBorderLine(0);
  label.setFontColor(color);
  label.setFontSize(18);
  label.addEventListener("click", on_select);
  map.addOverLay(label);
}

export function TiandituProductMap({
  snapshot,
  facilities,
  pending_coordinate,
  on_map_select,
  simulation,
  simulation_dispatch,
  simulation_run,
  runtime_summary = null,
}: TiandituProductMapProps) {
  const container_ref = useRef<HTMLDivElement>(null);
  const map_ref = useRef<TiandituMapInstance | null>(null);
  const api_ref = useRef<TiandituNamespace | null>(null);
  const map_click_handler_ref = useRef<((event: TiandituMapClickEvent) => void) | null>(null);
  const on_map_select_ref = useRef(on_map_select);
  const api_key = import.meta.env.VITE_TIANDITU_KEY?.trim() ?? "";
  const [status, set_status] = useState<ProductMapStatus>(api_key === "" ? "missing-key" : "loading");
  const [error_message, set_error_message] = useState("");
  const [selected_detail, set_selected_detail] = useState("点击地图标记查看业务详情");

  useEffect(() => {
    on_map_select_ref.current = on_map_select;
  }, [on_map_select]);

  useEffect(() => {
    if (api_key === "" || container_ref.current === null) {
      return;
    }
    let active = true;
    set_status("loading");

    load_tianditu(api_key)
      .then((api) => {
        if (!active || container_ref.current === null) {
          return;
        }
        container_ref.current.replaceChildren();
        const map = new api.Map(container_ref.current);
        map.centerAndZoom(new api.LngLat(114.0913, 32.147), 13);
        map.enableScrollWheelZoom();
        map.setStyle("indigo");
        const handle_map_click = (event: TiandituMapClickEvent) => {
          on_map_select_ref.current({
            longitude: event.lnglat.getLng(),
            latitude: event.lnglat.getLat(),
          });
        };
        map.addEventListener("click", handle_map_click);
        map_click_handler_ref.current = handle_map_click;
        api_ref.current = api;
        map_ref.current = map;
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
      if (map_ref.current !== null && map_click_handler_ref.current !== null) {
        map_ref.current.removeEventListener("click", map_click_handler_ref.current);
      }
      map_ref.current?.clearOverLays();
      map_ref.current = null;
      api_ref.current = null;
      map_click_handler_ref.current = null;
    };
  }, [api_key]);

  useEffect(() => {
    const api = api_ref.current;
    const map = map_ref.current;
    if (status !== "ready" || api === null || map === null) {
      return;
    }
    map.clearOverLays();

    if (simulation !== null) {
      const nodes = new Map(simulation.nodes.map((node) => [node.node_id, node]));
      const closed_edge_ids = new Set(
        (simulation_run?.closed_road_ids ?? []).map(synthetic_edge_id_from_road_id),
      );
      const live_bins = new Map((simulation_run?.bins ?? []).map((bin) => [bin.bin_id, bin]));
      simulation.edges.forEach((edge) => {
        const from = nodes.get(edge.from_node);
        const to = nodes.get(edge.to_node);
        if (from === undefined || to === undefined) {
          return;
        }
        const closed = closed_edge_ids.has(edge.edge_id);
        map.addOverLay(new api.Polyline(path_points(api, [from, to]), {
          color: closed ? "#ef4444" : edge.congestion_level >= 0.72 ? "#d97706" : "#38606b",
          lineStyle: closed ? "dashed" : "solid",
          opacity: closed ? 0.95 : edge.congestion_level >= 0.72 ? 0.5 : 0.28,
          weight: closed ? 5 : edge.congestion_level >= 0.72 ? 2 : 1,
        }));
      });

      const route_colors = ["#22d3ee", "#a78bfa", "#34d399", "#fb923c", "#f472b6", "#60a5fa"];
      const visible_routes = simulation_run?.routes ?? simulation_dispatch?.routes ?? [];
      visible_routes.forEach((route, index) => {
        if (route.path.length < 2) {
          return;
        }
        map.addOverLay(new api.Polyline(path_points(api, route.path), {
          color: route_colors[index % route_colors.length],
          lineStyle: "solid",
          opacity: 0.95,
          weight: 5,
        }));
      });

      simulation_run?.vehicles.forEach((vehicle) => {
        add_risk_point(
          api,
          map,
          vehicle.coordinate,
          vehicle.status === "BROKEN" ? "#ef4444" : "#22d3ee",
          () => set_selected_detail(
            `${vehicle.vehicle_id} · ${vehicle_status_label(vehicle.status)} · 载荷 ${Math.round(vehicle.current_load_liters)}/${Math.round(vehicle.capacity_liters)} 升 · 节点 ${vehicle.current_node_id}`,
          ),
        );
      });

      simulation.bins
        .filter((bin) => bin.risk_level === "CRITICAL" || bin.risk_level === "HIGH")
        .sort((first, second) => second.risk_score - first.risk_score)
        .slice(0, 36)
        .forEach((bin) => {
          const critical = bin.risk_level === "CRITICAL";
          const live_bin = live_bins.get(bin.bin_id);
          const fill_ratio = live_bin?.fill_ratio ?? bin.fill_ratio;
          add_risk_point(
            api,
            map,
            bin,
            critical ? "#fb7185" : "#fbbf24",
            () => set_selected_detail(
              `${bin.bin_id} · ${bin.site_name} · 当前装载率 ${Math.round(fill_ratio * 100)}% · 风险 ${bin.risk_score} · ${bin.risk_reasons.join("；")}`,
            ),
          );
        });
    }

    snapshot?.roads.forEach((road) => {
      if (road.from_coordinate === null || road.to_coordinate === null) {
        return;
      }
      map.addOverLay(new api.Polyline(
        path_points(api, [road.from_coordinate, road.to_coordinate]),
        {
          color: road.status === "CLOSED" ? "#ef4444" : "#5d7f89",
          lineStyle: road.status === "CLOSED" ? "dashed" : "solid",
          opacity: 0.65,
          weight: road.status === "CLOSED" ? 5 : 3,
        },
      ));
    });

    snapshot?.active_plan?.vehicle_routes.forEach((route, index) => {
      if (route.path.length < 2) {
        return;
      }
      map.addOverLay(new api.Polyline(path_points(api, route.path), {
        color: index % 2 === 0 ? "#a78bfa" : "#fb923c",
        lineStyle: "dashed",
        opacity: 0.98,
        weight: 7,
      }));
    });

    const active_targets = new Set(
      (snapshot?.tasks ?? [])
        .filter((task) => task.status !== "COMPLETED")
        .map((task) => task.target_id),
    );
    snapshot?.waste_points.forEach((point) => {
      if (point.coordinate === null) {
        return;
      }
      const active = active_targets.has(point.id);
      add_label(
        api,
        map,
        point.coordinate,
        `${active ? "任务点" : "收运点"} ${point.id}`,
        active
          ? { background: "#4a3500", border: "#fbbf24", foreground: "#fef3c7" }
          : { background: "#123d32", border: "#34d399", foreground: "#d1fae5" },
        () => set_selected_detail(
          `${point.id} · 当前量 ${point.current_load}/${point.capacity}${active ? " · 存在待执行任务" : ""}`,
        ),
      );
    });

    snapshot?.vehicles.forEach((vehicle) => {
      if (vehicle.coordinate === null) {
        return;
      }
      const broken = vehicle.status === "BROKEN";
      add_label(
        api,
        map,
        vehicle.coordinate,
        `${broken ? "故障车辆" : "车辆"} ${vehicle.id}`,
        broken
          ? { background: "#4b171d", border: "#f87171", foreground: "#fee2e2" }
          : { background: "#0f3652", border: "#60a5fa", foreground: "#dbeafe" },
        () => set_selected_detail(
          `${vehicle.id} · ${vehicle_status_label(vehicle.status)} · 当前节点 ${vehicle.current_node_id}`,
        ),
      );
    });

    facilities.forEach((facility) => {
      add_label(
        api,
        map,
        facility,
        `台账 · ${facility.name}`,
        facility.status === "ACTIVE"
          ? { background: "#3b1f5e", border: "#c084fc", foreground: "#f3e8ff" }
          : { background: "#30343b", border: "#9ca3af", foreground: "#e5e7eb" },
        () => set_selected_detail(
          `${facility.name} · ${facility.facility_id} · ${facility.address || "未填写地址"} · ${facility.coordinate_system}`,
        ),
      );
    });

    if (pending_coordinate !== null) {
      add_label(
        api,
        map,
        pending_coordinate,
        "新设施选点",
        { background: "#5b2508", border: "#fb923c", foreground: "#ffedd5" },
        () => set_selected_detail("当前待录入设施位置"),
      );
    }
  }, [facilities, pending_coordinate, simulation, simulation_dispatch, simulation_run, snapshot, status]);

  if (status === "missing-key" || status === "error") {
    const nodes = new Map((simulation?.nodes ?? []).map((node) => [node.node_id, node]));
    const coordinates = simulation?.nodes ?? [];
    const longitudes = coordinates.map((point) => point.longitude);
    const latitudes = coordinates.map((point) => point.latitude);
    const min_longitude = Math.min(...longitudes);
    const max_longitude = Math.max(...longitudes);
    const min_latitude = Math.min(...latitudes);
    const max_latitude = Math.max(...latitudes);
    const longitude_span = Math.max(max_longitude - min_longitude, 0.000001);
    const latitude_span = Math.max(max_latitude - min_latitude, 0.000001);
    const project = (point: GeoCoordinate) => ({
      x: 35 + ((point.longitude - min_longitude) / longitude_span) * 930,
      y: 55 + ((max_latitude - point.latitude) / latitude_span) * 490,
    });
    const closed_edge_ids = new Set((simulation_run?.closed_road_ids ?? []).map(synthetic_edge_id_from_road_id));
    const live_bins = new Map((simulation_run?.bins ?? []).map((bin) => [bin.bin_id, bin]));
    const visible_routes = simulation_run?.routes ?? simulation_dispatch?.routes ?? [];
    const route_colors = ["#22d3ee", "#a78bfa", "#34d399", "#fb923c", "#f472b6", "#60a5fa"];

    return <div className="product-map-shell product-map-fallback">
      <div className="product-map-fallback-heading">
        <strong>合成路网视图</strong>
        <span>非真实地图 · {status === "error" ? "天地图不可用" : "无需地图密钥"}</span>
      </div>
      {simulation ? <svg className="product-map-fallback-svg" viewBox="0 0 1000 600" role="img" aria-label="合成路网、调度路线、风险点和执行车辆">
        {simulation.edges.map((edge) => {
          const from = nodes.get(edge.from_node);
          const to = nodes.get(edge.to_node);
          if (!from || !to) return null;
          const start = project(from);
          const end = project(to);
          const closed = closed_edge_ids.has(edge.edge_id);
          return <line key={edge.edge_id} data-edge-id={edge.edge_id} x1={start.x} y1={start.y} x2={end.x} y2={end.y}
            stroke={closed ? "#ef4444" : edge.congestion_level >= 0.72 ? "#d97706" : "#38606b"}
            strokeWidth={closed ? 5 : edge.congestion_level >= 0.72 ? 2 : 1.5}
            strokeOpacity={closed ? 0.95 : edge.congestion_level >= 0.72 ? 0.65 : 0.5}
            strokeDasharray={closed ? "7 5" : undefined} />;
        })}
        {visible_routes.map((route, index) => <polyline key={route.vehicle_id} data-route-id={route.vehicle_id}
          points={route.path.map((point) => { const position = project(point); return `${position.x},${position.y}`; }).join(" ")}
          fill="none" stroke={route_colors[index % route_colors.length]} strokeWidth="5" strokeOpacity="0.9" strokeLinejoin="round" />)}
        {simulation.bins.filter((bin) => bin.risk_level === "CRITICAL" || bin.risk_level === "HIGH")
          .sort((first, second) => second.risk_score - first.risk_score).slice(0, 36).map((bin) => {
            const position = project(bin);
            const fill_ratio = live_bins.get(bin.bin_id)?.fill_ratio ?? bin.fill_ratio;
            return <circle key={bin.bin_id} data-bin-id={bin.bin_id} cx={position.x} cy={position.y} r="4.5"
              fill={bin.risk_level === "CRITICAL" ? "#fb7185" : "#fbbf24"} stroke="#081f30" strokeWidth="1.5"
              onClick={() => set_selected_detail(`${bin.bin_id} · ${bin.site_name} · 当前装载率 ${Math.round(fill_ratio * 100)}% · 风险 ${bin.risk_score}`)} />;
          })}
        {simulation_run?.vehicles.map((vehicle) => {
          const position = project(vehicle.coordinate);
          return <circle key={vehicle.vehicle_id} data-vehicle-id={vehicle.vehicle_id} cx={position.x} cy={position.y} r="8"
            fill={vehicle.status === "BROKEN" ? "#ef4444" : "#22d3ee"} stroke="#fff" strokeWidth="2"
            onClick={() => set_selected_detail(`${vehicle.vehicle_id} · ${vehicle_status_label(vehicle.status)} · 载荷 ${Math.round(vehicle.current_load_liters)}/${Math.round(vehicle.capacity_liters)} 升`)} />;
        })}
      </svg> : <div className="product-map-fallback-loading">正在准备合成路网…</div>}
      <div className="product-map-fallback-legend">
        <span><i className="legend-simulation" />高风险点</span>
        <span><i className="legend-simulation-route" />调度路线</span>
        <span><i className="legend-run-vehicle" />车辆</span>
        <span><i className="legend-closed-road" />封闭道路</span>
      </div>
      <div className="product-map-detail" aria-live="polite">{selected_detail}</div>
      <div className="product-map-notice">{status === "error" ? `${error_message}；` : ""}仅显示可复现的合成路网，不表示真实道路或设施位置；此视图不支持真实地理选点。</div>
    </div>;
  }

  const located_entity_count = snapshot
    ? snapshot.waste_points.filter((point) => point.coordinate !== null).length
      + snapshot.vehicles.filter((vehicle) => vehicle.coordinate !== null).length
    : 0;

  return <div className="product-map-shell">
    <div ref={container_ref} className="product-map-canvas" role="application" aria-label="城市环卫实时态势地图" />
    <div className="product-map-status">
      <Tag color="blue">天地图</Tag>
      <Tag color={status === "ready" ? "success" : "processing"}>{status === "ready" ? "底图已连接" : "正在加载"}</Tag>
      <Tag color={snapshot ? "success" : "default"}>{snapshot ? "运行快照已连接" : "等待运行快照"}</Tag>
      <Tag color="purple">台账 {facilities.length}</Tag>
      {simulation && <Tag color="gold">仿真 {simulation.analysis.road_node_count} 节点 / {simulation.analysis.bin_count} 桶</Tag>}
      {simulation_run === null && simulation_dispatch?.status === "SUCCESS" && <Tag color="cyan">已验证 {simulation_dispatch.summary.route_count} 条路线</Tag>}
      {simulation_run && <Tag color={simulation_run.status === "NEEDS_ATTENTION" ? "error" : "cyan"}>当前 {simulation_run.routes.length} 条路线</Tag>}
      {simulation_run && <Tag color={simulation_run.status === "NEEDS_ATTENTION" ? "error" : "processing"}>执行 +{simulation_run.elapsed_minutes} 分钟</Tag>}
      {(simulation_run?.closed_road_ids.length ?? 0) > 0 && <Tag color="error">封闭道路 {simulation_run?.closed_road_ids.length}</Tag>}
    </div>
    {runtime_summary && <div className="product-map-facts" aria-live="polite">
      <strong><span className="live-dot" />最新运行事实</strong>
      <span><b>事件</b>{runtime_summary.event}</span>
      <span><b>任务</b>{runtime_summary.task}</span>
      <span><b>调度</b>{runtime_summary.route}</span>
    </div>}
    {(located_entity_count > 0 || facilities.length > 0) && <div className="product-map-legend">
      <span><i className="legend-vehicle" />车辆</span>
      <span><i className="legend-point" />收运点</span>
      <span><i className="legend-facility" />设施台账</span>
      {simulation && <span><i className="legend-simulation" />仿真高风险桶</span>}
      {((simulation_run?.routes.length ?? 0) > 0 || (simulation_run === null && simulation_dispatch?.status === "SUCCESS")) && <span><i className="legend-simulation-route" />仿真调度路线</span>}
      {simulation_run && <span><i className="legend-run-vehicle" />执行车辆</span>}
      {(simulation_run?.closed_road_ids.length ?? 0) > 0 && <span><i className="legend-closed-road" />封闭道路</span>}
      <span><i className="legend-route" />调度路线</span>
    </div>}
    <div className="product-map-detail" aria-live="polite">{selected_detail}</div>
    <div className="product-map-notice">{simulation
      ? `${simulation_run ? "青色点为当前仿真车辆节点；" : ""}${simulation_dispatch?.status === "SUCCESS" ? "彩色粗线为已验证路线；" : ""}细线为仿真路网，风险点不代表真实单位。`
      : "点击地图可登记设施。台账点位独立持久化，尚未同步到调度运行态。"}</div>
  </div>;
}
