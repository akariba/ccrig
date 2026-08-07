"""Targeted regression tests for the 2026-08-06 bug review.

Covers: (1) counterparty event ranking must not be a raw exposure_pct sum,
(2) counterparties must never appear as structural PPR/Mode-1 nodes,
(3) Theme Radar discovery pipeline, (4) entity extraction alias matching,
(5) backtest scenario replay labelling, (6) ownership N/A handling.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.data import STORE
from app.core import event_parser, themes as theme_mod, backtest, scoring


TAIWAN_TEXT = "A major earthquake in Taiwan disrupts TSMC production, affecting NVIDIA, AMD and Apple."
CHINA_EXPORT_TEXT = ("China announces restrictions affecting advanced semiconductor equipment "
                      "exports to Taiwan-linked manufacturers.")


# --------------------------------------------------------------------------
# Issue 1 (verified already-correct): counterparty relevance must be
# exposure-weighted by event relevance, never a raw sum of exposure_pct.
# --------------------------------------------------------------------------
def test_counterparty_relevance_not_raw_exposure_sum():
    result = event_parser.parse_event(TAIWAN_TEXT)
    scores = {c["counterparty"]: c["exposure_weighted_relevance"] for c in result["relevant_counterparties"]}
    assert scores, "expected at least one relevant counterparty for the Taiwan scenario"
    # a raw sum of ~100%-summing exposure_pct would push many scores near 1.0;
    # the relevance-weighted formula must spread scores out well below that.
    assert all(s <= 1.0 for s in scores.values())
    assert max(scores.values()) < 0.95
    assert len(set(round(s, 2) for s in scores.values())) > 1, "scores must not all collapse to ~portfolio breadth"


# --------------------------------------------------------------------------
# Issue 2 (verified already-correct): counterparties must never surface as
# structural Mode 1 / Mode 2 (PPR) results - only via the explicit Layer C
# exposure join.
# --------------------------------------------------------------------------
def test_counterparties_excluded_from_structural_ppr():
    result = event_parser.parse_event(TAIWAN_TEXT)
    m1_ids = {r["entity_id"] for r in result["mode1_bounded_traversal"]["results"]}
    m2_ids = {r["entity_id"] for r in result["mode2_personalized_pagerank"]["results"]}
    cp_ids = set(STORE.counterparty_ids)
    assert not (m1_ids & cp_ids), "Mode 1 must never surface a counterparty as a structural result"
    assert not (m2_ids & cp_ids), "Mode 2 PPR must never surface a counterparty as a structural result"
    assert "CP_ANCHOR" not in m1_ids and "CP_ANCHOR" not in m2_ids


# --------------------------------------------------------------------------
# Issue 3: Theme Radar must expose a real discovery pipeline distinct from
# the curated taxonomy, with both kinds clearly tagged.
# --------------------------------------------------------------------------
def test_theme_radar_has_discovery_pipeline_distinct_from_curated():
    curated = theme_mod.theme_stats()
    assert len(curated) == 47
    assert all(t["kind"] == "CURATED_THEME" for t in curated)

    discovered = theme_mod.discover_themes()
    assert isinstance(discovered, list)
    for t in discovered:
        assert t["kind"] == "DISCOVERED_THEME"
        assert t["theme_id"] not in STORE.keywords_by_id, "a discovered theme id must not collide with a curated one"

    combined = theme_mod.all_themes()
    assert len(combined) == len(curated) + len(discovered)
    assert {t["kind"] for t in combined} <= {"CURATED_THEME", "DISCOVERED_THEME"}


def test_discovered_theme_not_duplicate_of_curated_synonym():
    # canonicalisation/dedup: nothing discovered should reuse a curated
    # theme's own synonym set as its keyphrase (that would double-count).
    for t in theme_mod.discover_themes():
        assert theme_mod._matches_curated_theme(t["keyphrase_terms"]) is None


# --------------------------------------------------------------------------
# Issue 4: entity extraction must find common-name mentions (TSMC, NVIDIA,
# Apple), not just tickers/ids that happen to already be a bare token.
# --------------------------------------------------------------------------
def test_taiwan_earthquake_entity_extraction():
    entities = event_parser.detect_entities(TAIWAN_TEXT)
    for expected in ("TSM", "NVDA", "AMD", "AAPL"):
        assert expected in entities, f"expected {expected} to be detected in: {TAIWAN_TEXT}"


def test_china_export_restriction_extraction():
    result = event_parser.parse_event(CHINA_EXPORT_TEXT)
    assert "Taiwan" in result["detected_countries"]
    theme_ids = {t["id"] for t in result["detected_themes"]}
    assert "SEMICONDUCTORS" in theme_ids
    assert "TAIWAN" in theme_ids


def test_deterministic_fallback_still_works_offline():
    from app.ai.provider import DeterministicProvider
    assert DeterministicProvider().extract_entities(TAIWAN_TEXT) == []
    # detect_entities must still resolve everything via the alias index alone
    entities = event_parser.detect_entities(TAIWAN_TEXT)
    assert {"TSM", "NVDA", "AMD", "AAPL"} <= set(entities)


# --------------------------------------------------------------------------
# Issue 5: the Taiwan scenario must be labelled Scenario Replay / Backtest
# Prototype, and must state the narrative is synthetic while prices are real.
# --------------------------------------------------------------------------
def test_backtest_labelled_as_scenario_replay_not_historical():
    scenarios = {s["id"]: s for s in backtest.list_scenarios()}
    scenario = scenarios["taiwan_earthquake_2026"]
    assert scenario["narrative_type"] == "SYNTHETIC"
    assert scenario["price_data_type"] == "REAL"
    assert "Scenario Replay" in scenario["label"] or "Backtest Prototype" in scenario["label"]

    result = backtest.run_backtest("taiwan_earthquake_2026")
    assert result["news_source"]["is_synthetic"] is True
    assert any("SYNTHETIC" in w and "SCENARIO REPLAY" in w for w in result["warnings"])


# --------------------------------------------------------------------------
# Issue 6: Ownership must show as N/A when the dataset has zero
# PARENT_OF/SUBSIDIARY_OF edges, and must never distort normalisation.
# --------------------------------------------------------------------------
def test_ownership_flagged_na_when_no_data():
    assert STORE.has_ownership_data is False
    comp = scoring.composite_score(scoring.feature_vector("TSM", "NVDA"))
    assert comp["ownership_status"] == "N/A (no ownership data in dataset)"
    assert "ownership" in comp["missing_components"]
    # renormalisation must exclude ownership's weight entirely, not just zero it
    assert "ownership" not in comp["used_weights"]
    assert abs(sum(comp["used_weights"].values()) - 1.0) < 1e-3  # rounded to 4dp in composite_score
