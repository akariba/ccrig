# Data Intelligence Studio — architecture and discovery

Status: **design only. No application code was written and no canonical data was changed** to produce this document.
Everything below marked *(verified)* was read from the repository or computed from the files on branch
`phase2/event-impact-map` (commit `509c5af`) with read-only scripts. Anything marked *(not verified)* is an assumption to confirm.

The two references (`Ingest Bench.html`, `Neural Cable Graph.html`) were read. Both are **simulations**: Ingest Bench's sources
(`exposures.parquet` 412,880 rows, `market_ticks` 1.28 M …), "Haiku/Sonnet/Opus" agents, throughput, eval loss and log lines are
hard-coded constants driven by a seeded random number generator and a timer; Neural Cable Graph's 16-node / 288-edge graph is
generated. Nothing in either is ingestion behaviour. They are used here only for layout, motion vocabulary and state-machine ideas (section 9).

---

## 0. What the investigation found (read this first)

| # | Finding | Why it matters for ingestion |
|---|---|---|
| 1 | **Canonical data is not edited as data.** `entities.json`, `fact_edges.json`, `counterparties.json`, `exposure_edges.json`, the news files and the CCR files are *generated* by hand-maintained Python dictionaries in `scripts/build_dataset.py` (652 lines) and `scripts/build_ccr_dataset.py` (524 lines). Review today = reading a git diff. | "Promotion" cannot mean "edit the JSON"; the next run of a build script would silently overwrite it. The Studio needs its own promotion target (or the build scripts must become a consumer of promoted data). |
| 2 | **There is no approval workflow for analytical data.** The only controls are: `is_synthetic` / `source_type` / `evidence_status` fields, the validation harness (baseline drift), and — for the event register only — verification-by-retrieval against an approved-source allow-list. No reviewer, no decision log, no versions. | The Studio's review/approval/ledger layers are genuinely new, not a wrapper around something existing. |
| 3 | **84 of 86 `fact_edges` are labelled `WELL_DOCUMENTED_PUBLIC` but only 2 carry an `evidence_url`** (both `REPORTED_NEWS`). Of the 34 supply/licence edges (the ones that drive relationship scoring) 2 have a link. | The status claims documentation that the data cannot show. The first high-value ingestion job is *evidence back-fill* for existing edges, not new edges. |
| 4 | **A real entity-resolution defect exists in derived data.** `core/data.py::_fuzzy_match` links entities to GLEIF records by token overlap. Result: **`ARM` (Arm Holdings plc) is bound to HSBC's LEI `MLU0ZO3ML4LN2LL2TL39`** (shared tokens "holdings", "plc"); `ARM` and `HSBC` therefore share one LEI. 3 more issuers (`SKHY`, `SSNLF`, `XOM`) have no match and 3 GLEIF keys have no usable record (`IBM`, `Exxon Mobil`, `TSM`). *(verified)* | Proves the identifier strategy in section 5 must be exact-key first and must never auto-promote a fuzzy match. Not fixed here (out of scope: "do not modify analytical models"); it is the best first profiling demo. |
| 5 | **Two different "counterparty" datasets exist and must stay separate.** Portfolio holdings: 18 synthetic `CP_*` names (`counterparties.json`, mirrored as 18 `Counterparty` nodes in `entities.json`, identical on id/name/country/region) with 80 exposure edges. CCR exposure: 19 synthetic records (`ccr_counterparties.json`, ids like `CP_HF_001`) with RC/PFE/NSE/limits/breach. **No id overlap; two names coincide** (`Kestrel Family Office` = `CP_KESTREL` vs `CP_FUND_009`; `Cascade Regional Bank Treasury` = `CP_CASCADE` vs `CP_BANK_002`) but with different legal names and attributes. Only 2 of 19 CCR records reference an issuer (`NVDA`, `LMT`). | Matches the brief: do not merge. Any link is a *reviewed crosswalk record*, never a merge. |
| 6 | **"Events" means three unrelated things:** `ccr_events.json` (4 synthetic stress scenarios), `data/events/events_nvidia.json` (8 real, verified publications), and Event Studio's free-text parser (`core/event_parser.py`). | The Studio must give each its own contract and label; ingested real events may never be mixed into scenario data. |
| 7 | **The static (GitHub Pages) build publishes everything under `backend/data/`.** `frontend/scripts/vendor-backend.mjs` copies `app/` and `data/` wholesale into `public/backend/` and a manifest; the browser downloads them. | Raw files, staging data, decision logs and anything confidential **must live outside `backend/data/`** and the vendor step must be tested to exclude them. |
| 8 | The provenance registry (`core/provenance.py`) is a hard-coded narrative: it omits the CCR datasets, the event register, calibration anchors and the product taxonomy, and calls prices "OHLC" although the files contain only `date,close`. *(verified)* | Ingestion history must become the source of truth for this registry. |
| 9 | Price series are uneven: 13 files with 650–651 daily closes (2024-01-02 → 2026-08-06; `NVDA`, `MSFT`, `TSM` have 650), `SKHY` only 20 rows from 2026-07-10. There is **no price connector in the repo**; ticker is parsed from the file name. | Profiling will flag these automatically; a connector is out of MVP scope. |
| 10 | Only one ingestion path exists: `POST /api/themes/ingest` — in-memory, news only, **off by default** (`CCRIG_ENABLE_INGEST`), max 200 docs, always stored as unverified synthetic, lost on restart, not persisted. | Good precedent for "write endpoints off by default" and "provenance cannot be forged by the caller". It is not a pipeline. |
| 11 | `FACT_GRAPH` is a `MultiDiGraph` keyed by **relation** (`key=fe["relation"]`) and fact edges have **no id**. Today there are no collisions *(verified)*, but two sources for the same `(source, relation, target)` would silently overwrite each other. | Staging must define a stable `edge_key = source|relation|target` and detect collisions *before* promotion. |
| 12 | `data/evidence/` exists on disk but is empty and untracked. | Name clash to avoid: the Studio's evidence store must not reuse this folder. |

