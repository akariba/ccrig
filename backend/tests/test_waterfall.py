"""Composite relatedness score waterfall - exact reconciliation.

The waterfall is a direct decomposition of an already-linear formula
(renormalized weighted average), not a SHAP/attribution estimate. These
tests assert the decomposition is exact, not merely plausible.
"""
from app.core import scoring


def test_waterfall_contributions_sum_to_score():
    for a, b in [("TSM", "NVDA"), ("TSM", "ASML"), ("NVDA", "AMD")]:
        result = scoring.composite_score(scoring.feature_vector(a, b))
        if result["score"] is None:
            continue
        total = sum(entry["contribution"] for entry in result["waterfall"])
        assert abs(total - result["score"]) < 1e-3, (a, b, total, result["score"])


def test_waterfall_contribution_equals_value_times_renormalized_weight():
    result = scoring.composite_score(scoring.feature_vector("TSM", "NVDA"))
    assert result["score"] is not None
    for entry in result["waterfall"]:
        expected = round(result["component_values"][entry["component"]] * result["used_weights"][entry["component"]], 4)
        assert abs(entry["contribution"] - expected) < 1e-3


def test_missing_components_are_excluded_not_zero():
    result = scoring.composite_score(scoring.feature_vector("TSM", "NVDA"))
    assert result["score"] is not None
    waterfall_components = {e["component"] for e in result["waterfall"]}
    excluded_components = {e["component"] for e in result["excluded_components"]}
    # every component is either scored or explicitly excluded, never both
    assert waterfall_components.isdisjoint(excluded_components)
    assert waterfall_components | excluded_components == set(result["component_values"].keys())
    # a component missing from the pair is absent from the sum entirely -
    # it does not silently contribute 0 while still being weighted
    for excluded in result["excluded_components"]:
        assert excluded["component"] not in result["used_weights"]


def test_waterfall_sorted_by_contribution_descending():
    result = scoring.composite_score(scoring.feature_vector("TSM", "NVDA"))
    contributions = [entry["contribution"] for entry in result["waterfall"]]
    assert contributions == sorted(contributions, reverse=True)


def test_no_score_case_has_no_waterfall_key_crash():
    # a pair where nothing is available should not raise - composite_score
    # returns the short-circuit dict without a waterfall key, and callers
    # (API layer) must treat that as "no score", not fabricate one.
    result = scoring.composite_score({k: None for k in [
        "sector_similarity", "geography_similarity", "semantic_similarity",
        "news_theme_similarity", "supply_chain_forward", "supply_chain_reverse",
        "ownership", "market_positive", "market_negative",
    ]})
    assert result["score"] is None
    assert "waterfall" not in result
