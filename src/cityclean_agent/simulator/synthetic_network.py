"""Deterministic map-area sandbox data for development without business feeds."""

from __future__ import annotations

import math
import random
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SandboxContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SiteType(str, Enum):
    SCHOOL = "SCHOOL"
    HOSPITAL = "HOSPITAL"
    RESIDENTIAL = "RESIDENTIAL"
    COMMERCIAL = "COMMERCIAL"
    TRANSIT = "TRANSIT"
    PUBLIC_SPACE = "PUBLIC_SPACE"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SyntheticRoadNode(SandboxContract):
    node_id: str
    longitude: float
    latitude: float


class SyntheticRoadEdge(SandboxContract):
    edge_id: str
    from_node: str
    to_node: str
    distance_km: float = Field(gt=0)
    travel_minutes: int = Field(gt=0)
    congestion_level: float = Field(ge=0, le=1)


class SyntheticBin(SandboxContract):
    bin_id: str
    node_id: str
    site_type: SiteType
    site_name: str
    longitude: float
    latitude: float
    capacity_liters: int = Field(gt=0)
    current_load_liters: float = Field(ge=0)
    fill_ratio: float = Field(ge=0)
    hourly_generation_liters: float = Field(gt=0)
    waste_type: str
    priority: int = Field(ge=1, le=5)
    sensitivity: str
    service_window: str
    access_constraint: str
    last_collected_minutes_ago: int = Field(ge=0)
    sensor_confidence: float = Field(ge=0, le=1)
    forecast_hours_to_overflow: float = Field(ge=0)
    risk_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    risk_reasons: tuple[str, ...]


class SyntheticNetworkAnalysis(SandboxContract):
    road_node_count: int
    road_edge_count: int
    bin_count: int
    critical_bin_count: int
    high_risk_bin_count: int
    projected_overflow_4h_count: int
    sensitive_site_high_risk_count: int
    average_fill_ratio: float
    total_capacity_liters: int
    disconnected_node_count: int


class SyntheticNetwork(SandboxContract):
    scenario_id: str
    seed: int
    data_mode: str = "synthetic"
    disclaimer: str
    center_longitude: float
    center_latitude: float
    nodes: tuple[SyntheticRoadNode, ...]
    edges: tuple[SyntheticRoadEdge, ...]
    bins: tuple[SyntheticBin, ...]
    analysis: SyntheticNetworkAnalysis


_SITE_WEIGHTS = (
    (SiteType.SCHOOL, 12),
    (SiteType.HOSPITAL, 8),
    (SiteType.RESIDENTIAL, 46),
    (SiteType.COMMERCIAL, 18),
    (SiteType.TRANSIT, 9),
    (SiteType.PUBLIC_SPACE, 7),
)

_SITE_LABELS = {
    SiteType.SCHOOL: "模拟学校片区",
    SiteType.HOSPITAL: "模拟医院片区",
    SiteType.RESIDENTIAL: "模拟居民片区",
    SiteType.COMMERCIAL: "模拟商业片区",
    SiteType.TRANSIT: "模拟交通站点",
    SiteType.PUBLIC_SPACE: "模拟公共空间",
}


def generate_synthetic_network(
    *,
    center_longitude: float = 114.0913,
    center_latitude: float = 32.147,
    seed: int = 20260922,
    road_node_count: int = 120,
    bin_count: int = 180,
) -> SyntheticNetwork:
    """Build a connected, reproducible network around a map coordinate."""

    if not 64 <= road_node_count <= 225:
        raise ValueError("road_node_count must be between 64 and 225")
    if not 80 <= bin_count <= 400:
        raise ValueError("bin_count must be between 80 and 400")
    if not -180 <= center_longitude <= 180 or not -90 <= center_latitude <= 90:
        raise ValueError("invalid map center")

    rng = random.Random(seed)
    columns = math.ceil(math.sqrt(road_node_count * 1.4))
    rows = math.ceil(road_node_count / columns)
    longitude_span = 0.052
    latitude_span = 0.038
    nodes = _build_nodes(
        rng,
        center_longitude,
        center_latitude,
        road_node_count,
        rows,
        columns,
        longitude_span,
        latitude_span,
    )
    edges = _build_edges(rng, nodes, rows, columns, seed)
    bins = _build_bins(rng, nodes, bin_count)
    analysis = _analyse(nodes, edges, bins)
    return SyntheticNetwork(
        scenario_id=f"sandbox-{seed}-{road_node_count}-{bin_count}",
        seed=seed,
        disclaimer="全部点位、负荷和业务属性均为确定性仿真数据，不代表地图中的真实单位或设施。",
        center_longitude=center_longitude,
        center_latitude=center_latitude,
        nodes=tuple(nodes),
        edges=tuple(edges),
        bins=tuple(bins),
        analysis=analysis,
    )


