"""The processing-flow view: structured events from real ledger rows, stage states, the Oracle-NVIDIA journey end to end, and the negative cases."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import DATA_DIR
from app.core.graph_store import FACT_GRAPH
from app.main import app as main_app            # imported at collection time, when the Studio is not enabled
from app.routers import studio, studio_ops
from app.studio import acquire, flow, overlay, pipeline, resolve, review
from app.studio.store import StudioStore
from tests.relationship_helpers import AS_OF, ORACLE_QUOTE, ingest_rows, oracle_source, rel_row
from tests.studio_helpers import tree_hash

TOKEN = "flow-token"
J = {"X-Studio-Token": TOKEN}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("CCRIG_ENABLE_STUDIO", "1")
    monkeypatch.setenv("CCRIG_STUDIO_TOKEN", TOKEN)
    monkeypatch.setenv("CCRIG_STUDIO_DIR", str(tmp_path / "ws"))
    before = tree_hash(DATA_DIR)
    edges_before = sorted((a, b, k) for a, b, k in FACT_GRAPH.edges(keys=True))
    yield StudioStore(tmp_path / "ws")
    assert tree_hash(DATA_DIR) == before, "canonical data changed"
    assert sorted((a, b, k) for a, b, k in FACT_GRAPH.edges(keys=True)) == edges_before


def states(p):
    return {s["id"]: s["state"] for s in p["stages"]}


def codes(p, stage):
    return {f["code"] for s in p["stages"] if s["id"] == stage for f in s["findings"]}


# ------------------------------------------------------------------ the mandatory journey
def test_oracle_nvidia_journey_from_source_to_overlay_and_back(ws):
    preview = flow.scenario_preview("oracle-nvidia")
    assert preview["quote_found_verbatim"] and {"NVDA", "ORCL"} <= {e["entity_id"] for e in preview["entities"]}
    assert all("not a relationship" not in m["context"] for m in preview["mentions"][:1]) and "mention is not a relationship" in preview["note"]

    naive = flow.run_scenario(ws, "oracle-nvidia", "cooccurrence", operator="op")
    pn = flow.project(ws, naive["job"]["job_id"])
    assert states(pn) == {"SOURCE": "COMPLETED", "PARSE": "COMPLETED", "PROFILE": "COMPLETED", "VALIDATE": "COMPLETED", "RESOLVE": "COMPLETED", "LLM": "SKIPPED", "EVIDENCE": "FAILED_CHECKS", "REVIEW": "BLOCKED", "PROMOTE": "SKIPPED"}
    assert pn["state"] == "BLOCKED" and "UNSUPPORTED_RELATIONSHIP_ASSERTION" in codes(pn, "EVIDENCE")
    rec = next(s for s in pn["stages"] if s["id"] == "EVIDENCE")["records"]
    assert (rec["processed"], rec["accepted"], rec["rejected"]) == (1, 0, 1)                    # the claim is counted as rejected, not proposed
    a = pn["assessments"][0]
    assert a["verdict"] == "REJECTED" and a["quotes"][0]["both"] and a["quotes"][0]["cue"] is None and a["quotes"][0]["found_in_stored_source"]
    assert not pn["review"]["can_approve"] and pn["review"]["blocked_because"]
    with pytest.raises(review.ReviewError) as e:
        review.approve(ws, naive["job"]["job_id"], reviewer="alice", reason="x", acknowledge_assertions=True)
    assert e.value.code == "BLOCKED_BY_FINDINGS"
    assert ws.current(overlay.DATASET) is None

    asserted = flow.run_scenario(ws, "oracle-nvidia", "asserted", operator="op")
    jid = asserted["job"]["job_id"]
    pa = flow.project(ws, jid)
    assert states(pa)["EVIDENCE"] == "COMPLETED_WITH_WARNINGS" and states(pa)["REVIEW"] == "AWAITING_REVIEW" and states(pa)["PROMOTE"] == "QUEUED"
    assert pa["assessments"][0]["verdict"] == "ASSERTED_NEEDS_ACKNOWLEDGEMENT"
    assert [c["state"] for c in pa["connections"]][-2:] == ["AWAITING", "IDLE"]           # paused at the gate
    prop = pa["proposal"][0]
    assert (prop["source"], prop["relation"], prop["target"]) == ("NVDA", "SUPPLIES", "ORCL") and "supplier" in prop["semantics"]["direction"]
    assert prop["provenance"]["source_sha256"] and prop["provenance"]["source_tier"] and prop["assertion"]["basis"] == "PROPOSER_ASSERTED"
    assert pa["review"]["requires"]["acknowledge_assertions"] and pa["destination"]["status"] == "NOT_PROMOTED"
    assert overlay.load(ws) == ([], None)                                                      # nothing is visible before approval

    with pytest.raises(review.ReviewError) as e:                                             # the explicit acknowledgement is preserved
        review.approve(ws, jid, reviewer="alice", reason="looks right")
    assert e.value.code == "ASSERTIONS_NOT_ACKNOWLEDGED"
    review.approve(ws, jid, reviewer="alice", reason="Confirmed against the quoted sentence.", acknowledge_assertions=True)
    pp = flow.project(ws, jid)
    assert pp["state"] == "APPROVED" and states(pp)["REVIEW"] == "APPROVED" and states(pp)["PROMOTE"] == "COMPLETED"
    d = pp["destination"]
    assert d["status"] == "LIVE_IN_OVERLAY" and d["canonical_data_modified"] is False and d["edges"] == [{"source": "NVDA", "relation": "SUPPLIES", "target": "ORCL", "visible_in_overlay": True}]
    assert any(l["href"] == "/graph?id=ORCL&studio=1" for l in d["links"]) and d["adoption"]["scoring_changed_by_approval"] is False
    assert any("no measured exposure" in g.lower() or "wrong-way" in g.lower() for g in d["adoption"]["gaps"])
    assert pp["review"]["decisions"][0]["reviewer"] == "alice"
    merged = overlay.merged_graph(overlay.load(ws)[0])
    assert merged.has_edge("NVDA", "ORCL") and not FACT_GRAPH.has_edge("NVDA", "ORCL") or any(k for k in merged["NVDA"]["ORCL"].values() if k.get("studio"))

    review.rollback(ws, overlay.DATASET, "", reviewer="bob", reason="demonstrating rollback")
    pr = flow.project(ws, jid)
    assert pr["state"] == "ROLLED_BACK" and states(pr)["PROMOTE"] == "ROLLED_BACK" and pr["destination"]["status"] == "ROLLED_BACK" and pr["destination"]["edges"] == []
    assert overlay.load(ws) == ([], None)
    assert [e["type"] for e in pr["events"] if e["stage_id"] in ("REVIEW", "PROMOTE")] == ["REVIEW_AWAITING", "REVIEW_APPROVED", "PROMOTED", "ROLLED_BACK"]    # history retained
    assert len(pr["review"]["decisions"]) == 1 and pr["ledger"]["ok"]


def test_displayed_events_match_the_backend_ledger_exactly(ws):
    out = flow.run_scenario(ws, "oracle-nvidia", "asserted", operator="op")
    jid = out["job"]["job_id"]
    review.approve(ws, jid, reviewer="alice", reason="ok", acknowledge_assertions=True)
    raw = ws.events(jid)
    shaped = flow.project(ws, jid)["events"]
    by_seq = {}
    for e in shaped:
        by_seq.setdefault(e["seq"], []).append(e)
    assert sorted(by_seq) == [r["seq"] for r in raw]                                           # every ledger row, no invention
    for r in raw:
        group = by_seq[r["seq"]]
        assert {e["hash"] for e in group} == {r["hash"]} and {e["ts"] for e in group} == {r["ts"]} and group[0]["id"] == str(r["seq"])
        assert {e["job_id"] for e in group} == {jid}
    parse = next(e for e in shaped if e["type"] == "STAGE_COMPLETED" and e["pipeline_stage"] == "PARSE")
    assert parse["records"]["processed"] == 1 and parse["records"]["rejected"] == 0 and parse["source_sha256"] == out["job"]["sha256"] and parse["source_id"] == "rel-asserted"
    resolve_ev = next(e for e in shaped if e["pipeline_stage"] == "RESOLVE" and e["type"] == "STAGE_COMPLETED")
    assert resolve_ev["resolution"]["distinct_identifiers"] == 2 and resolve_ev["resolution"]["unresolved"] == 0
    evidence_ev = next(e for e in shaped if e["pipeline_stage"] == "STAGE" and e["type"] == "STAGE_COMPLETED")
    assert evidence_ev["evidence"]["references"][0]["source_sha256"] == flow.project(ws, jid)["proposal"][0]["provenance"]["source_sha256"]
    promoted = next(e for e in shaped if e["type"] == "PROMOTED")
    assert promoted["destination"]["dataset"] == "relationship_evidence" and promoted["destination"]["canonical_data_modified"] is False and promoted["destination"]["kind"] == "STUDIO_OVERLAY"


def test_metrics_are_measured_or_declared_unavailable(ws):
    p = flow.project(ws, flow.run_scenario(ws, "oracle-nvidia", "asserted")["job"]["job_id"])
    m = p["metrics"]
    assert m["measured"]["job_elapsed_ms"] is not None and set(m["measured"]["stage_ms"]) >= {"SOURCE", "PARSE", "PROFILE", "VALIDATE", "RESOLVE", "EVIDENCE"}
    assert {u["metric"] for u in m["unavailable"]} == {"throughput", "latency_percentiles", "model_usage", "quality_score"}
    assert "throughput" not in m["measured"] and "model_usage" not in m["measured"]


# ------------------------------------------------------------------ negative cases
def test_rejected_by_the_reviewer_promotes_nothing(ws):
    jid = flow.run_scenario(ws, "oracle-nvidia", "asserted")["job"]["job_id"]
    review.reject(ws, jid, reviewer="alice", reason="The sentence does not establish a supply relationship.")
    p = flow.project(ws, jid)
    assert p["state"] == "REJECTED" and states(p)["REVIEW"] == "REJECTED" and states(p)["PROMOTE"] == "SKIPPED"
    assert p["destination"]["status"] == "NOT_PROMOTED" and overlay.load(ws) == ([], None) and ws.releases(overlay.DATASET) == []
    assert p["review"]["decisions"][0]["decision"] == "REJECT" and "nothing was promoted" in next(s for s in p["stages"] if s["id"] == "PROMOTE")["message"]


def test_duplicate_ingestion_returns_the_same_job_and_records_it(ws):
    first = flow.run_scenario(ws, "oracle-nvidia", "asserted")
    again = flow.run_scenario(ws, "oracle-nvidia", "asserted")
    assert again["duplicate"] and again["job"]["job_id"] == first["job"]["job_id"] and len(ws.list_jobs()) == 1
    ev = flow.project(ws, first["job"]["job_id"])["events"]
    dup = [e for e in ev if e["type"] == "DUPLICATE_SUBMISSION"]
    assert len(dup) == 1 and "no new job" in dup[0]["message"] and dup[0]["stage_id"] is None


def test_missing_evidence_fails_the_evidence_stage(ws):
    src = oracle_source(ws)
    row = rel_row(src, "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE], source_sha256="0" * 64)
    job = ingest_rows(ws, [row], source_id="missing-evidence")
    p = flow.project(ws, job["job_id"])
    assert states(p)["EVIDENCE"] == "FAILED_CHECKS" and "EVIDENCE_MISSING" in codes(p, "EVIDENCE") and states(p)["REVIEW"] == "BLOCKED"
    assert p["assessments"][0]["verdict"] == "REJECTED" and p["assessments"][0]["quotes"][0]["found_in_stored_source"] is None


def test_unresolved_identifier_is_reported_at_the_resolve_stage(ws):
    src = oracle_source(ws)
    row = rel_row(src, "NVDA", "Samsung", "SUPPLIES", [ORACLE_QUOTE])
    job = ingest_rows(ws, [row], source_id="unresolved-id")
    p = flow.project(ws, job["job_id"])
    assert states(p)["RESOLVE"] == "FAILED_CHECKS" and "UNRESOLVED_ENTITY" in codes(p, "RESOLVE")
    res = next(s for s in p["stages"] if s["id"] == "RESOLVE")["resolution"]
    assert res["unresolved"] == 1 and res["ambiguous"] == 0 and states(p)["REVIEW"] == "BLOCKED"


def test_ambiguous_identifier_is_reported_with_candidates_and_never_chosen(ws, monkeypatch):
    real = pipeline.resolve_distinct

    def fake(values, kind, index=None):
        out = real(values, kind, index)
        for v, r in list(out.items()):
            if v == "ORCL":
                out[v] = resolve.Resolution(value=v, status=resolve.AMBIGUOUS, rule="NAME_EXACT", reason="two issuers share this name", candidates=["ORCL", "ORCL2"])
        return out

    monkeypatch.setattr(pipeline, "resolve_distinct", fake)
    src = oracle_source(ws)
    job = ingest_rows(ws, [rel_row(src, "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE])], source_id="ambiguous-id")
    p = flow.project(ws, job["job_id"])
    assert "AMBIGUOUS_ENTITY" in codes(p, "RESOLVE") and next(s for s in p["stages"] if s["id"] == "RESOLVE")["resolution"]["ambiguous"] == 1
    assert p["state"] == "BLOCKED" and p["proposal"] == []


def test_invalid_schema_and_refused_content_skip_the_remaining_stages(ws):
    bad = pipeline.ingest(ws, json.dumps({"rows": [{"source": "NVDA"}]}).encode(), source_id="bad-schema", filename="bad.json", target="relationship_evidence", as_of=AS_OF)
    p = flow.project(ws, bad["job"]["job_id"])
    assert states(p)["VALIDATE"] == "FAILED_CHECKS" and p["state"] == "BLOCKED" and "MISSING_REQUIRED_COLUMN" in {f["code"] for f in p["quality"]["findings"]}
    refused = pipeline.ingest(ws, b"%PDF-1.7 not a table", source_id="a-pdf", filename="x.json", target="relationship_evidence", as_of=AS_OF)
    r = flow.project(ws, refused["job"]["job_id"])
    assert r["state"] == "REFUSED" and states(r)["SOURCE"] == "FAILED" and all(states(r)[s] == "SKIPPED" for s in ("PARSE", "PROFILE", "VALIDATE", "RESOLVE", "LLM", "EVIDENCE", "REVIEW", "PROMOTE"))
    assert r["job"]["error_code"] == "FORBIDDEN_CONTENT"


def test_interrupted_processing_is_shown_as_interrupted_and_promotes_nothing(ws, monkeypatch):
    def boom(*a, **k):
        raise KeyboardInterrupt()

    src = oracle_source(ws)
    with monkeypatch.context() as m, pytest.raises(KeyboardInterrupt):
        m.setattr(acquire, "parse", boom)                                                       # the process "dies" while parsing
        ingest_rows(ws, [rel_row(src, "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE])], source_id="interrupted")
    job = ws.list_jobs()[0]
    p = flow.project(ws, job["job_id"])
    assert p["job"]["status"] == "ACQUIRING" and p["state"] == "INTERRUPTED" and states(p)["SOURCE"] == "COMPLETED" and states(p)["PARSE"] == "FAILED"
    assert states(p)["REVIEW"] == "QUEUED" and p["destination"]["status"] == "NOT_PROMOTED" and ws.releases(overlay.DATASET) == []
    err = next(e for e in p["events"] if e["type"] == "STAGE_FAILED")["error"]
    assert err["type"] == "KeyboardInterrupt"


def test_history_survives_a_restart(ws, tmp_path):
    jid = flow.run_scenario(ws, "oracle-nvidia", "asserted")["job"]["job_id"]
    review.approve(ws, jid, reviewer="alice", reason="ok", acknowledge_assertions=True)
    review.rollback(ws, overlay.DATASET, "", reviewer="bob", reason="undo")
    before = flow.project(ws, jid)
    reopened = StudioStore(tmp_path / "ws")                                                    # a new process would do exactly this
    after = flow.project(reopened, jid)
    assert after == before and after["ledger"]["ok"] and after["state"] == "ROLLED_BACK"


def test_unknown_scenario_and_claim_are_refused(ws):
    with pytest.raises(flow.FlowError):
        flow.run_scenario(ws, "nope", "asserted")
    with pytest.raises(flow.FlowError):
        flow.run_scenario(ws, "oracle-nvidia", "invented")


def test_support_matrix_does_not_overclaim():
    m = flow.support_matrix()
    levels = {d["dataset"]: d["level"] for d in m["domains"]}
    assert levels["relationship_evidence"] == "SUPPORTED" and levels["ccr_exposures"] == "PARTIAL" and levels["exposure_edges"] == "PARTIAL" and levels["profile_only"] == "PROFILE_ONLY"
    assert sum(1 for v in levels.values() if v == "SUPPORTED") == 1
    ccr = next(d for d in m["domains"] if d["dataset"] == "ccr_exposures")
    assert "No measured exposure" in ccr["limits"] and "wrong-way" in ccr["limits"]
    assert next(f for f in m["formats"] if f["format"].startswith("PDF"))["level"] == "UNSUPPORTED"


# ------------------------------------------------------------------ HTTP: gating, polling, streaming
@pytest.fixture
def client(ws):
    studio_ops._store_for.cache_clear()
    a = FastAPI()
    a.include_router(studio.router)
    a.include_router(studio_ops.router)
    yield TestClient(a)
    studio_ops._store_for.cache_clear()


def test_flow_routes_need_the_operator_token_and_do_not_exist_when_disabled(client, monkeypatch):
    assert client.get("/api/studio/flow/scenarios").status_code == 401
    assert client.get("/api/studio/flow/scenarios", headers={"X-Studio-Token": "wrong"}).status_code == 401
    assert client.post("/api/studio/flow/run", json={"scenario": "oracle-nvidia", "claim": "asserted"}).status_code == 401
    assert client.get("/api/studio/flow/stream").status_code == 401
    monkeypatch.delenv("CCRIG_ENABLE_STUDIO")
    assert not any("/flow" in p for p in main_app.openapi()["paths"])


def test_api_run_poll_and_stream_agree_with_the_ledger(client):
    run = client.post("/api/studio/flow/run", headers=J, json={"scenario": "oracle-nvidia", "claim": "asserted", "operator": "api"}).json()
    jid = run["job"]["job_id"]
    polled = client.get("/api/studio/flow/events", headers=J, params={"since": 0, "job_id": jid}).json()
    raw = client.get(f"/api/studio/jobs/{jid}", headers=J).json()["events"]
    assert {e["seq"] for e in polled["events"]} == {r["seq"] for r in raw} and polled["last_seq"] == raw[-1]["seq"]
    assert client.get("/api/studio/flow/events", headers=J, params={"since": polled["last_seq"]}).json()["events"] == []        # nothing new
    half = raw[len(raw) // 2]["seq"]
    tail = client.get("/api/studio/flow/events", headers=J, params={"since": half, "job_id": jid}).json()["events"]
    full = {e["id"]: e for e in polled["events"]}
    assert all(e["id"] in full and e["records"] == full[e["id"]]["records"] for e in tail)                                       # a slice is shaped like the whole

    with client.stream("GET", "/api/studio/flow/stream", headers=J, params={"since": 0, "timeout": 0.5, "job_id": jid}) as r:
        body = "".join(r.iter_text())
    assert r.headers["content-type"].startswith("text/event-stream")
    streamed = [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:") and '"seq"' in line]
    assert [e["id"] for e in streamed] == [e["id"] for e in polled["events"]] and "event: end" in body

    # an event recorded while a client is connected arrives through the stream
    review_resp = client.post(f"/api/studio/jobs/{jid}/approve", headers=J, json={"reviewer": "alice", "reason": "ok", "acknowledge_assertions": True})
    assert review_resp.status_code == 200
    with client.stream("GET", "/api/studio/flow/stream", headers=J, params={"since": polled["last_seq"], "timeout": 0.5}) as r:
        later = "".join(r.iter_text())
    assert "REVIEW_APPROVED" in later and "PROMOTED" in later
    detail = client.get(f"/api/studio/flow/jobs/{jid}", headers=J).json()
    assert detail["state"] == "APPROVED" and detail["destination"]["status"] == "LIVE_IN_OVERLAY"
    assert client.get("/api/studio/flow/jobs/job-99999-none", headers=J).status_code == 404
    assert client.post("/api/studio/flow/run", headers=J, json={"scenario": "oracle-nvidia", "claim": "invented"}).status_code == 422


# ------------------------------------------------------------------ the language-model stage
def test_a_job_with_no_model_invocation_shows_the_llm_stage_as_skipped_never_as_running(ws):
    p = flow.project(ws, flow.run_scenario(ws, "oracle-nvidia", "asserted")["job"]["job_id"])
    llm = next(s for s in p["stages"] if s["id"] == "LLM")
    assert llm["state"] == "SKIPPED" and llm["llm"] is None and "no model invocation was recorded" in llm["message"]
    assert not any(e["stage_id"] == "LLM" and e["state"] in ("RUNNING", "COMPLETED") for e in p["events"])


def _with_llm_rows(ws, monkeypatch, *rows):
    """SYNTHETIC: make the pipeline write the given ledger rows for the LLM stage between RESOLVE and CHECK, as a model-assisted step would. The real pipeline writes none."""
    real = pipeline._resolve_rows

    def wrapped(contract, typed, findings):
        out = real(contract, typed, findings)
        jid = ws.list_jobs()[0]["job_id"]
        for kind, counts, error in rows:
            ws.add_event(jid, "LLM", kind, counts=counts, error=error)
        return out

    monkeypatch.setattr(pipeline, "_resolve_rows", wrapped)


def test_recorded_model_invocations_are_shown_exactly_as_recorded(ws, monkeypatch):
    _with_llm_rows(ws, monkeypatch, ("STARTED", None, None), ("COMPLETED", {"provider": "test-provider", "model": "test-model", "calls": 1, "latency_ms": 812, "input_tokens": 1500}, None))
    job = ingest_rows(ws, [rel_row(oracle_source(ws), "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE])], source_id="llm-shape")
    p = flow.project(ws, job["job_id"])
    ev = [e for e in p["events"] if e["stage_id"] == "LLM"]
    assert [e["state"] for e in ev] == ["RUNNING", "COMPLETED"] and states(p)["LLM"] == "COMPLETED"             # no skip event is added when a call was recorded
    assert ev[1]["llm"] == {"provider": "test-provider", "model": "test-model", "calls": 1, "latency_ms": 812, "input_tokens": 1500, "output_tokens": None}      # unrecorded stays null


def test_a_failed_model_call_is_a_failed_stage(ws, monkeypatch):
    _with_llm_rows(ws, monkeypatch, ("STARTED", None, None), ("FAILED", None, {"type": "ConnectError", "message": "provider unreachable"}))
    job = ingest_rows(ws, [rel_row(oracle_source(ws), "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE])], source_id="llm-fail")
    p = flow.project(ws, job["job_id"])
    assert states(p)["LLM"] == "FAILED" and next(e for e in p["events"] if e["type"] == "STAGE_FAILED" and e["stage_id"] == "LLM")["error"]["type"] == "ConnectError"
