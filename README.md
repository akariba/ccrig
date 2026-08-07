# CCRIG · AI Analyst Platform (POC)

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
```

Restart the backend. The sidebar badge will change from "Offline deterministic mode" to reflect the active provider. The AI layer is never used for bulk pairwise relationship scoring in either mode — see `docs/LIMITATIONS.md`.

### 4. Run tests

```bash
cd backend
python3 -m pytest -q
```

12 tests covering the 7 mandate-required invariants (candidate generation precedes scoring, signed correlation never abs()'d, directionality preserved, Layer A/B/C never summed, two Event Studio ranking modes never mixed in units, typed-path determinism, evidence-quality labels never rendered as fake confidence %) plus pipeline sanity checks.

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
