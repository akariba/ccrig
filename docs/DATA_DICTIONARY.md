# Data Dictionary

All files live in `backend/data/`. Every record type below carries an explicit provenance classification, also surfaced live in the Data & Provenance view (`/api/provenance`).

Provenance tags used throughout this platform:

- **`REAL_PUBLIC_DATA`** — sourced from a real, publicly available dataset or filing (market prices, GLEIF LEI registry, curated real news headlines).
- **`SYNTHETIC_POC_DATA`** — fabricated for this proof of concept, clearly labelled `is_synthetic: true` at the record level.
- **`DERIVED_DATA`** — computed at request time from Layer A/real data (e.g. Layer B relationship feature vectors, correlations). Never persisted as a separate ground-truth table.
- **`AI_ASSISTED_EXTRACTION`** — produced by the `AIProvider` (DeterministicProvider by default, or an LLM if configured) for parsing/labelling/explanation text only.

---

## `entities.json` — REAL_PUBLIC_DATA (classification) + SYNTHETIC_POC_DATA (counterparties)

Entity master for all 43 issuers + 18 counterparties (61 total nodes).

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable entity ID, usually ticker (e.g. `TSM`) or synthetic counterparty ID (e.g. `CP_ALPHA`) |
| `name` | string | Full legal/display name |
| `node_type` | string | `"Company/Issuer"` or `"Counterparty"` |
| `sector` | string | GICS-like sector label (real classification, hand-curated) |
| `industry` | string | Sub-sector / industry description |
| `country` | string | Country of primary listing/HQ |
| `region` | string | Continental region (used for geography feature component) |
| `ticker` | string \| null | Exchange ticker where applicable |
| `has_market_data` | bool | Whether bundled daily price history exists for this entity |
| `is_synthetic` | bool | `false` for real issuers, `true` for synthetic counterparties |

Sector/country/industry classification is analyst/public knowledge as of the build date — **not** individually pulled from a single verifiable filing per field.

## `fact_edges.json` — REAL_PUBLIC_DATA (Layer A: Fact Relations)

86 directional, sourced factual relations between issuers (supply chain, ownership, sector membership, licensing).

| Field | Type | Description |
|---|---|---|
| `source` | string | Entity ID (the "from" side; direction matters, e.g. supplier → customer) |
| `target` | string | Entity ID (the "to" side) |
| `relation` | string | Relation type, e.g. `SUPPLIES`, `BELONGS_TO_SECTOR`, `LICENSES_TECH_FROM`, `PARENT_OF` |
| `criticality` | float 0–1 | Analyst-assigned importance of this relation (not a probability) |
| `note` | string | Human-readable description shown in Fact Relations tables |
| `evidence_status` | string | `WELL_DOCUMENTED_PUBLIC` (84 edges) or `REPORTED_NEWS` (2 edges) — an evidence-quality label, never rendered as a fake confidence percentage |
| `evidence_url` | string (optional) | Present only where a specific 2026 news URL backs the edge |

## `counterparties.json` — SYNTHETIC_POC_DATA

18 fictional counterparties (hedge funds, asset managers, insurers) used to demonstrate Layer C exposure without using any real institution's actual holdings.

| Field | Type | Description |
|---|---|---|
| `id` | string | Synthetic counterparty ID, e.g. `CP_ALPHA` |
| `name` | string | Fictional display name, e.g. "Alpha Quant Capital LP" |
| `industry` | string | Fictional institution type/strategy description |
| `country`, `region` | string | Fictional domicile |
| `is_synthetic` | bool | Always `true` |

## `exposure_edges.json` — SYNTHETIC_POC_DATA (Layer C: Counterparty Exposures)

80 directional, synthetic counterparty → issuer holdings, entirely fabricated for the POC.

| Field | Type | Description |
|---|---|---|
| `counterparty` | string | Counterparty ID |
| `issuer` | string | Issuer entity ID being held |
| `relation` | string | e.g. `HOLDS_EQUITY` |
| `exposure_pct` | float 0–1 | Fictional exposure percentage of the counterparty's book to this issuer |
| `is_synthetic` | bool | Always `true` |

