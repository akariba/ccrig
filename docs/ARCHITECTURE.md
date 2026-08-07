# Architecture

## Overview

CCRIG is a FastAPI backend + React/Vite frontend. The backend holds the entire dataset in memory (loaded once at startup from JSON files in `backend/data/`) and exposes it through a set of read-mostly REST endpoints. There is no database — the dataset is small enough (43 issuers, 18 counterparties, ~86 fact edges, ~80 exposure edges, 47 themes) to serve directly from Python data structures, which keeps the POC simple to run and inspect.

## The three data layers (never joined until after relevance)

The mandate's central architectural constraint is that three logically distinct kinds of relationship must **never be collapsed into one score or one table** until after candidate relevance has already been established:

| Layer | Name | Nature | Example | File |
|---|---|---|---|---|
| **A** | Fact Relations | Sourced, directional, factual | "TSM `SUPPLIES_TO` NVDA (Reuters, 2025-03-01)" | `backend/data/fact_edges.json` |
| **B** | Derived Relationships | Computed, symmetric, a *feature vector* (never a scalar) | sector/geography/supply-chain/ownership/semantic/news/market-corr(±) components between two issuers | Computed at request time by `core/scoring.py` from Layer A + market + news data — never persisted as a standalone ground-truth table |
| **C** | Counterparty Exposures | Synthetic, directional, counterparty → issuer | "CP_ALPHA has 4.2% exposure to NVDA" | `backend/data/exposure_edges.json` (clearly synthetic, see Data & Provenance) |

**Why this matters:** a counterparty's exposure percentage (Layer C) and an entity's relatedness score (Layer B) are different units and are never summed or compared directly anywhere in the UI — every screen that shows both (Counterparty 360, Event Studio's "Relevant Counterparties") explicitly labels them separately and calls out in-UI that they are not comparable.

## Request flow: candidate generation before scoring

For any "find related/relevant entities" query (Entity 360's related panel, Theme Radar drill-down, Event Studio), the pipeline is:

1. **Candidate generation** (`core/candidates.py`) — cheap, index-based retrieval from up to 5 sources:
   - shared-sector/country block
   - TF-IDF business-description nearest neighbours (`core/semantic.py`)
   - shared-theme nearest neighbours
   - market-correlation nearest neighbours (`core/market.py`)
   - direct Layer A fact-graph neighbours
   
   Each source's contribution is **instrumented and shown in the UI** (Entity 360's relationship-instrumentation KPIs: pairs considered → candidates generated → candidates retained → reduction % → number of blocking sources).

2. **Relevance scoring** (`core/scoring.py`) — only the retained candidate set is scored, using the current Model Lab weight vector, producing a per-pair **feature vector** (not a single scalar) with `n/a` for components that have no evidence for that pair (e.g. no supply-chain edge exists between two entities → `supply_chain: n/a`, not `0`).

3. **Typed path explanation** (`core/paths.py`) — every retained pair gets a deterministic, human-readable typed path (`FACT_PATH`, `DERIVED_PATH`, etc.) describing *why* it was retained, shown in the Explain panel.

This ordering (cheap retrieval → instrumented reduction → expensive scoring only on survivors) is what lets the platform simulate scaling to 100k+ entities without brute-force O(n²) pairwise scoring — see the Scalability Simulation table on the Data & Provenance page and `core/scalability.py`.

## Graph traversal & Event Studio's two ranking modes

`core/graph_store.py` builds an in-memory `networkx` multigraph from Layers A, B (materialized on demand for the current ego-graph), and C, with edge attributes tagging layer/type/direction. Two distinct, **never-mixed-unit** ranking modes are exposed for event-relevance queries (`core/ppr.py` + `core/paths.py`):

- **Mode 1 — bounded typed traversal**: BFS-style hop expansion with a fixed per-hop decay factor (0.65), producing a bounded relevance score with an explicit hop count and "via" path.
- **Mode 2 — Personalized PageRank**: a full PPR computation seeded at the detected entities, producing a PPR score.

Both appear side-by-side in Event Studio's results tables with explicit "units NOT comparable" labeling — the UI never sorts a single combined table across both.

`DebtRank`-style contagion scoring is referenced in the mandate as an experimental, non-production concept; it is **not implemented** in this POC (see `docs/LIMITATIONS.md`).

## AI layer (`app/ai/provider.py`)

An `AIProvider` abstract interface has two implementations:

- **`DeterministicProvider`** (default, always available): regex/keyword-based entity, theme, and event-type extraction; templated (non-LLM) explanation and theme-label text. Zero network calls. This is what powers the app when `AI_BASE_URL` / `AI_API_KEY` / `AI_MODEL` are unset — the app is **fully functional offline**.
- **`OpenAIProvider`** (opt-in): same interface, backed by any OpenAI-compatible chat completions endpoint, used only for parsing/labelling/explanation text. **Never used for bulk pairwise relationship scoring** — scoring is always the deterministic feature-vector pipeline in `core/scoring.py`, regardless of AI provider.

The active mode is shown at all times via the sidebar badge ("Offline deterministic mode" / AI-enabled).

## Backtest Lab and look-ahead prevention

`core/backtest.py` computes the model-predicted "top movers" score **as of the event date**, using only fact-graph edges and pre-event correlation windows (`ROLLING_WINDOW_DAYS` ending at the event's data cutoff). Observed/forward labels are computed strictly *after* T0 using `forward_move()` over a fixed forward window. The two are never allowed to share a data window, which is what prevents look-ahead bias. Only one scenario (`taiwan_earthquake_2026`) has bundled real price + news data end-to-end; the other two mandate-required scenario slots return an explicit `400 scenario '<id>' is not implemented in this POC` rather than fabricating data (see `docs/LIMITATIONS.md`).

## Frontend

React + TypeScript + Vite, one page-component per view under `frontend/src/pages/`, a typed fetch client under `frontend/src/api/`, and Cytoscape.js for the Graph Explorer's interactive ego-graph rendering (three visually distinct edge styles per layer — solid/directional for Layer A, dashed/symmetric for Layer B, dotted/directional for Layer C).

## API surface

All endpoints are namespaced under `/api/*` and registered in `backend/app/main.py`:

| Router | Prefix | Purpose |
|---|---|---|
| `entities.py` | `/api/entities` | Entity 360 data, related-candidates, explain panel |
| `counterparties.py` | `/api/counterparties` | Counterparty 360 data |
| `themes.py` | `/api/themes` | Theme Radar list + drill-down |
| `search.py` | `/api/search` | Home / AI Copilot universal search |
| `event.py` | `/api/event` | Event Studio parsing + dual-mode ranking |
| `graph.py` | `/api/graph` | Graph Explorer ego-graph queries |
| `model_lab.py` | `/api/model` | Model Lab weight presets + live re-ranking |
| `misc.py` | `/api/backtest`, `/api/provenance`, `/api/scalability`, `/health` | Backtest Lab, Data & Provenance, scalability simulation, health check |

Interactive OpenAPI docs are available at `/docs` when the backend is running.
