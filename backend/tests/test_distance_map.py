"""Distance Map: counterparty -> issuer graph distance and inferred
correlation (rho = 1 - d). See app/core/distance.py for the algorithm.
"""
import dataclasses

from fastapi.testclient import TestClient

from app.core.data import STORE
from app.core.distance import CorrelationChannel, compute_counterparty_distances
from app.main import app

client = TestClient(app)

CP_ID = STORE.counterparty_ids[0]  # real counterparty from this dataset (e.g. CP_ALPHA)


def test_result_is_sorted_descending():
    result = compute_counterparty_distances(CP_ID)
    rhos = [i.rho for i in result.issuers]
    assert rhos == sorted(rhos, reverse=True)


def test_all_rho_and_distance_in_range_and_consistent():
    result = compute_counterparty_distances(CP_ID)
    assert result.issuers, "expected at least one reachable issuer for this counterparty"
    for iss in result.issuers:
        assert 0.0 <= iss.rho <= 1.0
        assert 0.0 <= iss.distance <= 1.0
        assert abs(iss.rho - (1.0 - iss.distance)) < 0.01


def test_direct_channel_pairs_have_high_rho():
    """A direct Layer A ownership or supply edge should produce a
    meaningfully higher rho than a purely derived (Layer B) pair."""
    result = compute_counterparty_distances(CP_ID)
    direct_pairs = [i for i in result.issuers if i.is_direct]
    for pair in direct_pairs:
        assert pair.rho >= 0.60, f"Direct pair {pair.issuer_name} has unexpectedly low rho={pair.rho}"


def test_min_rho_filter():
    result = compute_counterparty_distances(CP_ID, min_rho=0.5)
    for iss in result.issuers:
        assert iss.rho >= 0.5


def test_is_synthetic_always_true():
    result = compute_counterparty_distances(CP_ID)
    for iss in result.issuers:
        assert iss.is_synthetic is True


def test_channel_is_one_of_the_four_defined():
    result = compute_counterparty_distances(CP_ID)
    for iss in result.issuers:
        assert iss.channel in CorrelationChannel


def test_never_scores_the_full_issuer_universe():
    """Distance Map reuses the bounded candidate set (core/candidates.py) -
    it must never silently fall back to scoring every issuer in the
    dataset for a single counterparty."""
    result = compute_counterparty_distances(CP_ID)
    assert len(result.issuers) < len(STORE.issuer_ids)


def test_exposure_context_kept_separate_from_rho():
    result = compute_counterparty_distances(CP_ID)
    d = dataclasses.asdict(result)
    assert "exposure_context" in d
    # exposure_pct (if present) must never leak into an issuer's rho/distance
    for holding in d["exposure_context"]:
        assert "rho" not in holding


def test_unknown_counterparty_returns_none():
    assert compute_counterparty_distances("CP_DOES_NOT_EXIST_ZZZZZ") is None


def test_issuer_id_is_not_accepted_as_counterparty():
    assert compute_counterparty_distances(STORE.issuer_ids[0]) is None


def test_api_list_counterparties():
    r = client.get("/api/distance-map/counterparties")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(STORE.counterparty_ids)
    assert any(c["counterparty_id"] == CP_ID for c in body["results"])


def test_api_get_distances():
    r = client.get(f"/api/distance-map/counterparty/{CP_ID}")
    assert r.status_code == 200
    body = r.json()
    assert "issuers" in body and "methodology_note" in body and "concentration_alert" in body
    rhos = [i["rho"] for i in body["issuers"]]
    assert rhos == sorted(rhos, reverse=True)


def test_api_min_rho_query_param():
    r = client.get(f"/api/distance-map/counterparty/{CP_ID}", params={"min_rho": 0.6})
    assert r.status_code == 200
    for iss in r.json()["issuers"]:
        assert iss["rho"] >= 0.6


def test_api_unknown_counterparty_returns_404_not_500():
    r = client.get("/api/distance-map/counterparty/FAKE_ID_XYZ")
    assert r.status_code == 404
