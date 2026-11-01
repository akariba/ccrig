"""Progress events for the Ingest Bench console: a ProgressReporter that agents call, and a Server-Sent Events route that streams what they reported.

    reporter = ProgressReporter(simulated=False)
    reporter.start(sources=[{"name": "exposures.parquet", "totalRows": 412880, "domain": "credit"}, ...])
    reporter.progress("A", "Haiku", rows_by_source={...}, tokens=1200, loss=0.08, rms_by_domain={"credit": 310, "market": 205, "signals": 120},
                      checks={...six values...}, throughput=48200, latency_p95_ms=320, active_field="cpty_id", progress=0.4)
    reporter.log("Haiku", "parsing exposures.parquet")
    reporter.stage_done("A", residual_bp=127, loss=0.0294)
    reporter.complete(elapsed_s=14.2)                    # or reporter.error("B", "schema registry unreachable")

Every call publishes one event to the run's channel: an ordered history plus one asyncio queue per connected subscriber (publishing is thread-safe, so agents may run in
threads). A client that reconnects with ?since=<last id> resumes without gaps or duplicates. Events are held in memory only (last 20 runs, 5000 events each).

The route exists only when the operator Studio is enabled (CCRIG_ENABLE_STUDIO) and needs the operator token, like every other write-adjacent route; nothing here starts an
ingestion. The demo emitter (POST /api/ingest/demo-run) publishes a SCRIPTED run flagged simulated=true, so the page can never mistake it for a real one.
"""
from __future__ import annotations

import asyncio
import json
import math
import threading
import time
import uuid
from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

STAGES = ("A", "B", "C", "D")
DOMAINS = ("credit", "market", "signals")
CHECKS = ("completeness", "schemaMatch", "duplicates", "ratingMap", "creditEvents", "freshness")
MAX_RUNS, MAX_EVENTS, MAX_TEXT = 20, 5000, 300
_runs: "OrderedDict[str, RunChannel]" = OrderedDict()
_runs_lock = threading.Lock()


class RunChannel:
    """Ordered event history for one run, plus a queue per subscriber."""

    def __init__(self, run_id: str):
        self.run_id, self.history, self.next_id, self.finished = run_id, [], 1, False
        self._subs: list = []
        self._lock = threading.Lock()

    def publish(self, event: dict) -> int:
        with self._lock:
            eid = self.next_id
            self.next_id += 1
            self.history.append((eid, event))
            if len(self.history) > MAX_EVENTS:
                del self.history[: len(self.history) - MAX_EVENTS]
            if event["type"] in ("run_completed", "error"):
                self.finished = True
            for loop, q in list(self._subs):
                try:
                    loop.call_soon_threadsafe(q.put_nowait, (eid, event))
                except RuntimeError:                       # that subscriber's loop has closed
                    self._subs.remove((loop, q))
        return eid

    def subscribe(self, loop: asyncio.AbstractEventLoop, since: int = 0):
        """Everything after `since` that already happened, then a queue for what follows (registered under the same lock, so nothing is missed or repeated)."""
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            backlog = [(i, e) for i, e in self.history if i > since]
            self._subs.append((loop, q))
        return backlog, q

    def unsubscribe(self, q) -> None:
        with self._lock:
            self._subs = [(lp, x) for lp, x in self._subs if x is not q]


def channel(run_id: str, create: bool = False) -> RunChannel | None:
    with _runs_lock:
        if run_id == "latest":
            return next(reversed(_runs.values()), None) if _runs else None
        ch = _runs.get(run_id)
        if ch is None and create:
            ch = _runs[run_id] = RunChannel(run_id)
            while len(_runs) > MAX_RUNS:
                _runs.popitem(last=False)
        return ch


def _num(x, name: str, lo: float = -math.inf, hi: float = math.inf) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not lo <= x <= hi:
        raise ValueError(f"{name} must be a finite number in [{lo}, {hi}]")
    return float(x)


