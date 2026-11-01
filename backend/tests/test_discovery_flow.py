"""Event discovery end to end: rich, limited, ambiguous, empty and undocumented-relationship cases; review; the map's two modes; honesty when a provider is unavailable."""
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import event_discovery
from app.core.config import DATA_DIR
from app.discovery import bridge, service
from app.routers import impact_map, studio, studio_ops
from app.studio import review
from app.studio.store import StudioStore
from tests.discovery_helpers import AS_OF, FIX, blocked, transport
from tests.studio_helpers import tree_hash

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("CCRIG_ENABLE_STUDIO", "1")
    monkeypatch.setenv("CCRIG_STUDIO_TOKEN", "t0ken")
    monkeypatch.setenv("CCRIG_STUDIO_DIR", str(tmp_path / "ws"))
    studio_ops._store_for.cache_clear()
    before = tree_hash(DATA_DIR)
    store = StudioStore(tmp_path / "ws")
    yield store
    assert tree_hash(DATA_DIR) == before, "discovery modified canonical data"
    studio_ops._store_for.cache_clear()


def run_nvda(store, **kw):
    return service.run(store, kw.pop("text", "NVIDIA"), transport=kw.pop("transport", None) or transport(), as_of=AS_OF, client=kw.pop("client", None), **kw)


# ------------------------------------------------------------------ rich coverage
def test_a_company_with_rich_coverage_returns_verified_events_with_every_step_explained(ws):
    r = run_nvda(ws)
    assert r["status"] == "STAGED" and r["entity"]["entity_id"] == "NVDA" and r["resolution"]["rule"] == "CORE_NAME"
    titles = [e["title"] for e in r["events"]]
    assert [e["published_date"] for e in r["events"]] == ["2026-10-28", "2026-10-27", "2026-10-26", "2026-10-21"]       # newest first
    assert any("Oracle" in t for t in titles) and any("Meta" in t for t in titles) and any("Conference Call" in t for t in titles) and any("Supply Chain" in t for t in titles)
    f = r["funnel"]
    assert f["listed_by_providers"] == f["excluded_before_retrieval"] + f["retrieved"] and f["selected"] == 4 and f["after_deduplication"] == 4
    st = {p["id"]: p for p in r["providers"]}
    assert st["nvidia_newsroom_feed"]["status"] == "SEARCHED" and st["federal_register"]["status"] == "SEARCHED"
    assert r["ai"]["configured"] is False and r["ai"]["mode"].startswith("deterministic extraction only")
    blogs = [n for n in r["not_returned"] if "blogs.nvidia.com" in n["reason"]]
    assert len(blogs) == 3 and all(n["stage"] == "SEARCH" and n["url"].startswith("https://blogs.nvidia.com") for n in blogs)
    assert any("not named" in n["reason"] for n in r["not_returned"]), "Federal Register hits that do not name the company are excluded with that reason"
    assert any("not a ranking by financial impact" in c.lower() or "not a ranking by financial impact or importance" in c.lower() for c in r["selection_criteria"])
    assert all("impact" not in (e.get("event_date_basis") or "").lower() for e in r["events"])
    for e in r["events"]:                                                    # evidence is stored, hash-addressed and re-verifiable
        assert e["verification"]["status"] == "VERIFIED_BY_RETRIEVAL" and ws.read_raw(e["source_sha256"])
        assert e["source_url"].startswith("https://nvidianews.nvidia.com/") and all(len(q) >= 25 for q in e["evidence_quotes"])
    berlin = next(e for e in r["events"] if "Supply Chain" in e["title"])
    assert berlin["location"]["gazetteer_key"] == "berlin-de" and "GTC Berlin" in berlin["location"]["basis_text"]
    others = [e for e in r["events"] if e is not berlin]
    assert all(not e["location"].get("gazetteer_key") and e["location"]["unmapped_reason"] for e in others)
    job = ws.get_job(r["staging_job_id"])
    assert job["status"] == "PENDING_REVIEW" and not job["blocking"] and job["target"] == "discovered_events" and job["scope"] == "NVDA"
    stages = [(e["stage"], e["kind"]) for e in ws.events(r["run_id"])]
    for s in ("DISCOVER_SEARCH", "DISCOVER_EXTRACT", "DISCOVER_DEDUPE", "DISCOVER_VERIFY", "DISCOVER_SELECT"):
        assert (s, "COMPLETED") in stages
    assert ws.verify_chain()["ok"]