---

## 1. Existing-data inventory

All counts verified by reading the files. "Loader" = how the app reads it. "Real/Synthetic" is what the file itself says
(`is_synthetic`, `source_type`), not an independent audit.

| File | Format · size | Records | Key | Role | Real / synthetic | Loader |
|---|---|---|---|---|---|---|
| `entities.json` | JSON · 26.6 kB | 82: 43 issuers, 18 counterparties, 14 countries, 6 sectors, 1 region | `id` (ticker-like slug, e.g. `TSM`, `SKHY`; `CP_*` for counterparties) | Entity master; nodes of every graph. Fields: `name, node_type, sector, industry, country, region, ticker, has_market_data, is_synthetic`. Only 14 issuers have a `ticker`/prices. | Issuer classification real-public (curated); the 18 counterparties synthetic | `DataStore` |
| `fact_edges.json` | JSON · 20.3 kB | 86: 43 `BELONGS_TO_SECTOR`, 31 `SUPPLIES`, 9 `OPERATES_IN`, 3 `LICENSES_TO` | none; implicit `(source, relation, target)` | **Layer A facts** (directed, `criticality` = curated judgement, `evidence_status`, optional `evidence_url`). 21 of 43 issuers touch a supply/licence edge. | "Real public" by label; 84 well-documented (no link), 2 reported-news (linked) | `DataStore` → `FACT_GRAPH` |
| `keywords.json` | JSON · 8.1 kB | 47 themes with synonyms | `id` | Theme taxonomy for Theme Radar / Event Studio | Curated | `DataStore` |
| `entity_keyword_weights.json` | JSON · 6.7 kB | 14 entities (grows to 61 at run time from news co-mentions) | entity id | Seed for the *news* feature in relationship scoring | Curated seed + runtime-derived | `DataStore` (mutated at start-up) |
| `news_real.json` | JSON · 8.9 kB | 14 documents, 2025-12-03 → 2026-07-27 (Reuters 7, Bloomberg, CNBC, TrendForce, Fortune ×2, Business Insider, White House) | `id` (`r1…`) | Headline + snippet + URL; entity and theme tags | `REAL_PUBLIC_NEWS`; URLs *not re-verified here* | `DataStore` |
| `news_synthetic.json` | JSON · 27.3 kB | 34 documents | `id` (`n1…`) | Density for Theme Radar demo | Synthetic (`SYNTHETIC_NARRATIVE`) | `DataStore` |
| `counterparties.json` | JSON · 4.2 kB | 18 | `id` (`CP_ALPHA` …) | **Portfolio-holdings universe** master (mirrored in `entities.json`) | Synthetic | `DataStore` |
| `exposure_edges.json` | JSON · 12.9 kB | 80: 56 `HOLDS_EQUITY`, 16 `HOLDS_BONDS`, 5 `LENDS_TO`, 3 `HOLDS_VIA_FUND` | none; `(counterparty, issuer, relation)` | **Layer C portfolio holdings** (`exposure_pct`) | All 80 synthetic | `DataStore` → `EXPOSURE_GRAPH` |
| `ccr_counterparties.json` | JSON · 43.0 kB | 19 | `id` (`CP_HF_001` …) | **CCR exposure universe**: `exposure` {rc, pfe, nse current/previous, settlement}, `limit` {id, type, value, as_of, source}, `breach`, `collateral`, `netting_set`, `sensitivities`, `notional`, `reference_entity_id`, `linked_event_id` … Ratings null in 19/19; limit missing in 3; 1 breach; limit source `POC_HEURISTIC` ×16 | All synthetic | `DataStore` → `CCRDataProvider` |
| `ccr_events.json` | JSON · 1.4 kB | 4 scenarios | `id` | CCR stress-scenario catalogue | Synthetic | `DataStore` |
| `ccr_model_impacts.json` | JSON · 0.6 kB | 1 run | `id` | Model-run impact summary | Synthetic | `DataStore` |
| `gleif_sample.json` | JSON · 8.7 kB | 43 name-keyed records (3 without a usable record) | company name → `lei` | LEI / legal name / country cross-check | Real (GLEIF API), fetched at build time | `DataStore` (fuzzy name match, see finding 4) |
| `gleif_level2_cache.json` | JSON · 13.5 kB | 40 name-keyed parent records | LEI | Real GLEIF ownership (direct/ultimate parent or reporting exception) → `PARENT_OF`/`SUBSIDIARY_OF` edges when both ends are tracked (currently none) | Real | `core/ownership.py` |
| `gleif_level2_demo.json` | JSON · 0.7 kB | 1 relationship | — | Isolated demo of a real parent link; not in the 43-entity graph | Real | tests only |
| `raw_prices/*.csv` | CSV · 14 files, 0.4–12.3 kB | 650–651 rows each; `SKHY` 20 | `date` (file name carries ticker + batch hash) | Daily close → return correlation (`core/market.py`) | Real-public by label; provenance of the download not recorded | `DataStore._load_prices` |
| `product_taxonomy.json` | JSON · 3.4 kB | 14 products | product code | CCR product reference | Curated reference | `ccr_priority` |
| `calibration_anchors.json` | JSON · 8.6 kB | 34 anchors (train/holdout) | none | Weak-supervision ranking constraints | `POC_EXPERT_ANCHOR` | `calibration.py` |
| `events/approved_sources.json` | JSON · 1.9 kB | 4 sources (3 in use) with tiers | `id` | **Allow-list** of domains for event evidence | Policy | `core/event_register.py` |
| `events/entity_aliases.json` | JSON · 1.3 kB | brand aliases, "must be followed by" rules, denied aliases | — | Precision rules for entity resolution in text | Policy | `core/event_entities.py` |
| `events/gazetteer.json` | JSON · 3.2 kB | 19 places (6 cities, 13 countries) | place key | Display coordinates (approximate) | Curated | `core/event_geo.py` |
| `events/events_nvidia.json` | JSON · 20.9 kB | 8 events, each `VERIFIED_BY_RETRIEVAL` | `id` (`nvda-YYYYMMDD-slug`) | Real publications with verbatim evidence; built by `scripts/event_register.py` | Real | `core/event_register.py` (offline) |