class ProgressReporter:
    """What an agent calls to report progress. Each method validates its arguments, builds one typed event and publishes it."""

    def __init__(self, run_id: str | None = None, *, simulated: bool = False):
        self.run_id = run_id or f"run-{uuid.uuid4().hex[:8]}"
        self.simulated, self._t0, self._sources = simulated, time.monotonic(), []
        self.channel = channel(self.run_id, create=True)

    def _emit(self, event: dict) -> None:
        self.channel.publish(event)

    def start(self, sources: list, targets: dict | None = None) -> None:
        clean = []
        for s in sources:
            if s.get("domain") not in DOMAINS:
                raise ValueError(f"domain must be one of {DOMAINS}")
            clean.append({"name": str(s["name"])[:MAX_TEXT], "totalRows": int(_num(s["totalRows"], "totalRows", 0)), "domain": s["domain"]})
        self._sources, self._t0 = clean, time.monotonic()
        ev = {"type": "run_started", "runId": self.run_id, "sources": clean, "simulated": self.simulated}
        if targets:
            ev["targets"] = {k: _num(v, k, 0) for k, v in targets.items() if k in CHECKS}
        self._emit(ev)

    def progress(self, stage: str, agent: str, *, rows_by_source: dict, tokens: int, loss: float, rms_by_domain: dict, checks: dict, throughput: float, latency_p95_ms: float,
                 active_field: str | None = None, progress: float | None = None) -> None:
        if stage not in STAGES:
            raise ValueError(f"stage must be one of {STAGES}")
        if set(rms_by_domain) != set(DOMAINS):
            raise ValueError(f"rms_by_domain needs exactly {DOMAINS}")
        if set(checks) != set(CHECKS):
            raise ValueError(f"checks needs exactly {CHECKS}")
        ev = {"type": "progress", "stage": stage, "agent": str(agent)[:MAX_TEXT], "rowsBySource": {str(k)[:MAX_TEXT]: int(_num(v, "rows", 0)) for k, v in rows_by_source.items()},
              "tokens": int(_num(tokens, "tokens", 0)), "loss": _num(loss, "loss", 0), "rmsByDomain": {d: _num(rms_by_domain[d], d, 0) for d in DOMAINS},
              "checks": {c: _num(checks[c], c) for c in CHECKS}, "throughput": _num(throughput, "throughput", 0), "latencyP95Ms": _num(latency_p95_ms, "latency_p95_ms", 0)}
        if active_field:
            ev["activeField"] = str(active_field)[:MAX_TEXT]
        if progress is not None:
            ev["progress"] = _num(progress, "progress", 0, 1)
        self._emit(ev)

    def log(self, agent: str, message: str, ts: float | None = None) -> None:
        self._emit({"type": "log", "ts": round(time.monotonic() - self._t0 if ts is None else _num(ts, "ts", 0), 1), "agent": str(agent)[:MAX_TEXT], "message": str(message)[:MAX_TEXT]})

    def stage_done(self, stage: str, residual_bp: float, loss: float) -> None:
        if stage not in STAGES:
            raise ValueError(f"stage must be one of {STAGES}")
        self._emit({"type": "stage_completed", "stage": stage, "residualBp": _num(residual_bp, "residual_bp", 0), "loss": _num(loss, "loss", 0)})

    def complete(self, elapsed_s: float | None = None) -> None:
        self._emit({"type": "run_completed", "elapsedS": round(time.monotonic() - self._t0 if elapsed_s is None else _num(elapsed_s, "elapsed_s", 0), 1)})

    def error(self, stage: str, message: str) -> None:
        self._emit({"type": "error", "stage": str(stage)[:20], "message": str(message)[:MAX_TEXT]})


