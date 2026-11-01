# CCRIG · AI Analyst Platform (POC)

https://akariba.github.io/ccrig/

A working proof-of-concept for a **Counterparty Credit Risk Intelligence Graph (CCRIG)** analyst platform: a candidate-generation-first, feature-vector relationship engine over three logically separate data layers (factual relations, derived relatedness, synthetic counterparty exposure), with an AI Copilot used for parsing/labelling/explanation only — never for bulk pairwise scoring.

This is a strong proof of concept intended to demonstrate the complete business vision described in `BUILD_MANDATE.md`. It is **not** a production architecture decision. See `BUILD_REPORT.md` (repo root) for what is real, what is synthetic, and what remains out of scope, and `docs/LIMITATIONS.md` for known gaps.

## What this is

10 views across three groups:

- **Analyst**: Home / AI Copilot, Theme Radar, Entity 360, Counterparty 360, Event Studio, Graph Explorer
- **Modeling**: Model Lab, Backtest Lab
- **System**: Data & Provenance

Every relationship is a **typed feature vector** (sector / geography / supply-chain / ownership / semantic / news co-mention / market correlation ± ), never a single opaque score. Every returned pair carries a **typed path** explaining why it was returned. Every data point is tagged `REAL_PUBLIC_DATA`, `SYNTHETIC_POC_DATA`, `DERIVED_DATA`, or `AI_ASSISTED_EXTRACTION` and that tag is visible in the UI (see the Data & Provenance view).

## Quick start

Requires **Python 3.11+** and **Node.js 18+** (built and tested on Python 3.14 / Node 20).

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API is now live at `http://localhost:8000` (interactive docs at `/docs`). The dataset in `backend/data/` is already built and committed — you do **not** need to rebuild it to run the app.

To rebuild the dataset from source definitions (optional, e.g. after editing `backend/scripts/build_dataset.py`):

