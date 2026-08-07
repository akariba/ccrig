# Known Limitations & Out-of-Scope Items

This POC intentionally demonstrates the complete business vision from `BUILD_MANDATE.md` at a scope sized for fast iteration and clear demoability, not production breadth. The items below are explicit, deliberate scope cuts — not oversights hidden from the user.

## Not implemented

- **DebtRank-style contagion scoring** is referenced in the mandate as an experimental, non-production concept and is **not implemented** in this POC. No DebtRank UI, endpoint, or computation exists anywhere in the codebase.
- **Backtest Lab scenarios**: only `taiwan_earthquake_2026` ("A magnitude 7.2 earthquake struck near Hsinchu, Taiwan…") is fully implemented end-to-end with bundled real price + news data. The two other mandate-required scenario slots — a regional bank funding-stress scenario (SVB-style) and the 2011 Japan earthquake supply-chain shock — are **NOT_IMPLEMENTED_NO_BUNDLED_DATA**: they appear as selectable (disabled-styled) pills in the UI and return an explicit `400 Bad Request: scenario '<id>' is not implemented in this POC` rather than fabricating results. This is a deliberate honesty choice per the mandate's "never fabricate data" principle.
- **GLEIF parent/child LEI relationships** are not bundled — only flat LEI/legal-name/country/status records per entity. Ownership (`PARENT_OF`) facts in `fact_edges.json` are deliberately thin (a handful of well-known parent/subsidiary relationships), not a comprehensive ownership graph.

## Scale limitations

- **Brute-force nearest-neighbour search does not scale past roughly 10,000 entities** without an approximate nearest-neighbour index (FAISS, HNSW, or similar). The current candidate-generation pipeline uses exact/brute-force similarity search (`core/semantic.py`, `core/market.py`), which is correct and fast at this POC's scale (43 issuers) but would need an ANN index swapped in before scaling to production-size universes. The Scalability Simulation table on the Data & Provenance page shows measured brute-force timings (N=100: ~0.0003s/query, N=1,000: ~0.0005s/query, N=10,000: ~0.005s/query) and projects the candidate-generation reduction ratio out to 500,000 entities — but the underlying search itself would need re-architecting past ~10k, not just more compute.
- **Dataset size**: 43 issuers (vs. a 50–100 target implied by the mandate's production vision) and 47 themes (vs. a 50–150 target). Sized for demoability and to keep Model Lab re-ranking and Graph Explorer rendering fast and legible, not as a coverage ceiling.
- **`SKHY` (SK Hynix)** has a notably sparse real price history — only ~18–20 rows starting `2026-07-10` — versus the ~2.5 years of daily data available for the other 13 priced issuers. This is a genuine gap in the bundled source CSV, not a processing bug; it is visible in Entity 360's price chart and flagged in the Data & Provenance per-entity coverage table.

## AI boundaries (by design, not a limitation to fix)

- The AI layer (`AIProvider` abstraction, `DeterministicProvider` by default) is used **only** for parsing free-text queries/events, labelling themes, and generating explanation text. It is **never** used to bulk-score entity pairs — relationship scoring is always the deterministic feature-vector pipeline in `core/scoring.py`, regardless of whether an LLM-backed provider is configured via `.env`. This is a hard architectural boundary, not a temporary gap.
- The app is fully functional with zero AI configuration (`AI_BASE_URL`/`AI_API_KEY`/`AI_MODEL` all unset) — every one of the 10 views works end-to-end offline. This was verified throughout QA.

## Data quality caveats

- Sector/country/industry classifications in `entities.json` and relation types in `fact_edges.json` reflect analyst/public knowledge as of the build date. 84 of 86 fact edges are tagged `WELL_DOCUMENTED_PUBLIC` (general public knowledge, not individually re-verified against a specific filing at build time); only 2 edges carry a specific dated news URL (tagged `REPORTED_NEWS`). This distinction is preserved and shown as an evidence-quality label in the UI — never rendered as a fake numeric confidence percentage.
- The 34-document synthetic narrative news corpus exists solely to give Theme Radar enough document density for a convincing demo; it is clearly tagged `is_synthetic: true` / `source_type: SYNTHETIC_NARRATIVE` at the record level and visually badged in every UI surface that displays it.
- All 18 counterparties and all 80 exposure edges are entirely synthetic/fictional — no real institution's actual holdings are represented or implied.

## Frontend

- The sidebar/layout is optimized for desktop analyst workflows (per the mandate's target user); it does not collapse into a hamburger menu on narrow mobile viewports. This is an intentional trade-off for an internal analyst tool, not a responsive-design bug — verified at 390px width; content remains fully readable, just alongside a persistent full-height sidebar rather than a mobile-optimized nav pattern.
- Bundle size warning (~1.09 MB / 331 KB gzipped, mostly Cytoscape.js + Recharts) — acceptable for a local/POC deployment; would warrant code-splitting for a production build.

## What a production system would need beyond this POC

- Replace brute-force candidate generation with an ANN index (FAISS/HNSW) for >10k-entity universes.
- Replace the in-memory JSON dataset with a real graph database (e.g. Neo4j) or a relational store with a graph query layer.
- Expand fact-edge sourcing to a systematic, per-edge-verified pipeline (e.g. automated 10-K/10-Q supply-chain disclosure extraction) rather than curated analyst knowledge.
- Add authentication, audit logging, and role-based access control before any real counterparty exposure data is loaded.
- Implement the remaining two backtest scenarios with real historical price + news data once sourced.