def test_the_same_run_twice_adds_nothing_new(ws):
    a, b = run_nvda(ws), run_nvda(ws)
    assert a["run_id"] == b["run_id"] and a["staging_job_id"] == b["staging_job_id"] and a["selected_event_ids"] == b["selected_event_ids"]
    assert len(ws.list_jobs()) == 1 and len(ws.list_runs()) == 1


def test_results_do_not_depend_on_hash_seeds(tmp_path):
    code = ("import json,sys;sys.path.insert(0,'.');from datetime import date;from tests.discovery_helpers import transport,AS_OF;from app.studio.store import StudioStore;"
            "from app.discovery import service;r=service.run(StudioStore(sys.argv[1]),'NVIDIA',transport=transport(),as_of=AS_OF,client=None);"
            "print(json.dumps({k:r[k] for k in ('selected_event_ids','events','not_returned','funnel','explanation')},sort_keys=True))")
    outs = {subprocess.run([sys.executable, "-c", code, str(tmp_path / f"w{s}")], cwd=BACKEND, capture_output=True, text=True, env={**os.environ, "PYTHONHASHSEED": s}).stdout for s in ("1", "777")}
    assert len(outs) == 1 and all(outs)


# ------------------------------------------------------------------ limited, empty, ambiguous, unavailable
def test_a_company_with_limited_evidence_returns_fewer_events_and_says_so(ws):
    feb = date(2026, 2, 1)
    r = service.run(ws, "NVIDIA", transport=transport("NVDA", feb, fr_key="nvda_2026-02-01"), as_of=feb, client=None)
    assert len(r["events"]) == 1 and r["events"][0]["category"] == "REGULATORY_ACTION" and r["events"][0]["location"]["gazetteer_key"] == "country-us"
    assert "fewer than the 5 requested" in r["explanation"] and "no event was added to fill the count" in r["explanation"]
    assert any("outside the window" in n["reason"] for n in r["not_returned"])


@pytest.mark.parametrize("entity,key", [("AMD", "amd_2026-11-01"), ("JPM", "jpm_2026-11-01")])
def test_an_entity_with_no_supported_events_returns_none_and_invents_none(ws, entity, key):
    r = service.run(ws, entity, transport=transport(entity, AS_OF, fr_key=key, feed=False), as_of=AS_OF, client=None)
    assert r["status"] == "NO_EVENTS" and r["events"] == [] and r["staging_job_id"] is None and ws.list_jobs() == []
    assert "None are invented" in r["explanation"] and {p["id"]: p["status"] for p in r["providers"]}["nvidia_newsroom_feed"] == "NOT_APPLICABLE"
    assert r["funnel"]["retrieved"] > 0 and all("not named" in n["reason"] for n in r["not_returned"])
    shown = bridge.discovered_response(entity, as_of=AS_OF)
    assert shown["available"] is True and shown["events"] == [] and shown["review"]["status"] == "NO_EVENTS"


@pytest.mark.parametrize("text,rule", [("Samsung", "DENIED_ALIAS"), ("Totally Unknown Co", "NO_MATCH"), ("", "EMPTY")])
def test_an_ambiguous_or_unknown_company_stops_before_anything_is_searched(ws, text, rule):
    t = transport()
    r = service.run(ws, text, transport=t, as_of=AS_OF, client=None)
    assert r["status"] == "ENTITY_UNRESOLVED" and r["resolution"]["rule"] == rule and r["entity"] is None and "Nothing was searched" in r["explanation"]
    assert t.requested == [] and ws.list_runs() == [] and ws.list_jobs() == []


def test_an_unavailable_provider_is_disclosed_and_nothing_is_simulated(ws):
    t = blocked()
    r = service.run(ws, "NVIDIA", transport=t, as_of=AS_OF, client=None)
    assert r["status"] == "NO_EVENTS" and r["events"] == [] and r["funnel"]["retrieved"] == 0
    assert {p["status"] for p in r["providers"]} == {"UNAVAILABLE"} and all("NETWORK_DISABLED" in p["reason"] for p in r["providers"])
    assert "Provider unavailable" in r["explanation"] and "could not search any approved source" in r["explanation"]
    assert ws.list_jobs() == []


def test_the_real_transport_refuses_without_the_operators_switch(ws, monkeypatch):
    monkeypatch.delenv("CCRIG_DISCOVERY_NETWORK", raising=False)
    r = service.run(ws, "NVIDIA", as_of=AS_OF, client=None)                      # default transport: HttpTransport
    assert r["status"] == "NO_EVENTS" and all(p["status"] == "UNAVAILABLE" for p in r["providers"])


