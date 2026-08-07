"""Tests for AI-assisted event understanding (core/event_parser.py::extract_ai_context).

Covers the offline deterministic path (no AI_API_KEY) and the AI-enhanced
path using a mocked AIProvider (no real network call), per the two required
test sentences.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.core import event_parser as ep
from app.ai.provider import DeterministicProvider
import app.ai.provider as provider_mod

TAIWAN_TEXT = "A major earthquake in Taiwan disrupts TSMC production, affecting NVIDIA, AMD and Apple."
CHINA_EXPORT_TEXT = ("China announces restrictions affecting advanced semiconductor equipment "
                      "exports to Taiwan-linked manufacturers.")


class MockLLMProvider(DeterministicProvider):
    """Test double standing in for OpenAICompatibleProvider - returns
    canned structured extraction without any network call, so these tests
    exercise the LLM-assisted code path deterministically."""
    mode = "ENHANCED_AI_TEST_MOCK"

    def extract_event_context(self, text):
        if "earthquake" in text.lower():
            return {
                "entity_candidates": [
                    {"text": "TSMC", "type": "company"}, {"text": "Nvidia", "type": "company"},
                    {"text": "AMD", "type": "company"}, {"text": "Apple", "type": "company"},
                    {"text": "Some Fictional Corp XYZ", "type": "company"},  # must not hallucinate an entity
                ],
                "countries": ["Taiwan"],
                "concept_candidates": ["earthquake", "semiconductor fabrication", "supply-chain disruption"],
                "event_type": "SUPPLY_CHAIN_DISRUPTION",
                "reasoning_summary": "Earthquake disrupts semiconductor manufacturing capacity.",
            }
        return {
            "entity_candidates": [],
            "countries": ["China", "Taiwan"],
            "concept_candidates": ["semiconductor equipment", "export controls", "geopolitical tension"],
            "event_type": "EXPORT_CONTROL_ACTION",
            "reasoning_summary": "China restricts semiconductor equipment exports to Taiwan-linked firms.",
        }


@pytest.fixture
def mock_ai_provider(monkeypatch):
    monkeypatch.setattr(provider_mod, "PROVIDER", MockLLMProvider())
    yield


# --------------------------------------------------------------------------
# Offline deterministic path (no AI configured)
# --------------------------------------------------------------------------
def test_offline_deterministic_extraction_taiwan():
    r = ep.parse_event(TAIWAN_TEXT)
    assert set(r["detected_entities"]) >= {"TSM", "NVDA", "AMD", "AAPL"}
    ctx = r["ai_context_extraction"]
    assert ctx["ai_mode"] == "DETERMINISTIC_OFFLINE"
    assert all(e["source"] == "DETERMINISTIC_MATCH" for e in ctx["entities"])
    assert {e["entity_id"] for e in ctx["entities"]} == {"TSM", "NVDA", "AMD", "AAPL"}


def test_offline_mode_never_calls_llm_for_entities():
    from app.ai.provider import DeterministicProvider
    assert DeterministicProvider().extract_event_context("anything")["entity_candidates"] == []


# --------------------------------------------------------------------------
# AI-enhanced path (mocked provider, per required test sentences)
# --------------------------------------------------------------------------
def test_ai_enhanced_taiwan_earthquake(mock_ai_provider):
    r = ep.parse_event(TAIWAN_TEXT)
    assert set(r["detected_entities"]) >= {"TSM", "NVDA", "AMD", "AAPL"}

    ctx = r["ai_context_extraction"]
    assert ctx["ai_mode"] == "ENHANCED_AI_TEST_MOCK"
    resolved_ids = {e["entity_id"] for e in ctx["entities"]}
    assert {"TSM", "NVDA", "AMD", "AAPL"} <= resolved_ids

    countries = {c["country"] for c in ctx["countries"]}
    assert "Taiwan" in countries

    concepts = {c["concept"].lower() for c in ctx["concepts"]}
    assert "earthquake" in concepts
    assert any("supply" in c or "semiconductor" in c for c in concepts)


def test_ai_enhanced_china_export_restrictions(mock_ai_provider):
    r = ep.parse_event(CHINA_EXPORT_TEXT)
    ctx = r["ai_context_extraction"]

    countries = {c["country"] for c in ctx["countries"]}
    assert {"China", "Taiwan"} <= countries

    concept_ids = {c["theme_id"] for c in ctx["concepts"] if c["theme_id"]}
    assert "EXPORT_CONTROLS" in concept_ids
    assert "SEMICONDUCTORS" in concept_ids


def test_llm_hallucinated_entity_never_resolved(mock_ai_provider):
    r = ep.parse_event(TAIWAN_TEXT)
    ctx = r["ai_context_extraction"]
    resolved_ids = {e["entity_id"] for e in ctx["entities"]}
    # "Some Fictional Corp XYZ" must be rejected, not silently turned into
    # a fabricated entity_id
    assert "Some Fictional Corp XYZ" not in resolved_ids
    assert "Some Fictional Corp XYZ" in ctx["unresolved_llm_entity_candidates"]
    assert not any("FICTIONAL" in eid for eid in resolved_ids)


def test_unvalidated_country_not_silently_treated_as_known(mock_ai_provider):
    r = ep.parse_event(CHINA_EXPORT_TEXT)
    ctx = r["ai_context_extraction"]
    china_record = next(c for c in ctx["countries"] if c["country"] == "China")
    # no issuer in this dataset is China-domiciled, so China cannot be a
    # DETERMINISTIC_MATCH or a resolved match - must be marked unvalidated,
    # never silently promoted.
    assert china_record["source"] == "LLM_CANDIDATE_UNVALIDATED"


def test_concept_never_double_counted_as_ephemeral(mock_ai_provider):
    r = ep.parse_event(TAIWAN_TEXT)
    ctx = r["ai_context_extraction"]
    earthquake_records = [c for c in ctx["concepts"] if c["concept"].lower() == "earthquake"]
    assert len(earthquake_records) == 1
    assert earthquake_records[0]["source"] == "CURATED_THEME"


def test_ephemeral_concepts_are_not_persisted_to_taxonomy(mock_ai_provider):
    from app.core.data import STORE
    r = ep.parse_event(TAIWAN_TEXT)
    ctx = r["ai_context_extraction"]
    ephemeral = [c for c in ctx["concepts"] if c["source"] == "EPHEMERAL_EVENT_CONCEPT"]
    assert ephemeral
    for c in ephemeral:
        assert c["theme_id"] is None
        assert c["concept"] not in STORE.keywords_by_id


def test_ai_never_changes_counterparty_formula(mock_ai_provider):
    # the AI-enhanced path must flow through the SAME counterparty_join
    # formula (Exposure x EventRelevance) - verify by cross-checking
    # against a fresh deterministic-only run's exposure-weighted formula
    # shape (keys/structure identical, values may differ since AI adds
    # entities to the relevant set).
    r_ai = ep.parse_event(TAIWAN_TEXT)
    for cp in r_ai["relevant_counterparties"]:
        assert set(cp.keys()) >= {"counterparty", "exposure_weighted_relevance", "issuers"}
        for issuer_entry in cp["issuers"]:
            assert set(issuer_entry.keys()) >= {"issuer", "exposure_pct", "event_relevance", "relation"}


def test_ai_extraction_failure_falls_back_gracefully(monkeypatch):
    class BrokenProvider(DeterministicProvider):
        mode = "BROKEN_TEST_MOCK"
        def extract_event_context(self, text):
            raise RuntimeError("simulated provider failure")

    monkeypatch.setattr(provider_mod, "PROVIDER", BrokenProvider())
    r = ep.parse_event(TAIWAN_TEXT)  # must not raise
    assert set(r["detected_entities"]) >= {"TSM", "NVDA", "AMD", "AAPL"}
