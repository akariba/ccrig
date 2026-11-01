"""Relationship evidence: what counts as a documented relationship, how it is approved, how it reaches the graph, and what it does and does not change."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import event_discovery
from app.core.config import DATA_DIR
from app.core.graph_store import FACT_GRAPH
from app.routers import graph as graph_router, impact_map
from app.studio import impact, overlay, relationships, report, review
from app.studio.store import StudioStore
from tests.relationship_helpers import (ORACLE_QUOTE, SKHY_QUOTE, AS_OF, ingest_rows, oracle_source, rel_row, skhy_source)
from tests.studio_helpers import tree_hash


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("CCRIG_ENABLE_STUDIO", "1")
    monkeypatch.setenv("CCRIG_STUDIO_TOKEN", "t")
    monkeypatch.setenv("CCRIG_STUDIO_DIR", str(tmp_path / "ws"))
    before = tree_hash(DATA_DIR)
    edges_before = sorted((a, b, k) for a, b, k in FACT_GRAPH.edges(keys=True))
    yield StudioStore(tmp_path / "ws")
    assert tree_hash(DATA_DIR) == before, "canonical data changed"
    assert sorted((a, b, k) for a, b, k in FACT_GRAPH.edges(keys=True)) == edges_before, "the canonical graph was modified in memory"


def codes(store, job, severity=None):
    return {f["code"] for f in store.findings(job["job_id"]) if severity in (None, f["severity"])}


# ------------------------------------------------------------------ what a quote can establish
def test_wording_between_the_names_gives_the_relationship_and_its_direction():
    ok = relationships.analyse("SUPPLIES", "SKHY", "NVDA", SKHY_QUOTE)
    assert ok["both"] and ok["order"] == "TARGET_FIRST" and ok["orientation"] == "T_S" and ok["direction_ok"] is True and "supply" in ok["cue"]
    flipped = relationships.analyse("SUPPLIES", "NVDA", "SKHY", SKHY_QUOTE)                    # the same sentence cannot support the opposite direction
    assert flipped["cue"] and flipped["direction_ok"] is False
    s_t = relationships.analyse("SUPPLIES", "NVDA", "MSFT", "NVIDIA supplies Microsoft with accelerated computing systems for its data centres worldwide.")
    assert s_t["order"] == "SOURCE_FIRST" and s_t["direction_ok"] is True
    lic = relationships.analyse("LICENSES_TO", "ARM", "NVDA", "Arm Holdings plc licenses its processor architecture to NVIDIA for use in new chips.")
    assert lic["direction_ok"] is True
    assert relationships.analyse("AFFILIATED_WITH", "GOOGL", "META", "Alphabet and Meta are affiliates in this joint venture across several markets worldwide.")["direction_ok"] is True


def test_co_occurrence_is_not_a_relationship():
    base = dict(source="NVDA", target="ORCL", relation="SUPPLIES", is_synthetic=False)
    only_one = {**base, "evidence_quotes": ["NVIDIA today announced plans with a group of partners to expand global manufacturing capacity."], "assertion": {"basis": "EXPLICIT_CUE"}}
    assert relationships.check_row(only_one)[0][:2] == ("ERROR", "CO_OCCURRENCE_ONLY")
    named = {**base, "evidence_quotes": [ORACLE_QUOTE]}
    assert relationships.check_row({**named, "assertion": {"basis": "EXPLICIT_CUE"}})[0][:2] == ("ERROR", "CUE_NOT_FOUND")
    assert relationships.check_row({**named, "assertion": {}})[0][:2] == ("ERROR", "UNSUPPORTED_RELATIONSHIP_ASSERTION")
    assert relationships.check_row({**named, "assertion": {"basis": "PROPOSER_ASSERTED", "rationale": "too short"}})[0][:2] == ("ERROR", "UNSUPPORTED_RELATIONSHIP_ASSERTION")
    asserted = relationships.check_row({**named, "assertion": {"basis": "PROPOSER_ASSERTED", "rationale": "Oracle deploys NVIDIA systems, so it is NVIDIA's customer."}})
    assert asserted[0][:2] == ("WARN", "NO_EXPLICIT_CUE")
    wrong = relationships.check_row({"source": "NVDA", "target": "SKHY", "relation": "SUPPLIES", "is_synthetic": False, "evidence_quotes": [SKHY_QUOTE], "assertion": {"basis": "EXPLICIT_CUE"}})
    assert wrong[0][:2] == ("ERROR", "DIRECTION_CONFLICT")
    assert relationships.check_row({**base, "target": "NVDA", "evidence_quotes": [ORACLE_QUOTE], "assertion": {}})[0][1] == "SELF_RELATIONSHIP"


def test_a_source_page_must_be_approved_and_contain_its_title_and_date(ws):
    from tests.discovery_helpers import FIX, MANIFEST
    from tests.relationship_helpers import ORACLE_TITLE, ORACLE_URL

    page = (FIX / next(f for u, f in MANIFEST["pages"].items() if "oracle" in u)).read_bytes()
    for kw, why in ((dict(url="https://evil.example/x"), "approved"), (dict(published_date="2026-10-01"), "publication date"), (dict(title="Another title entirely"), "title")):
        args = dict(url=ORACLE_URL, published_date="2026-10-27", title=ORACLE_TITLE)
        args.update(kw)
        with pytest.raises(ValueError, match=why):
            relationships.add_source(ws, page, **args)
    ok = oracle_source(ws)
    assert len(ok["source_sha256"]) == 64 and ok["source_tier"] == "PRIMARY_ISSUER" and ws.read_raw(ok["source_sha256"]) == page


# ------------------------------------------------------------------ ingest, review, approve
def test_a_documented_relationship_is_staged_reviewed_and_approved_with_full_provenance(ws):
    src = oracle_source(ws)
    row = rel_row(src, "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE])
    job = ingest_rows(ws, [row])
    assert job["status"] == "PENDING_REVIEW" and not job["blocking"] and codes(ws, job) == {"NO_EXPLICIT_CUE"}
    stg = ws.load_staging(job["job_id"])
    assert stg["graph_effect"]["new_edges"] == 1 and stg["graph_effect"]["edges"][0]["status"] == "NEW_EDGE" and stg["assertions_to_confirm"] == [["NVDA", "SUPPLIES", "ORCL"]]
    with pytest.raises(review.ReviewError) as e:
        review.approve(ws, job["job_id"], reviewer="alice", reason="checked the release")
    assert e.value.code == "ASSERTIONS_NOT_ACKNOWLEDGED"
    done = review.approve(ws, job["job_id"], reviewer="alice", reason="the release describes OCI deploying NVIDIA systems", acknowledge_assertions=True)
    assert done["version"] == 1 and ws.current("relationship_evidence")["approved_by"] == "alice"
    decision = ws.decisions(job["job_id"])[0]
    assert decision["decision"] == "APPROVE" and decision["detail"]["assertions_confirmed"] == [["NVDA", "SUPPLIES", "ORCL"]]
    edges, release = overlay.load(ws)
    e = edges[0]
    assert (e["source"], e["relation"], e["target"], e["in_canonical"], e["status"]) == ("NVDA", "SUPPLIES", "ORCL", False, "STUDIO_APPROVED")
    ev = e["evidence"][0]
    assert ev["source_url"].startswith("https://nvidianews.nvidia.com/") and ev["quotes"] == [ORACLE_QUOTE] and ev["source_sha256"] == src["source_sha256"]
    assert ev["assertion"]["basis"] == "PROPOSER_ASSERTED" and ev["relationship_as_of"] == "2026-10-27" and ev["verification"]["status"] == "VERIFIED_BY_RETRIEVAL"
    assert ws.read_raw(ev["source_sha256"]) and release["version"] == 1


@pytest.mark.parametrize("make,expect", [
    (lambda src: rel_row(src, "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE], basis="EXPLICIT_CUE"), "CUE_NOT_FOUND"),
    (lambda src: rel_row(src, "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE], basis=None, rationale=None), "UNSUPPORTED_RELATIONSHIP_ASSERTION"),
    (lambda src: rel_row(src, "NVDA", "ORCL", "SUPPLIES", ["NVIDIA announced this on the very same day as other news."]), "EVIDENCE_NOT_FOUND"),
    (lambda src: rel_row(src, "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE], source_sha256="0" * 64), "EVIDENCE_MISSING"),
    (lambda src: rel_row(src, "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE], is_synthetic=True), "SYNTHETIC_RELATIONSHIP"),
    (lambda src: rel_row(src, "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE], as_of="2026-12-31"), "RELATIONSHIP_DATE_AFTER_SOURCE"),
    (lambda src: rel_row(src, "ORCL", "NVDA", "AFFILIATED_WITH", [ORACLE_QUOTE], rationale="Both are named as collaborators in the release text."), "SYMMETRIC_NOT_ORDERED"),
    (lambda src: rel_row(src, "NVDA", "NOT-A-COMPANY", "SUPPLIES", [ORACLE_QUOTE]), "UNRESOLVED_ENTITY"),
    (lambda src: rel_row(src, "NVDA", "ORCL", "OWNS_SOME_OF", [ORACLE_QUOTE]), "INVALID_ENUM"),
    (lambda src: rel_row(src, "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE], source_url="http://nvidianews.nvidia.com/x"), "INVALID_URL"),
])
def test_unsupported_or_unverifiable_relationship_assertions_are_blocked(ws, make, expect):
    src = oracle_source(ws)
    job = ingest_rows(ws, [make(src)])
    assert job["blocking"] and expect in codes(ws, job, "ERROR"), (expect, codes(ws, job))
    with pytest.raises(review.ReviewError) as e:
        review.approve(ws, job["job_id"], reviewer="a", reason="x", acknowledge_assertions=True, acknowledge_changes=True, acknowledge_mappings=True)
    assert e.value.code == "BLOCKED_BY_FINDINGS"


def test_evidence_for_an_existing_edge_with_an_explicit_cue_needs_no_assertion(ws):
    src = skhy_source(ws)
    job = ingest_rows(ws, [rel_row(src, "SKHY", "NVDA", "SUPPLIES", [SKHY_QUOTE], basis="EXPLICIT_CUE", cue="secure a stable supply", rationale=None)])
    assert job["status"] == "PENDING_REVIEW" and not job["blocking"] and codes(ws, job) == set()
    e = ws.load_staging(job["job_id"])["graph_effect"]["edges"][0]
    canon = FACT_GRAPH.get_edge_data("SKHY", "NVDA", "SUPPLIES")
    assert e["status"] == "EVIDENCE_FOR_CANONICAL_EDGE" and e["canonical_has_evidence_url"] is bool(canon.get("evidence_url")) and e["canonical_evidence_status"] == canon["evidence_status"]
    assert ws.load_staging(job["job_id"])["assertions_to_confirm"] == []
    review.approve(ws, job["job_id"], reviewer="alice", reason="the quoted sentence states the supply arrangement")
    edges, _ = overlay.load(ws)
    assert edges[0]["in_canonical"] is True
    g = overlay.merged_graph(edges)
    assert g.number_of_edges() == FACT_GRAPH.number_of_edges(), "evidence for an existing edge adds provenance, not a second edge"


def test_an_edge_that_runs_opposite_to_a_canonical_edge_needs_explicit_acknowledgement(ws):
    title, quote = "Test Fixture Release On Reverse Edges", "Microsoft supplies NVIDIA with cloud capacity for its internal research and development teams worldwide."
    html = f"<html><head><title>{title}</title></head><body><h1>{title}</h1><p>October 20, 2026 {quote}</p></body></html>".encode()
    src = relationships.add_source(ws, html, url="https://nvidianews.nvidia.com/news/test-reverse-edge", published_date="2026-10-20", title=title)    # a TEST FIXTURE page
    job = ingest_rows(ws, [rel_row(src, "MSFT", "NVDA", "SUPPLIES", [quote], basis="EXPLICIT_CUE", cue="supplies", rationale=None)])
    assert job["status"] == "PENDING_REVIEW" and not job["blocking"]
    edge = ws.load_staging(job["job_id"])["graph_effect"]["edges"][0]
    assert edge["status"] == "NEW_EDGE" and edge["reverse_edge_in_canonical"] is True                 # canonical has NVDA -> MSFT
    with pytest.raises(review.ReviewError) as e:
        review.approve(ws, job["job_id"], reviewer="alice", reason="supply runs both ways here")
    assert e.value.code == "CHANGES_NOT_ACKNOWLEDGED" and "opposite to an existing canonical edge" in e.value.message
    assert review.approve(ws, job["job_id"], reviewer="alice", reason="supply runs both ways here", acknowledge_changes=True)["version"] == 1


def test_financing_is_a_typed_relationship_that_is_displayed_but_never_fed_to_scoring(ws):
    title, quote = "Test Fixture Release On Financing", "Microsoft finances NVIDIA through a committed credit facility for its data centre build-out across several regions."
    html = f"<html><head><title>{title}</title></head><body><h1>{title}</h1><p>October 20, 2026 {quote}</p></body></html>".encode()
    src = relationships.add_source(ws, html, url="https://nvidianews.nvidia.com/news/test-financing", published_date="2026-10-20", title=title)           # a TEST FIXTURE page
    job = ingest_rows(ws, [rel_row(src, "MSFT", "NVDA", "FINANCES", [quote], basis="EXPLICIT_CUE", cue="finances", rationale=None)])
    assert not job["blocking"] and ws.load_staging(job["job_id"])["graph_effect"]["edges"][0]["used_by_scoring_if_adopted"] is False
    review.approve(ws, job["job_id"], reviewer="alice", reason="typed financing evidence")
    eff = impact.adoption_effect(overlay.load(ws)[0])
    assert eff["analytical_coverage"]["count"] == 0 and eff["connectivity"]["newly_connected_issuers"] == []             # shown in the graph, outside the scoring relations


# ------------------------------------------------------------------ the graph, coverage and linked counterparties
def approve_oracle(ws):
    src = oracle_source(ws)
    job = ingest_rows(ws, [rel_row(src, "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE])])
    review.approve(ws, job["job_id"], reviewer="alice", reason="OCI deploys NVIDIA systems", acknowledge_assertions=True)
    return job


def test_the_overlay_adds_the_approved_edge_to_a_copy_and_never_to_the_canonical_graph(ws):
    approve_oracle(ws)
    ov = overlay.approved(True)
    assert ov["available"] and len(ov["edges"]) == 1 and ov["release"]["version"] == 1
    g = overlay.merged_graph(ov["edges"])
    assert g.has_edge("NVDA", "ORCL", key="SUPPLIES") and not FACT_GRAPH.has_edge("NVDA", "ORCL", key="SUPPLIES")
    data = g.get_edge_data("NVDA", "ORCL", "SUPPLIES")
    assert data["criticality"] is None and data["evidence_status"] == "STUDIO_APPROVED" and data["studio"] is True


def test_the_graph_explorer_shows_the_approved_relationship_only_when_asked_and_with_its_provenance(ws):
    approve_oracle(ws)
    a = FastAPI()
    a.include_router(graph_router.router)
    c = TestClient(a)
    plain = c.get("/api/graph/ego/ORCL?layers=fact&hops=1").json()
    assert "studio_overlay" not in plain and not any(e["relation"] == "SUPPLIES" for e in plain["edges"])        # default: exactly the canonical view (ORCL has only its sector link)
    withov = c.get("/api/graph/ego/ORCL?layers=fact&hops=1&include_studio=true").json()
    assert withov["studio_overlay"]["available"] and withov["studio_overlay"]["edges_added"] == 1 and withov["studio_overlay"]["release"]["approved_by"] == "alice"
    edge = next(e for e in withov["edges"] if e["relation"] == "SUPPLIES")
    assert (edge["source"], edge["relation"], edge["target"], edge["weight"]) == ("NVDA", "SUPPLIES", "ORCL", None)
    assert edge["evidence"]["evidence_status"] == "STUDIO_APPROVED" and edge["evidence"]["studio_evidence"][0]["quotes"] == [ORACLE_QUOTE]
    assert {"ORCL", "NVDA"} <= {n["id"] for n in withov["nodes"]} and len(withov["edges"]) == len(plain["edges"]) + 1


def test_without_a_studio_the_overlay_says_it_is_unavailable(monkeypatch):
    monkeypatch.delenv("CCRIG_ENABLE_STUDIO", raising=False)
    a = FastAPI()
    a.include_router(graph_router.router)
    out = TestClient(a).get("/api/graph/ego/ORCL?layers=fact&include_studio=true").json()
    assert out["studio_overlay"]["available"] is False and "canonical dataset only" in out["studio_overlay"]["reason"] and not any(e["relation"] == "SUPPLIES" for e in out["edges"])


def test_approved_evidence_changes_connectivity_and_coverage_but_no_score(ws):
    approve_oracle(ws)
    edges, _ = overlay.load(ws)
    eff = impact.adoption_effect(edges)
    c = eff["connectivity"]
    assert c["newly_connected_issuers"] == ["ORCL"]
    assert c["with_approved"]["issuers_with_a_documented_relationship"] == c["canonical"]["issuers_with_a_documented_relationship"] + 1
    assert c["with_approved"]["issuers_without_any"] == c["canonical"]["issuers_without_any"] - 1
    assert c["with_approved"]["documented_issuer_pairs"] == c["canonical"]["documented_issuer_pairs"] + 1
    assert eff["analytical_coverage"]["scoring_changed_by_approval"] is False and eff["analytical_coverage"]["issuer_pairs_gaining_a_supply_or_ownership_component"] == [["NVDA", "ORCL"]]
    assert "criticality" in eff["analytical_coverage"]["note"] and "none is assumed" in eff["analytical_coverage"]["note"]
    linked = eff["linked_counterparties"]
    holders = {x["counterparty"] for x in linked["portfolio_holdings"]}
    assert holders == {"CP_ALPHA", "CP_HELIX", "CP_LATTICE", "CP_KESTREL", "CP_DELTA", "CP_EQUINOX"} and all(x["holds"] == "NVDA" and x["role_in_new_relationship"] == "source" for x in linked["portfolio_holdings"])
    assert [r["ccr_counterparty"] for r in linked["ccr_reference_entities"]["NVDA"]] == ["CP_FUND_009"] and linked["ccr_reference_entities"]["ORCL"] == []
    gaps = " ".join(eff["gaps"])
    assert "No portfolio counterparty in the holdings data holds ORCL" in gaps and "No CCR record references ORCL" in gaps
    assert "Wrong-way risk is not assessed" in gaps and "not an exposure amount" in gaps


def test_the_approved_relationship_changes_an_events_documented_paths_only_when_requested(ws):
    from app.discovery import bridge, service
    from tests.discovery_helpers import transport

    service.run(ws, "NVIDIA", transport=transport(), as_of=AS_OF, client=None)
    approve_oracle(ws)
    before = bridge.discovered_response("NVDA", as_of=AS_OF)
    oracle = lambda r: next(e for e in r["events"] if "Oracle" in e["title"])                      # noqa: E731
    assert next(x for x in oracle(before)["entities"] if x["entity_id"] == "ORCL")["relationship_to_target"] == "NO_DOCUMENTED_PATH"
    ov = overlay.approved(True)
    after = bridge.discovered_response("NVDA", as_of=AS_OF, graph=overlay.merged_graph(ov["edges"]))
    ent = next(x for x in oracle(after)["entities"] if x["entity_id"] == "ORCL")
    assert ent["relationship_to_target"] == "DOCUMENTED_DIRECT"
    path = next(p for p in oracle(after)["paths"] if p["entity_id"] == "ORCL" and p["relationship_type"] == "DOCUMENTED_DIRECT")
    hop = path["steps"][-1]
    assert (hop["relation"], hop["stored_edge"]) == ("SUPPLIES", {"source": "NVDA", "target": "ORCL"}) and hop["traversal"] == "AGAINST_STORED_DIRECTION"
    assert hop["evidence_status"] == "STUDIO_APPROVED" and hop["criticality"] is None
    a = FastAPI()
    a.include_router(impact_map.router)
    via_api = TestClient(a).get("/api/impact-map/NVDA/events?mode=discovered&as_of=2026-11-01&include_studio=true").json()
    assert via_api["studio_overlay"]["edges_added"] == 1 and any(x["relationship_to_target"] == "DOCUMENTED_DIRECT" for e in via_api["events"] for x in e["entities"] if x["entity_id"] == "ORCL")
    curated = TestClient(a).get("/api/impact-map/NVDA/events?include_studio=true").json()
    assert curated["register"]["coverage"] == "NVIDIA (NVDA) pilot" and curated["studio_overlay"]["requested"]
    assert json.dumps(event_discovery.discover("NVDA"), sort_keys=True) == json.dumps(TestClient(a).get("/api/impact-map/NVDA/events").json(), sort_keys=True)


def test_rolling_back_removes_the_relationship_everywhere_and_the_history_remains(ws):
    job = approve_oracle(ws)
    assert overlay.approved(True)["edges"]
    review.rollback(ws, "relationship_evidence", reviewer="bob", reason="the proposer's reading was too strong")
    assert overlay.approved(True)["edges"] == [] and overlay.approved(True)["reason"] == "No relationship evidence has been approved yet."
    assert not overlay.merged_graph(overlay.approved(True)["edges"]).has_edge("NVDA", "ORCL", key="SUPPLIES")
    assert [d["decision"] for d in ws.decisions(job["job_id"])] == ["APPROVE"] and ws.releases("relationship_evidence")[0]["status"] == "ROLLED_BACK"
    kinds = [e["kind"] for e in ws.events() if e["stage"] == "REVIEW"]
    assert "ROLLED_BACK" in kinds and "APPROVED" in kinds and ws.verify_chain()["ok"]
    review.restore(ws, "relationship_evidence", "", ws.releases("relationship_evidence")[0]["release_id"], reviewer="bob", reason="reconsidered")
    assert overlay.approved(True)["edges"][0]["target"] == "ORCL"


def test_the_quality_report_groups_findings_by_kind_of_problem(ws):
    src = oracle_source(ws)
    rows = [rel_row(src, "NVDA", "ORCL", "SUPPLIES", ["NVIDIA announced this on the very same day as other news."]),
            rel_row(src, "NVDA", "NOT-A-COMPANY", "SUPPLIES", [ORACLE_QUOTE], id="rel-nvda-supplies-nocompany-aaaaaa"),
            rel_row(src, "NVDA", "ORCL", "FINANCES", [ORACLE_QUOTE], basis="EXPLICIT_CUE", id="rel-nvda-finances-orcl-bbbbbb")]
    job = ingest_rows(ws, rows)
    rep = report.quality_report(ws, job["job_id"])
    assert rep["blocking"] and rep["verdict"].startswith("Blocked")
    cats = rep["categories"]
    assert "unsupported_relationship_assertions" in cats and "missing_references" in cats
    assert cats["unsupported_relationship_assertions"]["errors"] >= 2 and cats["missing_references"]["errors"] == 1
    assert "inconsistent_units" in rep["clean_categories"] and rep["source"]["sha256"] == job["sha256"]
    assert report.quality_report(ws, "job-99999-x") is None
