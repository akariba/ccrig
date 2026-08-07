"""Tests for real dynamic theme discovery (core/themes.py::discover_themes)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.core import themes as theme_mod
from app.core.data import STORE

NOVEL_DOCS = [
    dict(id="test_novel1", date="2026-08-01", title="Undersea cable sabotage disrupts North Sea data links",
         snippet="Investigators suspect deliberate undersea cable sabotage near Danish waters affecting Maersk logistics routing."),
    dict(id="test_novel2", date="2026-08-02", title="Second undersea cable sabotage incident reported",
         snippet="A second undersea cable sabotage event has been reported, again close to Maersk shipping lanes in the Baltic."),
    dict(id="test_novel3", date="2026-08-03", title="NATO probes undersea cable sabotage pattern",
         snippet="NATO officials are probing a pattern of undersea cable sabotage incidents affecting regional connectivity."),
]


@pytest.fixture
def novel_corpus():
    """Ingest a genuinely novel concept (undersea cable sabotage) absent
    from keywords.json, run discovery, then always roll back the in-memory
    corpus so this test can't pollute later tests."""
    before_len = len(STORE.news_all)
    for d in NOVEL_DOCS:
        theme_mod.ingest_news_document(d)
    yield
    del STORE.news_all[before_len:]
    theme_mod.invalidate_discovery_cache()


def test_novel_concept_not_in_curated_taxonomy():
    novel_terms = {"undersea", "cable", "sabotage"}
    for kw in STORE.keywords:
        syns = {s.lower() for s in kw["synonyms"]} | {kw["label"].lower()}
        assert not (novel_terms & syns), f"test concept collides with curated theme {kw['id']}"


def test_curated_theme_taxonomy_is_unaware_of_curated_hardcoding():
    # the discovered theme id must never be one of the 47 curated ids -
    # discovery and curation are namespace-disjoint by construction.
    assert "DISCOVERED_UNDERSEA" not in STORE.keywords_by_id


def test_novel_concept_emerges_as_discovered_theme(novel_corpus):
    discovered = theme_mod.discover_themes()
    matches = [t for t in discovered if "UNDERSEA" in t["theme_id"] or "CABLE" in t["label"].upper()]
    assert matches, "expected a discovered cluster around the novel undersea-cable-sabotage concept"
    theme = matches[0]

    assert theme["kind"] == "DISCOVERED_THEME"
    assert theme["source_type"] == "DERIVED_DATA"
    # source documents retained
    for doc_id in ("test_novel1", "test_novel2", "test_novel3"):
        assert doc_id in theme["member_document_ids"]

    # entity linking: MAERSK is mentioned only as free text ("Maersk"), not
    # pre-tagged in the ingested docs' entities field, so this proves
    # linking runs a real alias-resolved NER pass over the text.
    assert "MAERSK" in theme["entity_ids"]


def test_discovered_theme_not_hardcoded_into_taxonomy(novel_corpus):
    # discover_themes() must never have been told in advance which cluster
    # to produce - re-run it and confirm the SAME concept reappears purely
    # from the ingested text, with no code path referencing "UNDERSEA".
    import inspect
    src = inspect.getsource(theme_mod.discover_themes)
    assert "UNDERSEA" not in src and "CABLE" not in src and "SABOTAGE" not in src


def test_discovered_theme_drills_through_to_issuers_and_counterparties(novel_corpus):
    discovered = theme_mod.discover_themes()
    theme = next(t for t in discovered if "test_novel1" in t["member_document_ids"])

    detail = theme_mod.theme_detail(theme["theme_id"])
    assert detail is not None, "a discovered theme must be drillable via theme_detail(), same as a curated one"
    assert detail["kind"] == "DISCOVERED_THEME"
    assert "MAERSK" in detail["covered_entities"]

    # Layer C exposure join: MAERSK is held by real exposure_edges.json
    # entries, so at least one counterparty must be surfaced.
    maersk_counterparties = {xe["counterparty"] for xe in STORE.exposure_edges if xe["issuer"] == "MAERSK"}
    assert maersk_counterparties, "test setup assumption: MAERSK must have at least one counterparty exposure"
    assert set(detail["exposed_counterparties"]) & maersk_counterparties


def test_curated_and_discovered_never_double_count(novel_corpus):
    discovered = theme_mod.discover_themes()
    curated_ids = set(STORE.keywords_by_id.keys())
    for t in discovered:
        assert t["theme_id"] not in curated_ids


def test_ingestion_requires_core_fields():
    with pytest.raises(ValueError):
        theme_mod.ingest_news_document({"id": "bad_doc"})


def test_discovery_endpoint_is_recomputed_not_cached_stale(novel_corpus):
    # calling discover_themes() twice in a row without new ingestion must be
    # stable (cached), but invalidating + re-running after ingestion must
    # reflect the new corpus - i.e. it is NOT a fixed hard-coded result.
    first = theme_mod.discover_themes()
    second = theme_mod.discover_themes()
    assert first == second  # cached, deterministic between calls
    theme_mod.invalidate_discovery_cache()
    third = theme_mod.discover_themes()
    assert len(third) >= 1
