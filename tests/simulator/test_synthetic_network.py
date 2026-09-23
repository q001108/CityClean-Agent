from cityclean_agent.simulator.synthetic_network import (
    RiskLevel,
    SiteType,
    generate_synthetic_network,
)


def test_network_is_large_connected_and_deterministic() -> None:
    first = generate_synthetic_network(seed=42, road_node_count=120, bin_count=180)
    second = generate_synthetic_network(seed=42, road_node_count=120, bin_count=180)

    assert first == second
    assert len(first.nodes) == 120
    assert len(first.edges) >= 200
    assert len(first.bins) == 180
    assert first.analysis.disconnected_node_count == 0
    assert first.data_mode == "synthetic"


def test_network_contains_analysis_fields_and_sensitive_sites() -> None:
    network = generate_synthetic_network(seed=7)

    assert {SiteType.SCHOOL, SiteType.HOSPITAL, SiteType.RESIDENTIAL} <= {
        item.site_type for item in network.bins
    }
    assert any(
        item.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
        for item in network.bins
    )
    assert network.analysis.projected_overflow_4h_count > 0
    assert all(item.risk_reasons for item in network.bins)
    assert "仿真数据" in network.disclaimer