# ------------------------------------------------------------------ the AI layer inside a run
class OracleLLM:
    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user):
        self.calls += 1
        body = user.split("<<<TEXT\n", 1)[1].split("\nTEXT>>>", 1)[0]
        sentence = next((s for s in body.split(". ") if "Oracle" in s and "NVIDIA" in s), "")
        quote = sentence.strip() + ("." if sentence and not sentence.endswith(".") else "")
        return {"category": "NOT_A_CATEGORY", "quotes": ["NVIDIA secretly acquired Oracle for a hundred billion dollars.", quote] if quote else [],
                "relationships": [{"a": "NVIDIA", "b": "Oracle", "relation": "PARTNERS_WITH", "quote": quote}, {"a": "NVIDIA", "b": "Zorblax Dynamics", "relation": "SUPPLIES", "quote": quote}] if quote else []}


def test_ai_suggestions_are_guarded_and_never_become_edges_or_events(ws):
    det = run_nvda(ws)
    llm = OracleLLM()
    r = service.run(ws, "NVIDIA", transport=transport(), as_of=date(2026, 11, 1), client=llm, window_days=179)             # a different window -> a distinct run to compare
    assert llm.calls >= 1 and r["ai"]["configured"] and r["ai"]["used_on_documents"] >= 1 and r["ai"]["mode"].startswith("AI-assisted")
    assert {e["id"] for e in r["events"]} == {e["id"] for e in det["events"]}                           # the model cannot add or remove events
    for e in r["events"]:
        assert "acquired Oracle" not in " ".join(e["evidence_quotes"])                                 # an invented quote never reaches the evidence
        assert e["category"] in ("CORPORATE_ANNOUNCEMENT", "EARNINGS_RELEASE", "PARTNERSHIP_ANNOUNCEMENT", "PRODUCT_ANNOUNCEMENT", "REGULATORY_ACTION")
    assert r["ai"]["extra_quotes_accepted"] >= 1 and any(len(e["evidence_quotes"]) > 1 and e["verification"]["quotes_total"] == e["verification"]["quotes_found"] == len(e["evidence_quotes"]) for e in r["events"])
    assert any("not found verbatim" in d["reason"] for d in r["ai"]["dropped"]) and any("allowed categories" in d["reason"] for d in r["ai"]["dropped"])
    rel = r["relationship_candidates"]
    assert rel and all(x["status"] == "AI_PROPOSED_UNREVIEWED" and x["b_entity"] == "ORCL" for x in rel) and not any("Zorblax" in json.dumps(x) for x in rel)
    shown = bridge.discovered_response("NVDA", as_of=AS_OF)
    assert all(p["relationship_type"] in ("DIRECT_MENTION", "DOCUMENTED_DIRECT", "DOCUMENTED_INDIRECT") for e in shown["events"] for p in e["paths"])
    assert not any(h.get("relation") == "PARTNERS_WITH" for e in shown["events"] for p in e["paths"] for h in p["steps"]), "an AI-proposed relationship must never become a path"


# ------------------------------------------------------------------ review status and the map's data
def test_staged_events_are_shown_as_machine_verified_until_a_person_decides(ws):
    r = run_nvda(ws)
    pending = bridge.discovered_response("NVDA", as_of=AS_OF)
    assert pending["available"] and pending["review"]["status"] == "MACHINE_VERIFIED_AWAITING_REVIEW" and len(pending["events"]) == 4
    assert all(e["discovery"]["review_status"] == "MACHINE_VERIFIED_AWAITING_REVIEW" for e in pending["events"])
    assert pending["mode"] == "discovered" and pending["provenance"]["run_id"] == r["run_id"] and pending["provenance"]["ai"]["mode"].startswith("deterministic")
    review.approve(ws, r["staging_job_id"], reviewer="alice", reason="sources checked against the pages")
    approved = bridge.discovered_response("NVDA", as_of=AS_OF)
    assert approved["review"]["status"] == "APPROVED" and approved["review"]["decisions"][0]["reviewer"] == "alice"
    assert ws.current("discovered_events", "NVDA")["rows"] == 4


def test_a_rejected_run_is_not_shown_and_the_reason_is(ws):
    r = run_nvda(ws)
    review.reject(ws, r["staging_job_id"], reviewer="bob", reason="the Meta page date looks wrong")
    out = bridge.discovered_response("NVDA", as_of=AS_OF)
    assert out["available"] is False and out["unavailable_code"] == "REJECTED" and out["events"] == [] and "the Meta page date looks wrong" in out["explanation"]