# ------------------------------------------------------------------ the route
def _build_router() -> APIRouter:
    from .routers.studio_ops import require_operator

    router = APIRouter(prefix="/api/ingest", tags=["ingest-bench"], dependencies=[Depends(require_operator)])

    @router.get("/runs/{run_id}/events")
    async def run_events(request: Request, run_id: str, since: int = Query(default=0, ge=0)):
        """Server-Sent Events: `id: N`, `event: ingest`, `data: <IngestEvent JSON>`. `run_id` may be 'latest'. Resume with ?since=<last id>."""
        ch = channel(run_id)
        if ch is None:
            raise HTTPException(404, {"code": "NO_RUN", "message": f"no run '{run_id}'"})
        backlog, q = ch.subscribe(asyncio.get_running_loop(), since)

        async def gen():
            try:
                yield "retry: 1000\n\n"
                for eid, ev in backlog:
                    yield f"id: {eid}\nevent: ingest\ndata: {json.dumps(ev, separators=(',', ':'))}\n\n"
                    if ev["type"] in ("run_completed", "error"):
                        return
                while not await request.is_disconnected():
                    try:
                        eid, ev = await asyncio.wait_for(q.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    yield f"id: {eid}\nevent: ingest\ndata: {json.dumps(ev, separators=(',', ':'))}\n\n"
                    if ev["type"] in ("run_completed", "error"):
                        return
            finally:
                ch.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @router.post("/demo-run")
    def demo_run(seconds: float = Query(default=36, ge=2, le=120)):
        """Start a SCRIPTED run in a background thread, flagged simulated=true. For trying the live path end to end; it ingests nothing and measures nothing."""
        rep = ProgressReporter(simulated=True)
        threading.Thread(target=_scripted_run, args=(rep, seconds), daemon=True).start()
        return {"run_id": rep.run_id, "simulated": True, "events_url": f"/api/ingest/runs/{rep.run_id}/events"}

    return router


def _scripted_run(rep: ProgressReporter, seconds: float) -> None:
    """A sample run on a clock (the same shape as the front end's simulator): loss decays as 0.082·e^(−3.6k)+0.0075, RMS per domain falls to ~11% of 320/210/125 bp."""
    sources = [{"name": "exposures.parquet", "totalRows": 412880, "domain": "credit"}, {"name": "ratings_feed.json", "totalRows": 18240, "domain": "credit"},
               {"name": "collateral.csv", "totalRows": 96410, "domain": "credit"}, {"name": "market_ticks", "totalRows": 1284000, "domain": "market"}, {"name": "news_stream", "totalRows": 7920, "domain": "signals"}]
    agents, base, tick = ("Haiku", "Sonnet", "Opus", "All three"), (320, 210, 125), 0.2
    rep.start(sources)
    n, per = int(seconds / tick), seconds / 4
    done_stage = 0
    for i in range(n + 1):
        t = i * tick
        k = min(1.0, t / seconds)
        stage = min(3, int(t / per))
        while done_stage < stage:
            rep.stage_done(STAGES[done_stage], base[0] * (0.11 + 0.89 * math.exp(-3.1 * (done_stage + 1) / 4)), 0.082 * math.exp(-3.6 * (done_stage + 1) / 4) + 0.0075)
            done_stage += 1
        within = (t - stage * per) / per
        e = lambda x: 1 - (1 - max(0.0, min(1.0, x))) ** 3        # noqa: E731
        rep.progress(STAGES[stage], agents[stage], rows_by_source={s["name"]: int(s["totalRows"] * (min(1.0, within * 1.4) if stage == 0 else 1)) for s in sources},
                     tokens=int(2400 * t), loss=0.082 * math.exp(-3.6 * k) + 0.0075, rms_by_domain={d: base[j] * (0.11 + 0.89 * math.exp(-3.1 * k)) for j, d in enumerate(DOMAINS)},
                     checks={"completeness": 0.61 + 0.388 * e(k * 1.15), "schemaMatch": 0.44 + 0.551 * e((k - 0.12) * 2.4), "duplicates": 4210 * e((k - 0.25) * 4), "ratingMap": e((k - 0.5) * 4),
                             "creditEvents": 128 * e((k - 0.55) * 4.5), "freshness": 42 * (1 - e((k - 0.75) * 4))},
                     throughput=48200, latency_p95_ms=180 + 140 * stage, progress=max(0.0, min(1.0, within)))
        if i % 7 == 0:
            rep.log(agents[stage], f"scripted step {i // 7 + 1}")
        time.sleep(tick)
    rep.stage_done("D", base[0] * 0.11, 0.0105)
    rep.complete(seconds)
