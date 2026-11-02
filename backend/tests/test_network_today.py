"""The relationship network, the propagation index, reaches, and the Today / Counterparty / health endpoints."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.core import network, propagation, reaches, today as today_mod
from app.main import app

client = TestClient(app)
AS_OF = "2026-11-02"


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------- the network
def test_network_has_no_self_loops_dangling_ends_or_out_of_range_numbers():
    g = network.build()
    assert g["edges"], "the network is empty"
    for e in g["edges"]:
        assert e["source"] != e["target"]
        assert e["source"] in g["nodes"] and e["target"] in g["nodes"]
        assert e["channel"] in network.CHANNELS
        for k in ("strength", "confidence"):
            assert e[k] is None or 0 <= e[k] <= 1, (e["id"], k, e[k])
        if not e["directed"]:
            assert e["source"] < e["target"], "undirected edges are stored with sorted ends"
    assert len({e["id"] for e in g["edges"]}) == len(g["edges"]), "parallel duplicates are merged"


def test_every_channel_is_what_it_claims():
    g = network.build()
    kinds = lambda e: (g["nodes"][e["source"]]["kind"], g["nodes"][e["target"]]["kind"])   # noqa: E731
    by = {c: [e for e in g["edges"] if e["channel"] == c] for c in network.CHANNELS}
    assert not by["ownership"], "the canonical data has no ownership edges (GLEIF reports no parents)"
    assert all(kinds(e)[0] == "counterparty" and kinds(e)[1] in ("issuer", "factor") for e in by["exposure"])
    assert all(kinds(e) == ("issuer", "issuer") and e["relation"] in ("SUPPLIES", "LICENSES_TO") and e["confidence"] in (0.9, 0.6, None) for e in by["supply"])
    assert all(kinds(e) == ("counterparty", "counterparty") and e["strength"] >= network.SHARED_MIN_JACCARD and e["evidence"]["shared_issuers"] for e in by["shared"])
    assert all(kinds(e) == ("issuer", "issuer") and e["strength"] >= 0.3 and -1 <= e["evidence"]["signed_correlation"] <= 1 for e in by["comovement"])
    assert all(kinds(e) == ("factor", "factor") for e in by["hidden"])


def test_both_counterparty_universes_are_present_and_marked():
    nodes = network.build()["nodes"].values()
    ccr = [n for n in nodes if n["kind"] == "counterparty" and n["universe"] == "ccr"]
    held = [n for n in nodes if n["kind"] == "counterparty" and n["universe"] == "portfolio"]
    assert len(ccr) == 19 and len(held) == 18
    assert all(n["holdings_only"] for n in held) and not any(n["holdings_only"] for n in ccr)
    assert all(n["rating"] is None and n["outlook"] is None and n["ews"] is None for n in ccr), "nothing is invented for fields the data lacks"


def test_network_and_clusters_are_deterministic_and_clusters_are_real_groups():
    assert _hash(network.build()["edges"]) == _hash(network.build()["edges"])
    cl = network.clusters()
    assert cl and _hash(cl) == _hash(network.clusters())
    seen = set()
    for c in cl:
        assert c["size"] == len(c["members"]) >= 2 and all(m.startswith("cp:") for m in c["members"])
        assert not seen & set(c["members"]), "a counterparty belongs to one cluster"
        seen |= set(c["members"])
        assert c["shared_issuers"], "a cluster is defined by issuers its members share"


def test_subgraph_scopes():
    ego = network.subgraph(["cp:CP_SOV_BETA"], 1)
    ids = {n["id"] for n in ego["nodes"]}
    assert "cp:CP_SOV_BETA" in ids and all(e["source"] in ids and e["target"] in ids for e in ego["edges"])
    two = {n["id"] for n in network.subgraph(["cp:CP_SOV_BETA"], 2)["nodes"]}
    assert ids < two
    assert {e["channel"] for e in network.subgraph(["cp:CP_HF_001"], 3, {"hidden"})["edges"]} <= {"hidden"}
    assert len(network.subgraph([], 1)["nodes"]) == len(network.build()["nodes"])


# ---------------------------------------------------------------- propagation
def _e(a, b, ch="supply", s=1.0, c=1.0, directed=False):
    return {"id": f"{a}-{b}", "source": a, "target": b, "channel": ch, "strength": s, "confidence": c, "directed": directed}


def test_propagation_decays_per_hop_and_each_node_is_reached_once():
    edges = [_e("a", "b"), _e("b", "c"), _e("a", "c", s=0.1), _e("c", "d")]
    r = propagation.propagate(edges, ["a"])
    w = propagation.CHANNEL_WEIGHTS["supply"] * propagation.HOP_DECAY
    assert r["a"] == {"distress": 1.0, "hop": 0, "via": None, "channel": None}
    assert r["b"]["distress"] == pytest.approx(w, abs=1e-4) and r["b"]["hop"] == 1
    assert r["c"]["hop"] == 1 and r["c"]["distress"] == pytest.approx(0.1 * w, abs=1e-4), "reached at hop 1 by the weak edge; the longer path cannot overwrite it"
    assert r["d"]["hop"] == 2 and r["d"]["via"] == "c"
    assert all(r[n]["distress"] <= 1 for n in r)


def test_propagation_respects_max_hops_missing_values_and_ties():
    edges = [_e("a", "b"), _e("b", "c"), _e("c", "d")]
    assert set(propagation.propagate(edges, ["a"], max_hops=1)) == {"a", "b"}
    none = _e("x", "y", s=None, c=None)
    assert propagation.edge_weight(none) == pytest.approx(0.5 * propagation.CHANNEL_WEIGHTS["supply"]), "missing strength is neutral 0.5, missing confidence is not a penalty"
    tie = propagation.propagate([_e("a", "c"), _e("b", "c")], ["a", "b"])
    assert tie["c"]["via"] == "a", "ties break by id, so the result never depends on iteration order"
    assert propagation.propagate(edges, ["zz"] and []) == {}


def test_a_zero_weight_channel_carries_nothing():
    assert propagation.propagate([_e("a", "b", ch="ownership")], ["a"], weights={**propagation.CHANNEL_WEIGHTS, "ownership": 0.0}) == {"a": {"distress": 1.0, "hop": 0, "via": None, "channel": None}}


def test_run_reports_limit_crossings_and_always_says_it_is_an_index():
    r = propagation.run(["rf:INTEREST_RATE"])
    assert "Not a loss estimate" in r["index_label"] and r["provenance"] == "derived"
    assert r["names_reached"] == len([n for n in r["nodes"] if n["hop"] > 0]) and r["hops_reached"] >= 1
    for n in r["nodes"]:
        if "utilisation_after" in n:
            assert n["utilisation_after"] >= n["utilisation_before"]
    for nid in r["crossing_100"]:
        n = next(x for x in r["nodes"] if x["id"] == nid)
        assert n["utilisation_before"] < 100 <= n["utilisation_after"]
    assert not any("loss" in k or "usd" in k.lower() for k in r), "no currency figure is produced"


def test_run_is_deterministic_and_reports_unknown_shocks():
    assert _hash(propagation.run(["cp:CP_HF_001"])) == _hash(propagation.run(["cp:CP_HF_001"]))
    assert propagation.run(["cp:NOPE"])["unknown"] == ["cp:NOPE"]


def test_every_scenario_preset_points_at_a_real_node():
    for s in propagation.scenarios():
        assert all(x in network.build()["nodes"] for x in s["shock"]), s["id"]


# ---------------------------------------------------------------- reaches
def test_reaches_are_exposure_holders_first_then_one_supply_step_and_bounded():
    r = reaches.reaches_for(["NVDA"], limit=50)
    assert r and r == sorted(r, key=lambda x: (x["hops"], -(x["strength"] or 0), x["name"]))
    assert {x["hops"] for x in r} <= {0, 1} and len({x["node_id"] for x in r}) == len(r)
    assert len(reaches.reaches_for(["NVDA"], limit=3)) == 3
    assert reaches.reaches_for(["NOT_AN_ISSUER"]) == []


def test_impact_map_events_are_unchanged_unless_reaches_are_asked_for():
    plain = client.get("/api/impact-map/NVDA/events").json()
    assert all("reaches" not in e for e in plain["events"])
    with_r = client.get("/api/impact-map/NVDA/events?include_reaches=true").json()
    assert all(isinstance(e["reaches"], list) for e in with_r["events"])
    assert [e["id"] for e in plain["events"]] == [e["id"] for e in with_r["events"]]
    for e in with_r["events"]:
        e.pop("reaches")
    assert _hash(with_r["events"]) == _hash(plain["events"]), "asking for reaches adds a field and changes nothing else"


# ---------------------------------------------------------------- endpoints
def test_today_payload_is_complete_honest_and_cached():
    r = client.get(f"/api/today?as_of={AS_OF}")
    assert r.status_code == 200
    d = r.json()
    assert {"headline", "summary", "kpis", "top_exposures", "stress_heatmap", "market_events", "concentration", "ratings", "map_entity", "clusters", "simulate", "scope"} <= set(d)
    assert d["summary_kind"] == "template" and d["scope"]["count"] == 10
    assert [k["id"] for k in d["kpis"]] == ["critical", "high", "overdue", "near_limit", "wwr", "new_links"]
    assert next(k for k in d["kpis"] if k["id"] == "new_links")["value"] is None, "no relationship has a date, so this cannot be counted"
    assert all(k["spark"] is None for k in d["kpis"]), "there is no history to draw"
    assert d["ratings"]["available"] is False and "rating" in d["ratings"]["reason"].lower()
    assert all(t["rating"] is None and t["outlook"] is None for t in d["top_exposures"])
    assert d["top_exposures"] == sorted(d["top_exposures"], key=lambda t: (t["utilisation_pct"] is None, -(t["utilisation_pct"] or 0), t["id"]))
    h = d["stress_heatmap"]
    assert "Not a loss estimate" in h["index_label"] and all(len(r["values"]) == len(h["scenarios"]) and all(0 <= v <= 1 for v in r["values"]) for r in h["rows"])
    assert d["simulate"] is None or d["simulate"]["id"] in d["scope"]["watchlist"]
    assert d["market_events"] == sorted(d["market_events"], key=lambda e: (e["date"], e["id"]), reverse=True)
    assert {e["badge"] for e in d["market_events"]} <= {"Verified", "Sample", "Reported"}
    assert client.get(f"/api/today?as_of={AS_OF}").json() == d, "same request, same answer"


def test_today_watchlist_and_validation():
    d = client.get(f"/api/today?as_of={AS_OF}&watchlist=CP_HF_001,CP_SOV_BETA,NOT_A_CP").json()
    assert d["scope"]["watchlist"] == ["CP_SOV_BETA", "CP_HF_001"] or set(d["scope"]["watchlist"]) == {"CP_HF_001", "CP_SOV_BETA"}
    assert client.get("/api/today?as_of=2026-13-45").status_code == 422
    assert client.get("/api/today?as_of=garbage!!").status_code == 422


def test_stress_endpoints():
    s = client.get("/api/stress/scenarios").json()
    assert s["scenarios"] and "Not a loss estimate" in s["index_label"]
    r = client.post("/api/stress/run", json={"shock": ["CP_HF_001"], "label": "Example default"})
    assert r.status_code == 200 and r.json()["shocked"] == ["cp:CP_HF_001"] and r.json()["label"] == "Example default"
    assert client.post("/api/stress/run", json={"shock": ["rf:EQUITY"], "max_hops": 1}).json()["hops_reached"] == 1
    assert client.post("/api/stress/run", json={"shock": ["nobody"]}).status_code == 404
    assert client.post("/api/stress/run", json={"shock": []}).status_code == 422
    assert client.post("/api/stress/run", json={"shock": ["rf:EQUITY"], "max_hops": 9}).status_code == 422


def test_network_graph_endpoint_scopes_and_errors():
    ego = client.get("/api/network/graph?scope=ego&center=CP_HF_001&hops=1").json()
    assert ego["seeds"] == ["cp:CP_HF_001"] and ego["node_count"] == len(ego["nodes"])
    assert client.get("/api/network/graph?scope=ego").status_code == 422
    assert client.get("/api/network/graph?scope=ego&center=NOBODY").status_code == 404
    assert client.get("/api/network/graph?scope=all").json()["node_count"] == len(network.build()["nodes"])
    only = client.get("/api/network/graph?scope=all&channels=supply,hidden").json()
    assert {e["channel"] for e in only["edges"]} <= {"supply", "hidden"}
    iss = client.get("/api/network/graph?scope=ego&center=NVDA&hops=1").json()
    assert "is:NVDA" in iss["seeds"]
    assert client.get("/api/network/graph?scope=bogus").status_code == 422
    wl = client.get("/api/network/graph?scope=watchlist").json()
    assert wl["nodes"] and all(c["size"] >= 2 for c in wl["clusters"])


def test_studio_overlay_is_declared_unavailable_on_a_deployment_without_the_studio():
    d = client.get("/api/network/graph?scope=all&include_studio=true").json()
    assert d["studio_overlay"]["available"] is False and d["studio_overlay"]["edges_added"] == 0 and d["studio_overlay"]["reason"]


def test_counterparty_page_for_both_universes():
    ccr = client.get("/api/cp/CP_HF_001").json()
    assert ccr["header"]["priority"] and ccr["kpis"]["utilisation_pct"] is not None and ccr["decision"]["decision"]
    assert ccr["header"]["rating"] is None and ccr["kpis"]["ews"] is None
    pts = ccr["exposure_series"]["points"]
    assert [p["label"] for p in pts] == ["Previous", "Current"] and "no exposure history" in ccr["exposure_series"]["note"]
    assert ccr["exposure_series"]["limit"]["applies_to"] in ("pfe", "nse", "settlement", None) and ccr["events_entity"]
    assert ccr["systemic_rank"]["rank"] >= 1 and ccr["systemic_rank"]["of"] == 37
    assert sum(ccr["channel_mix"].values()) == pytest.approx(1.0, abs=0.01) and all(l["channel"] in network.CHANNELS for l in ccr["links"])
    assert ccr["stress"]["scenarios"] and "Not a loss estimate" in ccr["stress"]["index_label"]
    held = client.get("/api/cp/CP_ALPHA").json()
    assert held["holdings_only"] is True and held["kpis"] is None and held["exposure_series"] is None and held["holdings"]
    assert client.get("/api/cp/NOPE").status_code == 404


def test_health_endpoints_say_what_they_cannot_know():
    p = client.get("/api/health/pipeline").json()
    assert p["available"] is False and p["operator_only"] is True and "operator" in p["reason"].lower()
    s = client.get(f"/api/health/sources?as_of={AS_OF}").json()
    assert {x["id"] for x in s["sources"]} == {"prices", "news", "register", "limits", "gleif"} and "not agreed targets" in s["sla_note"]
    for x in s["sources"]:
        assert x["status"] in ("ok", "stale", "unknown") and (x["status"] == "unknown") == (x["age_days"] is None)
        assert (x["status"] == "stale") == (x["age_days"] is not None and x["age_days"] > x["sla_days"])
    m = client.get("/api/health/models").json()
    assert m["providers"][0]["status"] == "active" and m["usage"]["available"] is False
    text = json.dumps(m).lower()
    assert "http" not in text and "bearer" not in text and "sk-" not in text, "no key and no host ever leave the server (variable names may be mentioned, never values)"


def test_default_watchlist_is_the_top_ten_by_priority():
    ids = today_mod.default_watchlist()
    assert len(ids) == 10 and ids[0] == "CP_PUB_ALPHA"


def test_an_approved_studio_relationship_is_drawn_as_an_overlay_edge_with_its_evidence_and_no_criticality(monkeypatch):
    from app.studio import overlay

    ev = {"source_url": "https://example.test/doc", "source_publisher": "Example Publisher", "source_published_date": "2026-10-01", "quotes": ["A quoted sentence."], "source_sha256": "a" * 64}
    fake = {"requested": True, "available": True, "reason": None, "release": {"version": 3, "approved_by": "reviewer"}, "edges": [
        {"source": "NVDA", "target": "AMD", "relation": "SUPPLIES", "evidence": [ev], "in_canonical": False, "first_documented": "2026-10-01"},
        {"source": "NVDA", "target": "NOT_AN_ISSUER", "relation": "SUPPLIES", "evidence": [ev], "in_canonical": False, "first_documented": "2026-10-01"},
        {"source": "AMD", "target": "NVDA", "relation": "GUARANTEES", "evidence": [ev], "in_canonical": False, "first_documented": "2026-10-01"}]}
    monkeypatch.setattr(overlay, "approved", lambda include: fake)
    d = client.get("/api/network/graph?scope=ego&center=NVDA&hops=1&include_studio=true").json()
    added = [e for e in d["edges"] if e["studio"]]
    assert d["studio_overlay"]["available"] and d["studio_overlay"]["edges_added"] == 2, "an edge whose end is not in the network is skipped"
    assert {(e["channel"], e["relation"]) for e in added} == {("supply", "SUPPLIES"), ("ownership", "GUARANTEES")}
    assert all(e["strength"] is None and e["confidence"] is None for e in added), "approved relationships carry no criticality"
    assert added[0]["evidence"]["studio_evidence"][0]["source_url"].startswith("https://")
    assert not any(e["studio"] for e in client.get("/api/network/graph?scope=ego&center=NVDA&hops=1").json()["edges"]), "off by default"
