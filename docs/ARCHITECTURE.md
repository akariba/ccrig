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

   **Candidate pool (layer separation).** For an issuer, all five sources draw on issuers only (`candidates.relatedness_pool`): counterparties are Layer C and reach an issuer's view through the exposure join, search and the Graph Explorer's exposure layer - never as "related" peers - and sector/country metadata nodes are not entities. A counterparty-centred query (the Distance Map) still uses the legacy all-browsable pool; changing that is part of the separately authorised Distance Map work. Pair scores do not depend on the pool.

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

## Request validation (server and in-browser)

Request constraints live in the endpoints' own signatures and request models (`Query(ge=..., le=...)`, pydantic fields, and the shared validators in `app/request_validation.py`): finite weights in [0, 1] with a positive sum and known component names only, `top_k` within `MAX_TOP_K`, bounded `max_hops` / `min_score`, non-blank bounded text, known presets. Invalid input is a `422` with FastAPI's standard error body; it is never silently coerced or ignored. Valid requests are computed exactly as before.

The GitHub Pages build has no server: `app/browser_dispatch.py` calls the endpoint functions in-process inside Pyodide. It validates parameters through pydantic from the same signatures (and resolves omitted `Query(...)` defaults), so the static build rejects and accepts exactly what the server does. `tests/test_dispatcher_parity.py` sends every case in `validation/request_cases.py` through both paths and requires identical statuses and error locations; the dispatcher refuses at import time any endpoint parameter kind it cannot reproduce (`Depends`, `Header`, `Request`, ...).

## Determinism

Every response is a pure function of the request and the shipped data: it does not depend on the process, a restart, or Python's per-process string-hash randomisation. Wherever order is part of a result it is an explicit rule, not an accident of set iteration: Counterparty 360 visits direct holdings by total exposure (largest first, ties by issuer id) before applying its 20-row cap; Event Studio keeps mentioned entities (sorted by id) before geographic ones, ranks ties by entity id, and joins counterparties in order of event relevance. `python -m validation.determinism` fingerprints ~370 responses byte for byte and `tests/test_determinism.py` runs it in separate interpreters with different `PYTHONHASHSEED` values.

## Static build runtime (GitHub Pages)

`frontend/src/api/pyodide-pins.json` is the single source of truth for the in-browser runtime: the Pyodide release (the npm `pyodide` dependency is pinned to the same exact version), the scientific packages Pyodide loads (`numpy`, `scipy`, `scikit-learn`), and exact `micropip` pins for everything fetched from PyPI (`fastapi` equal to `requirements.txt`, plus its resolved dependencies). Packages bundled by Pyodide (pydantic, networkx, ...) are fixed by the release; the file records their versions so drift is detected. These can differ from `requirements.txt` (the server's pins) - the analytical baseline in `backend/validation/` is what shows that results do not depend on the difference. pandas is not used by the application and is not installed.

Weights are also checked for *usability*: if every component carrying weight has no data (ownership has none anywhere in this dataset; market components need price history; supply-chain needs a documented edge), the request is a `422` that names the components, says why, and lists the ones that do have data - it is never answered with an empty ranking that reads as "nothing is related". Dataset-wide cases are caught in the shared `Weights` validator (every weight-taking endpoint); entity- or pair-specific cases in `/score` and `/pair` (`app/core/weight_usability.py`). Scoring itself is unchanged: weighted components with missing values are still excluded and the rest re-normalised.

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
