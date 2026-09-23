"""Deterministic directed road-network queries for the domain layer."""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from typing import Iterable, Mapping

from cityclean_agent.domain.enums import RoadStatus
from cityclean_agent.domain.models import Road


@dataclass(frozen=True, slots=True)
class RoadPath:
    """A shortest open-road path between two nodes."""

    road_ids: tuple[str, ...]
    total_distance: float
    total_travel_time: int


@dataclass(frozen=True, slots=True)
class GeoCoordinate:
    """A verified WGS84-style longitude/latitude pair for one city node."""

    longitude: float
    latitude: float

    def __post_init__(self) -> None:
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")


class RoadNetwork:
    """A directed network where only open roads can be traversed."""

    def __init__(
        self,
        roads: Iterable[Road] = (),
        *,
        node_coordinates: Mapping[str, GeoCoordinate] | None = None,
    ) -> None:
        self._roads: dict[str, Road] = {}
        self._outgoing: dict[str, list[Road]] = {}
        self._node_coordinates = dict(node_coordinates or {})
        if any(not node_id for node_id in self._node_coordinates):
            raise ValueError("coordinate node IDs must not be empty")
        for road in roads:
            self.add_road(road)

    @property
    def roads(self) -> tuple[Road, ...]:
        """Return all roads ordered by their stable identifiers."""

        return tuple(self._roads[road_id] for road_id in sorted(self._roads))

    @property
    def node_ids(self) -> frozenset[str]:
        """Return all nodes referenced by the network."""

        return frozenset(
            node_id
            for road in self._roads.values()
            for node_id in (road.from_node, road.to_node)
        )

    @property
    def node_coordinates(self) -> dict[str, GeoCoordinate]:
        """Return an isolated copy of known real-world node coordinates."""

        return dict(self._node_coordinates)

    def get_node_coordinate(self, node_id: str) -> GeoCoordinate | None:
        """Return a node coordinate when the state source supplied one."""

        return self._node_coordinates.get(node_id)

    def add_road(self, road: Road) -> None:
        """Add one directed road, rejecting duplicate identifiers."""

        if road.id in self._roads:
            raise ValueError(f"duplicate road ID: {road.id}")
        self._roads[road.id] = road
        self._outgoing.setdefault(road.from_node, []).append(road)
        self._outgoing[road.from_node].sort(key=lambda item: item.id)

    def get_road(self, road_id: str) -> Road:
        """Return a road by identifier."""

        try:
            return self._roads[road_id]
        except KeyError as exc:
            raise KeyError(f"unknown road ID: {road_id}") from exc

    def set_road_status(self, road_id: str, status: RoadStatus) -> None:
        """Change whether a road may be entered on a future simulation tick."""

        self.get_road(road_id).status = status

    def shortest_path(self, from_node: str, to_node: str) -> RoadPath | None:
        """Return the fastest open-road path, or ``None`` when unreachable.

        Ties use total distance and then lexicographic road IDs so repeated calls
        over identical state produce the same path.
        """

        if from_node == to_node:
            return RoadPath(road_ids=(), total_distance=0.0, total_travel_time=0)

        start_cost = (0, 0.0, ())
        best_costs: dict[str, tuple[int, float, tuple[str, ...]]] = {
            from_node: start_cost
        }
        queue: list[tuple[int, float, tuple[str, ...], str]] = [
            (*start_cost, from_node)
        ]

        while queue:
            travel_time, distance, road_ids, node_id = heappop(queue)
            if (travel_time, distance, road_ids) != best_costs.get(node_id):
                continue
            if node_id == to_node:
                return RoadPath(road_ids, distance, travel_time)

            for road in self._outgoing.get(node_id, []):
                if road.status is RoadStatus.CLOSED:
                    continue
                candidate = (
                    travel_time + road.travel_time,
                    distance + road.distance,
                    road_ids + (road.id,),
                )
                if candidate < best_costs.get(road.to_node, (float("inf"), float("inf"), ())):
                    best_costs[road.to_node] = candidate
                    heappush(queue, (*candidate, road.to_node))

        return None

    def is_reachable(self, from_node: str, to_node: str) -> bool:
        """Return whether an open-road path currently exists."""

        return self.shortest_path(from_node, to_node) is not None