def test_events_keep_sources_dates_locations_paths_and_unknowns(ws):
    run_nvda(ws)
    out = bridge.discovered_response("NVDA", as_of=AS_OF)
    for e in out["events"]:
        assert e["sources"][0]["url"].startswith("https://nvidianews.nvidia.com/") and e["published_date"] and e["event_date"] and e["event_date_basis"]
        assert e["impact"]["status"] == "NOT_ESTIMATED" and e["impact"]["estimate"] is None and e["verified_exposure"]["status"] == "NOT_AVAILABLE"
        assert e["verification"]["status"] == "VERIFIED_BY_RETRIEVAL" and e["location"].get("basis")
        for ent in e["entities"]:
            if ent["relationship_to_target"] == "NO_DOCUMENTED_PATH":
                assert [p for p in e["paths"] if p["entity_id"] == ent["entity_id"]] == []
    oracle = next(e for e in out["events"] if "Oracle" in e["title"])
    undocumented = [x for x in oracle["entities"] if x["relationship_to_target"] == "NO_DOCUMENTED_PATH"]
    assert undocumented and any("gap in the data" in lim for lim in oracle["limitations"])                   # a named company with no documented path is flagged, not connected
    assert oracle["location"]["mapped"] is False and "dateline" in oracle["location"]["reason"]
    nodes = {n["id"]: n for n in out["graph"]["nodes"]}
    assert not any(n["type"] == "EVENT" and n.get("position") for n in nodes.values() if "Oracle" in n["label"])      # nothing is plotted without an evidenced place
    assert out["limitations"] == service.LIMITATIONS and any("never assumed" in l for l in out["limitations"])
    assert out["register"]["coverage"].startswith("Dynamic discovery run")


def test_curated_mode_is_untouched_by_everything_above(ws):
    before = json.dumps(event_discovery.discover("NVDA"), sort_keys=True)
    run_nvda(ws)
    assert json.dumps(event_discovery.discover("NVDA"), sort_keys=True) == before
    assert len(event_discovery.discover("NVDA")["events"]) == 5 and event_discovery.discover("NVDA")["register"]["coverage"] == "NVIDIA (NVDA) pilot"


def test_curated_and_discovered_modes_are_compared_side_by_side(ws):
    run_nvda(ws)
    c = bridge.compare("NVDA", as_of=AS_OF)
    assert c["curated"]["count"] == 5 and c["discovered"]["count"] == 4 and c["discovered"]["available"] and "same source document" in c["basis"]
    both = [x["curated"]["title"] for x in c["overlap"]["in_both"]]
    assert both == ["NVIDIA and Supply Chain Partners Expand Capacity to Accelerate AI Infrastructure Buildout"]
    only_new = {e["title"] for e in c["overlap"]["only_discovered"]}
    assert any("Oracle" in t for t in only_new) and any("Meta" in t for t in only_new) and any("Conference Call" in t for t in only_new)
    assert len(c["overlap"]["only_curated"]) == 4 and all(e["published_date"] < "2026-10-21" for e in c["overlap"]["only_curated"])
    assert len(c["how_they_differ"]) == 3 and "benchmark" in c["how_they_differ"][0]


def test_compare_when_discovery_is_unavailable_still_shows_the_curated_side(tmp_path, monkeypatch):
    monkeypatch.delenv("CCRIG_ENABLE_STUDIO", raising=False)
    c = bridge.compare("NVDA")
    assert c["curated"]["count"] == 5 and c["discovered"]["available"] is False and "operator" in c["discovered"]["reason_unavailable"] and c["overlap"]["in_both"] == []


# ------------------------------------------------------------------ HTTP: the map's endpoints and the operator's
def map_client():
    a = FastAPI()
    a.include_router(impact_map.router)
    return TestClient(a)


def test_the_map_api_serves_both_modes_and_defaults_to_curated(ws):
    run_nvda(ws)
    c = map_client()
    assert "mode" not in c.get("/api/impact-map/NVDA/events").json()                                   # the curated response is exactly what it always was
    d = c.get("/api/impact-map/NVDA/events?mode=discovered&as_of=2026-11-01").json()
    assert d["mode"] == "discovered" and d["available"] and len(d["events"]) == 4
    assert c.get("/api/impact-map/NVDA/events?mode=nonsense").status_code == 422
    assert c.get("/api/impact-map/NVDA/compare").json()["discovered"]["count"] == 4
    assert c.get("/api/impact-map/NOPE/compare").status_code == 404


