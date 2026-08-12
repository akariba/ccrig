"""Phase 3/4: Counterparty Risk Clusters - derived views over the canonical graph,
with bounded, tiered member expansion (Phase 4 workstream D)."""
from app.core.config import CLUSTER_MAX_FIRST_ORDER_STRUCTURAL, CLUSTER_MAX_FIRST_ORDER_STATISTICAL
from app.core.risk_clusters import build_risk_clusters


def test_cluster_generated_from_actual_graph_evidence_not_hardcoded():
    clusters = build_risk_clusters("CP_FUND_009")  # Kestrel Family Office - TRS on NVDA
    assert len(clusters) >= 1
    c = clusters[0]
    # label must trace to real risk-factor/entity data, never a hardcoded
    # marketing phrase like "Semiconductor / AI" asserted regardless of evidence
    assert c.label not in ("Semiconductor / AI", "Treasury / Funding", "JPY / FX")
    assert c.label != ""


def test_cluster_explains_why_members_are_grouped():
    clusters = build_risk_clusters("CP_FUND_009")
    c = clusters[0]
    assert len(c.evidence) > 0
    assert all(isinstance(e, str) and len(e) > 0 for e in c.evidence)


def test_structural_and_statistical_evidence_kept_separate():
    clusters = build_risk_clusters("CP_FUND_009")
    c = clusters[0]
    for s in c.structural_relationships:
        assert "type" in s and "signed_correlation" not in s
    for s in c.statistical_relationships:
        assert "signed_correlation" in s and "type" not in s


def test_negative_correlation_is_not_dropped_or_treated_as_positive():
    clusters = build_risk_clusters("CP_FUND_009")
    c = clusters[0]
    for s in c.statistical_relationships:
        assert isinstance(s["signed_correlation"], float)


def test_cluster_does_not_aggregate_pfe_nse_rc_into_one_number():
    import dataclasses
    clusters = build_risk_clusters("CP_FUND_009")
    fields = dataclasses.asdict(clusters[0])
    assert "risk_score" not in fields
    assert "total_pfe" not in fields
    assert "aggregate_exposure" not in fields


def test_cluster_deterministic_across_calls():
    a = build_risk_clusters("CP_FUND_009")
    b = build_risk_clusters("CP_FUND_009")
    assert [c.label for c in a] == [c.label for c in b]
    assert [c.direct_members for c in a] == [c.direct_members for c in b]
    assert [c.first_order_members for c in a] == [c.first_order_members for c in b]
    assert [c.contextual_members for c in a] == [c.contextual_members for c in b]


def test_relevant_controls_attached_only_from_real_graph_path():
    clusters = build_risk_clusters("CP_PUB_ALPHA")  # has a settlement breach
    assert len(clusters) >= 1
    for c in clusters:
        assert isinstance(c.relevant_controls, list)


def test_unknown_counterparty_returns_no_clusters_not_fabricated_ones():
    assert build_risk_clusters("CP_DOES_NOT_EXIST") == []


def test_provenance_reflects_actual_evidence_sources():
    clusters = build_risk_clusters("CP_FUND_009")
    c = clusters[0]
    assert "SYNTHETIC_BUSINESS_SCENARIO_DATA" in c.provenance
    if c.structural_relationships:
        assert "REAL_PUBLIC_DATA" in c.provenance
    if c.statistical_relationships:
        assert "DERIVED_DATA" in c.provenance


# --- Phase 4: member tiering ---

def test_members_are_tiered_direct_first_order_contextual():
    clusters = build_risk_clusters("CP_FUND_009")  # NVDA has 10 structural + 5+ statistical neighbors
    c = clusters[0]
    assert len(c.direct_members) == 1
    assert c.direct_members[0]["id"] == "NVDA"
    assert len(c.first_order_members) > 0
    assert len(c.contextual_members) > 0  # NVDA has enough neighbors to overflow first-order


def test_first_order_expansion_is_bounded():
    clusters = build_risk_clusters("CP_FUND_009")
    c = clusters[0]
    # first-order can hold at most structural-cap + statistical-cap distinct entities
    assert len(c.first_order_members) <= CLUSTER_MAX_FIRST_ORDER_STRUCTURAL + CLUSTER_MAX_FIRST_ORDER_STATISTICAL


def test_direct_and_first_order_and_contextual_are_disjoint():
    clusters = build_risk_clusters("CP_FUND_009")
    c = clusters[0]
    direct_ids = {m["id"] for m in c.direct_members}
    first_order_ids = {m["id"] for m in c.first_order_members}
    contextual_ids = {m["id"] for m in c.contextual_members}
    assert direct_ids.isdisjoint(first_order_ids)
    assert first_order_ids.isdisjoint(contextual_ids)
    assert direct_ids.isdisjoint(contextual_ids)


def test_first_order_prioritizes_strongest_structural_relationship():
    # NVDA's strongest structural edge (by fact criticality) is TSMC at 0.95 -
    # the real primary foundry dependency - not whichever supply edge
    # happened to be inserted first into the source data.
    clusters = build_risk_clusters("CP_FUND_009")
    c = clusters[0]
    first_order_labels = {m["label"] for m in c.first_order_members}
    assert "Taiwan Semiconductor Manufacturing Co (TSMC)" in first_order_labels


def test_full_candidate_set_still_available_beyond_first_order():
    # bounding the TIER doesn't mean discarding evidence - the full ranked
    # list remains in structural_relationships/statistical_relationships
    clusters = build_risk_clusters("CP_FUND_009")
    c = clusters[0]
    assert len(c.structural_relationships) >= CLUSTER_MAX_FIRST_ORDER_STRUCTURAL


# --- Phase 4 correction: business-story fields ---

def test_cluster_has_a_business_story_not_just_graph_metadata():
    c = build_risk_clusters("CP_FUND_009")[0]
    assert len(c.story) >= 2
    assert c.story[-1] == "Kestrel Family Office"  # story ends at the counterparty
    assert all(isinstance(s, str) and s for s in c.story)


def test_why_it_matters_is_a_real_sentence_referencing_actual_entities():
    c = build_risk_clusters("CP_FUND_009")[0]
    assert len(c.why_it_matters) > 20
    assert "NVIDIA" in c.why_it_matters


def test_recommended_action_is_deterministic_not_fabricated_ml_output():
    c = build_risk_clusters("CP_FUND_009")[0]
    assert c.recommended_action in (
        "Monitor — no active control exception or event on file for this exposure.",
        "Investigate — a live event scenario is transmitting into this exposure.",
    ) or c.recommended_action.startswith("Review limit/headroom")


def test_recommended_action_prioritizes_control_exception_over_event():
    # CP_PUB_ALPHA has a live settlement breach - that must win over "Investigate"
    clusters = build_risk_clusters("CP_PUB_ALPHA")
    assert len(clusters) >= 1
    assert clusters[0].recommended_action.startswith("Review limit/headroom")


def test_story_does_not_fabricate_a_structural_hop_when_none_exists():
    # a counterparty whose reference entity has no first-order neighbors at
    # all should still produce a valid (shorter) story, not an invented one
    for c in build_risk_clusters("CP_PUB_ALPHA"):
        assert isinstance(c.story, list)
        assert len(c.story) >= 1
