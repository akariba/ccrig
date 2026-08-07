# BUILD_REPORT — CCRIG AI Analyst Platform (POC)

## 1. What I actually implemented

A working, locally runnable, full-stack proof of concept built to `BUILD_MANDATE.md`: a FastAPI backend (~2,475 lines of Python across `app/routers`, `app/core`, `app/ai`, `app/pipelines`) and a React + TypeScript + Vite frontend (~1,484 lines of TypeScript/TSX), talking over a REST API.

**All 10 required views are implemented and interactive**, verified live via Playwright QA (screenshots in `screenshots/`):

1. **Home / AI Copilot** — universal search box, 6 required sample scenarios (`IBM`, `Taiwan`, `AI bubble`, the Taiwan earthquake narrative, `TSM supply chain`, `SKHY`), intent resolution, offline-mode badge.
2. **Theme Radar** — scatter chart + full 47-theme table, drill-down with mentions/entities/counterparties KPIs, evidence list with real/synthetic badges. Fixed a theme-label capitalization bug during QA (see §6).
3. **Entity 360** — GLEIF LEI badge, relationship instrumentation KPIs (pairs considered → candidates generated → retained → reduction % → blocking-source count), per-component Explain panel showing the feature vector (never a scalar, with explicit `n/a` for missing components), typed FACT_PATH explanations, directional Fact Relations table, Theme Exposure pills, Counterparties Exposed (Layer C, explicitly never comparable to relatedness units), real price chart, signed correlation table (verified negative values render unmodified, e.g. SK Hynix at -0.699).
4. **Counterparty 360** — 18-counterparty picker, synthetic-data disclaimer, Direct Holdings (Layer C), sector/theme concentration, Indirect Relationships explicitly labeled "LAYER B RELATEDNESS — NEVER SUM WITH EXPOSURE_PCT."
5. **Event Studio** — free-text/headline parsing, entity/theme/country detection, Mode 1 (bounded typed traversal, 0.65 decay/hop) and Mode 2 (Personalized PageRank) shown side by side with explicit "units not comparable" labeling, exposure-weighted relevant-counterparties table. Fixed a crash bug during QA (see §6).
6. **Graph Explorer** — interactive Cytoscape.js ego-graph, 3 visually distinct edge styles per layer (solid/directional Layer A, dashed/symmetric Layer B, dotted/directional Layer C), togglable layer checkboxes (verified: toggling off "derived" correctly drops the graph from 18 nodes/22 edges to 15/14), hop selector, clickable edges populating a "Selected Edge" detail panel with the typed relation and evidence text.
7. **Model Lab** — 8 live weight sliders (sector, geography, supply chain, ownership, semantic, news, market corr. +/-), 4 named presets (General, Supply-chain/geographic shock, Market/funding shock, Thematic/technology shock), live re-ranking table on "Recompute rank" (verified against TSM: Samsung/ASML/NVIDIA top the ranked list with a "25 scored / 15 retained" instrumentation badge).
8. **Backtest Lab** — 3 scenario pills; only `taiwan_earthquake_2026` is fully implemented with real bundled data (Precision@5 0.6, Recall@5 0.375, NDCG@5 0.6797 against real forward price moves); the other two mandate-listed scenarios (SVB-style bank funding stress, 2011 Japan earthquake) correctly return an explicit `400 scenario '<id>' is not implemented in this POC` rather than fabricating results — verified live.
9. **Data & Provenance** — KPI grid (43 issuers, 18 counterparties, 86 fact edges, 80 exposure edges, 47 themes, 14 real + 34 synthetic news docs), full data-sources registry table with `REAL_PUBLIC_DATA` / `SYNTHETIC_POC_DATA` / `DERIVED_DATA` / `AI_ASSISTED_EXTRACTION` tags, per-entity coverage table (61 entities), and a scalability simulation table (brute-force vs. candidate-first pairs, N=100 to N=500,000, with measured real-time brute-force benchmark timings).
10. **AI Copilot infrastructure** — an `AIProvider` abstract interface with a `DeterministicProvider` (regex/keyword-based, always available, zero network calls) and an optional OpenAI-compatible provider, used only for parsing/labelling/explanation text — never for bulk pairwise relationship scoring.