def _build_nodes(
    rng: random.Random,
    center_longitude: float,
    center_latitude: float,
    count: int,
    rows: int,
    columns: int,
    longitude_span: float,
    latitude_span: float,
) -> list[SyntheticRoadNode]:
    nodes = []
    for index in range(count):
        row, column = divmod(index, columns)
        longitude = center_longitude - longitude_span / 2 + longitude_span * column / max(columns - 1, 1)
        latitude = center_latitude + latitude_span / 2 - latitude_span * row / max(rows - 1, 1)
        nodes.append(SyntheticRoadNode(
            node_id=f"SN-{index + 1:03d}",
            longitude=round(longitude + rng.uniform(-0.00055, 0.00055), 6),
            latitude=round(latitude + rng.uniform(-0.00045, 0.00045), 6),
        ))
    return nodes


def _build_edges(
    rng: random.Random,
    nodes: list[SyntheticRoadNode],
    rows: int,
    columns: int,
    seed: int,
) -> list[SyntheticRoadEdge]:
    del rows
    edges = []
    node_by_index = {index: node for index, node in enumerate(nodes)}

    def add_edge(first_index: int, second_index: int) -> None:
        first = node_by_index.get(first_index)
        second = node_by_index.get(second_index)
        if first is None or second is None:
            return
        distance = _distance_km(first, second)
        congestion = round(rng.uniform(0.08, 0.92), 2)
        travel_minutes = max(1, round(distance / (28 - congestion * 17) * 60))
        edges.append(SyntheticRoadEdge(
            edge_id=f"SE-{len(edges) + 1:03d}",
            from_node=first.node_id,
            to_node=second.node_id,
            distance_km=round(distance, 3),
            travel_minutes=travel_minutes,
            congestion_level=congestion,
        ))

    for index in range(len(nodes)):
        row, column = divmod(index, columns)
        if column + 1 < columns:
            add_edge(index, index + 1)
        add_edge(index, index + columns)
        if (row + column + seed) % 4 == 0:
            add_edge(index, index + columns + 1)
    return edges


def _build_bins(
    rng: random.Random,
    nodes: list[SyntheticRoadNode],
    count: int,
) -> list[SyntheticBin]:
    site_types = [item[0] for item in _SITE_WEIGHTS]
    weights = [item[1] for item in _SITE_WEIGHTS]
    site_counts = {site_type: 0 for site_type in site_types}
    bins = []
    for index in range(count):
        site_type = rng.choices(site_types, weights=weights, k=1)[0]
        site_counts[site_type] += 1
        node = nodes[(index * 37 + rng.randrange(len(nodes))) % len(nodes)]
        profile = _site_profile(site_type)
        capacity = rng.choice(profile["capacities"])
        fill_ratio = min(1.18, rng.uniform(*profile["fill_range"]))
        if index % 17 == 0:
            fill_ratio = rng.uniform(0.91, 1.12)
        generation = rng.uniform(*profile["generation_range"])
        confidence = rng.uniform(0.68, 0.99)
        hours_to_overflow = max(0.0, (capacity * max(0, 1 - fill_ratio)) / generation)
        risk_score, risk_level, reasons = _risk(
            site_type,
            fill_ratio,
            hours_to_overflow,
            confidence,
            profile["access_constraint"],
        )
        bins.append(SyntheticBin(
            bin_id=f"SB-{index + 1:03d}",
            node_id=node.node_id,
            site_type=site_type,
            site_name=f"{_SITE_LABELS[site_type]} {site_counts[site_type]:02d}",
            longitude=round(node.longitude + rng.uniform(-0.00065, 0.00065), 6),
            latitude=round(node.latitude + rng.uniform(-0.00055, 0.00055), 6),
            capacity_liters=capacity,
            current_load_liters=round(capacity * fill_ratio, 1),
            fill_ratio=round(fill_ratio, 3),
            hourly_generation_liters=round(generation, 1),
            waste_type=profile["waste_type"],
            priority=profile["priority"],
            sensitivity=profile["sensitivity"],
            service_window=profile["service_window"],
            access_constraint=profile["access_constraint"],
            last_collected_minutes_ago=rng.randint(45, 720),
            sensor_confidence=round(confidence, 2),
            forecast_hours_to_overflow=round(hours_to_overflow, 1),
            risk_score=risk_score,
            risk_level=risk_level,
            risk_reasons=reasons,
        ))
    return bins