Existing validation / provenance / approval controls *(verified)*:
`is_synthetic`/`source_type` flags everywhere; `evidence_status` on facts; `core/provenance.py` registry (narrative, partly stale);
analytics-snapshot + validation baselines and a cross-process determinism sweep (`validation/`); `tests/test_ingest_hardening.py`
(ingest guard); `core/event_register.validate_event` (approved domain, verbatim quote ≥ 25 chars, date and dateline present in the retrieved text,
forbidden flags such as `hypothetical`); 656 backend tests. **Missing:** reviewer identity, decision log, versioned datasets, rollback, content hashes of sources.

---

## 2. Source-to-destination map (as it is today)

```
 AUTHORING / SOURCES                         CANONICAL FILES            RUNTIME (process start)                 OUTPUT
 ─────────────────────────────────────────  ─────────────────────────  ─────────────────────────────────────  ─────────────────────────────
 scripts/build_dataset.py  (hand dicts)  ─► entities, fact_edges,   ─┐
                                            keywords, weights,        │  DataStore (core/data.py, once)       FACT_GRAPH / EXPOSURE_GRAPH
                                            counterparties,           ├─► entities_by_id, issuer_ids …   ───► candidates → scoring → priority
                                            exposure_edges, news_*    │   TF-IDF space over entity text       semantic (TF-IDF) ─► Model Lab, Distance Map,
 scripts/build_ccr_dataset.py (hand dicts)► ccr_counterparties,     ─┤   GLEIF fuzzy match (finding 4)       Relationships, Entity 360, Backtest
                                            ccr_events, impacts       │   prices ← raw_prices/*.csv           themes (clusters) ─► Theme Radar
 external price export (no script)       ─► raw_prices/*.csv        ─┤   CCRDataProvider                      ccr_priority/materiality ─► Daily Review,
 api.gleif.org via fetch_gleif_level2.py ─► gleif_*.json            ─┘                                        Breaches, Counterparty 360
 hand-curated anchors / taxonomy         ─► calibration_anchors,       …
                                            product_taxonomy
 scripts/event_register.py (live fetch,  ─► data/events/*.json  ───────► core/event_register (offline)  ───►  /api/impact-map/* ─► Event Impact Map
   approved domains, verify quotes)
 POST /api/themes/ingest (flag off)      ─────────────────────────────► STORE.news_all (memory only)       Theme Radar (lost on restart)

 Delivery:  FastAPI (uvicorn, Render)  — same code, files read from disk
            Static (GitHub Pages)      — vendor-backend.mjs copies app/ + data/ into public/backend/ → fetched → Pyodide runs the same code
```

Things that cross dataset boundaries *by identifier* (genuinely related, verified): `fact_edges` ↔ `entities` (`id`, all endpoints resolve);
`exposure_edges` ↔ `counterparties` and `entities` (all resolve); `news_*` `entities` lists ↔ `entities` (all resolve);
`entity_keyword_weights` ↔ `entities` and `keywords`; `calibration_anchors` ↔ `entities`; `prices` ↔ `entities.ticker` (via file name);
`ccr_counterparties.reference_entity_id` ↔ `entities` (2 of 19); `ccr_counterparties.linked_event_id` ↔ `ccr_events`;
`events_nvidia` entities ↔ `entities` through the alias rules (not stored ids — resolved at read time).

