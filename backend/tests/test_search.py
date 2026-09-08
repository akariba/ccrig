"""Universal search dispatch - regression tests for two real bugs found via
screenshot review: (1) a multi-word risk-factor query like "interest rate
volatility" never matched a shorter theme label ("interest rates") because
the substring check only ran query-in-label, never label-in-query; (2) a
short theme query like "AI" was hijacked into an unrelated entity match
because "ai" is a raw substring of "Taiwan" - fixed with word-boundary
anchored matching instead of naive `in` containment.
"""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_multiword_risk_factor_query_resolves_to_theme_not_ambiguous():
    r = client.get("/api/search", params={"q": "interest rate volatility"})
    body = r.json()
    assert body["resolved_as"] == "theme"
    assert body["resolved_id"] == "INTEREST_RATES"


def test_short_theme_query_does_not_get_hijacked_by_unrelated_entity_substring():
    r = client.get("/api/search", params={"q": "AI"})
    body = r.json()
    # "ai" is a raw substring of "Taiwan" - must NOT resolve to TSM
    assert body["resolved_as"] == "theme"
    assert body["resolved_id"] == "AI"
    assert body["entity_matches"] == []


def test_ticker_search_still_resolves_to_entity():
    r = client.get("/api/search", params={"q": "NVDA"})
    body = r.json()
    assert body["resolved_as"] == "entity"
    assert body["resolved_id"] == "NVDA"


def test_partial_company_name_prefix_still_matches():
    r = client.get("/api/search", params={"q": "Samsung"})
    body = r.json()
    assert any(m["id"] == "SSNLF" for m in body["entity_matches"])


def test_word_boundary_match_excludes_midword_substring():
    # "ai" must not match "Taiwan" (mid-word, no boundary before it) even
    # though it's a raw substring - this is the exact bug that hijacked the
    # "AI" theme query into an unrelated TSM entity match.
    r = client.get("/api/search", params={"q": "ai"})
    body = r.json()
    assert not any(m["id"] == "TSM" for m in body["entity_matches"])
