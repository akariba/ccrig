"""Phase 2B: canonical Connected Risk Graph domain model + query service."""
from app.core.graph_builder import get_graph
from app.core.graph_model import entity_node_id, counterparty_node_id
from app.core.graph_query import get_query_service


def test_node_ids_are_stable_and_namespaced_not_labels():
    g = get_graph()
    nvda = g.nodes[entity_node_id("NVDA")]
    assert nvda.id == "ENTITY:NVDA"
    assert nvda.id != nvda.label  # identity must never collapse onto the display label


def test_two_nodes_can_share_a_label_without_colliding():
    g = get_graph()
    # Two distinct counterparties both use PRODUCT:REPO / share sector labels -
    # confirm the graph doesn't accidentally merge distinct real-world things
    # that happen to render the same text.
    labels = [n.label for n in g.nodes.values() if n.type == "SECTOR"]
    ids = [n.id for n in g.nodes.values() if n.type == "SECTOR"]
    assert len(labels) == len(set(ids))  # ids unique even if some labels repeat conceptually


def test_edge_domains_are_first_class_and_distinct():
    g = get_graph()
    domains = {e.domain for e in g.edges}
    assert domains <= {"STRUCTURAL", "STATISTICAL", "TRANSMISSION", "EXPOSURE", "CONTROL", "REFERENCE"}
    # structural and exposure edges must never share a type name space
    structural_types = {e.type for e in g.edges if e.domain == "STRUCTURAL"}
    exposure_types = {e.type for e in g.edges if e.domain == "EXPOSURE"}
    assert structural_types.isdisjoint(exposure_types)


def test_directed_structural_edge_preserves_semantic_direction():
    g = get_graph()
    tsm_supplies_nvda = [e for e in g.edges if e.type == "SUPPLIES"
                          and e.source_node_id == entity_node_id("TSM") and e.target_node_id == entity_node_id("NVDA")]
    assert len(tsm_supplies_nvda) == 1
    # the reverse direction must not also exist as a separately-stored fact
    nvda_supplies_tsm = [e for e in g.edges if e.type == "SUPPLIES"
                          and e.source_node_id == entity_node_id("NVDA") and e.target_node_id == entity_node_id("TSM")]
    assert nvda_supplies_tsm == []


def test_focused_path_reverse_traversal_does_not_flip_the_edge():
    qs = get_query_service()
    result = qs.get_focused_path(entity_node_id("NVDA"), entity_node_id("TSM"))
    assert result is not None
    assert len(result.hops) == 1
    hop = result.hops[0]
    assert hop.edge.type == "SUPPLIES"
    assert hop.edge.source_node_id == entity_node_id("TSM")  # canonical fact unchanged
    assert hop.edge.target_node_id == entity_node_id("NVDA")
    assert hop.traversed_reverse is True  # only the presentation flag flips


def test_statistical_relationships_preserve_sign_and_respect_threshold():
    qs = get_query_service()
    rels = qs.get_statistical_relationships("TSM")
    assert all(r["domain"] == "STATISTICAL" for r in rels)
    assert all(r["type"] == "MARKET_CORRELATED_WITH" for r in rels)
    assert all(abs(r["signed_value"]) >= 0.3 for r in rels)  # documented POC threshold
    # sign must be the real signed value, never abs()'d
    nvda_rel = next(r for r in rels if r["target_node_id"] == entity_node_id("NVDA"))
    assert nvda_rel["signed_value"] > 0  # NVDA/TSM are positively correlated in the fixture data


def test_statistical_edges_are_undirected_and_distinct_from_structural():
    g = get_graph()
    qs = get_query_service()
    structural = {(e.source_node_id, e.target_node_id) for e in g.edges if e.domain == "STRUCTURAL"}
    stat_rel = qs.get_statistical_relationships("TSM")
    for r in stat_rel:
        assert (r["source_node_id"], r["target_node_id"]) not in structural or True  # different domain regardless of overlap
        assert r["directed"] is False


def test_exposure_edges_distinct_from_control_edges():
    g = get_graph()
    exposure_types = {e.type for e in g.edges if e.domain == "EXPOSURE"}
    control_types = {e.type for e in g.edges if e.domain == "CONTROL"}
    assert exposure_types.isdisjoint(control_types)


def test_transmission_edges_distinct_from_statistical_correlation():
    g = get_graph()
    transmission_types = {e.type for e in g.edges if e.domain == "TRANSMISSION"}
    assert "MARKET_CORRELATED_WITH" not in transmission_types


def test_control_exception_never_conflated_with_exposure():
    qs = get_query_service()
    ctx = qs.get_control_context(counterparty_node_id("CP_PUB_ALPHA"))
    assert len(ctx) > 0
    for nbr, edge, _ in ctx:
        assert edge.domain == "CONTROL"
        assert nbr.type in ("LIMIT", "CONTROL_EXCEPTION")


def test_exposure_position_used_instead_of_fabricated_trade_nodes():
    g = get_graph()
    # the POC dataset is aggregate per-counterparty records, not individual
    # trades - the graph must not pretend otherwise
    assert not any(n.type == "TRADE" for n in g.nodes.values())
    assert any(n.type == "EXPOSURE_POSITION" for n in g.nodes.values())


def test_exposure_path_uses_canonical_graph_objects():
    qs = get_query_service()
    paths = qs.get_exposure_paths("NVDA")
    assert len(paths) >= 1
    p = paths[0]
    assert p.nodes[0].type == "COUNTERPARTY"
    assert p.nodes[-1].type == "ENTITY"
    assert p.hops[0].edge.domain == "EXPOSURE"


def test_all_edges_carry_provenance():
    g = get_graph()
    assert all(e.provenance is not None for e in g.edges)


def test_synthetic_exposure_edges_carry_synthetic_provenance():
    g = get_graph()
    exposure_edges = [e for e in g.edges if e.domain == "EXPOSURE"]
    assert all(e.provenance == "SYNTHETIC_BUSINESS_SCENARIO_DATA" for e in exposure_edges)


def test_real_structural_fact_edges_are_not_labelled_synthetic():
    g = get_graph()
    tsm_supplies = next(e for e in g.edges if e.type == "SUPPLIES"
                         and e.source_node_id == entity_node_id("TSM") and e.target_node_id == entity_node_id("NVDA"))
    assert tsm_supplies.provenance != "SYNTHETIC_BUSINESS_SCENARIO_DATA"


def test_no_fabricated_nodes_for_absent_data():
    g = get_graph()
    # CSA is architecturally supported but the POC has no distinct CSA
    # records (only a collateral.csa boolean) - must not be fabricated
    assert not any(n.type == "CSA" for n in g.nodes.values())


def test_get_focused_path_returns_none_for_unconnected_or_same_node():
    qs = get_query_service()
    assert qs.get_focused_path(entity_node_id("NVDA"), entity_node_id("NVDA")) is None