def test_without_the_studio_the_discovered_mode_says_so_instead_of_pretending(monkeypatch):
    monkeypatch.delenv("CCRIG_ENABLE_STUDIO", raising=False)
    d = map_client().get("/api/impact-map/NVDA/events?mode=discovered").json()
    assert d["available"] is False and d["unavailable_code"] == "STUDIO_DISABLED" and d["events"] == [] and d["curated_available"] is True and "simulated" in d["explanation"]


def operator_client():
    a = FastAPI()
    a.include_router(studio.router)
    a.include_router(studio_ops.router)
    return TestClient(a), {"X-Studio-Token": "t0ken"}


def test_the_operator_api_runs_discovery_and_stays_honest_when_the_network_is_off(ws, monkeypatch):
    monkeypatch.delenv("CCRIG_DISCOVERY_NETWORK", raising=False)
    c, h = operator_client()
    assert c.post("/api/studio/discovery/run", json={"query": "NVIDIA"}).status_code == 401
    info = c.get("/api/studio/discovery/providers", headers=h).json()
    assert info["network_enabled"] is False and info["ai_configured"] is False and {p["id"] for p in info["providers"]} == {"nvidia_newsroom_feed", "federal_register"}
    run = c.post("/api/studio/discovery/run", json={"query": "NVIDIA", "window_days": 90}, headers=h).json()
    assert run["status"] == "NO_EVENTS" and all(p["status"] == "UNAVAILABLE" for p in run["providers"]) and run["events"] == []
    assert c.get("/api/studio/discovery/resolve?q=Samsung", headers=h).json()["rule"] == "DENIED_ALIAS"
    assert c.post("/api/studio/discovery/run", json={"query": "NVIDIA", "limit": 9}, headers=h).status_code == 422
    assert c.get(f"/api/studio/discovery/runs/{run['run_id']}", headers=h).json()["run_id"] == run["run_id"]
    assert c.get("/api/studio/discovery/runs/nope", headers=h).status_code == 404 and len(c.get("/api/studio/discovery/runs", headers=h).json()["runs"]) == 1


# ------------------------------------------------------------------ the Studio's own validation re-checks stored evidence
def stage_rows(store, rows, source_id="forged"):
    from app.studio import pipeline
    from app.studio.store import canonical_json

    return pipeline.ingest(store, canonical_json({"discovered_events": rows}).encode(), source_id=source_id, filename="e.json", target="discovered_events", scope="NVDA",
                           operator="tester", as_of=AS_OF)["job"]


def codes_of(store, job):
    return {f["code"] for f in store.findings(job["job_id"]) if f["severity"] == "ERROR"}


def test_edited_or_forged_evidence_cannot_pass_staging(ws):
    rows = run_nvda(ws)["events"]
    forged = json.loads(json.dumps(rows[0]))
    forged["evidence_quotes"] = ["NVIDIA announced something that the source never said, in these exact words."]
    assert "EVIDENCE_NOT_FOUND" in codes_of(ws, stage_rows(ws, [forged], "f1"))
    moved = json.loads(json.dumps(rows[0]))
    moved["published_date"] = "2026-10-01"
    moved["event_date"] = "2026-10-01"
    assert "EVIDENCE_NOT_FOUND" in codes_of(ws, stage_rows(ws, [moved], "f2"))
    missing = json.loads(json.dumps(rows[0]))
    missing["source_sha256"] = "0" * 64
    assert "EVIDENCE_MISSING" in codes_of(ws, stage_rows(ws, [missing], "f3"))
    future = json.loads(json.dumps(rows[0]))
    future["event_date"] = "2026-11-30"
    assert {"EVENT_AFTER_PUBLICATION"} <= codes_of(ws, stage_rows(ws, [future], "f4"))
    scenario = json.loads(json.dumps(rows[0]))
    scenario["title"] = "Scenario: " + scenario["title"]
    assert "SCENARIO_NOT_EVENT" in codes_of(ws, stage_rows(ws, [scenario], "f5"))
    unapproved = json.loads(json.dumps(rows[0]))
    unapproved["source_url"] = "http://nvidianews.nvidia.com/x"
    assert "INVALID_URL" in codes_of(ws, stage_rows(ws, [unapproved], "f6"))
    untouched = stage_rows(ws, [rows[0]], "genuine")
    assert not untouched["blocking"], "the unmodified row passes the same checks"
