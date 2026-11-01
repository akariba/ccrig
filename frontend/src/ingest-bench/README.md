# Ingest Bench

A live data-ingestion console drawn as an optical-bench engineering sheet: three LLM agents (Haiku, Sonnet, Opus) bring five sources into the risk dashboard, stage by stage (A parse, B validate and dedupe, C enrich, D publish). Route: **/ingest-bench**.

* `?demo=1` runs the **simulator** (36 s at 1x). Everything it shows is sample data and the page says **SIMULATED**.
* With no query it asks the backend for the latest run (`/api/ingest/runs/latest/events`). If nothing answers (or on the public static site, which has no server) it falls back to the simulator and says why.
* `?run=<run_id>` streams a specific run.

## Emitting events from an agent

The backend (operator mode: `CCRIG_ENABLE_STUDIO=1 CCRIG_STUDIO_TOKEN=...`) exposes `GET /api/ingest/runs/{run_id}/events` (Server-Sent Events, operator token in `X-Studio-Token`). Your agents publish through `ProgressReporter`, in the same process as the API:

```python
from app.ingest_events import ProgressReporter

rep = ProgressReporter()                      # add run_id="14" to choose the id; simulated=True only for scripted runs
rep.start(sources=[{"name": "exposures.parquet", "totalRows": 412880, "domain": "credit"},   # domain: credit | market | signals
                   {"name": "market_ticks", "totalRows": 1284000, "domain": "market"}])
rep.progress("A", "Haiku", rows_by_source={"exposures.parquet": 120000, "market_ticks": 400000}, tokens=4100, loss=0.081,
             rms_by_domain={"credit": 305.0, "market": 207.0, "signals": 121.0},
             checks={"completeness": 0.71, "schemaMatch": 0.47, "duplicates": 0, "ratingMap": 0.0, "creditEvents": 0, "freshness": 42},
             throughput=48200, latency_p95_ms=320, active_field="cpty_id", progress=0.3)       # progress = 0..1 within the stage (optional)
rep.log("Haiku", "parsing exposures.parquet · 412,880 rows")
rep.stage_done("A", residual_bp=127, loss=0.0294)
...
rep.complete()            # or: rep.error("B", "schema registry unreachable")
```

Call `progress` as often as you have something new (a few times per second is plenty); the UI interpolates between events. Methods validate their arguments (stage in A-D, exactly the three domains and six checks, finite numbers) and raise `ValueError` without publishing. Events are kept in memory (last 20 runs, 5000 events each); a client that reconnects resumes after the last `id` it saw. `ProgressReporter` is thread-safe.

`checks` are raw values: `completeness`, `schemaMatch`, `ratingMap` are fractions 0..1; `duplicates` is a count removed; `creditEvents` a count tagged; `freshness` minutes of lag. The gauge rings are normalised against targets (4210 duplicates, 128 credit events, 42 minutes) that a run can override: `rep.start(sources, targets={"duplicates": 9000})`.

## Event schema (`types.ts`)

```ts
run_started     { runId, sources: {name, totalRows, domain}[], simulated?, targets? }
progress        { stage: "A"|"B"|"C"|"D", agent, rowsBySource, tokens, loss, rmsByDomain, checks, throughput, latencyP95Ms, activeField?, progress? }
log             { ts, agent, message }
stage_completed { stage, residualBp, loss }
run_completed   { elapsedS }
error           { stage, message }
```
`simulated`, `targets` and `progress` are optional additions to the base schema. A run flagged `simulated: true` is always labelled SIMULATED. `POST /api/ingest/demo-run?seconds=10` (operator only) starts such a scripted run so the live path can be tried end to end.

## What is real and what is decoration

Real (from events): records, tokens, loss and its curve, RMS per domain (focus-spot size, ridgeline noise), the six checks, throughput, latency, the active field, logs, revisions. Decoration with no data behind it: the scribbles, the ray geometry, the weight heatmaps and the network's route re-routing. In a **live** run the optical-analogue numbers of the simulator (feeds/s, "% in 10 ms", BFL/EFL, Δz rows) are not shown, because nothing measured them; the page shows open sources, p95 latency and overall progress instead.

## Files

`IngestBench.tsx` layout and the single animation loop · `useIngestStream.ts` SSE + simulator + pause · `reducer.ts` (pure) · `simulator.ts` (pure) · `canvas/` pure draw functions `(ctx, view, colors, timeMs)` · `panels/` DOM panels · `tokens.css` the design tokens (light and dark; `prefers-color-scheme` or a `data-theme` attribute) · backend: `backend/app/ingest_events.py`.

Tests: `npm test` (reducer, simulator), `backend/tests/test_ingest_events.py`, `node e2e/ingest-bench-e2e.mjs` (add `E2E_LIVE=1` with an operator backend for the SSE path).