def _site_profile(site_type: SiteType) -> dict:
    profiles = {
        SiteType.SCHOOL: ((120, 240, 660), (0.35, 0.95), (12, 32), "混合垃圾", 4, "HIGH", "06:00-07:30 / 18:00-20:00", "上放学时段限行"),
        SiteType.HOSPITAL: ((240, 660), (0.45, 1.02), (18, 42), "生活垃圾", 5, "CRITICAL", "全天候", "需避让急救通道"),
        SiteType.RESIDENTIAL: ((240, 660), (0.28, 0.98), (10, 30), "生活垃圾", 3, "NORMAL", "05:30-09:00 / 19:00-23:00", "夜间噪声限制"),
        SiteType.COMMERCIAL: ((240, 660), (0.32, 1.05), (16, 38), "混合垃圾", 3, "NORMAL", "22:00-07:00", "营业时段拥堵"),
        SiteType.TRANSIT: ((120, 240), (0.38, 1.08), (14, 36), "混合垃圾", 4, "HIGH", "01:00-05:00", "客流高峰限行"),
        SiteType.PUBLIC_SPACE: ((120, 240), (0.2, 0.9), (8, 24), "混合垃圾", 2, "NORMAL", "04:00-08:00", "步行区域限速"),
    }
    capacities, fill_range, generation_range, waste_type, priority, sensitivity, window, access = profiles[site_type]
    return {
        "capacities": capacities,
        "fill_range": fill_range,
        "generation_range": generation_range,
        "waste_type": waste_type,
        "priority": priority,
        "sensitivity": sensitivity,
        "service_window": window,
        "access_constraint": access,
    }


def _risk(
    site_type: SiteType,
    fill_ratio: float,
    hours_to_overflow: float,
    confidence: float,
    access_constraint: str,
) -> tuple[float, RiskLevel, tuple[str, ...]]:
    sensitivity_points = {
        SiteType.HOSPITAL: 16,
        SiteType.SCHOOL: 12,
        SiteType.TRANSIT: 9,
        SiteType.RESIDENTIAL: 6,
        SiteType.COMMERCIAL: 5,
        SiteType.PUBLIC_SPACE: 3,
    }[site_type]
    score = min(fill_ratio, 1.0) * 55 + max(0, 4 - hours_to_overflow) / 4 * 22
    score += sensitivity_points + (5 if "限" in access_constraint else 0)
    score += max(0, 0.8 - confidence) * 15
    score = round(min(100, score), 1)
    level = RiskLevel.CRITICAL if score >= 85 else RiskLevel.HIGH if score >= 70 else RiskLevel.MEDIUM if score >= 45 else RiskLevel.LOW
    reasons = []
    if fill_ratio >= 1:
        reasons.append("已达到或超过标称容量")
    elif fill_ratio >= 0.8:
        reasons.append("当前装载率较高")
    if hours_to_overflow <= 4:
        reasons.append("预计四小时内满溢")
    if site_type in {SiteType.HOSPITAL, SiteType.SCHOOL, SiteType.TRANSIT}:
        reasons.append("位于敏感或高客流模拟场所")
    if confidence < 0.8:
        reasons.append("传感数据可信度偏低，需复核")
    if not reasons:
        reasons.append("当前风险可控")
    return score, level, tuple(reasons)


def _analyse(
    nodes: list[SyntheticRoadNode],
    edges: list[SyntheticRoadEdge],
    bins: list[SyntheticBin],
) -> SyntheticNetworkAnalysis:
    high_risk = [item for item in bins if item.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}]
    sensitive_types = {SiteType.HOSPITAL, SiteType.SCHOOL, SiteType.TRANSIT}
    return SyntheticNetworkAnalysis(
        road_node_count=len(nodes),
        road_edge_count=len(edges),
        bin_count=len(bins),
        critical_bin_count=sum(item.risk_level is RiskLevel.CRITICAL for item in bins),
        high_risk_bin_count=len(high_risk),
        projected_overflow_4h_count=sum(item.forecast_hours_to_overflow <= 4 for item in bins),
        sensitive_site_high_risk_count=sum(item.site_type in sensitive_types for item in high_risk),
        average_fill_ratio=round(sum(item.fill_ratio for item in bins) / len(bins), 3),
        total_capacity_liters=sum(item.capacity_liters for item in bins),
        disconnected_node_count=0,
    )


def _distance_km(first: SyntheticRoadNode, second: SyntheticRoadNode) -> float:
    latitude_scale = 111.0
    longitude_scale = 111.0 * math.cos(math.radians((first.latitude + second.latitude) / 2))
    return math.hypot(
        (first.longitude - second.longitude) * longitude_scale,
        (first.latitude - second.latitude) * latitude_scale,
    )