Things that **only look related** (must never be joined on appearance):
* the two counterparty universes (shared names, different ids and attributes — finding 5);
* GLEIF records ↔ entities by name tokens (finding 4);
* `ccr_events` scenarios ↔ real register events (a synthetic "JPY depreciation shock" is not an event about anything real);
* sector/industry/country/theme overlaps and TF-IDF similarity ↔ documented relationships;
* "Samsung": the issuer `SSNLF` (Samsung Electronics) is not Samsung Electro-Mechanics named in an NVIDIA release (deliberately denied alias);
* news snippets that mention two companies ↔ a supply relationship.

---

## 3. Proposed architecture (ten layers)

The principle: **each layer reads only the artifact types of the layer before it, writes one new artifact type, and never edits what it read.**
Four kinds of record are kept apart on purpose:

| Kind | Meaning | Who/what makes it | Trust |
|---|---|---|---|
| **Raw observation** | Bytes, text passages or rows exactly as retrieved, with a content hash and where they came from | Connector / parser | Authentic copy, says nothing about truth |
| **Candidate** | A machine's *proposal*: an entity mention, a relationship, an event, a row mapping | Resolver / extractor | Unverified; always `PROPOSED` |
| **Verified evidence** | A quote or row whose **text was found in the stored raw bytes** by a deterministic check | Validator | Proves *"the source says this"*, not *"this is true"* |
| **Canonical record** | A record in a CCRIG dataset the platform reads | Promotion, after a named human approves | The only thing analytics may read |

