"""API-level tests for the Daily Review, Breaches & Actions, the Event
Studio materiality join, and the Entity 360 counterparty-materiality panel.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_priority_queue_endpoint_summary_and_ordering():
    r = client.get("/api/priority-queue")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["critical"] >= 1
    assert body["summary"]["high"] >= 1
    assert body["summary"]["overdue_breaches"] >= 1
    assert "informational" in body["summary"]
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFORMATIONAL": 4}
    ranks = [order[row["priority"]] for row in body["results"]]
    assert ranks == sorted(ranks)
    assert "thresholds" in body and body["thresholds"]["label"] == "POC_HEURISTIC"
    assert "fictional" in body["note"].lower()


def test_priority_queue_filter_by_priority():
    r = client.get("/api/priority-queue?priority=CRITICAL")
    body = r.json()
    assert all(row["priority"] == "CRITICAL" for row in body["results"])


def test_priority_detail_endpoint_has_decision_object():
    r = client.get("/api/priority-queue/CP_HF_001")
    assert r.status_code == 200
    body = r.json()
    assert body["priority"] == "HIGH"
    assert body["decision"]["decision"]
    assert body["limit"]["limit_type"] == "PFE_LIMIT"


def test_priority_detail_404_for_unknown():
    r = client.get("/api/priority-queue/CP_DOES_NOT_EXIST")
    assert r.status_code == 404


def test_settlement_breach_via_api():
    r = client.get("/api/priority-queue/CP_PUB_ALPHA")
    body = r.json()
    assert body["limit"]["limit_type"] == "SETTLEMENT_LIMIT"
    assert body["exposure"]["pfe_current"] is None
    assert body["utilisation_pct"] is not None  # computed off settlement_exposure, not PFE


def test_breaches_endpoint():
    r = client.get("/api/breaches")
    body = r.json()
    assert body["count"] >= 1
    assert all(row["is_breach"] for row in body["results"])


def test_breaches_overdue_filter():
    r = client.get("/api/breaches?status=overdue")
    body = r.json()
    assert all(row["is_overdue"] for row in body["results"])


def test_event_parse_includes_materiality_join():
    r = client.post("/api/event/parse", json={
        "text": "A major earthquake in Taiwan disrupts TSMC production, affecting NVIDIA, AMD and Apple."
    })
    assert r.status_code == 200
    body = r.json()
    assert "materiality_join" in body
    mj = body["materiality_join"]
    assert "nominates candidates" in mj["note"]
    referenced = {row["reference_entity_id"] for row in mj["results"]}
    assert referenced & {"TSM", "NVDA"}


def test_entity_360_includes_counterparty_materiality():
    r = client.get("/api/entities/NVDA")
    assert r.status_code == 200
    body = r.json()
    assert "counterparty_materiality" in body
    cm = body["counterparty_materiality"]["results"]
    assert any(row["reference_entity_id"] == "NVDA" for row in cm)


def test_entity_360_materiality_never_used_for_relatedness_ranking():
    r = client.get("/api/entities/TSM")
    body = r.json()
    scores = [row["composite_score"] for row in body["relationship_summary"]["top_related"] if row["composite_score"] is not None]
    assert scores == sorted(scores, reverse=True)