**Never comparable to or summed with Layer B relatedness scores** — different units, enforced in every UI surface that shows both.

## `keywords.json` — hand-curated taxonomy (47 themes)

| Field | Type | Description |
|---|---|---|
| `id` | string | Theme ID, e.g. `AI_BUBBLE` |
| `label` | string | Display label with correct casing (acronyms like `AI`, `GPU`, `HBM`, `NATO`, `OPEC` preserved uppercase; proper nouns like `Taiwan`, `China` capitalized; common terms lowercase) |
| `synonyms` | string[] | Regex/keyword match terms used by the DeterministicProvider for entity/theme extraction from free text |

## `entity_keyword_weights.json` — DERIVED_DATA (curated seed, augmented at runtime)

Maps entity ID → `{theme_id: weight 0–1}`, a curated seed of entity↔theme relevance. Augmented at runtime from live news co-mention counts (real + synthetic corpora) to compute Theme Radar mention counts and entity coverage.

## `news_real.json` — REAL_PUBLIC_DATA

14 curated real public news headlines with source attribution and canonical URLs (headline + short snippet only — no full-article redistribution).

| Field | Type | Description |
|---|---|---|
| `id` | string | e.g. `r1` |
| `date` | string (ISO date) | Publication date |
| `entities` | string[] | Entity IDs mentioned |
| `keywords` | string[] | Theme IDs detected |
| `title` | string | Headline |
| `source` | string | Publisher, e.g. Bloomberg, Reuters, CNBC, TrendForce, Fortune, White House fact sheets |
| `url` | string | Canonical source URL |
| `snippet` | string | Short excerpt |
| `is_synthetic` | bool | Always `false` |
| `source_type` | string | Always `"REAL_PUBLIC_NEWS"` |

## `news_synthetic.json` — SYNTHETIC_POC_DATA

34 fabricated narrative documents generated to give the Theme Radar enough document density for a convincing demo.

Same shape as `news_real.json` plus a `text` field (full synthetic narrative body), `url: null`, `is_synthetic: true`, `source_type: "SYNTHETIC_NARRATIVE"`, `source: "Synthetic Narrative Corpus (POC)"`.

## `gleif_sample.json` — REAL_PUBLIC_DATA

Live-fetched at build time from the public [GLEIF API](https://api.gleif.org) for 40 of 43 issuers. Keyed by company name.

| Field | Type | Description |
|---|---|---|
| `lei` | string | 20-character Legal Entity Identifier |
| `legal_name` | string | Official registered legal name |
| `country` | string | ISO country code of registration |
| `hq_city` | string | Registered HQ city |
| `status` | string | LEI registration status, e.g. `ACTIVE` |
| `registered_as` | string | Registration/company number |

No parent/child LEI relationship data is bundled in this POC pass (see `docs/LIMITATIONS.md`).

## `raw_prices/*.csv` — REAL_PUBLIC_DATA

14 issuers with bundled daily OHLC-derived close price history (`date,close` columns), `2024-01-01` through `2026-08-06`. Sourced from the user-provided price history CSVs. `SKHY` has a notably short/sparse real sample (~18–20 rows from `2026-07-10` onward) — a known limitation, not a bug.

## Derived/computed-only structures (never persisted as files)

- **Layer B relationship feature vectors** — computed per-pair on request in `core/scoring.py`: `{sector, geography, supply_chain, ownership, semantic, news, market_positive, market_negative}`, each `0–1` or `n/a` if no evidence exists for that component for the pair. **`market_negative` and correlation-derived components preserve sign** — a strong negative correlation is never `abs()`'d into a positive relatedness signal.
- **Typed paths** — deterministic strings like `FACT_PATH: TSM -SUPPLIES-> NVDA` or `DERIVED_PATH: shared theme AI (weight 0.6)`, generated by `core/paths.py`.
- **Graph traversal scores** — Mode 1 bounded-traversal scores and Mode 2 Personalized PageRank scores, computed per-query in `core/ppr.py` / `core/graph_store.py`, never stored.