| # | Layer | Responsibility | Output artifact | Mutates? |
|---|---|---|---|---|
| 1 | **Connectors / acquisition** | Fetch from an allow-listed source (HTTPS URL on an approved domain, official API, file upload on the operator's machine). SSRF, size, time and content-type limits. Never parses. | bytes + response metadata | no |
| 2 | **Raw store + immutable manifest** | Write bytes once under their SHA-256; write a `SourceManifest`. Re-fetching the same URL creates a *new* manifest pointing at the previous one. | `raw/<sha256>`, `manifests/<id>.json` | append-only |
| 3 | **Parsing + schema profiling** | Deterministic parsers (HTML→text, CSV, JSON; Parquet only in server mode). Per-file profile: columns, types, null rate, key uniqueness, value domains, date ranges, row-count anomalies. | `ParsedArtifact`, `ProfileReport` | no |
| 4 | **Data-quality validation** | Contract checks against the *target* dataset contract (section 4) and source policy: required fields, referential integrity, date sanity, duplicate keys, synthetic-flag rules, forbidden flags. Results are findings with severity; nothing is fixed silently. | `ValidationReport` | no |
| 5 | **Entity identification + resolution** | Map mentions/keys to `entity_id` with the precision-first ladder in section 5. Output states *why* (rule) and a reasoned class (`EXACT`, `ALIAS`, `NEEDS_REVIEW`, `REJECTED`), never a made-up probability. | `Mention` + `ResolutionResult` | no |
| 6 | **Evidence + relationship extraction** | Turn parsed text/rows into candidate events, relationships or records, each carrying evidence references (manifest, locator, verbatim quote). AI-assisted extraction, if ever used, is a candidate generator only and is labelled `AI_ASSISTED`. | `Candidate*` + `Evidence` | no |
| 7 | **Staging + conflict detection** | Group candidates into a `StagingSet` for one target dataset. Compare with canonical: new / duplicate / **conflict** (same `edge_key`, different attribute) / supersedes. Compute the *impact preview*: which canonical files change and whether analytical baselines would drift. | `StagingSet` | no (dry-run) |
| 8 | **Human review + approval** | A reviewer sees each candidate beside its raw evidence, approves, edits-and-approves, rejects or defers, with a reason. Decisions are append-only; approvals reference the exact candidate hash. | `ReviewDecision` log | append-only |
| 9 | **Versioned promotion** | Apply approved decisions to a *release*: new dataset files + `Release` record (before/after hashes, decision ids, validation + baseline results, parent release). Rollback restores the parent hashes. | `Release`, new dataset files | creates new version |
| 10 | **Provenance, monitoring, history** | Hash-chained ledger of every run/stage/decision/promotion; derived dashboards (source freshness, rejection reasons, review backlog). Replaces the hand-written provenance registry. | `ledger.jsonl`, derived views | append-only |

Where the checks that exist today fit: the event register's `validate_event` / `source_policy` become layer 4 for events; `event_entities`/`event_geo`
become layer 5/6 for events; the `CCRDataProvider` interface is the seam for confidential CCR feeds later (a `ProductionCCRProvider` is
already anticipated in `core/ccr_provider.py`).

---

## 4. Data contracts

All contracts are JSON (schema-validated in tests), carry `schema_version`, and are written with sorted keys so a re-run is byte-identical.

### 4.1 Source side

**`SourceManifest`** (immutable) — `manifest_id`, `source_id` (key in the allow-list), `connector`, `uri`, `retrieved_at`, `operator`,
`tool_version`, `http` {`status`, `etag`, `last_modified`, `content_type`, `final_url`}, `bytes`, `sha256`, `classification`
(`PUBLIC` | `INTERNAL` | `CONFIDENTIAL`), `is_synthetic`, `terms_note`, `previous_manifest_id`.

**`ParsedArtifact`** — `manifest_id`, `parser` + `parser_version`, `format`, `text` or `rows`, `locators` (char offset / row number for every unit).

**`ProfileReport`** — `rows`, `columns[]` {`name`, `inferred_type`, `null_rate`, `distinct`, `min`, `max`, `examples`}, `key_candidates[]`
(unique columns/tuples), `date_range`, `anomalies[]` (e.g. "650 rows vs 651 in sibling files").

**`ValidationReport`** — `target_contract`, `findings[]` {`code`, `severity` (`ERROR`/`WARN`/`INFO`), `locator`, `message`}.

### 4.2 Candidate side

**`Mention`** — `manifest_id`, `locator`, `surface`, `candidate_entity_ids[]`, `rule` (`LEI`, `TICKER_TOKEN`, `NAME_MATCH`, `BRAND_ALIAS`, `FUZZY`), `class`
(`EXACT` | `ALIAS` | `NEEDS_REVIEW` | `REJECTED`), `reason`. (Mirrors the existing rule names in `event_entities.py`.)

**`Evidence`** — `evidence_id`, `manifest_id`, `sha256`, `locator`, `quote` (verbatim), `verification` {`method: QUOTE_FOUND_IN_RAW`, `checked_at`, `ok`}. It states only that the text exists in the stored bytes.

**`CandidateEntity | CandidateRelationship | CandidateEvent | CandidateRecord`** — `candidate_id` (hash of content), `target_dataset`, `proposed` (a body that already
conforms to the canonical contract), `evidence_ids[]`, `mentions[]`, `origin` (`RULE` | `AI_ASSISTED` | `MANUAL`), `status: PROPOSED`, `conflicts[]`.

**`StagingSet`** — `staging_id`, `target_dataset`, `base_release_id`, `candidates[]`, `summary` {`new`, `duplicate`, `conflict`, `supersedes`}, `impact` {`files_changed`, `analytical_baselines_affected`: bool, `predicted_drift`}.

### 4.3 Decision and canonical side

**`ReviewDecision`** (append-only) — `decision_id`, `staging_id`, `candidate_id`, `candidate_hash`, `decision` (`APPROVE` | `APPROVE_WITH_EDIT` | `REJECT` | `DEFER`),
`reviewer`, `at`, `reason`, `edit` (JSON patch, if any), `evidence_seen[]`.

**`Release`** — `release_id` (monotonic), `parent_release_id`, `dataset`, `files[]` {`path`, `sha256_before`, `sha256_after`}, `decision_ids[]`,
`validation` {`contracts_ok`, `baseline_check`: `UNCHANGED` | `EXPECTED_DRIFT_APPROVED`}, `promoted_at`, `promoted_by`, `rollback_of`.

**Canonical contracts** (what promotion must produce — these already exist and must not change shape):

| Dataset | Required shape (today) | New provenance goes in… |
|---|---|---|
| Event register | `events_<entity>.json` — `id`, `kind`, `title`, `category`, `published_date`, `event_date`, `event_date_basis`, `location`, `sources[]`, `evidence[]`, `verification` | already in the record; add `manifest_sha256` to each source |
| Entities | `id`, `name`, `node_type`, `sector`, `industry`, `country`, `region`, `ticker`, `has_market_data`, `is_synthetic` | sidecar `identifiers.json` (below) |
| Fact edges | `source`, `target`, `relation`, `criticality`, `note`, `evidence_status`, `evidence_url` | **sidecar** `evidence_links.json` keyed by `edge_key` |
| Exposure edges / holdings | `counterparty`, `issuer`, `relation`, `exposure_pct`, `is_synthetic` | sidecar |
| CCR records | the 25 fields in `ccr_counterparties.json` (`exposure`, `limit` with explicit `limit_type`, `breach`, …) | sidecar |
| Prices | `date,close` per ticker file | manifest per file |

**Why sidecars.** `fact_edges` rows are passed through into API responses (e.g. `supply_chain_edges`), so adding fields to canonical rows changes API output
and breaks the analytical snapshot. Provenance for canonical rows is therefore stored in a **sidecar keyed by a stable id** and joined only by Studio and
Provenance views. This keeps existing baselines untouched. Stable ids: `edge_key = source|relation|target`; `entity_id` as is; holdings `counterparty|relation|issuer`.

---

## 5. Identifiers and entity resolution

**Today:** the join key is the internal `entity_id` (ticker-like slug for issuers, `CP_*` for synthetic counterparties). LEIs exist for 40/43 issuers but
were attached by fuzzy name match (finding 4); no ISIN/FIGI/CIK; tickers on 14 issuers only; no exchange (MIC) recorded.

**Strategy.**
1. Keep `entity_id` as the only internal key. Add a **sidecar identifier table** (`identifiers.json`): per `entity_id` — `lei`, `tickers[]` {`symbol`, `mic`}, `isin[]`, `cik`, `legal_names[]`, `aliases[]` {`text`, `reason`, `approved_by`}, `country`.
2. **Resolution ladder (first hit wins, stops at ambiguity):**
   `LEI exact` → `ticker + MIC exact` → `ISIN/CIK exact` → `normalised legal name + country exact` → `approved alias (with reason)` →
   everything else is `NEEDS_REVIEW` with the *candidates listed*, never auto-promoted. Short all-caps tickers resolve only as standalone uppercase tokens, product names follow
   `require_following` rules, and `denied_aliases` always win — exactly the precision-first behaviour already implemented for events.
3. Fuzzy matching may *propose* but never *decide*. The first Studio profiling job should re-run the GLEIF binding as a review queue and expose the ARM/HSBC collision.
4. **Counterparty crosswalk.** Two universes → two namespaces. A link is a `Crosswalk` record `{left: CP_KESTREL, right: CP_FUND_009, basis, status: PROPOSED|APPROVED|REJECTED}`; neither dataset is rewritten and no analytic reads a crosswalk unless a later, separate decision adopts it.
5. New entities are never created by an ingest job as a side effect; they are `CandidateEntity` records that a reviewer approves, with `is_synthetic=false` only when a real identifier backs them.

---

## 6. Deployment and security boundaries

| Capability | FastAPI server | Local development | GitHub Pages / Pyodide |
|---|---|---|---|
| Browse ingestion history, runs, review queue (read) | yes | yes | **yes — read-only snapshot** of promoted data and a *recorded* run history (clearly labelled "recorded") |
| Fetch from external sources | only with explicit flag, allow-list and egress control | **primary home** | **no** (browser cannot fetch most sites — CORS — and must not hold keys) |
| Parse/profile an operator-supplied file | yes (bounded size) | yes | optional **in-browser preview only**: the file never leaves the tab, nothing is stored or promoted |
| Write staging / decisions | disabled by default (`CCRIG_ENABLE_STUDIO=1` **and** operator token, bound to localhost or a private network) | yes | **never** |
| Promote / roll back | server operator only, or (recommended) a CLI that produces a git-reviewable change | yes | **never** |
| Parquet/PDF parsers (`pyarrow`, etc.) | yes (server-only extras, not in pinned Pyodide set) | yes | no |

Rules:
* **Workspace outside the repo and outside `backend/data/`**: `CCRIG_INGEST_DIR` (default `~/ccrig-ingest`), git-ignored. `vendor-backend.mjs` copies all of `backend/data/` into the public bundle, so a CI test must assert that no workspace file, manifest, raw file or decision can enter `public/backend/`.
* **No secrets in the repository or in any bundle.** Connector keys only from server environment variables; never returned by any endpoint; redacted from manifests.
* **Confidentiality tiers.** Real CCR/portfolio data is `CONFIDENTIAL`: processed only on the operator machine/server, never committed, never shipped to Pages. The synthetic datasets stay the only CCR data in the repo. The `CCRDataProvider` seam is where a real feed would plug in.
* **Acquisition hardening:** HTTPS only; domain allow-list from `approved_sources.json` (extended with `connector`, `rate_limit`, `terms_note`); resolve DNS and refuse private/link-local addresses; no cross-domain redirects; response size cap and timeout; content-type allow-list; identified User-Agent (SEC EDGAR returned 403 without a registered contact — earlier finding).
* **Untrusted content:** raw text is never rendered as HTML; quotes shown escaped; archives are not extracted; a poisoned page can at worst create a `PROPOSED` candidate that a human rejects.
* **No auto-promotion, ever.** AI output (if enabled later) is labelled `AI_ASSISTED` and cannot approve itself.
* The API today has no authentication (CORS is the only gate). Studio write endpoints therefore need their own operator token and must not be enabled on the public Render service.

**Storage, persistence and rollback (simplest thing that works).** Plain files plus an append-only hash-chained `ledger.jsonl`:

```
$CCRIG_INGEST_DIR/
  raw/<sha256>                 immutable bytes
  manifests/<manifest_id>.json immutable
  parsed/ profiles/ validation/ staging/<staging_id>.json
  decisions.jsonl             append-only
  releases/<release_id>/      before/ and after/ copies + release.json
  CURRENT                     pointer to the active release
  ledger.jsonl                every event, each line carries the hash of the previous line
```

No database for the MVP: one operator, kilobytes–megabytes of data, diff-ability matters, and Pyodide cannot persist. SQLite becomes worthwhile only with several concurrent
reviewers or >10⁵ observations. **Rollback** = restore the `before/` hashes of a release and move `CURRENT` back (verified by hash); the *canonical* record of history stays git:
promotion also emits the changed files as an ordinary commit/PR, so `git revert` is always available. Running processes read datasets at start-up (`DataStore` is a module singleton),
so activation of a release means a restart (or a future explicit reload) — an accepted MVP limit, documented in the UI.

---

## 7. Implementation dependencies

* **Python (server/local):** standard library only for MVP (`urllib`, `hashlib`, `json`, `csv`, `html.parser`, `ipaddress`, `socket`) — the repo already uses an in-house `html_to_text`. No new pinned dependency is required. Optional later: `pyarrow` (Parquet), a PDF text extractor (server-only; must not enter the Pyodide pin set).
* **Existing code to reuse unchanged:** `core/event_register.py` (policy + validation), `core/event_entities.py`, `core/event_geo.py`, `scripts/event_register.py` (`fetch`, `retrieve`, `check`, `record`, `verify`), `validation/` harness (baseline impact check), `browser_dispatch.py` (so read endpoints work in Pyodide).
* **Code that must be refactored, not rewritten:** `scripts/event_register.py` builds the whole register in one pass from a hard-coded `SPECS` list; the Studio needs the same steps as separate, resumable stages.
* **New backend modules (proposed):** `core/ingest/{manifest,store,connectors,parse,profile,validate,resolve,stage,review,promote,ledger}.py`, `routers/studio.py` (flag-gated), `scripts/studio.py` CLI.
* **Frontend:** a `Data Studio` page and a pure-logic module tested with node:test (same pattern as `impactmap/model.ts`); no new runtime dependency (Canvas 2D, as the Impact Map already does).
* **Repo hygiene:** `.gitignore` entry for the workspace; a vendor-exclusion test; documentation updates to `DATA_DICTIONARY.md` and the provenance registry.
* **Decisions needed from the owner** (blocking): who reviews (a single named operator is acceptable for the MVP; the log still records identity); legal/terms position on retrieving each source; whether promotion should write canonical files directly or only emit a PR.

---

## 8. Prioritised functional MVP scope

**P0 — the first workflow (section 10).** Event evidence ingestion, promoted into the event register, with full manifest/hash/review/ledger/rollback.

**P1 — evidence back-fill for existing facts.** Attach reviewed, verified evidence (manifest + verbatim quote) to the 34 supply/licence edges via the `evidence_links.json` sidecar, closing finding 3 without changing any canonical row or baseline. Same engine; the candidate type changes from `CandidateEvent` to `EvidenceLink`.

**P2 — identifier hygiene.** The GLEIF binding as a review queue (fixes finding 4 through an approved identifier sidecar, not by editing analytics); LEI/ticker/MIC capture.

**P3 — profiling of tabular drops.** CSV/JSON profiling and validation for price files and counterparty/holdings files (server/local), with the contracts above; no promotion into analytical datasets yet.

**P4 — analytical promotion.** Promotion into `fact_edges` / entities / holdings / CCR with the baseline gate: the Studio computes the predicted drift by running `validation.run --check` on the staged release and a promotion that changes analytical outputs needs an explicit `EXPECTED_DRIFT_APPROVED` decision. Requires `data.py` to read from the active release (a small, separately authorised change to the loader).

**Explicitly out of MVP:** scheduled/automatic feeds, LLM extraction, multi-user roles, a database, browser-side fetching, real CCR connectors, merging counterparty universes.

---

## 9. The animated ingestion UI (Ingest Bench / Neural Cable Graph as vocabulary, not behaviour)

**What is borrowed:** the lane/stage layout, the elapsed-time and counter strip, the log panel, replay controls, and the cable-with-travelling-particle language already used by the Impact Map.
**What is not:** invented volumes, model names, loss curves, throughput, "agents", or any progress that is not a measured quantity.

**Rule: every visual state is a function of a real record.** The UI renders a pure `StudioState` built from the run's ledger events; the animation layer has no state of its own.

| Visual | Bound to |
|---|---|
| Stage node (Acquire, Snapshot, Parse + Profile, Validate, Resolve, Stage, Review, Promote) | the stage's real status: `idle`, `running`, `ok`, `warn`, `failed`, `skipped`, `waiting-for-human` |
| Counter on a node | real counts from artifacts: bytes, rows or passages, findings by severity, mentions by class, candidates, conflicts |
| Cable between stages | an existing artifact handoff (`manifest_id → parsed → staging`); drawn only after the upstream artifact exists |
| Particle on a cable | one artifact in flight, in the direction of the data flow; none when the stage is waiting or finished |
| Source and target dataset nodes | the allow-listed source and the canonical dataset (with its current release id) |
| Log panel | ledger lines, verbatim; timestamps are real |
| Bench progress bar | only where a denominator is known (bytes received / `Content-Length`, rows parsed / rows total); otherwise an indeterminate marker, never a fabricated percentage |
| Review stage | a real queue: nothing moves while it waits for a person; "waiting for review" is shown as stillness plus a count |
| Colours | stage status and finding severity only — never "risk" or "impact" |

Layout: left = sources and run history; centre = the bench (pipeline lanes + cables, render-on-demand canvas like the Impact Map); right = inspector for the selected artifact
(raw excerpt beside the parsed result, profile table, findings, resolution reasons); bottom = review queue with candidate cards (evidence quote, resolved entities, conflicts, approve/edit/reject).
Reduced motion, an animation switch and pause-when-idle follow the Impact Map implementation. In Pages/Pyodide mode the bench shows a **recorded** run (a committed, sanitised ledger) and says so; it never simulates.

Pure, tested pieces (like `impactmap/model.ts`): `buildStudioState(ledger)`, `stageStatus`, `cableState`, `particlesFor`, `progressOf` (returns `null` unless measured).

---

## 10. The smallest genuine end-to-end workflow to build first

**"Ingest one approved-source publication into the event register, with proof, review and rollback."**

1. **Acquire** — operator enters a URL on an approved domain (from `approved_sources.json`) and a target entity (`NVDA`). The connector fetches with the hardening above.
2. **Snapshot** — bytes stored under their SHA-256; `SourceManifest` written (status, content-type, bytes, hash, time, operator).
3. **Parse + profile** — HTML → text with locators (existing `html_to_text`); profile: length, sentences, detected dates, dateline.
4. **Validate** — existing `validate_event` rules as a report: approved domain, publication date present in the text, dateline present, quotes ≥ 25 chars and verbatim, forbidden flags absent.
5. **Resolve** — existing entity/place resolution produces mentions with rules and reasons; ambiguous ones are `NEEDS_REVIEW`.
6. **Stage** — a `CandidateEvent` in the existing register shape, evidence quotes chosen by the operator from the text; conflict check against `events_nvidia.json` (same URL or same date+title = duplicate); impact preview ("changes `events_nvidia.json` only; analytical baselines unaffected").
7. **Review** — a person sees the quote highlighted in the stored raw text beside the proposed record; approves, edits or rejects with a reason; the decision is appended to the log.
8. **Promote** — a new release of `events_nvidia.json` (before/after hashes, decision ids); `validation.run --check` and the register verifier must pass; the event appears in the Event Impact Map after restart.
9. **Rollback** — one command restores the previous release; hashes verify; the event disappears.
10. **History** — the ledger shows every step with hashes; a Data Studio view replays it.

Why this one: it touches **no analytical dataset or baseline**, reuses most of the existing, tested code (fetch, text extraction, quote verification, entity and place resolution, source policy),
is genuinely end-to-end (real network → real bytes → real validation → human decision → versioned promotion → visible in the product), and proves each layer's contract before higher-risk datasets (P1–P4) depend on it.

---

## 11. Test strategy and acceptance criteria

**Layer tests (unit, deterministic, no network):** connector refusals (non-HTTPS, off-allow-list, private IP, oversize, wrong content-type, off-domain redirect); manifest immutability and hash correctness; parser
locators round-trip to the source offsets; profiler anomalies on fixture files (including a 650-vs-651-row series and a 20-row series); validators produce exactly the expected findings on valid, tampered and adversarial inputs
(truncated quote, altered date, hypothetical flag); resolution ladder cases (ARM vs HSBC token-overlap case must come out `NEEDS_REVIEW`, never `EXACT`; Samsung denied alias; RTX-product vs company);
conflict detection (`edge_key` collision, duplicate URL).

**Contract tests:** every artifact validates against its JSON schema; canonical outputs of promotion validate against the *existing* dataset contracts and loaders (`core/event_register.validate_register`).

**End-to-end tests (fixture raw snapshot committed, network mocked):** the workflow in section 10 produces byte-identical staging output across `PYTHONHASHSEED` values; re-ingesting identical bytes creates no duplicate candidate; approve → promote → loader reads the new release → API returns the event;
rollback restores byte-identical files; a tampered raw file makes verification fail and blocks promotion; promotion is refused without an approval or when baselines would drift without an `EXPECTED_DRIFT_APPROVED`.

**Security tests:** SSRF set (localhost, 169.254.x, DNS rebinding to private IP); path traversal in uploads; oversized and zip-bomb inputs; script injection in titles/quotes is rendered inert; Studio endpoints return 404/403 when the flag or token is absent; secrets never appear in any response, manifest or bundle.

**Deployment tests:** a build test proves `public/backend/` contains no workspace content; Pyodide static check still passes (read-only history endpoints work through `browser_dispatch`); Studio write routes are absent from the static dispatcher.

**UI tests:** the visual state is a pure function of the ledger (unit-tested); no animation when idle; a failed stage shows its real finding and stops downstream cables; review-waiting shows stillness; reduced-motion and animation-off remove all particles; keyboard review path (approve/reject) works; Playwright run in dev and static (recorded) modes.

**Acceptance criteria for the MVP (all must hold):**
1. Every promoted event traces to a stored raw file by SHA-256 and a verbatim quote found in it.
2. No candidate reaches a canonical file without a recorded human decision naming the candidate hash.
3. `validation.run --check`, the full backend suite, the Pyodide verification and the browser suites pass before and after a promotion.
4. Rollback returns every changed file to its previous hash.
5. Re-running any stage on the same inputs yields identical artifacts.
6. No UI element shows a number that is not a measured quantity or a record count.
7. Nothing from the workspace appears in the static bundle; Studio writes are impossible in Pages mode and off by default on the public server.
8. The synthetic and real data labels are preserved end to end; ingested items are never labelled more trusted than their evidence.

---

## 12. Open risks

* **Terms of use / robots / rate limits** per source are not yet recorded; the allow-list must carry them before any connector is enabled.
* **Single reviewer:** four-eyes control is impossible with one operator; the log records identity but not independence.
* **Process-start data loading:** a promotion needs a restart to take effect.
* **Finding 3 and 4 are existing data-quality defects** the Studio will expose; fixing them is a *data* decision (and may move baselines), not part of this design.
* **Verification ≠ truth:** a verified quote proves the publisher said it. Primary-issuer statements are promotional (already noted in the source limits); the review UI must keep `source tier` and `limits` next to every quote.
