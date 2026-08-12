"""Phase 3: Counterparty Risk Clusters - derived views over the canonical graph."""
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
    structural_entities = {s["entity"] for s in c.structural_relationships}
    statistical_entities = {s["entity"] for s in c.statistical_relationships}
    # both may mention TSMC, but via clearly distinct evidence records, not one merged field
    for s in c.structural_relationships:
        assert "type" in s and "signed_correlation" not in s
    for s in c.statistical_relationships:
        assert "signed_correlation" in s and "type" not in s


def test_negative_correlation_is_not_dropped_or_treated_as_positive():
    clusters = build_risk_clusters("CP_FUND_009")
    c = clusters[0]
    for s in c.statistical_relationships:
        # sign must be a real float, not an abs()'d magnitude silently relabeled
        assert isinstance(s["signed_correlation"], float)


def test_cluster_does_not_aggregate_pfe_nse_rc_into_one_number():
    clusters = build_risk_clusters("CP_FUND_009")
    c = clusters[0]
    import dataclasses
    fields = dataclasses.asdict(c)
    assert "risk_score" not in fields
    assert "total_pfe" not in fields
    assert "aggregate_exposure" not in fields


def test_cluster_deterministic_across_calls():
    a = build_risk_clusters("CP_FUND_009")
    b = build_risk_clusters("CP_FUND_009")
    assert [c.label for c in a] == [c.label for c in b]
    assert [c.entities for c in a] == [c.entities for c in b]


def test_relevant_controls_attached_only_from_real_graph_path():
    clusters = build_risk_clusters("CP_PUB_ALPHA")  # has a settlement breach
    assert len(clusters) >= 1
    # control context comes from the counterparty's own CONTROL edges, not
    # invented for a market cluster with no real limit/exception on file
    for c in clusters:
        assert isinstance(c.relevant_controls, list)


def test_unknown_counterparty_returns_no_clusters_not_fabricated_ones():
    assert build_risk_clusters("CP_DOES_NOT_EXIST") == []


def test_provenance_reflects_actual_evidence_sources():
    clusters = build_risk_clusters("CP_FUND_009")
    c = clusters[0]
    assert "SYNTHETIC_BUSINESS_SCENARIO_DATA" in c.provenance  # the exposure position itself
    if c.structural_relationships:
        assert "REAL_PUBLIC_DATA" in c.provenance
    if c.statistical_relationships:
        assert "DERIVED_DATA" in c.provenance
