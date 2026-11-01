"""Ingest Bench events: the ProgressReporter's validation and schema, the SSE route (gating, resume, ending), and the scripted demo run's honesty flag."""
import json
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import ingest_events as ie
from app.main import app as main_app            # imported at collection time, when the Studio is not enabled

TOKEN, H = "ingest-token", {"X-Studio-Token": "ingest-token"}
SOURCES = [{"name": "exposures.parquet", "totalRows": 100, "domain": "credit"}, {"name": "market_ticks", "totalRows": 50, "domain": "market"}]
CHECKS = {"completeness": 0.9, "schemaMatch": 0.9, "duplicates": 10, "ratingMap": 0.5, "creditEvents": 3, "freshness": 12}
RMS = {"credit": 300.0, "market": 200.0, "signals": 120.0}


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    monkeypatch.setenv("CCRIG_ENABLE_STUDIO", "1")
    monkeypatch.setenv("CCRIG_STUDIO_TOKEN", TOKEN)
    monkeypatch.setenv("CCRIG_STUDIO_DIR", str(tmp_path / "ws"))
    ie._runs.clear()
    yield
    ie._runs.clear()


@pytest.fixture
def client():
    a = FastAPI()
    a.include_router(ie._build_router())
    return TestClient(a)


def progress(rep, stage="A", **kw):
    rep.progress(stage, "Haiku", rows_by_source={"exposures.parquet": 40}, tokens=1000, loss=0.08, rms_by_domain=RMS, checks=CHECKS, throughput=1000, latency_p95_ms=200, **kw)


def run_to_end(rep):
    rep.start(SOURCES)
    progress(rep, active_field="cpty_id", progress=0.3)
    rep.log("Haiku", "parsing exposures.parquet")
    rep.stage_done("A", 127, 0.0294)
    rep.complete(14.2)


def parse(body: str):
    out = []
    for block in body.split("\n\n"):
        eid = next((l[4:] for l in block.splitlines() if l.startswith("id: ")), None)
        data = next((l[6:] for l in block.splitlines() if l.startswith("data: ")), None)
        if data:
            out.append((int(eid), json.loads(data)))
    return out


def test_events_follow_the_documented_schema():
    rep = ie.ProgressReporter("r1")
    run_to_end(rep)
    evs = [e for _, e in ie.channel("r1").history]
    assert [e["type"] for e in evs] == ["run_started", "progress", "log", "stage_completed", "run_completed"]
    assert evs[0] == {"type": "run_started", "runId": "r1", "sources": SOURCES, "simulated": False}
    p = evs[1]
    assert set(p) == {"type", "stage", "agent", "rowsBySource", "tokens", "loss", "rmsByDomain", "checks", "throughput", "latencyP95Ms", "activeField", "progress"} and p["activeField"] == "cpty_id"
    assert evs[3] == {"type": "stage_completed", "stage": "A", "residualBp": 127.0, "loss": 0.0294} and evs[4] == {"type": "run_completed", "elapsedS": 14.2}
    assert [i for i, _ in ie.channel("r1").history] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("call", [
    lambda r: r.progress("E", "x", rows_by_source={}, tokens=1, loss=0.1, rms_by_domain=RMS, checks=CHECKS, throughput=1, latency_p95_ms=1),
    lambda r: r.progress("A", "x", rows_by_source={}, tokens=1, loss=float("nan"), rms_by_domain=RMS, checks=CHECKS, throughput=1, latency_p95_ms=1),
    lambda r: r.progress("A", "x", rows_by_source={}, tokens=1, loss=0.1, rms_by_domain={"credit": 1}, checks=CHECKS, throughput=1, latency_p95_ms=1),
    lambda r: r.progress("A", "x", rows_by_source={}, tokens=1, loss=0.1, rms_by_domain=RMS, checks={"completeness": 1}, throughput=1, latency_p95_ms=1),
    lambda r: r.progress("A", "x", rows_by_source={}, tokens=1, loss=0.1, rms_by_domain=RMS, checks=CHECKS, throughput=1, latency_p95_ms=1, progress=1.5),
    lambda r: r.stage_done("Z", 1, 1), lambda r: r.start([{"name": "x", "totalRows": 1, "domain": "other"}]),
])
def test_invalid_reports_are_refused_and_publish_nothing(call):
    rep = ie.ProgressReporter("bad")
    with pytest.raises(ValueError):
        call(rep)
    assert ie.channel("bad").history == []


