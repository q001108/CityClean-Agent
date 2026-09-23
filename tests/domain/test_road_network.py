import pytest

from cityclean_agent.domain.enums import RoadStatus
from cityclean_agent.domain.models import Road
from cityclean_agent.domain.road_network import GeoCoordinate, RoadNetwork


def make_network() -> RoadNetwork:
    return RoadNetwork(
        [
            Road("R1", "A", "B", distance=10, travel_time=5),
            Road("R2", "B", "C", distance=10, travel_time=5),
            Road("R3", "A", "C", distance=50, travel_time=20),
            Road("R4", "A", "D", distance=8, travel_time=5),
            Road("R5", "D", "C", distance=8, travel_time=5),
        ]
    )


def test_shortest_path_uses_open_roads_and_fastest_travel_time() -> None:
    path = make_network().shortest_path("A", "C")

    assert path is not None
    assert path.road_ids == ("R4", "R5")
    assert path.total_travel_time == 10
    assert path.total_distance == 16


def test_closed_road_is_not_used_and_network_can_reroute() -> None:
    network = make_network()
    network.set_road_status("R4", RoadStatus.CLOSED)

    path = network.shortest_path("A", "C")

    assert path is not None
    assert path.road_ids == ("R1", "R2")


def test_unreachable_destination_returns_none() -> None:
    network = make_network()
    network.set_road_status("R1", RoadStatus.CLOSED)
    network.set_road_status("R3", RoadStatus.CLOSED)
    network.set_road_status("R4", RoadStatus.CLOSED)

    assert network.shortest_path("A", "C") is None
    assert not network.is_reachable("A", "C")


def test_shortest_path_is_deterministic_for_equal_cost_options() -> None:
    network = RoadNetwork(
        [
            Road("R2", "A", "B", distance=1, travel_time=1),
            Road("R3", "B", "C", distance=1, travel_time=1),
            Road("R1", "A", "D", distance=1, travel_time=1),
            Road("R4", "D", "C", distance=1, travel_time=1),
        ]
    )

    assert network.shortest_path("A", "C").road_ids == ("R1", "R4")


def test_duplicate_road_ids_are_rejected() -> None:
    road = Road("R1", "A", "B", distance=1, travel_time=1)

    with pytest.raises(ValueError, match="duplicate"):
        RoadNetwork([road, road])


def test_node_coordinates_are_validated_and_returned_as_a_copy() -> None:
    network = RoadNetwork(
        [Road("R1", "A", "B", distance=1, travel_time=1)],
        node_coordinates={"A": GeoCoordinate(114.0913, 32.147)},
    )

    coordinates = network.node_coordinates
    coordinates["B"] = GeoCoordinate(114.1, 32.15)

    assert network.get_node_coordinate("A") == GeoCoordinate(114.0913, 32.147)
    assert network.get_node_coordinate("B") is None
    with pytest.raises(ValueError, match="longitude"):
        GeoCoordinate(181, 32.147)
