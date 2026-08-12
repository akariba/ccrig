"""Phase 4 workstream C: central Metric Definition Registry."""
from app.core.metric_definitions import get_metric_definition, list_metric_definitions

REQUIRED_IDS = {
    "MARKET_CORRELATION", "COMPOSITE_RELATEDNESS", "RELATIONSHIP_COMPONENT_CONTRIBUTION",
    "PPR_RELEVANCE", "MODE1_TRAVERSAL", "PFE", "DELTA_PFE", "RC", "STRESS_NSE",
    "LIMIT_UTILISATION", "HEADROOM", "WWR_STATUS", "THEME_VELOCITY", "THEME_COVERAGE",
    "THEME_REACH", "DRIVER_CLASSIFICATION",
}


def test_all_required_metric_ids_present():
    ids = {d.id for d in list_metric_definitions()}
    missing = REQUIRED_IDS - ids
    assert not missing, f"missing definitions: {missing}"


def test_metric_ids_are_unique():
    ids = [d.id for d in list_metric_definitions()]
    assert len(ids) == len(set(ids))


def test_every_definition_has_required_fields():
    for d in list_metric_definitions():
        assert d.id and d.label and d.short_description and d.meaning and d.category


def test_pfe_rc_stress_are_defined_separately_not_conflated():
    pfe = get_metric_definition("PFE")
    rc = get_metric_definition("RC")
    stress = get_metric_definition("STRESS_NSE")
    assert pfe.id != rc.id != stress.id
    assert "RC" not in pfe.meaning.split()  # not casually merged
    assert "stress/NSE" in pfe.what_it_is_not[1] or any("stress" in w.lower() for w in pfe.what_it_is_not)


def test_limit_utilisation_defined_as_matching_metric_over_matching_limit():
    d = get_metric_definition("LIMIT_UTILISATION")
    assert d.formula is not None
    assert "MatchingLimit" in d.formula or "matching" in d.formula.lower()
    assert any("universal exposure ratio" in w or "independent of limit type" in w for w in d.what_it_is_not)


def test_composite_relatedness_explicitly_not_a_probability():
    d = get_metric_definition("COMPOSITE_RELATEDNESS")
    assert "probability" in d.what_it_is_not


def test_ppr_explicitly_not_exposure_or_risk():
    d = get_metric_definition("PPR_RELEVANCE")
    assert "exposure" in d.what_it_is_not
    assert any("risk" in w for w in d.what_it_is_not)


def test_theme_metrics_explicitly_marked_as_discovery_not_risk():
    for metric_id in ["THEME_VELOCITY", "THEME_COVERAGE", "THEME_REACH"]:
        d = get_metric_definition(metric_id)
        assert d.category == "THEME_DISCOVERY"
        assert any("risk" in w.lower() for w in d.what_it_is_not)


def test_waterfall_contribution_reconciliation_documented_and_not_called_shap():
    d = get_metric_definition("RELATIONSHIP_COMPONENT_CONTRIBUTION")
    assert "Composite Relatedness" in d.formula
    assert any("SHAP" in w for w in d.what_it_is_not)


def test_unknown_metric_id_returns_none_not_fabricated_definition():
    assert get_metric_definition("NOT_A_REAL_METRIC") is None


def test_driver_classification_documents_simulation_noise_evidence_requirement():
    d = get_metric_definition("DRIVER_CLASSIFICATION")
    assert "simulation noise" in d.meaning.lower() or "confirmation flag" in d.meaning.lower()