**Backend invariants**: 12/12 pytest tests pass (verified in a clean virtual environment against the pinned `requirements.txt`), covering candidate-generation-before-scoring ordering, signed (non-`abs()`'d) correlation, directionality preservation, Layer A/B/C separation, Event Studio's two non-mixed ranking-mode units, typed-path determinism, and evidence-quality labels never rendered as fake confidence percentages.

**Architecture is fully documented** in `docs/ARCHITECTURE.md`, `docs/DATA_DICTIONARY.md`, and `docs/LIMITATIONS.md`.

## 2. What data is real

- **Daily close price history** for 14 of 43 issuers (`backend/data/raw_prices/*.csv`), sourced from the user-provided CSVs, `2024-01-01` through `2026-08-06`.
- **GLEIF Legal Entity Identifier records** for 40 of 43 issuers, live-fetched from the public [GLEIF API](https://api.gleif.org) at dataset build time (`backend/data/gleif_sample.json`): LEI, legal name, country, HQ city, registration status.
- **14 real public news headlines** with full source attribution and canonical URLs (`backend/data/news_real.json`) — Bloomberg, Reuters, CNBC, TrendForce, Fortune, White House fact sheets. Headline + short snippet only, no full-article redistribution.
- **86 factual relations** (`backend/data/fact_edges.json`) reflecting analyst/public knowledge as of the build date — sector membership, well-documented supply-chain relationships (e.g. TSM supplies NVDA/AMD/AAPL), and 2 edges backed by a specific dated news URL (tagged `REPORTED_NEWS`); the remaining 84 are tagged `WELL_DOCUMENTED_PUBLIC` (general public knowledge, not individually re-verified against a specific filing per edge in this POC pass).
- **Sector/industry/country classification** for all 43 real issuers.

## 3. What data is synthetic

- **All 18 counterparties** (`backend/data/counterparties.json`) — fictional hedge funds, asset managers, and insurers. No real institution's identity or holdings are represented.
- **All 80 counterparty exposure edges** (`backend/data/exposure_edges.json`) — fabricated exposure percentages, clearly tagged `is_synthetic: true`.
- **34 synthetic narrative news documents** (`backend/data/news_synthetic.json`) — generated to give Theme Radar sufficient document density for a convincing demo, tagged `is_synthetic: true` / `source_type: SYNTHETIC_NARRATIVE`, visually badged everywhere they appear in the UI.
- Every synthetic record carries an explicit `is_synthetic` flag at the data level, and every UI surface that displays synthetic data shows a visible badge or disclaimer (verified on Counterparty 360, Theme Radar evidence lists, and the Data & Provenance registry).

## 4. What remains mocked / not implemented

- **DebtRank-style contagion scoring** — referenced in the mandate as experimental/non-production; not implemented anywhere in the codebase (no endpoint, no UI element, no computation).
- **Two of three Backtest Lab scenarios** (SVB-style bank funding stress; 2011 Japan earthquake supply-chain shock) have no bundled data and correctly return an explicit `NOT_IMPLEMENTED` error rather than fabricated results.
- **GLEIF parent/child ownership relationships** are not bundled — only flat per-entity LEI records. The `PARENT_OF` fact-edge set is deliberately thin.
- Dataset breadth is 43 issuers / 47 themes rather than the mandate's illustrative 50–150 range — sized for demoability, not a coverage ceiling.
- `SKHY` has a sparse real price sample (~18–20 rows from `2026-07-10`), a genuine gap in the source data, surfaced (not hidden) in the Entity 360 chart and the Data & Provenance coverage table.

Full detail on every scope cut is in `docs/LIMITATIONS.md`.

## 5. Exact commands to run it

```bash
# Backend
cd backend
pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The bundled dataset in `backend/data/` is pre-built — no rebuild step is required to run the app. To rebuild it from source definitions: `python3 backend/scripts/build_dataset.py`. To run the invariant test suite: `cd backend && python3 -m pytest -q` (12/12 passing, verified in a clean venv against the pinned `requirements.txt`). Full instructions, including optional AI-provider configuration via `.env.example`, are in `README.md`.

## 6. QA notes (bugs found and fixed during this build)

Two real bugs were found and fixed during the Playwright QA pass, evidence of the QA rigor applied before delivery:

- **Event Studio crash**: `detected_entities`/`detected_themes` are arrays of `{id, label}` objects (not plain strings) in the API response, causing a full-page React crash ("Objects are not valid as a React child"). Fixed with type-safe extraction and made the entity pills clickable through to Entity 360. Verified fix via reload — zero console errors.
- **Theme label casing**: the deterministic theme labeller was naively `.title()`-casing multi-word labels, turning acronyms/tickers into incorrect casing (e.g. "Ai" instead of "AI"). Fixed with a casing helper that preserves known acronyms (AI, GPU, HBM, NATO, OPEC, CHIPS Act, M&A) and proper nouns (Taiwan, China, South Korea, Germany, Russia, Ukraine, Europe) while keeping common terms lowercase. Verified live against all 47 themes after a backend restart.

All 10 views were visually and functionally QA'd via a persistent Playwright session (desktop 1600×900, plus a mobile 390×844 spot-check on Home); no other layout defects (overflow, clipping, broken text) were found. This is a strong proof of concept demonstrating the complete business vision — not a final production architecture decision.