def test_long_text_is_truncated_and_history_is_bounded(monkeypatch):
    monkeypatch.setattr(ie, "MAX_EVENTS", 10)
    rep = ie.ProgressReporter("big")
    rep.log("a" * 1000, "m" * 1000)
    assert len(ie.channel("big").history[0][1]["message"]) == ie.MAX_TEXT
    for i in range(30):
        rep.log("x", str(i))
    ch = ie.channel("big")
    assert len(ch.history) == 10 and ch.history[-1][0] == 31


def test_publishing_from_threads_gives_unique_ordered_ids():
    rep = ie.ProgressReporter("thr")
    ts = [threading.Thread(target=lambda: [rep.log("t", "x") for _ in range(50)]) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    ids = [i for i, _ in ie.channel("thr").history]
    assert ids == list(range(1, 201))


def test_only_the_last_runs_are_kept(monkeypatch):
    monkeypatch.setattr(ie, "MAX_RUNS", 3)
    for i in range(5):
        ie.ProgressReporter(f"r{i}")
    assert list(ie._runs) == ["r2", "r3", "r4"] and ie.channel("latest").run_id == "r4"


# ------------------------------------------------------------------ the route
def test_the_route_needs_the_operator_token_and_does_not_exist_when_the_studio_is_off(client):
    rep = ie.ProgressReporter("r1")
    rep.start(SOURCES)
    rep.complete(1)                                    # finished, so the stream below ends by itself
    assert client.get("/api/ingest/runs/r1/events").status_code == 401
    assert client.get("/api/ingest/runs/r1/events", headers={"X-Studio-Token": "wrong"}).status_code == 401
    assert not any("/api/ingest" in p for p in main_app.openapi()["paths"])           # the default deployment has no such route
    assert client.get("/api/ingest/runs/nope/events", headers=H).status_code == 404 and client.get("/api/ingest/runs/latest/events", headers=H).status_code == 200


def test_a_finished_run_streams_in_full_and_ends(client):
    run_to_end(ie.ProgressReporter("r1"))
    with client.stream("GET", "/api/ingest/runs/r1/events", headers=H) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        got = parse("".join(r.iter_text()))
    assert [e["type"] for _, e in got] == ["run_started", "progress", "log", "stage_completed", "run_completed"] and [i for i, _ in got] == [1, 2, 3, 4, 5]


def test_resuming_with_since_skips_what_was_seen(client):
    run_to_end(ie.ProgressReporter("r1"))
    with client.stream("GET", "/api/ingest/runs/r1/events?since=3", headers=H) as r:
        got = parse("".join(r.iter_text()))
    assert [i for i, _ in got] == [4, 5]


def test_events_published_while_a_client_is_connected_arrive_in_order_without_gaps(client):
    rep = ie.ProgressReporter("live")
    rep.start(SOURCES)

    def later():
        time.sleep(0.3)
        progress(rep, progress=0.5)
        rep.log("Sonnet", "dropped 4,210 duplicate trades")
        rep.error("B", "schema registry unreachable")

    t = threading.Thread(target=later)
    t.start()
    with client.stream("GET", "/api/ingest/runs/live/events", headers=H) as r:
        got = parse("".join(r.iter_text()))                       # the stream ends by itself after the error event
    t.join()
    assert [e["type"] for _, e in got] == ["run_started", "progress", "log", "error"] and [i for i, _ in got] == [1, 2, 3, 4]
    assert got[-1][1]["message"] == "schema registry unreachable"


def test_the_demo_run_is_scripted_and_flagged_simulated(client):
    r = client.post("/api/ingest/demo-run?seconds=2", headers=H).json()
    assert r["simulated"] is True
    with client.stream("GET", f"/api/ingest/runs/{r['run_id']}/events", headers=H) as s:
        got = parse("".join(s.iter_text()))
    assert got[0][1]["type"] == "run_started" and got[0][1]["simulated"] is True and got[-1][1]["type"] == "run_completed"
    assert {"progress", "log", "stage_completed"} <= {e["type"] for _, e in got}
    assert client.post("/api/ingest/demo-run?seconds=2").status_code == 401