```bash
cd backend
python3 scripts/build_dataset.py
python3 scripts/sanity_check.py   # optional invariant sanity pass
```

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api/*` to `http://localhost:8000`.

### 3. (Optional) Enable the LLM-backed AI Copilot

The platform runs **fully offline** by default (a `DeterministicProvider` handles entity/theme extraction, event parsing, and explanation text using regex/keyword rules — no network calls, no API key). To switch the AI Copilot to a real LLM for richer natural-language parsing and explanations:

```bash
cp .env.example backend/.env
# edit backend/.env: set AI_BASE_URL, AI_API_KEY, AI_MODEL (any OpenAI-compatible endpoint)
# the app reads process environment variables only - load the file when starting the server:
#   cd backend && python3 -m uvicorn app.main:app --env-file .env
```

Restart the backend. The sidebar badge will change from "Offline deterministic mode" to reflect the active provider. The AI layer is never used for bulk pairwise relationship scoring in either mode — see `docs/LIMITATIONS.md`.

### Deployments and CORS

* **Local development** needs nothing: Vite proxies `/api` to the backend, and the API allows `localhost` / `127.0.0.1` origins by default.
* **GitHub Pages** (`npm run build:static`) has no server; the backend runs in the browser via Pyodide, with every runtime version pinned in `frontend/src/api/pyodide-pins.json`.
* **Render** serves the frontend from a different origin, so `render.yaml` sets `CCRIG_CORS_ORIGIN_REGEX` for the backend. Rename the frontend service or use a custom domain and you must update it (or set `CCRIG_CORS_ORIGINS`). See `.env.example`.

### 4. Run tests

```bash
cd backend
python3 -m pytest -q
```

The suite (run it for the current count) covers the 7 mandate-required invariants (candidate generation precedes scoring, signed correlation never abs()'d, directionality preserved, Layer A/B/C never summed, two Event Studio ranking modes never mixed in units, typed-path determinism, evidence-quality labels never rendered as fake confidence %) plus pipeline sanity checks.

Frontend checks (from `frontend/`):

```bash
npm run lint                # oxlint
npx tsc -p tsconfig.app.json --noEmit
npm test                    # dependency-free node:test checks of the UI logic (error messages, backend-status badge)
npm run verify:static       # boots the pinned in-browser runtime headlessly and checks it (needs network)
```

`npm run verify:static` is the check for the GitHub Pages build: it vendors the backend exactly as `build:static` does, boots Pyodide with the pinned packages from `frontend/src/api/pyodide-pins.json`, asserts every installed version equals its pin (and that pandas is absent), and runs the analytical baseline plus all shared request-validation cases through the in-browser dispatcher. Run it whenever `pyodide-pins.json`, `requirements.txt` or the dispatcher changes.

### 5. Validation harness and analytical baseline

`backend/validation/` is a **read-only** harness that is not imported by the app and not shipped in the static build.

```bash
cd backend
python3 -m validation.run                   # print leave-edge-out retrieval, baselines and inversion report
python3 -m validation.run --check           # fail if any analytical output drifts from the recorded baseline
python3 -m validation.run --write-baseline  # re-record, ONLY when a change is intended to alter analytics
```

* `baseline/analytics_snapshot.json` pins the output of ~27 representative endpoints (Entity 360, Model Lab, Event Studio, Backtest, priority queue, Distance Map, ...). `tests/test_validation_baseline.py` fails if a change that is not meant to alter analytics moves a score, rank or priority.
* `baseline/validation_baseline.json` records how the relationship ranking performs against documented supply/licence edges (with the edge-derived components masked) versus simple single-feature baselines, plus an inversion count and the documented hard cases. These numbers are descriptive and carry the caveats printed by the report (21 queries; curated inputs).
* Three pre-existing process-level non-determinisms in the app (hash-seed dependent ordering in Counterparty 360 and Event Studio) are neutralised in the snapshot and documented in `validation/snapshot.py`; they are not fixed by the harness.

## Project layout

```
backend/
  app/
    routers/        FastAPI routers — one per view/domain (entity, theme, counterparty, event, graph, model, backtest, provenance)
    pipelines/       Candidate generation, relationship scoring, graph traversal, backtesting
    ai/              AIProvider abstraction: DeterministicProvider (offline) + OpenAI-compatible provider
    core/            Config, weight presets, constants
    main.py          FastAPI app entrypoint
  data/              Built dataset (entities, fact edges, exposure edges, keywords, news, GLEIF sample, raw price CSVs)
  scripts/
    build_dataset.py   Rebuilds backend/data/*.json from source definitions
    sanity_check.py    Standalone invariant checks
  tests/             pytest suite (7 required invariants + pipeline sanity)
frontend/
  src/
    pages/           One file per view (Home, ThemeRadar, Entity360, Counterparty360, EventStudio, GraphExplorer, ModelLab, BacktestLab, DataProvenance)
    components/      Shared UI (sidebar/nav, cards, tables, badges)
    api/             Typed fetch client for the backend
docs/
  ARCHITECTURE.md      System design, data flow, layer separation
  DATA_DICTIONARY.md   Every dataset field, its type, and its provenance tag
  LIMITATIONS.md       Explicit list of what is not implemented / out of scope
screenshots/           Reference screenshots of every view
BUILD_REPORT.md         What was implemented, real vs. synthetic data, what remains mocked, run commands
.env.example            AI provider configuration (all optional)
```

## Sample scenarios to try

From the Home / AI Copilot search bar:

- `IBM` — single-entity lookup → Entity 360
- `Taiwan` — country/geography query
- `AI bubble` — thematic query → Theme Radar drill-down
- `A major earthquake in Taiwan disrupts semiconductor fabrication` — event narrative → Event Studio (also the worked Backtest Lab scenario)
- `TSM supply chain` — supply-chain-directed query
- `SKHY` — sparse real-data entity (demonstrates partial coverage handling)

## Notes on scope

This POC uses a curated dataset of 43 issuers, 18 synthetic counterparties, 86 factual relations, 80 synthetic exposure edges, and 47 themes — sized for demoability and fast iteration in the Model Lab and Graph Explorer, not for production breadth. See `docs/LIMITATIONS.md` for the full list of known gaps and `BUILD_REPORT.md` for a complete accounting of what is real vs. synthetic.






You are reviewing and extending an existing Citi internal proof-of-concept called:

CCRIG — Counterparty Risk Information Graph / CCR AI Analyst Platform

The source code has been pushed to the Git repository available in this environment.

IMPORTANT:
Start by inspecting the ACTUAL repository and running the existing tests.

Do not assume this description perfectly matches the latest code.
The repository is the source of truth.

Do NOT redesign the application from scratch.

The objective is to take the existing working POC and determine how Citi internal capabilities — particularly CAM and the R2D2 API — can replace or enrich the current public/synthetic inputs where appropriate.

============================================================
1. BUSINESS PROBLEM
============================================================

This originated from a Counterparty Credit Risk / Portfolio Analytics discussion.

The fundamental analyst question is:

“If something happens to X, what other issuers, entities and counterparties should a CCR analyst immediately look at, and why?”

Examples:

Entity query:
    NVIDIA
        ↓
    which entities are structurally/economically close?
        ↓
    AMD, TSMC, Broadcom, Micron, etc.
        ↓
    which Citi counterparties are exposed?

Theme query:
    Taiwan
        ↓
    relevant issuers
        ↓
    TSMC / semiconductor ecosystem
        ↓
    relevant counterparties

Event query:
    “A major earthquake in Taiwan disrupts semiconductor fabrication.”
        ↓
    identify:
        Taiwan
        earthquake
        semiconductor manufacturing
        TSMC
        supply-chain disruption
        ↓
    first-order issuers
        ↓
    second-order issuers
        ↓
    Citi counterparties with relevant exposures

Another example:

    AI bubble
        ↓
    NVIDIA
    AMD
    TSMC
    SK Hynix
    hyperscalers
    data-centre ecosystem
        ↓
    exposed counterparties

The important concept discussed by the business was a form of:

    ENTITY DISTANCE / RELATEDNESS

Small conceptual distance = entities are highly related.

Large conceptual distance = entities have little meaningful relationship.

The relationship must NOT be based on only market correlation.

It should combine multiple dimensions.

============================================================
2. CURRENT RELATIONSHIP MODEL
============================================================

The existing POC uses an explainable feature vector approximately of the form:

RelationshipVector(A,B) = [

    sector,
    geography,
    supply_chain,
    ownership,
    semantic,
    news,
    market_positive,
    market_negative

]

The composite relatedness view is approximately:

Score(A,B)
=
Σ available_k w_k * f_k(A,B)
/
Σ available_k w_k

Missing components are excluded and the available weights are renormalized.

Current heuristic starting weights are approximately:

sector              0.15
geography           0.08
supply_chain        0.25
ownership           0.10
semantic            0.12
news                0.15
market_positive     0.10
market_negative     0.05

The score is a VIEW over the underlying feature vector.

It must NOT be presented as mathematical ground truth.

If useful for the UI/business terminology:

    Distance(A,B) = 1 - Relatedness(A,B)

can be exposed as an alternative representation.

Do not change the underlying score simply to call it distance.

============================================================
3. IMPORTANT ARCHITECTURAL PRINCIPLE
============================================================

The system deliberately separates THREE different concepts.

LAYER A — FACTS

Examples:

    SUPPLIES
    LICENSES_TO
    OPERATES_IN
    BELONGS_TO_SECTOR
    PARENT_OF
    SUBSIDIARY_OF

These should be sourced/provenanced factual relationships.

------------------------------------------------------------

LAYER B — DERIVED RELATIONSHIP

Examples:

    sector similarity
    geography similarity
    semantic similarity
    news co-relevance
    market correlation
    structural relatedness

These are computed/derived signals.

They are NOT exposures.

------------------------------------------------------------

LAYER C — COUNTERPARTY EXPOSURE

Examples:

    HOLDS_EQUITY
    HOLDS_BONDS
    LENDS_TO
    other approved Citi exposure relationships

These represent an actual counterparty → issuer/security/exposure relationship.

Layer C MUST remain separate from Layer B.

Do not mix an exposure percentage with an issuer-relatedness score.

============================================================
4. CURRENT COUNTERPARTY EVENT FORMULA
============================================================

The existing implementation was specifically fixed so that event ranking is not simply total portfolio exposure.

The intended formula is:

CounterpartyRelevance(C,E)
=
Σ_i
Exposure(C,i)
*
EventRelevance(E,i)

where:

C = counterparty
E = event
i = issuer/security/entity

Preserve this logic.

Do not revert to:

    Σ Exposure

because that incorrectly makes a fully allocated portfolio appear maximally relevant to every event.

============================================================
5. CURRENT EVENT PIPELINE
============================================================

The current conceptual flow is:

EVENT TEXT
    ↓
entity / country / concept extraction
    ↓
direct issuer relevance
    ↓
Mode 1:
bounded factual typed-path traversal
    ↓
Mode 2:
issuer-only graph propagation / PPR
    ↓
EventRelevance(E, issuer)
    ↓
relevant issuers
    ↓
EXPLICIT Layer C exposure join
    ↓
relevant counterparties

Important:

Counterparties should NOT be inserted into the issuer PageRank/structural propagation graph merely because they have exposures.

The exposure join comes AFTER issuer relevance has been calculated.

============================================================
6. SECOND-ORDER RELATIONSHIPS
============================================================

The business explicitly wants second-order analysis.

Example:

Taiwan earthquake
    ↓
Taiwan
    ↓
TSMC
    ↓ SUPPLIES / economic dependency
NVIDIA
    ↓ actual exposure
Counterparty X

The application must retain a typed path explaining WHY something was surfaced.

An analyst should be able to distinguish:

    FACTUAL PATH

from

    DERIVED SIMILARITY

from

    EVENT RELEVANCE

from

    COUNTERPARTY EXPOSURE.

Do not collapse these into one unexplained score.

============================================================
7. SCALE REQUIREMENT
============================================================

The original discussion considered a potentially very large universe — potentially hundreds of thousands of entities / securities / concepts.

We cannot compute:

    500,000 × 500,000

detailed relationship scores.

That would imply ~250 billion ordered comparisons.

The current architecture therefore intentionally uses:

UNIVERSE
    ↓
CANDIDATE GENERATION
    ↓
small candidate set
    ↓
feature calculation
    ↓
relationship scoring
    ↓
TOP-K neighbors

Preserve candidate-generation-first architecture.

Do NOT introduce a dense N × N relationship matrix.

Current POC scaling is still limited and does not yet have production ANN infrastructure such as FAISS/HNSW.

That can be assessed separately.

============================================================
8. EXISTING IMPLEMENTATION
============================================================

Before changing anything, verify these against the actual repository.

The latest known implementation includes approximately:

Backend:
    FastAPI / Python

Frontend:
    React / TypeScript / Vite

Views include:

    Home / AI Copilot
    Theme Radar
    Entity 360
    Counterparty 360
    Event Studio
    Graph Explorer
    Model Lab
    Scenario Replay / Backtest Prototype
    Data & Provenance

Existing backend areas include files such as:

    core/scoring.py
    core/candidates.py
    core/event_parser.py
    core/paths.py
    core/ppr.py
    core/themes.py
    core/calibration.py
    core/ownership.py
    core/market.py
    core/data.py
    ai/provider.py

Again: inspect actual repository before relying on these names.

============================================================
9. CALIBRATION ALREADY IMPLEMENTED
============================================================

An experimental calibration mechanism has been added.

It currently uses:

pairwise weak-supervision anchors

of the form:

    Score(A,B_positive) > Score(A,B_negative)

rather than pretending there is an exact true relationship score.

Example idea:

    TSMC–NVIDIA > TSMC–Exxon

The current implementation reportedly uses approximately:

    34 anchors
    25 train
    9 holdout

with pairwise logistic loss and regularization toward the starting heuristic coefficients.

This is explicitly:

    EXPERIMENTAL ANCHOR CALIBRATION

NOT:

    VALIDATED COEFFICIENTS.

The hand-selected anchors are currently only POC weak supervision.

Please preserve that warning.

A future goal is to determine whether Citi internal historical evidence, analyst judgments or event outcomes can provide a more defensible calibration dataset.

============================================================
10. DYNAMIC THEME DISCOVERY
============================================================

The POC originally started with approximately 47 curated themes.

It has since been extended with a discovery path approximately:

documents
    ↓
TF-IDF / text representation
    ↓
clustering
    ↓
keyphrase extraction
    ↓
canonicalization / dedup
    ↓
DISCOVERED_THEME
    ↓
entities
    ↓
counterparties

The important business requirement is:

A topic that was NOT pre-programmed should be capable of emerging from new information.

Examples:

    AI power constraints
    HBM shortage
    undersea cable disruption
    export restrictions
    new geopolitical theme

The system should distinguish:

    CURATED_THEME

from:

    DISCOVERED_THEME

and retain source-document provenance.

============================================================
11. AI ROLE
============================================================

The AI/LLM must NOT calculate all pairwise relationship scores.

Its appropriate role is primarily:

    understand unstructured analyst/event text
    extract candidate entities
    extract countries
    extract themes/concepts
    classify event type
    canonicalize terminology
    label discovered clusters
    summarize evidence
    generate human-readable explanation

It may suggest candidates.

But deterministic systems must:

    resolve entity identities
    validate aliases
    map to canonical identifiers
    calculate feature vectors
    calculate coefficients
    traverse graph
    aggregate exposures
    rank results

The LLM must not silently create factual relationships.

============================================================
12. USE R2D2 WHERE APPROPRIATE
============================================================

We have access inside Citi to the R2D2 LLM/API capability.

I want the application to use R2D2 where appropriate.

FIRST:

Search the repository, environment, internal examples, documentation or available SDKs for the ACTUAL approved R2D2 integration mechanism.

DO NOT invent:

    endpoint URLs
    authentication methods
    model names
    headers
    payload schemas
    API keys
    Citi infrastructure.

If R2D2 documentation/API access is available in this development environment, use the real documented interface.

If it is not available, STOP short of fabricating it.

Instead create or preserve a clean adapter such as:

    AIProvider
        ├── DeterministicProvider
        └── R2D2Provider

with explicit TODO/configuration boundaries.

============================================================
13. DESIRED R2D2 USE CASES
============================================================

The most important R2D2 integration is structured event extraction.

Ideally expose something equivalent to:

extract_event_context(text)

returning STRICT structured output such as:

{
  "entity_candidates": [
    {
      "text": "TSMC",
      "type": "company"
    },
    {
      "text": "NVIDIA",
      "type": "company"
    }
  ],

  "countries": [
    "Taiwan"
  ],

  "concept_candidates": [
    "semiconductor fabrication",
    "supply-chain disruption",
    "GPU supply"
  ],

  "event_type":
    "SUPPLY_CHAIN_DISRUPTION",

  "summary":
    "Earthquake disrupts semiconductor manufacturing capacity."
}

Do not request or expose hidden chain-of-thought.

A short structured rationale/summary is enough.

Then:

R2D2 output
    ↓
DETERMINISTIC RESOLVER
    ↓
canonical Citi/entity identifier

Example:

    "Nvidia"
        ↓
    NVDA / canonical entity

Unknown entity:

    unresolved

NOT:

    automatically create new graph node.

============================================================
14. R2D2 + THEME DISCOVERY
============================================================

R2D2 can also help LABEL/SUMMARIZE an already-discovered document cluster.

Example:

documents cluster
    ↓
deterministic/ML clustering
    ↓
representative headlines
    ↓
R2D2
    ↓
short canonical label:
        "AI power constraints"

R2D2 must not simply invent a new market theme unrelated to the documents.

Store the source documents used to create the theme.

============================================================
15. R2D2 + EXPLANATIONS
============================================================

R2D2 may turn structured deterministic evidence into an analyst-readable explanation.

Example input:

Entity A: TSMC
Entity B: NVIDIA

Evidence:

    same sector = 1.0
    supply-chain criticality = 0.95
    market correlation = 0.68
    news relationship = ...
    typed path = TSMC SUPPLIES NVIDIA

R2D2 can output something concise such as:

“TSMC is strongly related to NVIDIA primarily through a documented semiconductor supply-chain dependency, with additional market and thematic co-movement.”

But R2D2 must not introduce unsupported factual claims.

============================================================
16. OFFLINE / FALLBACK MODE
============================================================

Preserve deterministic functionality if R2D2 is unavailable.

Expected behavior:

R2D2 available:
    deterministic extraction
    +
    validated R2D2 candidates

R2D2 unavailable:
    existing regex/alias/synonym extraction
    +
    deterministic relationship engine

The quantitative engine must never require an LLM in order to run.

============================================================
17. USE CAM WHERE APPROPRIATE
============================================================

We also have Citi CAM.

Investigate the actual CAM interfaces/data available to this environment/team.

DO NOT assume CAM contains a field simply because it would be useful.

Do NOT invent:

    tables
    database names
    APIs
    field names
    positions
    exposure measures.

First discover/document what CAM actually exposes.

The primary question is:

Which parts of the current synthetic/public POC can legitimately be replaced or enriched using CAM?

Potential areas IF AVAILABLE AND APPROVED may include:

    counterparty master information
    counterparty identifiers
    issuer/counterparty relationships
    hierarchy
    industry classification
    country/region
    risk attributes
    exposure information
    portfolio/entity relationships

But use ONLY the fields that actually exist and that this application is authorized to access.

============================================================
18. CAM IS NOT AN LLM
============================================================

CAM should be treated as a trusted internal DATA source.

R2D2 should be treated as an AI interpretation capability.

Keep this conceptual separation:

R2D2
    ↓
“What does this event/text mean?”

CCRIG deterministic engine
    ↓
“Which entities are related and how strongly?”

CAM / approved Citi risk systems
    ↓
“What Citi counterparties/entities/exposures actually exist?”

Then:

    EVENT
        ↓
    R2D2
        ↓
    concepts + entities
        ↓
    CCRIG
        ↓
    related issuers
        ↓
    CAM / approved exposure source
        ↓
    impacted Citi counterparties

============================================================
19. MOST IMPORTANT CAM INVESTIGATION
============================================================

The current POC has synthetic Layer C data.

For example:

synthetic counterparty
    ↓
HOLDS_EQUITY
    ↓
NVDA

This is only demonstration data.

Determine whether CAM can provide the necessary information to replace part or all of this.

Specifically determine whether CAM can answer something functionally equivalent to:

    Counterparty C
        ↓
    exposure / holding / position / risk relationship
        ↓
    issuer/security i

If CAM does NOT contain this level of exposure information, identify which approved Citi source would logically have to provide Layer C.

Do not force CAM to serve as exposure data if it is not actually the correct source.

============================================================
20. INTERNAL IDENTIFIER RESOLUTION
============================================================

A production-quality version should avoid depending only on ticker strings.

Where available, map through approved identifiers such as:

    Citi internal entity IDs
    counterparty IDs
    LEI
    issuer IDs
    security IDs
    ticker
    canonical legal entity name

Determine what identifier model CAM uses.

Create a mapping boundary so CCRIG's internal node IDs can resolve to appropriate Citi identifiers.

Do not discard the current public identifiers; they remain useful for public-data enrichment.

============================================================
21. DATA GOVERNANCE
============================================================

Maintain explicit provenance.

Every piece of information should be classified where appropriate as something like:

    CITI_INTERNAL_DATA
    REAL_PUBLIC_DATA
    SYNTHETIC_POC_DATA
    DERIVED_DATA
    AI_ASSISTED_EXTRACTION

For internal data, retain useful metadata such as:

    source system
    retrieval timestamp
    internal identifier
    transformation step

subject to Citi standards and actual permissible metadata.

Do not log sensitive payloads unnecessarily.

Do not send CAM/internal sensitive data to any non-approved external model/API.

R2D2 should only receive fields/data permitted by Citi policy.

============================================================
22. CORPORATE OWNERSHIP
============================================================

The code reportedly supports GLEIF Level-2 corporate-parent relationships.

The current public sample returned no usable parent relationships for the main issuer universe.

If CAM contains superior approved entity hierarchy information, investigate whether it is more suitable for:

    DIRECT_PARENT
    ULTIMATE_PARENT
    SUBSIDIARY

Do not confuse:

    CORPORATE OWNERSHIP

with:

    COUNTERPARTY HOLDS_EQUITY.

They are different relationship types.

============================================================
23. MARKET DATA
============================================================

Current POC reportedly has real public historical price data for only part of the universe.

Determine whether an approved internal Citi market-data interface already available to this environment could safely supply:

    historical returns
    prices
    spreads
    CDS
    volatility
    stress-window relationships

Do not build a new market-data integration unless it is clearly available and relevant.

Market data should continue to be a relationship FEATURE.

Do not optimize the entire relationship graph to reproduce market correlation.

============================================================
24. POSSIBLE INTERNAL DATA STRATEGY
============================================================

The likely eventual architecture is:

                 INTERNAL NEWS / RESEARCH / EVENTS
                            +
                      ANALYST QUESTION
                            ↓
                           R2D2
                            ↓
             entities / concepts / event type
                            ↓
                  deterministic resolver
                            ↓
             ┌─────────────────────────┐
             │       CCRIG ENGINE      │
             │                         │
             │ sector                  │
             │ geography               │
             │ supply chain            │
             │ ownership               │
             │ semantic/news           │
             │ market relationship     │
             │ calibrated coefficients │
             └─────────────────────────┘
                            ↓
                  relevant issuers
                            ↓
                  CAM / approved
                 Citi exposure data
                            ↓
               relevant counterparties
                            ↓
                      explanation
                            ↓
                          R2D2

Please verify whether this architecture is realistic based on the ACTUAL internal APIs/data available.

============================================================
25. WHAT I WANT YOU TO DO
============================================================

PHASE 1 — INSPECT, DO NOT MODIFY YET

1. Pull/open the repository.
2. Inspect backend/frontend architecture.
3. Run all tests.
4. Confirm what is actually implemented.
5. Locate current AIProvider abstraction.
6. Locate current synthetic counterparty/exposure data.
7. Locate current public entity/market/news/GLEIF data.
8. Determine what actual R2D2 integration examples/docs are available.
9. Determine what actual CAM interfaces/data are available.
10. Identify any existing Citi internal packages/helpers already used elsewhere in the repository/environment.

Then produce a concise assessment:

    CURRENT COMPONENT
    CURRENT SOURCE
    POSSIBLE CITI SOURCE
    CAM / R2D2 / OTHER / KEEP EXISTING
    WHY
    ACCESS AVAILABLE? YES/NO/UNKNOWN

Do NOT start a broad refactor before doing this.

============================================================
26. PHASE 2 — PROPOSE THE MINIMUM INTERNAL INTEGRATION
============================================================

After inspection, propose the smallest useful integration.

Preferred target:

A. R2D2

Replace/add the current generic LLM provider with an actual:

    R2D2Provider

while preserving:

    DeterministicProvider.

Use R2D2 for:

    event structured extraction
    theme/concept extraction where useful
    cluster labeling
    evidence-based explanation.

------------------------------------------------------------

B. CAM

Create a proper data adapter rather than spreading CAM calls throughout business logic.

Something conceptually like:

    CounterpartyDataProvider

        SyntheticPOCProvider
        CAMProvider

Potential methods ONLY if supported by actual CAM capability:

    get_counterparty(id)
    search_counterparties(...)
    get_counterparty_relationships(id)
    get_entity_hierarchy(id)
    get_exposures(counterparty_id)
    get_counterparties_exposed_to(entity_id)

Do NOT implement unsupported methods just to match this conceptual interface.

Adapt it to real CAM capabilities.

------------------------------------------------------------

C. CONFIGURATION

Allow environment/config-based providers, for example conceptually:

    AI_PROVIDER=deterministic | r2d2

    COUNTERPARTY_PROVIDER=synthetic | cam

Use Citi-approved configuration standards actually available in the project.

Do not hard-code credentials.

============================================================
27. PHASE 3 — IMPLEMENT ONLY AFTER VERIFICATION
============================================================

If actual CAM and R2D2 access/documentation are available:

implement the minimum adapters and wire them into the current application.

DO NOT:

    rewrite scoring
    rewrite candidate generation
    merge graph layers
    remove synthetic fallback
    remove public-data fallback
    change event relevance formula
    alter calibration methodology without reason.

============================================================
28. TEST CASE: R2D2
============================================================

Use:

“A major earthquake in Taiwan disrupts TSMC production, affecting NVIDIA, AMD and Apple.”

Expected structured candidate extraction should resolve approximately:

    TSM
    NVDA
    AMD
    AAPL

Country:

    Taiwan

Concepts:

    earthquake
    semiconductor manufacturing
    supply-chain disruption

Then continue through the existing deterministic event pipeline.

Also test hallucination rejection.

If R2D2 returns:

    "Fictional Semiconductor Holdings XYZ"

and it cannot be resolved to the approved entity universe:

    mark it unresolved/rejected.

Do not insert it into the graph.

============================================================
29. TEST CASE: CAM
============================================================

If CAM exposure/relationship data is available and authorized, choose a very small permitted sample.

Do NOT attempt a mass production pull.

For example:

    5–20 approved counterparties

or an appropriately restricted test universe.

Demonstrate:

EVENT
    ↓
relevant issuers
    ↓
CAM relationship/exposure lookup
    ↓
counterparty ranking.

Verify the result continues using:

CounterpartyRelevance(C,E)
=
Σ Exposure(C,i) × EventRelevance(E,i)

if the underlying CAM measure is compatible with that formula.

If the available CAM metric has different units or semantics, DO NOT silently treat it as exposure_pct.

Document the units and adapt the formula carefully.

============================================================
30. SECURITY / DATA HANDLING
============================================================

Do not:

    commit credentials
    print tokens
    log confidential full CAM payloads
    send confidential CAM data to non-approved services
    commit internal raw extracts unless policy permits it
    fabricate sanitized values and call them real.

Where examples are needed:

use synthetic or explicitly sanitized examples.

============================================================
31. ANALYST UI
============================================================

Where practical, surface provenance to the analyst.

Examples:

ENTITY

    NVIDIA Corporation
    Source:
        Citi CAM
        GLEIF
        Public reference data

EVENT ENTITY

    TSMC
    [R2D2 candidate → deterministic match]

COUNTERPARTY EXPOSURE

    Source: CAM / <actual source>

RELATIONSHIP

    Supply chain
    Source: public/internal factual source

DERIVED SCORE

    Source: CCRIG derived relationship model

The analyst should be able to understand:

WHY was this entity surfaced?

and:

WHERE did the supporting information come from?

============================================================
32. GRAPH EXPLORER
============================================================

Do not turn the graph into an unreadable hairball.

The business use case is not:

“show every edge.”

Preferred analyst flow:

EVENT / ENTITY
    ↓
ranked relevant entities
    ↓
ranked counterparties
    ↓
WHY?
    ↓
focused typed path.

Example:

Taiwan earthquake
    ↓
TSMC
    ↓ SUPPLIES
NVIDIA
    ↓ EXPOSURE
Counterparty X

Full graph should remain an advanced exploration option.

============================================================
33. SUCCESS CRITERIA
============================================================

A successful internalized POC should be able to demonstrate:

1. Analyst enters an event in natural language.

2. R2D2 extracts candidate entities/themes/event context.

3. CCRIG deterministically resolves those candidates.

4. The relationship engine retrieves/scans only plausible candidates.

5. Multi-factor relatedness ranks relevant issuers.

6. Typed paths explain first/second-order relationships.

7. CAM or another approved Citi source supplies actual internal counterparty information where permitted.

8. Exposure remains separate from structural relatedness.

9. Relevant counterparties are ranked based on issuer event relevance × actual exposure/relationship.

10. Analyst can see provenance and an explanation.

11. The model still works in synthetic/offline mode if internal services are unavailable.

============================================================
34. QUESTIONS I WANT YOU TO ANSWER
============================================================

After inspecting Citi capabilities, answer these explicitly:

A. R2D2

1. Is an R2D2 API/SDK accessible from this repository/environment?
2. What is the approved authentication pattern?
3. Can it return structured JSON?
4. Can it support event/entity/theme extraction?
5. Can it label theme clusters?
6. What data classification restrictions apply?
7. What latency/rate constraints matter?

Do not guess if documentation is unavailable.

------------------------------------------------------------

B. CAM

1. What does CAM actually provide that is relevant to CCRIG?
2. Can CAM provide counterparty master information?
3. Can it provide actual counterparty-to-issuer/security exposure?
4. Does it provide hierarchy?
5. Does it provide industry/country/classification?
6. What identifiers does it use?
7. Can it be queried programmatically?
8. At what granularity?
9. What fields should NOT be used in this POC?
10. Which current synthetic datasets could it legitimately replace?

------------------------------------------------------------

C. OTHER INTERNAL SOURCES

If CAM is not the correct source for exposure/positions, identify — only from actual documentation/environment — what approved Citi source appears to be appropriate.

Do not invent source names.

============================================================
35. FINAL OUTPUT
============================================================

After inspection and any approved implementation, give me:

1. REPOSITORY HEALTH
   tests, build, main architecture

2. BUSINESS-CASE MATCH
   what the platform already solves

3. R2D2 ASSESSMENT
   exact available capability
   how it should be integrated
   what was implemented

4. CAM ASSESSMENT
   exact relevant data available
   how it should be integrated
   what was implemented

5. DATA-SOURCE MAP

Use one table:

Requirement
Current POC source
Recommended Citi source
Integration status
Important caveat

Include:

entity master
counterparty master
counterparty exposures
industry
geography
corporate hierarchy
supply chain
market history
news/research
event understanding
theme discovery
relationship scoring
coefficient calibration
explanations

6. FILES CHANGED

7. TEST RESULTS

8. ONE END-TO-END DEMO

Show:

event
→ R2D2 extraction
→ resolved entities/themes
→ related issuer ranking
→ typed second-order relationship
→ CAM/internal exposure join
→ counterparty ranking
→ explanation/provenance

9. REMAINING BLOCKERS

Be specific about missing entitlements, undocumented APIs or unavailable data.

10. RECOMMENDATION FOR NEXT BUSINESS DEMO

Keep the recommendation focused on what can realistically be demonstrated to the CCR team.

============================================================
36. MOST IMPORTANT RULE
============================================================

Do not make the POC look more complete by fabricating Citi integrations.

If CAM/R2D2 access is unavailable:

say exactly what is missing.

Create clean adapters/interfaces if useful.

Continue to use synthetic data for unsupported areas.

The objective is an auditable, credible CCR prototype — not a demo that falsely presents synthetic or guessed data as Citi production data.
