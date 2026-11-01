# CCRIG site audit (as of branch `phase2/ingest-bench`, 2026-11-01)

Read-only audit. No application code was changed; the only files added are this report and the screenshots in `docs/audit-screens/` (plus `docs/audit-screens/_metrics.json`, the raw page-load and API timings behind section 7).

**Confidentiality note.** The repository contains only public data and fictional synthetic data. The screenshots show that bundled dataset. In this report, specific counterparty and issuer names, ticker symbols, identifiers and amounts are replaced by placeholders (`Counterparty A`, `Issuer X`, `<amount>`). Field names, types, ranges and counts are real. No secrets, keys or hostnames appear.

**How to read the evidence.** Statements come from reading the code and from running the app locally (Vite dev server and API, no AI key configured, operator Studio switched off). "Unclear" means I could not determine it. Local timings are best-case: the API and browser were on one machine.

---

## 1. Overview

### 1.1 What the app does

CCRIG ("Counterparty Credit Risk Intelligence Graph", an "AI Analyst Platform" proof of concept) helps a counterparty-credit-risk analyst answer two chained questions. First: which companies are connected to the one I care about, and how? Second: which of our counterparties have exposure to those companies, and how urgent is that? The analyst types a company, counterparty, theme or news headline. The app returns related issuers ranked by a transparent weighted score. Each score is broken into components (sector, geography, supply chain, ownership, text similarity, news themes, price correlation). Every pair carries a typed explanation path.

A second family of screens works on synthetic counterparty data. It has a prioritised daily inbox (CRITICAL to INFORMATIONAL, produced by a rule cascade, not a model), limit breaches, exposure movers, and a counterparty page with "risk clusters". A map shows verified real company announcements (a pilot covering one issuer) with the documented relationship paths to that company. Research screens cover a theme radar, a graph explorer, a distance map, a weight-tuning "Model Lab" and a backtest. Two operator tools complete the product: a Data Intelligence Studio (governed ingestion with human review and rollback) and an Ingest Bench (an animated loading console, currently simulator-driven).

By design the app never estimates financial impact: impact is "Not estimated", exposure "Not available". Every data point is badged REAL_PUBLIC_DATA, SYNTHETIC_POC_DATA, DERIVED_DATA or AI_ASSISTED_EXTRACTION.

### 1.2 Tech stack

| Layer | What is used |
|---|---|
| Frontend framework | React 19.2, TypeScript 6, Vite 8, react-router-dom 7 (BrowserRouter, 16 routes). |
| Styling | Hand-written CSS. One global `frontend/src/index.css` (339 lines, CSS custom properties, institutional light theme), plus `studio/studio.css`, `ingest-bench/{tokens,ingestBench}.css`. Very heavy use of inline `style={{…}}` objects in pages. No CSS framework, no component library, no icon set. Fonts: Inter and JetBrains Mono from Google Fonts. |
| Charts and graphics | Recharts 3 (only two charts: a price line on Entity Explorer and a bubble scatter on Theme Radar). Cytoscape.js (Graph Explorer). d3-geo + topojson + world-atlas on Canvas 2D (Event Impact Map globe and flat map). Hand-written Canvas 2D (Data Intelligence Studio, Ingest Bench). Most other "bars" are `div` elements with a width percentage. |
| State management | None beyond React `useState` in each page. One React context, `InvestigationContext` (in-memory breadcrumb of the analyst's path; lost on reload). URL query parameters carry state on some pages. `sessionStorage` holds the Studio operator token; `localStorage` holds the Ingest Bench theme choice. No Redux, no data-fetching library, no cache. |
| Backend framework | FastAPI 0.141 (Python 3.11+), Pydantic 2, networkx 3.6, scikit-learn 1.9, numpy, scipy. |
| Database / storage | None for the public app: ~15 JSON files and 14 CSV price files in `backend/data/` (about 456 KB of JSON) are loaded into process memory at start-up (`core/data.py::STORE`) and into in-memory networkx graphs. Operator-only Studio uses SQLite (`~/.ccrig-studio`, tables: sources, jobs, findings, events (hash-chained ledger), decisions, releases, discovery_runs, current_release). |
| LLM / agent components | Optional. Default `DeterministicProvider` (regex and templates, zero network). If `AI_BASE_URL`, `AI_API_KEY` and `AI_MODEL` are all set, `OpenAICompatibleProvider` handles text tasks and a second JSON client (`discovery/agent.py`) assists event discovery. With no key set (the case when audited) no model is ever called. Details in section 6. |
| Frontend–backend transport | REST/JSON over `fetch` (`frontend/src/api/client.ts`). Server-Sent Events (read through `fetch`, not `EventSource`, so a token header can be sent) for the operator Studio flow stream and the Ingest Bench progress stream. No WebSocket. The GitHub Pages build has **no server**: the real Python backend runs in the browser through Pyodide (`api/pyodideClient.ts` + `backend/app/browser_dispatch.py`), and `client.ts` calls it in-process. |
| Deployment | GitHub Pages static build (Pyodide), or Render (`render.yaml`: a FastAPI web service and a static frontend; CORS regex set in the env). |

### 1.3 How to run it locally

```bash
# backend (Python 3.11+)
cd backend && pip install -r requirements.txt
python3 -m uvicorn app.main:app --port 8000        # API docs at /docs

# frontend (Node 18+)
cd frontend && npm install && npm run dev          # http://localhost:5173, proxies /api to :8000

# optional
CCRIG_ENABLE_STUDIO=1 CCRIG_STUDIO_TOKEN=<token> ... # enables operator Studio + Ingest Bench live stream (off by default)
AI_BASE_URL / AI_API_KEY / AI_MODEL                  # switch the text layer to an OpenAI-compatible model
CCRIG_ENABLE_INGEST=1                                # enables POST /api/themes/ingest (off by default)
CCRIG_DISCOVERY_NETWORK=1                            # lets operator discovery fetch from approved hosts (off by default)
python3 -m pytest -q                                 # backend tests (43 test modules)
npm test / npm run build:static / npm run verify:static   # frontend unit tests, static (Pyodide) build and its check
```

### 1.4 Folder structure

```
repo/
├─ README.md, BUILD_REPORT.md, render.yaml, .env.example
├─ docs/                      Architecture, limitations, data dictionary, per-feature docs (this audit lives here)
├─ backend/
│  ├─ app/
│  │  ├─ main.py              FastAPI app, CORS, router registration (operator routers only if CCRIG_ENABLE_STUDIO)
│  │  ├─ routers/             One file per URL family: entities, counterparties, themes, search, event, graph,
│  │  │                       model_lab, misc, priority, distance_map, impact_map, studio, studio_ops
│  │  ├─ core/                The analytics (pure Python): scoring, candidates, market, semantic, themes, ppr,
│  │  │                       event_parser, event_discovery/graph/register, distance, ccr_priority, risk_clusters,
│  │  │                       materiality, backtest, calibration, graph_builder/query/store, data (STORE)
│  │  ├─ ai/provider.py       AIProvider interface: Deterministic (default) and OpenAI-compatible implementations
│  │  ├─ discovery/           Operator-run event discovery from approved sources (providers, extract, verify, agent)
│  │  ├─ studio/              Governed ingestion: acquire → parse → profile → validate → resolve → stage → review → release
│  │  ├─ ingest_events.py     Progress reporter and SSE route for the Ingest Bench
│  │  └─ browser_dispatch.py  Calls endpoint functions in-process (used by the in-browser Pyodide build)
│  ├─ data/                   The whole dataset (JSON + raw_prices/*.csv + events/ + discovery/)
│  ├─ scripts/                Dataset builders and recorders (build_dataset.py, record_flow.py, …)
│  ├─ tests/                  43 backend test modules
│  └─ validation/             Determinism fingerprint, request-parity cases, analytics baselines
└─ frontend/
   ├─ src/
   │  ├─ App.tsx, main.tsx    Routes (all 16 inside one Layout)
   │  ├─ pages/               One component per route (16 files)
   │  ├─ components/          Layout (sidebar), Badge, RiskPath, Waterfall, MetricDefinition, GeoStage (map),
   │  │                       InvestigationBreadcrumb, PyodideBootOverlay
   │  ├─ api/                 client.ts (all REST calls, typed `any`), pyodideClient.ts, errors.ts, pyodide-pins.json
   │  ├─ context/             InvestigationContext (breadcrumb)
   │  ├─ graph/, impactmap/   Shared types/labels; map projection and scene logic (pure, unit-tested)
   │  ├─ studio/              Data Intelligence Studio modules (canvas, reducers, API client, own CSS)
   │  └─ ingest-bench/        Ingest Bench modules (canvas drawing, simulator, SSE hook, own tokens)
   ├─ public/studio-recordings/   Saved recording of one real Studio run (used on the public site)
   ├─ e2e/, tests/            Playwright scripts, Node unit tests
   └─ scripts/                Static-build vendoring and verification
```

---

## 2. Navigation and information architecture

### 2.1 Sitemap

All pages sit inside one shell. Every page is reachable from the left sidebar; there is no other primary navigation. There is **no catch-all (404) route**: an unknown URL renders the shell with an empty content area.

| # | Sidebar group | Sidebar label | Route | Page title (h1) | Other ways in |
|---|---|---|---|---|---|
| 1 | Relationship Intelligence | Relationships | `/` (landing) | Relationships | Logo is not a link. Search result links from other pages. |
| 2 | Relationship Intelligence | Events | `/event-studio` | Event Studio | `?text=` deep link from Relationships ("Open in Event Studio") and Entity Explorer ("Use as event subject"). |
| 3 | Relationship Intelligence | Event Impact Map | `/event-impact-map` | Global Event Impact Map | Params `q`, `days` (30/90/180/365/730), `event`, `view` (globe/flat), `source` (discovered), `studio=1`. |
| 4 | Relationship Intelligence | Counterparties | `/counterparty` | Counterparty 360 | `?id=` from Inbox, Controls, Exposure Movers, Event Studio, Entity Explorer, Theme Radar, Relationships. |
| 5 | Relationship Intelligence | Controls | `/breaches` | Control Exceptions | — |
| 6 | Research | Inbox | `/inbox` | Inbox | — |
| 7 | Research | Entity Explorer | `/entity` | Entity 360 | `?id=` from many pages (a hard-coded default issuer when absent). |
| 8 | Research | Exposure Movers | `/exposure-movers` | Exposure Movers | — |
| 9 | Research | Graph Explorer | `/graph` | Interactive Graph Explorer | `?id=` (also set by clicking a node), `?studio=1`. |
| 10 | Research | Distance Map | `/distance-map` | Distance Map | `?id=` (counterparty). |
| 11 | Research | Theme Radar | `/theme-radar` | Dynamic Theme Radar | `?theme=` from Entity Explorer theme pills and Relationships. |
| 12 | Research | Model Lab | `/model-lab` | Model Lab | — |
| 13 | Research | Backtest Lab | `/backtest-lab` | Backtest Lab | — |
| 14 | System | Data Intelligence Studio | `/data-studio` | Data Intelligence Studio | — |
| 15 | System | Ingest Bench | `/ingest-bench` | (sheet title "Haiku + Sonnet + Opus") | `?demo=1` forces the simulator; `?run=<id>` streams one run. |
| 16 | System | Data Sources | `/provenance` | Data & Provenance Explorer | — |

Naming is inconsistent between the sidebar, URL and page title ("Events" / `/event-studio` / "Event Studio"; "Controls" / `/breaches` / "Control Exceptions"; "Entity Explorer" / `/entity` / "Entity 360"; "Data Sources" / `/provenance` / "Data & Provenance Explorer"; "Counterparties" / `/counterparty`). Docs and screenshots call things "Home / AI Copilot", "Daily Review", "Breaches & Actions", so older names persist in code and file names.

### 2.2 Global layout

- **Shell** (`components/Layout.tsx`): a fixed-height flex row. Left **sidebar** about 220 px (15% of a 1440 px screen): logo and "AI ANALYST PLATFORM · POC", three labelled groups of text links with a left accent rule on the active item, and at the bottom a **backend status pill**. The right **main area** scrolls on its own (`overflow-y:auto`) with padding 24 px 32 px. At 760 px or narrower the sidebar becomes a horizontal scroll strip along the top.
- **Header:** none. The page title lives inside each page. An **investigation breadcrumb** (`InvestigationBreadcrumb`) appears above the page content once the analyst has traversed relationships on the Relationships page.
- **Footer:** none.
- **Global search:** none. The search box on the Relationships page is the closest thing (it classifies the query as entity, counterparty, theme, event/narrative, or ambiguous and routes accordingly); other pages have their own ID or name inputs.
- **Filters that persist across pages:** none. The only cross-page memory is the in-memory breadcrumb (it resets on reload; its links point at routes such as `/?q=…`, but the Relationships page ignores the `q` parameter, so clicking back does not restore the search).
- **User / role handling:** none. There is no login, no user identity and no roles. The only access control is the operator switch for the Studio and Ingest Bench live stream: server env `CCRIG_ENABLE_STUDIO=1` and a token header `X-Studio-Token` kept in `sessionStorage`. The public static site has no server and the Studio is read-only (it replays a saved recording).
- **Backend status pill:** "Offline deterministic mode / No AI key set" (default), AI-enabled mode text, or a red "backend unreachable" state that re-checks `/api/health` every 5 s.
- **Theming:** light by default; the Event Impact Map, Data Intelligence Studio and Ingest Bench render their own dark or "paper" skins inside the same shell. There is no global dark mode switch.

### 2.3 Typical user journey (landing to insight)

1. Land on **Relationships** (`/`). The search box is empty; four example chips are offered (an issuer ticker, another ticker, a theme phrase, a counterparty name).
2. Type a company, counterparty, theme or headline and press Enter. The app resolves it (one exact entity match → entity or counterparty; theme match with no entity match → "Open Theme Radar"; four or more words → "Open in Event Studio"; otherwise "multiple or no matches").
3. For an entity: a header card, then a "Top related" table (5 rows: entity, composite score 0–1, Inspect button). Link: "Open full Entity 360".
4. Click **Inspect** on a row. A relationship inspector opens: plain-language explanation, typed structural path, signed correlations (full / rolling / stress), score waterfall, and a "Portfolio relevance" summary. A link, "View exposure implications →", reveals up to 5 counterparties with product, priority and PFE.
5. Click a counterparty → **Counterparty 360** (three tabs: Relationships, Exposure & Controls, Decision) for risk clusters, controls and the recommended action.
6. In parallel the analyst can start from **Inbox** (top 5 priorities), **Controls** (breaches), **Events** (paste a headline → issuers nominated → counterparties joined with priority) or **Event Impact Map** (real announcements for one issuer on a map).
7. "Insight" is a counterparty with a priority label, a driver, an explanation and a suggested action. There is no saved view, no export, no alert and no way to share a finding.

---

## 3. Page-by-page description

General conventions, true for every page unless noted: state is held in the page component; data loads in `useEffect` on mount; **loading** is a plain grey text line ("Loading …"); **error** is usually a `.warning-box` (some pages swallow errors silently and show nothing); **empty** is a muted text line. Light theme tokens: background `#f6f5f1`, surfaces white, text `#232019`, primary petrol `#2c5b6b`, error `#a3455a`, warning `#96591c`, success `#3c7a4a`; body 14 px, tables 12.5 px, many labels 10–11 px; cards have a 1 px border and 6 px radius. Typical page width is the full main area (about 1150 px at 1440 px). Screenshots are at 1440 px wide in `docs/audit-screens/`.

A shared badge (`DataBadge`) tags data kind: REAL PUBLIC DATA (green), SYNTHETIC POC DATA (amber), DERIVED (petrol), AI-assisted (teal), FACT (neutral).

### 3.1 Relationships — `/`

- **Purpose:** "What is this company/counterparty/theme connected to, and does that connection touch our portfolio?" (relationship first, exposure second).
- **Layout:** Title and one-line subtitle. Card 1 (full width): search input (about 90% of the card) plus a "Search" button; while nothing is searched, a row of four example "pills". Below it, depending on the result: (a) ambiguous/multiple-match list, (b) theme link, (c) event link, or (d) three stacked cards: entity header (name, ID, sector · country, data badge at right); "Top related" table; relationship inspector (only after Inspect); business-exposure table (only after "View exposure implications").
- **Components:**
  - *Search box:* free text, Enter or button. Calls `GET /api/search?q=` then (for entity or counterparty) `GET /api/entities/{id}`. Loading text "Searching…".
  - *Top related table* (table, 3 columns: entity name, composite score `0.000`, Inspect button): first 5 of the entity's `relationship_summary.top_related` (backend returns up to 10 by default). Click Inspect → loads `GET /api/entities/{id}/explain/{other}` and the other entity's 360 (to union both sides' counterparty materiality).
  - *Relationship inspector:* AI-box with a one-sentence explanation (deterministic template unless an AI key is set); "RiskPath" chips showing typed hops (with arrows reversed if traversed against stored direction); three-column signed correlation (full-sample, rolling 30d, stress 10d) when both issuers have price data; **score waterfall** (stacked horizontal contributions per component plus excluded components with reason); "Portfolio relevance" bullets (counterparties connected, product channels, collateral linkages).
  - *Exposure table* (Counterparty link, Product, Priority text, PFE): first 5 only.
- **Filters and inputs:** the search text only. The example pills set the text and search.
- **Actions:** Search; Inspect; "View exposure implications"; links to Entity 360, Theme Radar, Event Studio, Counterparty 360. Clicking Inspect and counterparty links pushes steps onto the breadcrumb.
- **Data:** `/api/search`, `/api/entities/{id}`, `/api/entities/{a}/explain/{b}`, `/api/metric-definitions/{id}` (popover link "How calculated?").
- **Visual style:** light theme, cards, mono numerals. Dense text; inline styles.
- **Known problems:** only 5 related rows with no "show more" here; search state is lost on reload; breadcrumb "back" links do not restore the query; counterparty search results go to a different page than entity results; the AI box text is a template when no key is set (reads as AI but is not); errors from `api.search` become `null` and show nothing; exact-entity resolution means a name typed with different punctuation can fall to "ambiguous".
- **Screenshots:** `01-relationships-empty.png`, `02-relationships-result.png`, `03-relationships-inspector.png`, `27-phone-relationships.png`.

### 3.2 Events — `/event-studio` (Event Studio)

- **Purpose:** "If this headline happened, which issuers does it touch, directly and through the graph, and which counterparties have exposure to them?"
- **Layout:** Title with a long subtitle explaining the two ranking modes. Card with a multi-line text area (about 80 px tall, full width), then a button row: "Parse event" and three sample-headline pills. Then: result header card (event type, summary), the "Exposure, materiality & decision" card, and a collapsed card "How was this derived?".
- **Components:**
  - *Text area:* default sample headline (an earthquake affecting semiconductor fabrication); auto-parses on load.
  - *Result header:* event type (one of five rule labels or a default) and an AI-or-template summary.
  - *Materiality table* (11 columns: Priority pill, Counterparty link, Reference issuer link, Product, ΔPFE/ΔNSE, Utilisation, Headroom, Driver, Risk-factor path, Control flag, Decision): first 5 rows, "Show all N" toggle. Also a "Transmission" block of RiskPath chips for each distinct risk-factor path, and a note "N issuers nominated".
  - *Derivation (collapsed):* AI context extraction box; three columns of detected entities / concepts / countries, each with a source badge (RULE, AI-RESOLVED, AI-UNVALIDATED, CURATED, DISCOVERED, EPHEMERAL); two side-by-side tables, **Mode 1** (bounded typed traversal, decay 0.65 per hop, entity id and score) and **Mode 2** (relation-aware Personalized PageRank, entity id and PPR score), labelled "units not comparable"; "Relevant counterparties" table (exposure-weighted relevance).
- **Filters and inputs:** the text only. Backend supports `max_hops` (1–3), `min_score`, `sector`, `geography`, `top_k`, but the UI exposes none of them.
- **Actions:** Parse event → `POST /api/event/parse`; sample pills; links to Entity 360 and Counterparty 360.
- **States:** loading "Parsing…"; error in a warning box; stale responses are dropped by a request counter.
- **Visual style:** as general. The 11-column table overflows narrow widths.
- **Known problems:** the answer (counterparties by priority) is above the fold but the *why* (issuers, modes) is hidden under a collapsed card; entity ids not names in the two mode tables; the first parse call took about 1.0–1.2 s locally (graph build on first use), later calls are fast; many CCR counterparties have no issuer link (only 2 of 19 carry a `reference_entity_id`), so the join often returns few rows; "Show all" is the only control for >5 rows.
- **Screenshots:** `06-events.png`, `07-events-derivation.png`.

### 3.3 Event Impact Map — `/event-impact-map`

- **Purpose:** "What verified real-world announcements concern this company recently, where did they happen, and which documented relationships connect the named companies to it?" (pilot: one issuer covered).
- **Layout:** Full-bleed dark workspace replacing the page padding. Top toolbar: title and subtitle at left (~25%), search form (company input, recency select, Search button) at centre, "Include approved relationships" checkbox, a two-button segmented source switch (Curated register / Dynamic discovery), and a four-field status strip (Entity, Events "n of ≤5", Window, Source). Below, a two-column body: map stage on the left (~70% width, about 780 px tall at 900 px viewport height) and a ~360–380 px right panel (~30%). Footer strip: semantic-meaning pills, a "Curated register vs dynamic discovery" comparison card, and a collapsed "About this view" section.
- **Components:**
  - *Map* (`GeoStage`, Canvas 2D, d3-geo): a rotating **globe** or an Equal Earth **flat map** ("Auto" picks globe when everything fits one hemisphere). Event markers are numbered 1–5 and coloured by category; company markers sit at headquarters countries and carry ticker labels; thin arcs show stored relationships with arrowheads in their stored direction; the selected event gets a pulse. Controls: Overview / Investigation, Auto / Globe / Flat, zoom + / −, Frame, Animation on/off, collapsible legend. Drag rotates the globe; hover on a list item highlights its marker.
  - *Top 5 events list:* buttons with rank, title, date, place and category; newest first ("date order, not importance"); click selects (URL `?event=`).
  - *Global overview card* (nothing selected): counts of events, places, relationships, companies and unplotted events.
  - *Event panel* (selected): badges (Real publication, Verified by retrieval, category); "Source and dates" definition list (published, event date and basis, source publisher/tier/link with "n/m passages confirmed", location with precision and basis, countries named); verbatim evidence quotes; "Documented path to the company" with chip chains per named entity; an **Impact** block that always says "Not estimated" and "Verified exposure: Not available" with reasons; analytical limitations list.
  - *Entity panel:* click a company marker → events naming it, relationship wording and an "Open Entity 360" button.
  - *Comparison table:* curated vs discovery, in both, only-curated, only-discovered.
- **Filters and inputs:** company text (resolved via `GET /api/impact-map/search`); window 30/90/180/365/730 days; source mode; include approved relationships (Studio overlay); projection and view modes. Defaults: query = a hard-coded default issuer name, 180 days, curated, auto projection, overview.
- **Actions:** Search; select event/company; Retry on error; Compare the two modes (`GET …/compare`); Open Entity 360.
- **States:** skeleton rows while loading; warning boxes for errors, "no match", "dynamic discovery not available here" (always the case on the public site and when the operator has run no discovery); "Not plotted" list for events whose source gives no place.
- **Visual style:** dark navy `.impact-dark` workspace, teal/amber accents, mono labels, 10–12 px text. Light sidebar stays.
- **Known problems:** only one issuer has events (8 records in the register, 5 shown); the register is a static file (built 1 Nov 2026), not a feed; "Dynamic discovery" is operator-only and off by default so the second mode is usually "unavailable"; a dark full-bleed page inside a light shell is visually inconsistent; at phone width the panel stacks beneath the map and the page becomes about 1600 px tall; Canvas content has `aria-label`s but no text alternative for the arcs.
- **Screenshots:** `08-event-impact-map.png`, `09-event-impact-map-event.png`, `28-phone-event-impact-map.png`.

### 3.4 Counterparties — `/counterparty` (Counterparty 360)

- **Purpose:** "For one counterparty: what is it connected to, how is it exposed and controlled, and what should I do?"
- **Layout:** Title/subtitle. Card A: two blocks of selector pills: "CCR counterparties" (19, each with its priority) and "Portfolio-holdings counterparties" (18). Card B: counterparty header (name, legal entity, priority pill, SYNTHETIC badge), a three-tab bar (Relationships, Exposure & Controls, Decision), then the tab body.
- **Components:**
  - *Selector pills:* click sets `?id=`. Default selection: the top-priority CCR counterparty.
  - *Relationships tab:* "Key risk clusters" list (label, story arrow-chain, "View story"). The story expander shows a RiskPath, "Why it matters", "Next action", potential event triggers, and a hidden "Show evidence detail" section (direct, first-order and contextual members, evidence bullets, signed correlation evidence, relevant controls). Then "Counterparty details" (type, rating, watchlist), the risk-factor transmission path, reference issuer link and active event box. For portfolio-holdings counterparties: "Direct holdings" table (issuer, relation, exposure %), plus a collapsible "Concentration & indirect relationships" (sector concentration as `div` bars; indirect relationships table via/entity/score).
  - *Exposure & Controls tab:* economic exposure paths; fields (product, netting set, notional, direction, unmatched trades, collateral type); risk drivers list; **Materiality** table (metric, value, AVAILABLE/UNAVAILABLE) with ΔPFE and ΔNSE; linked stress scenario text; **Controls** table (constraint, value, status) with headroom and coverage owner; breach warning box.
  - *Decision tab:* decision label, reasons, missing information; collapsible "Technical evidence" (raw driver flags).
- **Inputs and filters:** pills only.
- **Actions:** switch counterparty/tab; expand a cluster; links to Entity Explorer.
- **Data:** `/api/counterparties`, `/api/priority-queue` (whole queue, 68 KB), `/api/counterparties/{id}`, `/api/priority-queue/{id}`, `/api/priority-queue/{id}/risk-clusters`. Loading "Loading Counterparty 360…".
- **Known problems:** **two disjoint counterparty universes** (19 CCR records and 18 portfolio-holdings records share no IDs; only 2 names coincide) are shown as two pill lists, so most CCR counterparties say "No portfolio-holdings data for this counterparty (CCR-only record)" and most portfolio counterparties say "No CCR investigation record"; on first load the page requests a portfolio record for a CCR id and gets a 404 (logged in the console, handled silently); the queue is fetched in full on every navigation (and twice in dev); ratings are all empty ("Unavailable"); 15 of 19 CCR records have no reference issuer, so the relationship story is a single "mixed market-risk" cluster; tabs and pills are `span`s (not keyboard-focusable); units of PFE/NSE ("$mm") are only implied.
- **Screenshots:** `10-counterparties-relationships.png`, `11-counterparties-exposure.png`, `12-counterparties-decision.png`.

### 3.5 Controls — `/breaches` (Control Exceptions)

- **Purpose:** "Which limit breaches are open, how old are they, and are they past their SLA?"
- **Layout:** title/subtitle; a three-link filter row (All / Overdue only / Within SLA); one table card.
- **Components:** table with columns Subject (link to Counterparty 360), Control (limit type), Exception (`+<excess>`), Age (days, "OVERDUE" in red), Owner ("Unassigned" in red when empty), Action (decision text). Click a row to expand a three-column detail (legal entity and product; exposure vs limit; SLA and root cause). Overdue rows get a red tint.
- **Filters:** status (server-side). Default: All.
- **Data:** `GET /api/breaches?status=`. Dataset contains one breach, so the table has one row.
- **Known problems:** a one-row table; filter links are `<a>` without `href`; expanded exposure value is recomputed on the client by limit type (duplicates a backend rule).
- **Screenshot:** `13-controls.png`.

### 3.6 Inbox — `/inbox`

- **Purpose:** "What are the 5 things worth a look today?"
- **Layout:** title/subtitle; a summary line of clickable counts ("n critical", "n high", "n overdue breaches", "n model/data items", "clear filter"); one table card.
- **Components:** 9-column table (Priority pill, Counterparty and id, Trigger (first reason), Key Exposure Move (ΔPFE or ΔNSE), Driver code, Control flag (OVERDUE BREACH, BREACH, WWR, WATCHLIST, NEAR LIMIT ≥85%, OK), Event/Risk factor, Owner, Next Action). Rows expand into a two-column detail: reasons, exposure table (PFE, NSE, RC previous→current, settlement, limit, utilisation, headroom), driver evidence trace, product/netting/collateral, missing information, decision and a link to Counterparty 360. Only the first 5 rows show; a "Show all N" link reveals the rest.
- **Filters:** the four summary counts are filters (priority, overdue, model/data). Default none.
- **Data:** `GET /api/priority-queue(?priority=)` (68 KB for 19 records).
- **Known problems:** the control flag thresholds are re-implemented in the page; the table is 9 columns wide with 10–11 px text; "Inbox" has no read/unread, assignment or snooze, so it is a report, not an inbox.
- **Screenshots:** `04-inbox.png`, `05-inbox-expanded.png`.

### 3.7 Entity Explorer — `/entity` (Entity 360)

- **Purpose:** "The relationship laboratory for one issuer: who is it related to, through which dimensions, with what evidence, and which counterparties are exposed?"
- **Layout:** title with an ID input and Load button (360 px wide); entity header card (name, id, sector · industry · country (region), data badge, LEI row when known); a two-column row (about 66% / 33%): "Top related entities" with Explain, and a "Methodology / diagnostics" rail; a second row (50/50): "Fact relations · Layer A" table and "Corporate hierarchy"; a "Counterparty exposure context" card with two tables side by side; then (when price data exists) a "Real price history" card with a 220 px line chart and a signed-correlation table.
- **Components:**
  - *Top related table:* score, Explain button (opens an in-card panel with waterfall, explanation, typed path, signed correlation); "Show all N" pill (5 shown by default, up to 10).
  - *Diagnostics rail:* theoretical pair count, candidates, retained, reduction ratio; theme pills (top 10, link to Theme Radar); quick links (Graph Explorer, "use as event subject").
  - *Fact relations:* direction arrow, other entity, relation type, criticality (2 decimals), evidence badge (High/Medium/Low) with "source" link.
  - *Corporate hierarchy:* GLEIF Level-2 parent/subsidiaries, or "Ownership — N/A / insufficient data" (always the latter in this dataset).
  - *Exposure context:* CCR counterparties (priority, product, PFE, utilisation) and portfolio holdings (exposure %).
  - *Price chart:* Recharts line of close price (every 3rd point), CartesianGrid, tooltip; correlation table (full-sample, stress 10d, positive and negative channel) for the top 8.
- **Inputs:** issuer id text (upper-cased, no autocomplete). Default `?id` falls back to a hard-coded default issuer.
- **Data:** `/api/entities/{id}` (about 100 KB), `/api/entities/{a}/explain/{b}`.
- **Known problems:** longest page (about 2,500–3,000 px); requires knowing a ticker; the price chart is the only time series in the product and only 14 issuers have prices (one has about 18 rows); correlations list "n/a" for most pairs; "Not found" for an unknown id has no suggestions; criticality is shown without explaining it is a curated judgement.
- **Screenshots:** `14-entity-explorer.png`, `15-entity-explain.png`.

### 3.8 Exposure Movers — `/exposure-movers`

- **Purpose:** "What moved, regardless of how risky it is?"
- **Layout:** title/subtitle; a card with four tab-like pills (PFE Movers, Stress / NSE Movers, RC / MTM Movers, Sensitivity Movers); one table.
- **Components:** table (Counterparty link, Move (amber when positive), Driver, Product, Utilisation, Priority badge), sorted by absolute move. The move is computed **in the page** from the priority queue: ΔPFE, ΔNSE, RC current − previous, or equity-delta move (fallback FX delta). Rows without a value are dropped.
- **Defaults:** PFE tab. Empty: "No counterparties have a confirmed move for this metric."
- **Known problems:** all logic is client-side on the full queue; the fourth tab mixes equity delta and FX delta (different units) in one column; no units; no chart; it largely duplicates Inbox.
- **Screenshot:** `16-exposure-movers.png`.

### 3.9 Graph Explorer — `/graph`

- **Purpose:** "Show me the neighbourhood of this entity in the three relationship layers."
- **Layout:** title/subtitle; a control card (centre-ID input + Go, Hops select 1/2, "Include Studio-approved relationships" checkbox, three layer checkboxes fact/derived/exposure, a node/edge count at far right); optional banner when approved relationships are included; a row: Cytoscape canvas card (about 66%, 480 px high) and a 33% side card with Legend and "Selected edge".
- **Components:** Cytoscape graph with a force layout (`cose`, no animation): centre node 34 px petrol, others 22 px; synthetic nodes amber, others grey; edge style by layer (solid arrow = fact, dashed no arrow = derived, dotted arrow = exposure; purple = Studio-approved); edge width 1 + 3 × weight. Click a **node** → recentres the graph on it (URL `?id=`). Click an **edge** → shows source → target, relation, layer, note, evidence link and any Studio-approved evidence with quote and source hash.
- **Data:** `GET /api/graph/ego/{id}?hops&layers&include_studio` (39 KB for 1 hop, 113 KB for 2).
- **Known problems:** node labels are internal IDs (including fictional counterparty ids) not names; labels overlap near the centre; node colours are hard-coded hex (Cytoscape cannot read CSS variables); no zoom controls, search, filter by type, pinning or legend of node types; clicking a node navigates instead of selecting, so there is no node inspector; "derived" edges are drawn for the top 8 only (default) and cannot be tuned.
- **Screenshots:** `17-graph-explorer.png`, `18-graph-explorer-2hop.png`.

### 3.10 Distance Map — `/distance-map`

- **Purpose:** "For a counterparty, which issuers is it 'close' to, through which channel, and how strongly?" (ρ = 1 − graph distance; inferred, not observed correlation).
- **Layout:** title/subtitle; counterparty pill card (18 portfolio counterparties); a result card: sector label and name at left, "Min ρ" select at right; three counters (ρ ≥ 0.80, 0.60–0.79, < 0.60); an optional concentration alert; a channel legend; then issuers grouped into four tiers (Direct ≥0.80, Significant 0.60–0.79, Moderate 0.40–0.59, Weak <0.40), each a list of rows.
- **Components:** each row: rank, issuer name, sector · ticker, channel pill (Ownership, Supply Chain, Historical Corr., Hidden Corr.), a 130 px bar and ρ. Click a row to expand: ρ, graph distance d, channel, RiskPath, sorted component bars (Layer B), evidence sentence and an italic caveat.
- **Inputs:** counterparty pill; Min ρ (0, 0.4, 0.6, 0.75). Defaults: first counterparty, show all.
- **Data:** `/api/distance-map/counterparties`, `/api/distance-map/counterparty/{id}?min_rho&max_hops`.
- **Known problems:** for the default counterparty every issuer lands in "Hidden Corr." with ρ of 0.18–0.48, so the page shows no differentiation; the "Direct" and "Significant" tiers are usually empty (there are no ownership edges and no counterparty-to-issuer supply edges), so the headline counters read 0 / 0 / 22; issuers without a market ticker display "· Private" even for obviously public companies (label is derived from a missing ticker, not from ownership status); channel "Historical corr." is a label for derived similarity, not a historical correlation; the Min ρ filter re-queries the server instead of filtering locally.
- **Screenshot:** `19-distance-map.png`.

### 3.11 Theme Radar — `/theme-radar`

- **Purpose:** "Which themes are gaining attention, how many issuers do they touch, and how many counterparties does that reach?"
- **Layout:** title and a four-line subtitle defining the axes; a row: bubble chart card (about 66%, 420 px high) and a scrolling "All themes (48)" table (33%); when a theme is selected, a full-width detail card.
- **Components:** Recharts `ScatterChart`: X = mention velocity, Y = entity coverage, bubble size = counterparties reached; circles = curated themes (petrol), diamonds = discovered themes (teal); tooltip shows the label; click selects. The table (Theme, Kind badge, Coverage, Relevance) sorted by mention count. Detail card: label, kind badges, AI-suggested label, a "Why this theme was detected" box for discovered themes (TF-IDF + clustering explanation, recent/prior mentions, velocity, novelty), representative headlines, source document ids, three KPI tiles (Mentions, Entities covered, Counterparties exposed), covered-entity and exposed-counterparty pills (links), and an evidence list with real/synthetic badges.
- **Data:** `/api/themes`, `/api/themes/{id}`. `POST /api/themes/discover` exists but is not called by the UI.
- **Known problems:** velocity of "no earlier mentions" is encoded as 999, so the X axis spans −350 to 1050 and nearly every bubble stacks in two vertical stripes (visible in the screenshot); the scatter has no labels so bubbles are unreadable without hovering; the corpus is only 48 documents (14 real, 34 synthetic) so every statistic is tiny-sample; the "discovered" theme count is 1; legend for shape/colour is missing; click handler relies on Recharts payload.
- **Screenshot:** `20-theme-radar.png`.

### 3.12 Model Lab — `/model-lab`

- **Purpose:** "What happens to the ranking if I change the relatedness weights, and can the weights be nudged toward a few hand-picked examples?"
- **Layout:** title/subtitle; a two-column row (about 43% / 57%): left card with presets, eight weight sliders, an issuer input and "Recompute rank"; right card with the ranked table. Below, a full-width "Experimental Anchor Calibration" card.
- **Components:** four preset pills (General, Supply-chain shock, Market funding shock, Thematic tech shock); sliders 0–0.5 step 0.01 per component (sector, geography, supply chain, ownership, semantic, news, market +, market −); ranked results table (#, entity link, score) with a "scored / retained" badge; calibration: "Run calibration", "Apply calibrated weights", "Restore heuristic weights"; table starting vs calibrated weights (ownership shown "N/A"); train and holdout summaries (satisfied/count, mean margin, pairwise loss vs heuristic); a market-agreement diagnostic; a mandatory disclaimer box.
- **Defaults:** issuer input = a hard-coded default issuer; weights = default preset.
- **Data:** `/api/model-lab/presets`, `POST /score`, `POST /calibration/run` (3.3 s locally), `POST /calibration/market-agreement`.
- **Known problems:** weights are not saved or shareable; 422s (for example all-zero or no-data weights) show the server message only; the ranking shows scores but no per-weight delta or rank-change indicator; sliders have no numeric entry; calibration is explicitly "not statistically validated".
- **Screenshots:** `21-model-lab.png`, `22-model-lab-calibration.png`.

### 3.13 Backtest Lab — `/backtest-lab`

- **Purpose:** "Would the relatedness model have named the issuers that actually moved after an event?"
- **Layout:** title/subtitle; scenario pill card; scenario header card (title, narrative, T0, data cutoff, "Real bundled price + news data" badge — the event text itself is synthetic); three KPI cards (Precision@3, Recall@3, NDCG@3); an explanation paragraph; a before/after "methodology correction" table; two side-by-side tables (model-predicted movers; observed movers with return, abnormal return, label); warnings box.
- **Defaults:** runs the one implemented scenario on load. The other two scenario pills are marked "(not implemented)" and return an error when clicked.
- **Data:** `/api/backtest/scenarios`, `/api/backtest/run?scenario_id=`.
- **Known problems:** one event, so the statistics cannot show skill (the page says so); no chart; scenario pills for unimplemented scenarios are clickable; no way to run a new event or date.
- **Screenshot:** `23-backtest-lab.png`.

### 3.14 Data Intelligence Studio — `/data-studio`

- **Purpose:** "Show how a source document becomes reviewed, versioned data: every step, every count, every decision, and the ability to roll back."
- **Layout:** top bar (title and job id, two recording buttons "Recorded · co-occurrence" and "Recorded · asserted", a "Recorded replay" button, 1×/2×/4× speed, a "RECORDED REPLAY" badge, Details). A banner explains read-only mode. The workspace (about 75–80% of the height) is a dark Canvas: seven nodes left to right (Source, Parse, Validate, Resolve, Verify, Review, Output), grouped under captions such as "Deterministic processing", with an optional Language-model layer above; glowing multi-strand cables carry pulses only when a recorded event happened; each node shows a big metric (bytes, rows, ids, state). A compact timeline strip along the bottom lists events. A right drawer (closed by default) has tabs Stage, Source, Quality, Review, Output, Events, About.
- **Behaviour:** on the **public/static site and on any server without the operator switch**, the page is read-only and plays back one saved recording (about 150 KB JSON) of a real run, labelled "Recorded replay". With `CCRIG_ENABLE_STUDIO=1` and a token, an operator can run a stored scenario excerpt, watch real events over SSE, and approve, reject or roll back (approval requires named reviewer, reason and explicit acknowledgement of assertions). Approved relationships can then be added to the Graph Explorer and Impact Map through the "include approved relationships" switch; the canonical dataset is never modified.
- **Language-model layer:** drawn but shows "not invoked — no model call was recorded", because nothing in the repo writes model calls to the ledger.
- **Known problems:** the live path is unavailable in the audited setup so only the replay was seen; 47 buttons on the page; heavy operator vocabulary (ledger, staging, overlay); contract/ingestion supports 10 target datasets but the product has only one worked scenario; nothing here feeds the analyst pages by default.
- **Screenshot:** `24-data-studio-public.png`.

### 3.15 Ingest Bench — `/ingest-bench`

- **Purpose:** an animated loading console meant to show three model agents (small, medium, large) ingesting five datasets into a risk dashboard. Purely illustrative today.
- **Layout:** a framed "engineering sheet" (about 1000 px wide, scrolls): title block with four KPIs (records, tokens, eval loss, stage), status bar (pulsing dot, Pause/Resume, Restart, 1×/2×/4×, auto/light/dark), a focus-bench canvas (~1000×430), a network-trace canvas (~1000×400), an instrument row (ridgelines, weight heatmaps, convergence), a spec strip, a revision table (click jumps in simulator mode) and an agent log.
- **Data:** the simulator (36 s run at 1×, always badged SIMULATED) unless an operator run exists (`GET /api/ingest/runs/latest/events`, SSE; none exists unless a producer calls `ProgressReporter`; there is a demo route `POST /api/ingest/demo-run` for operators).
- **Known problems:** it is not connected to any real ingestion (no agent in the repo emits events); optical figures (feeds/s, focal lengths, Δz) are decorative; it sits in the main navigation next to analyst tools; **a TypeError is thrown in the first frames in the dev server** (`Cannot read properties of undefined (reading 'x')` in the network-trace drawing function, observed twice at about 0.3 s after load on a 1440 px viewport; the page keeps rendering) — found in this audit and not fixed, since this task was read-only; eight Canvas elements animate continuously.
- **Screenshot:** `25-ingest-bench-demo.png`.

### 3.16 Data Sources — `/provenance` (Data & Provenance Explorer)

- **Purpose:** "Where does every number come from, is it real or synthetic, and how complete is it?"
- **Layout:** title/subtitle; a 3-up row of KPI cards (totals from the registry: counts by classification); a "Data sources registry" table (Source, classification badge, records, coverage note); a scrolling "Per-entity coverage (n entities)" table (320 px max height: market data, LEI, fact edges, themes); a "Scalability simulation" table (N entities, theoretical pairs, candidate pairs, reduction %) with a footnote on measured brute-force timings.
- **Data:** `/api/provenance`, `/api/provenance/coverage`, `/api/scalability/simulate`.
- **Known problems:** purely a reference page; the scalability table is a projection, not a measurement of the live system; no freshness timestamps per source ("generated at" only); no links from a number elsewhere in the app to its source row.
- **Screenshot:** `26-data-sources.png`.

---

## 4. Analytics inventory

Freshness for the public dataset is **static**: every computation reads files fixed at build time (price history 2024-01-02 to 2026-08-06; news 2025-12 to 2026-08; limits as of 2026-08-01; event register built 2026-11-01). "On request" means computed each time the endpoint is called from in-memory data. Nothing is real-time. Nothing is scheduled (there is no batch job or cron).

| # | Analytic | Definition / formula | Inputs | Computed in | Displayed on | Freshness |
|---|---|---|---|---|---|---|
| 1 | **Relationship feature vector** | Per issuer pair: sector 1/0; geography 1 (same country) / 0.5 (same region) / 0; supply chain = max criticality of a supply-type edge (SUPPLIES, CUSTOMER_OF, LICENSES_TO, LICENSES_FROM), kept directional (forward and reverse); ownership 1.0 if a PARENT_OF/SUBSIDIARY_OF edge exists (never, in this data); semantic = TF-IDF (1–2-grams) cosine over business descriptions; news = Σ min(weight_a, weight_b) over shared themes ÷ √(Σ weights_a × Σ weights_b) × number shared, capped at 1; market positive = max(ρ, 0); market negative = max(−ρ, 0), ρ from daily returns. Missing components are `null`, never 0. | entities.json, fact_edges.json, entity_keyword_weights.json, price CSVs | Backend `core/scoring.py` | Relationships, Entity Explorer (waterfall), Graph Explorer (derived edges), Distance Map components | On request |
| 2 | **Composite relatedness score** | Weighted average of available components with weights re-normalised over the available ones (default 0.15 / 0.08 / 0.25 / 0.10 / 0.12 / 0.15 / 0.10 / 0.05); exact waterfall decomposition. Four presets plus user weights. Heuristic, not fitted. | vector, weights | `core/scoring.py` | Relationships, Entity Explorer, Model Lab, Distance Map, Counterparty 360 (indirect), Event Studio nominations | On request |
| 3 | **Candidate generation** | Union of five bounded sources: sector/country block (≤40), TF-IDF nearest neighbours (15), shared-theme neighbours (15), market-correlation neighbours (10), direct fact-graph neighbours. Only candidates are scored. Instrumentation: theoretical pairs, candidates, retained, reduction ratio. | entities, themes, prices, graph | `core/candidates.py` | Entity Explorer diagnostics rail; Data Sources scalability table | On request |
| 4 | **Market correlation (signed)** | Pearson correlation of daily simple returns on aligned dates: full sample, rolling 30 days, stress window 10 days; positive and negative channels kept separate; `n_obs` reported; as-of variant for backtests (no look-ahead). Only 14 issuers have prices. | price CSVs (about 650 rows each; one issuer about 18 rows) | `core/market.py` | Relationships inspector, Entity Explorer (table + explain), Risk clusters (≥ |0.3|) | On request (returns cached) |
| 5 | **Per-relationship analysis ("explain")** | Vector + composite + typed path (BFS over the fact graph) + templated or LLM sentence. | pair of issuers | `GET /api/entities/{a}/explain/{b}` | Relationships inspector; Entity Explorer Explain | On request |
| 6 | **Distance Map ρ** | d = 1 − criticality (ownership edge); 1 − 0.85×criticality (direct supply edge); for a 2-hop supply chain d = min(d_parent + (1 − crit) × 0.65, 0.99); else d = 1 − composite score over the bounded candidate set. ρ = 1 − d. Channel: ownership / supply / "historical" (market ≥ 0.5 or sector ≥ 0.7 and news ≥ 0.5) / "hidden". Concentration alert at ≥ 4 issuers with ρ ≥ 0.75. | counterparty id | `core/distance.py` | Distance Map | On request |
| 7 | **Ownership / parent-subsidiary** | GLEIF Level-2 cache for 40 entities; mapped to PARENT_OF/SUBSIDIARY_OF only when both ends are tracked. Result: 0 direct parents, 0 ultimate parents, 37 "reporting exceptions", so **no ownership edges exist**. | gleif_level2_cache.json | `core/ownership.py` | Entity Explorer "Corporate hierarchy" (empty) | Static (fetched once) |
| 8 | **Supply-chain / licensing links** | 31 SUPPLIES and 3 LICENSES_TO edges, each with a curated criticality 0.15–1.0, evidence status (84 WELL_DOCUMENTED_PUBLIC, 2 REPORTED_NEWS) and URL. The other 52 fact edges are sector or country membership. | fact_edges.json | `core/data.py`, `graph_store.py` | Entity Explorer, Graph Explorer, Impact Map paths, scoring | Static |
| 9 | **Mode 1 bounded traversal** | Typed-path hop expansion from detected entities, decay 0.65 per hop, max 2–3 hops. | event text | `core/event_parser.py` | Event Studio (derivation) | On request |
| 10 | **Mode 2 Personalized PageRank** | networkx PageRank (damping 0.85) seeded on detected issuers over the issuer-only graph: fact edges both ways (reverse weighted ×0.6) plus top-8 derived edges (score > 0.05). Exposure deliberately excluded. | event text | `core/ppr.py` (graph cached after first use) | Event Studio | On request |
| 11 | **Event detection (text → event)** | Deterministic: alias index (ticker, legal-name stems, parenthetical abbreviations) → entities; keyword/synonym match → themes; country list → countries; five keyword rule sets → event type (natural disaster, funding stress, geopolitical, thematic/tech, supply-chain); optional LLM suggestion that must pass a resolver guard. | free text | `core/event_parser.py`, `ai/provider.py` | Event Studio, Relationships (event intent) | On request |
| 12 | **Event retrieval and verification (Impact Map)** | A static register of 8 events for one issuer, each from an approved source (4 approved source ids: issuer newsroom, regulator, related-party newsroom, filings), verified by retrieval (quotes found in text, date confirmed). Selection: admissible, recent (window), issuer named in evidence, newest first, ≤5; unreturned records listed with reasons. | events_nvidia.json, approved_sources.json, gazetteer (24 places) | `core/event_discovery.py` | Event Impact Map | Static register (built 2026-11-01) |
| 13 | **Documented path classification** | From each event's named companies to the target: DIRECT_MENTION, DOCUMENTED_DIRECT, DOCUMENTED_INDIRECT (≤2 hops, ≤3 paths over SUPPLIES, LICENSES_TO, PARENT_OF, SUBSIDIARY_OF) or NO_DOCUMENTED_PATH. Impact always "Not estimated". | register, fact graph | `core/event_graph.py` | Event Impact Map | On request |
| 14 | **Dynamic event discovery** | Operator-run: resolve entity → fetch from approved providers (two configured: a feed and a government register) → extract → dedupe → verify → stage for human review. Needs `CCRIG_DISCOVERY_NETWORK=1`. | providers.json | `discovery/*` | Impact Map ("Dynamic discovery" mode) | Operator-triggered; not available publicly |
| 15 | **Theme statistics** | Per curated theme: mention count; velocity = (recent − earlier) ÷ earlier around the corpus midpoint date (999 sentinel when there is no earlier mention); entity coverage; source diversity; "portfolio relevance" = distinct counterparties holding covered issuers. | 48 documents, 47 themes | `core/themes.py` | Theme Radar, Entity Explorer theme pills | On request |
| 16 | **Theme discovery** | TF-IDF (1–2-grams, English stop words) → agglomerative clustering (cosine, average); clusters = max(2, min(14, docs÷3)); min cluster size 2; deduped against curated themes; novelty score = share of documents with no curated theme; optional LLM label. | news corpus | `core/themes.py` | Theme Radar | Cached per process; recomputed on ingest/discover |
| 17 | **CCR driver classification** | Deterministic first-match cascade over evidence flags: LIMIT_BREACH, DATA_SOURCING_ISSUE, DATA_ISSUE, MODEL_COVERAGE_CHANGE, MODEL_RECALIBRATION, VOLATILITY_UPDATE, RECOVERY_CHANGE, REPLACEMENT_COST_MOVE, NON_NETTED_EXPOSURE, WWR_RELATED, NETTING_CHANGE, COLLATERAL_CHANGE, NEW_TRADE, MATURED_TRADE, MARKET_MOVE, SIMULATION_NOISE (only with an explicit flag), SMALL_MOVE, UNKNOWN. | 16 evidence flags per record | `core/ccr_priority.py` | Inbox, Counterparty 360, Event Studio table, Exposure Movers | On request |
| 18 | **CCR derived metrics** | ΔPFE, ΔNSE = current − previous; utilisation = metric matching the limit's own type ÷ limit (PFE_LIMIT→PFE, SETTLEMENT_LIMIT→settlement, STRESS_LIMIT→NSE; otherwise "Unavailable"); headroom; excess; overdue = age > SLA days. | exposure and limit fields | `core/ccr_priority.py` | Inbox, Controls, Counterparty 360 | On request |
| 19 | **Priority rule matrix** | CRITICAL: overdue breach, or WWR with utilisation ≥ 85%, or utilisation ≥ 100%. INFORMATIONAL: no confirmed exposure metric. LOW: PFE < 50 and utilisation < 10%. HIGH: real-risk driver with |Δ| ≥ 150 or utilisation ≥ 85%. MEDIUM: routed model/data drivers or other material moves. Thresholds labelled POC_HEURISTIC. Output is a label plus reasons, never a score. | enriched record, driver | `core/ccr_priority.py` | Inbox, Counterparty 360, Event Studio, Entity Explorer | On request |
| 20 | **Decision object** | Decision text, reasons, missing information, recommended owner, control flags, exposure paths. | classified record | `core/ccr_priority.py::build_decision` | Inbox, Counterparty 360 | On request |
| 21 | **Materiality join** | For nominated issuers, attach CCR counterparties whose `reference_entity_id` matches, sorted by priority then |ΔPFE|. | issuers, queue | `core/materiality.py` | Event Studio, Entity Explorer, Relationships | On request |
| 22 | **Risk clusters** | From each exposure position traverse the "Connected Risk Graph" to reference entity, structural neighbours (supply, ownership), statistical neighbours (|ρ| ≥ 0.3, signed); members tiered DIRECT / FIRST_ORDER (≤3 structural + ≤2 statistical) / CONTEXTUAL (≤10); label uses a sector only if ≥ 50% of the first-order members share it; story, "why it matters" and action are templated from gathered evidence. | graph, record | `core/risk_clusters.py`, `graph_builder.py`, `graph_query.py` | Counterparty 360 | On request |
| 23 | **Concentration (portfolio counterparties)** | Sum of exposure % by issuer sector and by theme-weighted exposure (top 8). Indirect relationships: for each holding (largest first) top-5 related issuers with composite > 0.3 that are not held, capped at 20. | exposure_edges.json | `routers/counterparties.py` | Counterparty 360 (collapsed section) | On request |
| 24 | **Exposure movers** | Sorting of queue rows by |ΔPFE|, |ΔNSE|, ΔRC or equity/FX delta. | queue | **Frontend** `ExposureMovers.tsx` | Exposure Movers | On request |
| 25 | **Backtest (methodology v2)** | One scenario. Model score computed as of T0 from fact graph and pre-T0 correlations; labels = absolute abnormal return (entity return − mean of other eligible entities) over one common forward window; positives = top third; metrics precision/recall/NDCG at 3 and 5, random baseline and hypergeometric tail probability; before/after correction table. | prices, narrative | `core/backtest.py` | Backtest Lab | On request |
| 26 | **Anchor calibration** | Constrained pairwise logistic-loss fit (γ = 8, L2 λ = 2 toward the starting weights, scipy `minimize`) on 34 hand-made anchors (25 train, 9 holdout); reports satisfied counts, mean margin, loss; separate market-agreement diagnostic. Experimental. | calibration_anchors.json | `core/calibration.py` | Model Lab | On request (3.3 s) |
| 27 | **Scalability projection** | Pair counts and candidate estimates for N entities plus a small measured brute-force benchmark. | — | `core/scalability.py` | Data Sources | On request |
| 28 | **Studio flow metrics** | Per stage: records processed/accepted/rejected, elapsed ms, resolution counts (exact, mapped, ambiguous, unresolved), validation counts, evidence refs; unmeasured values declared unavailable. | ledger rows | `studio/flow.py` | Data Intelligence Studio | Real time for operators; fixed for the saved recording |

### 4.1 Counterparty relationship discovery — what exists and what is missing

| Relationship type | Status |
|---|---|
| Supply chain / licensing between issuers | **Built (small).** 34 curated directional edges between issuers (31 SUPPLIES, 3 LICENSES_TO) with criticality and evidence status. No counterparty-to-counterparty supply links. |
| Ownership, parent/subsidiary | **Plumbing only.** Code path from GLEIF Level-2 to PARENT_OF edges exists and is tested on a demo pair; the real cache returns zero parents for all 40 entities, so the graph has no ownership edges and the scoring component is always excluded. |
| Guarantor | **Missing in analytics.** The Studio's relationship contract accepts GUARANTEES, FINANCES and AFFILIATED_WITH, and the overlay can carry them if an operator approves such evidence; none exist in the shipped data and no screen computes with them. |
| Shared issuers (two counterparties holding the same issuer) | **Missing.** Derivable from the 80 exposure edges but not computed or shown; no counterparty-to-counterparty edge or "common holdings" view. |
| Sector/country membership | Built (52 edges used as graph structure, not as insight). |
| Derived similarity (sector, geography, text, news themes, price) | **Built**, issuer-to-issuer; counterparty queries (Distance Map) apply it with counterparties' own metadata, which yields undifferentiated results. |
| Counterparty → issuer exposure | Built, synthetic: 80 edges (56 HOLDS_EQUITY, 16 HOLDS_BONDS, 5 LENDS_TO, 3 HOLDS_VIA_FUND) for 18 counterparties (3–9 each); a separate CCR dataset links 2 of 19 counterparties to one reference issuer. |
| Correlation / co-movement | **Partial.** Pairwise Pearson on daily returns for 14 issuers only; full / 30d / 10d windows. Not computed: counterparty-level or portfolio-level correlation, correlation matrix or heatmap, rolling time series display, beta to factors, lead-lag, tail dependence, regime changes. The Distance Map "ρ" is a graph-distance proxy, not a correlation. |
| Per-relationship analysis | Built for issuer pairs (explain). Missing for counterparty pairs, for relationship history/time, and for relationship strength over time. |
| Event detection | **Partial.** Text-to-entity/theme/type rules; one worked issuer for verified events (8 records); operator discovery behind a switch with two providers. No continuous monitoring, no alerting, no event de-duplication across days, no severity, no impact. |
| Stress testing and shock scenarios | **Missing as an engine.** No shock is applied to any value. What exists: three named scenario labels (`credit-spread widening`, `equity vol spike`, `currency depreciation shock`) attached as text to some CCR records; static NSE/PFE values supplied in the data; a 10-day "stress window" correlation (a recent-window statistic, not a stress test); event propagation scores (Mode 1/2) that rank issuers but have no units of loss. `docs/LIMITATIONS.md` also lists DebtRank-style contagion as not implemented. |
| News retrieval | **Missing as a live capability.** There is no news feed. The "news" corpus is 48 static documents (14 real headlines with URLs, 34 synthetic) tagged by hand with entities and keywords; matching to issuers is by those tags; no recency weighting beyond a midpoint split; no deduplication of the stored documents. The only retrieval path is operator discovery from approved hosts (off by default). |
| News summarisation | Templated sentences by default; LLM rephrasing only if configured. No article summaries. |
| News sentiment | **Absent** (no sentiment code anywhere in the repository). |

---

## 5. Data model

### 5.1 Entities (all JSON, loaded to memory; ids are strings)

| Entity | Count | Fields (type) |
|---|---|---|
| **Entity** (`entities.json`) | 82 total: 43 Company/Issuer, 18 Counterparty, 14 Country, 1 Country/Region, 6 Sector | `id` str, `name` str, `node_type` enum, `sector` str\|null, `industry` str\|null, `country` str\|null, `region` str\|null (North America 40, Europe 15, APAC 6, null 21), `ticker` str\|null, `has_market_data` bool (14 true), `is_synthetic` bool (18 true: counterparties) |
| **Fact edge** (`fact_edges.json`) | 86 | `source` id, `target` id, `relation` enum {BELONGS_TO_SECTOR 43, SUPPLIES 31, OPERATES_IN 9, LICENSES_TO 3}, `criticality` float 0.15–1.0, `note` str, `evidence_status` enum {WELL_DOCUMENTED_PUBLIC 84, REPORTED_NEWS 2}, `evidence_url` str\|null |
| **Exposure edge** (`exposure_edges.json`) | 80 | `counterparty` id, `issuer` id, `relation` enum {HOLDS_EQUITY 56, HOLDS_BONDS 16, LENDS_TO 5, HOLDS_VIA_FUND 3}, `exposure_pct` float (share of the counterparty's book), `is_synthetic` true |
| **Portfolio counterparty** (`counterparties.json`) | 18 | `id` (`CP_<NAME>`), `name`, `industry`, `country`, `region`, `is_synthetic` |
| **CCR counterparty record** (`ccr_counterparties.json`) | 19 | `id` (`CP_<TYPE>_<NAME>`), `name`, `legal_entity`, `counterparty_type` (Hedge Fund, Sovereign, Bank, Bank Treasury, Asset Manager, Family Office, SPV, Sovereign Wealth Fund), `rating` (all null), `watchlist` bool, `reference_entity_id` str\|null (2 of 19 set), `product` (11 distinct products), `netting_set`, `collateral{type, csa, haircut}`, `notional`, `direction`, `unmatched_trades`, `exposure{rc,pfe,nse previous/current, settlement_exposure}` (numbers in $mm; null when unavailable), `sensitivities{equity_delta prev/current, fx_delta, dv01, cs01}`, `limit{limit_id, limit_type, limit_value, currency, as_of_date, source}` (16 of 19 have a limit value), `breach{is_breach, age_days, sla_days, root_cause, excess}` (1 active), `driver_evidence{16 booleans}`, `analyst_explanation`, `risk_factor_path` [str], `linked_event_id`, `coverage_owner`, `suggested_action`, `is_synthetic`, `source_type` |
| **CCR scenario label** (`ccr_events.json`) | 4 (3 + "NONE") | `id`, `label`, `description`, `risk_factor_path`[5 str], `is_synthetic` |
| **Product taxonomy** | 14 products | per product: `label`, `risk_factors`, `sensitivities`, `ccr_channels`, optional `important_attributes` |
| **Theme / keyword** (`keywords.json`) | 47 | `id`, `label`, `synonyms`[~5] |
| **Entity–theme weights** | ~55 entities | map theme id → weight (float 0–1) |
| **News item** (`news_real.json`, `news_synthetic.json`) | 14 real + 34 synthetic | `id`, `date` (2025-12-03 to 2026-08-06), `entities`[ids], `keywords`[theme ids], `title`, `source` (publisher), `url` (real only), `snippet`, `text` (synthetic only), `is_synthetic`, `source_type` |
| **Price series** (`raw_prices/*.csv`) | 14 files, ~650 rows (one has ~18) | `date`, `close` (daily; 2024-01-02 to 2026-08-06) |
| **Verified event** (`events/events_nvidia.json`) | 8 (one issuer) | `id`, `kind`, `title`, `category` (CORPORATE_ANNOUNCEMENT 3, PRODUCT_ANNOUNCEMENT 2, EARNINGS_RELEASE 1, PARTNERSHIP_ANNOUNCEMENT 1, REGULATORY_ACTION 1), `published_date`, `event_date`, `event_date_basis`, `location{gazetteer_key, basis, basis_text}`, `sources[{id, publisher, url, title, published_date, tier, retrieved_at, …}]`, `evidence[{source_id, quote, url}]` (up to 6), `verification{status, method, checked_at, http_status, date_confirmed, quotes_total, quotes_found}` |
| **Gazetteer / approved sources / aliases** | 24 places / 4 sources / alias rules | place `{label, kind, lat, lon, country}`; source `{id, domains[], tier, description, limits}` |
| **GLEIF** | 40 LEI records; 40 Level-2 records | `lei`, `legal_name`, `country`, `hq_city`, `status`; Level-2: `direct_parent`, `ultimate_parent`, reporting-exception flags, `source`, `retrieved_at` |
| **Calibration anchor** | 34 (25 train / 9 holdout) | `anchor_entity`, `preferred_entity`, `less_related_entity`, `reason`, `split` |
| **Scenario (backtest)** | 3 slots, 1 implemented | computed in code; narrative from a synthetic news item |
| **Operator Studio tables** (SQLite, optional) | per workspace | sources, jobs, findings, events (hash-chained ledger rows), decisions, releases, discovery_runs, current_release |

A "news item" is not linked to a counterparty directly, only to issuers and themes. There is no "scenario" entity for stress testing and no exposure time series (only previous/current snapshots).

### 5.2 How relationships are stored

- **Representation:** edge lists in JSON, loaded into three networkx `MultiDiGraph`s at start-up (`FACT_GRAPH`, `EXPOSURE_GRAPH`, `DERIVED_GRAPH`, in `core/graph_store.py`), plus a "Connected Risk Graph" (`graph_builder.py`) built from exposure, taxonomy, events and fact edges. No graph database.
- **Three layers, never summed:** Layer A = sourced, directional facts; Layer B = derived, symmetric, a *vector* computed on request and never stored; Layer C = synthetic counterparty→issuer exposure. The UI repeats this separation in labels.
- **Types and direction:** `SUPPLIES` (source supplies target), `LICENSES_TO`, `BELONGS_TO_SECTOR`, `OPERATES_IN` (+ `PARENT_OF`/`SUBSIDIARY_OF`, `CUSTOMER_OF`, `LICENSES_FROM` recognised by scoring but absent from data). Direction is stored as source→target and never rewritten; reversed traversals are marked `traversedReverse` in the UI. Derived edges are symmetric and drawn dashed.
- **Confidence and evidence fields:** each fact edge has `criticality` (curated 0–1 judgement, explicitly "not a measured exposure"), `evidence_status`, `evidence_url`, `note`. There is **no numeric confidence**; evidence quality is a three-way label (High / Medium / Low in the UI). Approved relationships from the Studio carry quotes, source URL, publisher, tier, published date, `relationship_as_of`, assertion basis (EXPLICIT_CUE or PROPOSER_ASSERTED) and source SHA-256, and have no criticality. Events carry quote counts verified against the retrieved text.
- **Studio overlay:** approved relationships live in a release table and are merged into graph/impact responses only when `include_studio=true`; they never enter the canonical files or the scoring.

### 5.3 Volumes, cadence and sources

- **Universe:** 43 issuers (of which 14 have prices, 40 have an LEI), 18 portfolio counterparties, 19 CCR records, 47 themes, 48 news documents, 8 verified events (one issuer), 86 fact edges, 80 exposure edges. Scoring evaluates at most a few dozen candidate pairs per query; all responses are below ~115 KB.
- **Refresh cadence:** none automatic. Files are rebuilt by running `scripts/build_dataset.py` (and `fetch_gleif_level2.py`, `build_ccr_dataset.py`) and committing the result. The event register was built 2026-11-01. Prices stop at 2026-08-06.
- **Sources:** public price CSVs, GLEIF (LEI and Level-2), public company/regulator announcements for events, hand-curated supply-chain and sector facts (cited by URL for 2 of 86 edges; the rest labelled "well-documented public"), 34 synthetic narrative documents, and a synthetic CCR dataset. The README states that no confidential or real counterparty data is present.

### 5.4 API endpoints

All under `/api`, JSON, no authentication. Pydantic validates ranges; invalid input gives HTTP 422. Types below are schemas, not data.

| Method | Path | Parameters | Response shape (abridged) |
|---|---|---|---|
| GET | `/health` | — | `{status, ai_mode, …}` |
| GET | `/search` | `q` (1..max text), `max_hops` 1–3, `min_score` 0–1 | `{query, ai_intent_classification, ai_mode, entity_matches[{id,name,node_type}], theme_match, resolved_as ('entity'\|'counterparty'\|'theme'\|'event'\|'ambiguous'), resolved_id, event_result?, ai_event_summary?, ai_followup_suggestions}` |
| GET | `/entities` | `sector, country, node_type, q, limit` ≤1000 | `{count, results[entity summary]}` |
| GET | `/entities/{id}` | `top_k` ≤50 | `{header, relationship_summary{top_related[{entity_id,name,composite_score}], instrumentation, retained_count}, theme_exposure[], fact_links[], corporate_hierarchy, counterparties_exposed[], counterparty_materiality{results[]}, market{price_series[], correlations[]}}` |
| GET | `/entities/{a}/explain/{b}` | — | `{pair{vector, composite{score, waterfall[], excluded_components[], used_weights}}, typed_path{hops[]}, ai_explanation, ai_path_explanation, ai_mode}` |
| GET | `/counterparties` | — | `{results[{id,name,industry,country,…}]}` |
| GET | `/counterparties/{id}` | — | `{header, direct_holdings[{issuer,relation,exposure_pct}], total_direct_exposure_pct, concentration_by_sector{}, concentration_by_theme_top8[], indirect_relationships[], risk_cluster_note}` (404 for CCR-only ids) |
| GET | `/themes` | `q`, `kind` | `{count, curated_count, discovered_count, results[theme]}` |
| GET | `/themes/{id}` | — | theme + `ai_suggested_label`, evidence list, discovery fields for discovered themes |
| POST | `/themes/discover` | — | `{discovered_count, results[]}` |
| POST | `/themes/ingest` | body `{id,date,title,snippet,entities?,keywords?,source?,url?}` | 403 unless `CCRIG_ENABLE_INGEST=1`; always stored synthetic |
| POST | `/event/parse` | `{text, max_hops, min_score, sector?, geography?, top_k}` | `{event_type, ai_summary, ai_context_extraction, direct_relevance[], mode1_bounded_traversal{results[]}, mode2_personalized_pagerank{results[]}, relevant_counterparties[], materiality_join{nominated_issuer_count, note, results[queue rows]}}` |
| GET | `/event/sample-scenarios` | — | `{scenarios[{id,label,query,query_type}]}` |
| GET | `/graph/ego/{id}` | `hops` 1–2, `top_k`, `min_score`, `layers`, `node_types`, `include_studio` | `{center, hops, active_layers, node_count, edge_count, nodes[], edges[{source,target,relation,layer,weight,directed,evidence}], legend, studio_overlay?}` |
| GET | `/model-lab/presets` | — | `{presets, default_weights, disclaimer}` |
| POST | `/model-lab/score` | `{entity_id, weights?, preset?, top_k}` | `{weights_used, scored_pair_count, retained_count, results[{entity_id,name,score,…}]}` |
| POST | `/model-lab/pair` | `{a, b, weights?, preset?}` | pair vector + composite |
| GET | `/model-lab/calibration/anchors` | — | `{anchors[]}` |
| POST | `/model-lab/calibration/run` | `{starting_weights?, gamma, lam}` | `{starting_weights, calibrated_weights, n_train, n_holdout, train{…}, holdout{…}, disclaimer}` |
| POST | `/model-lab/calibration/market-agreement` | `{weights?}` | `{mean_top_k_abs_correlation, baseline_mean_abs_correlation, n_top_k_pairs_evaluated}` |
| GET | `/backtest/scenarios`, `/backtest/run` | `scenario_id` | scenarios list; run: `{scenario, event_narrative_at_t0, t0, data_cutoff, metrics{precision/recall/ndcg@3, random baselines, p-values, universe_size, n_positive}, correction_steps[], model_ranking_top_k[], observed_subsequent_movers_top_k[], evaluation{excluded[]}, seed_entities, warnings[]}` (400 for the two unimplemented slots) |
| GET | `/provenance`, `/provenance/coverage`, `/scalability/simulate` | — | totals + sources[]; rows[]; projections[] + measured_benchmark[] |
| GET | `/metric-definitions`, `/metric-definitions/{id}` | — | metric text (definition, formula, caveats) |
| GET | `/priority-queue` | `priority`, `driver` | `{summary{critical,high,medium,low,informational,overdue_breaches,model_or_data_items}, count, results[CCR record + delta_pfe, delta_nse, utilisation_pct, headroom, is_breach, is_overdue, excess, event, driver, driver_evidence_trace[], priority, reasons[], decision{…}], thresholds, note}` |
| GET | `/priority-queue/{id}`, `/priority-queue/{id}/risk-clusters` | — | one record; `{counterparty_id, count, results[cluster]}` |
| GET | `/breaches` | `status` (`overdue`\|`within_sla`) | `{count, results[queue rows]}` |
| GET | `/distance-map/counterparties`, `/distance-map/counterparty/{id}` | `min_rho` 0–1, `max_hops` 1–3 | list; `{counterparty_*, exposure_context[], issuers[{issuer_id, distance, rho, channel, channel_evidence, typed_path[], score_components, hop_count,…}], high_rho_count, concentration_alert, channel_counts, dominant_channel, methodology_note}` |
| GET | `/impact-map/search`, `/impact-map/register` | `q` | `{matches[{entity_id,name,ticker,event_coverage}], message}`; register metadata |
| GET | `/impact-map/{id}/events`, `/impact-map/{id}/compare` | `limit` ≤5, `recency_days` ≤730, `as_of` (YYYY-MM-DD), `mode` (curated\|discovered), `include_studio` | `ImpactResponse{entity, query, register, events[], not_returned[], explanation, graph{nodes,edges}, limitations[], studio_overlay?, provenance?, review?}`; comparison `{curated, discovered, overlap, how_they_differ}` |
| GET | `/studio/status`, `/studio/contracts` | — | capabilities, limits, target list (10 contracts); contract definitions |
| (operator only; exists only with `CCRIG_ENABLE_STUDIO=1`, `X-Studio-Token`) | `/studio/jobs` (POST, GET), `/jobs/{id}`, `/jobs/{id}/staging`, `/jobs/{id}/approve`, `/jobs/{id}/reject`, `/datasets…` (releases, rollback, restore, export), `/ledger/verify`, `/discovery/…`, `/relationships`, `/sources`, `/flow/scenarios`, `/flow/run`, `/flow/jobs/{id}`, `/flow/events`, `/flow/stream` (SSE) | Studio jobs, ledger and flow projections |
| (operator only) GET | `/ingest/runs/{run_id}/events?since=` (SSE; `latest` alias), POST `/ingest/demo-run` | — | `ingest` events: `run_started, progress, log, stage_done, run_completed, error` (+ optional `simulated`, `targets`) |

---

## 6. LLM / agent components

- **Default behaviour (as audited): no model is called.** `DeterministicProvider` produces intent classification (keyword rules), entity/theme extraction (alias and keyword matching), explanation sentences (templates filled from the computed vector and path), event summaries, theme labels and follow-up suggestions. The sidebar pill says "Offline deterministic mode".
- **Optional model layer (`OpenAICompatibleProvider`, `ai/provider.py`):** enabled only when `AI_BASE_URL`, `AI_API_KEY` and `AI_MODEL` are all set. Any OpenAI-compatible chat endpoint. Tasks and prompts (summarised): one system prompt ("credit/counterparty-risk analyst assistant; summarise **only** the structured object given") for (a) intent classification, (b) rewriting the already-computed relationship explanation, (c) rewriting a path explanation as one sentence, (d) rewriting an event summary for a risk committee in 3–4 sentences, (e) a 2–4-word theme label from top terms, (f) follow-up question suggestions, (g) answering from supplied snippets; and a separate extraction prompt returning JSON (entities and event context). Settings: temperature 0.2, `max_tokens` 220 (350 for extraction), 15 s timeout. **Any failure falls back to the deterministic provider.** Model output never feeds scoring: the AI is explicitly "never used for bulk pairwise scoring".
- **Event-discovery agent (`discovery/agent.py`, operator-only):** an OpenAI-compatible JSON client (temperature 0, JSON response, 30 s timeout) may *suggest* a category, extra verbatim quotes and relationship candidates for one retrieved document. The prompt treats the document as untrusted data. A guard keeps only: categories from the contract list, quotes found verbatim in the text, company names that appear in the quote and resolve to exactly one entity by the deterministic resolver (model-supplied ids are ignored). Relationship statements stay `AI_PROPOSED_UNREVIEWED` candidates, never edges. Failure returns nothing and the run uses deterministic extraction.
- **Studio:** the pipeline is deterministic (parse, profile, validate, resolve). The "language model" stage in the visual is optional and, by design, is shown running only if a model call is recorded in the ledger; today nothing writes such a row.
- **Ingest Bench:** the names "Haiku / Sonnet / Opus" are labels in an animation; no agent exists behind them.
- **Pipeline flow, latency, failure, storage:**
  - Input → (deterministic classification) → deterministic lookup → deterministic scoring → *optional* model rewrite of the text → JSON response. Rewrites add one blocking HTTP call (up to 15 s) per sentence; several endpoints make 2–3 such calls in sequence (for example explain: explanation and path explanation). No streaming, no retries, no timeouts surfaced to the user.
  - Results are **not cached or stored**. Only process-level memoisation exists for deterministic structures (TF-IDF model, PPR graph, theme discovery, price returns). Studio decisions and the discovery runs are stored in SQLite, hash-chained, for operators.
  - Latency of the audited deterministic mode (local): most endpoints 5–80 ms; event parse about 1.0–1.2 s on first use then fast; calibration about 3.3 s. Latency with a model configured was not measured (no key available).
- **Not present:** a retrieval-augmented question-answering agent, tool-using agents, multi-step planning, evaluation of model outputs, or any prompt/response logging.

---

## 7. UX and technical assessment

### 7.1 Top 10 UX problems (most severe first)

1. **Two unconnected counterparty universes.** 19 CCR records and 18 portfolio-holdings counterparties share no ids (2 names coincide). Counterparty 360 lists both as pills; most selections end with "no portfolio data" or "no CCR record". Only 2 of 19 CCR records link to an issuer, so the headline promise (graph relationships → exposure) works for almost nothing. The default landing selection triggers a 404.
2. **No stress testing or shock scenarios and no time series.** The product talks about shocks and stress, but there is no shock input, no scenario result and no exposure history chart. Analysts see static previous/current numbers. This is the biggest functional gap against the stated redesign direction.
3. **Entity-first design without discovery aids.** Entity Explorer, Graph Explorer and Model Lab need a typed ticker or internal id (upper-cased, no autocomplete, no recents); there is no global search; results show internal ids (Graph Explorer, Event Studio mode tables, Entity Explorer lists) instead of names.
4. **Overlapping pages with no clear hierarchy.** Inbox, Exposure Movers, Controls and Counterparty 360 all re-slice one 19-row queue; Relationships, Entity Explorer, Graph Explorer and Distance Map all answer "what is related". Sixteen flat sidebar links, inconsistent names between sidebar, URL and title, and operator tools (Studio, Ingest Bench) mixed into the analyst menu.
5. **Charts are almost absent and some mislead.** Only two real charts. Theme Radar's x-axis is dominated by a 999 sentinel (two stripes of bubbles, labels missing). Distance Map shows 22 near-identical "Hidden Corr." rows with ρ 0.18–0.48 and "Private" beside public issuers. Tables of 9–11 columns at 10–11 px carry most of the insight.
6. **Heavy jargon and disclaimers.** Layer A/B/C, PFE, NSE, RC, WWR, "POC_HEURISTIC", "typed path", and subtitles that are paragraphs of methodology. Units ($mm) are not shown. The "why" is often collapsed (Event Studio derivation) while the caveat is expanded.
7. **State is not durable or shareable.** Relationship search, inspector, Model Lab weights, Event Studio text (only via `?text=`), Distance Map filter and breadcrumb are lost on reload; breadcrumb links ignore the query they carry; no export (CSV/PDF), no saved view, no copy-link for most states.
8. **Accessibility and interaction quality.** Navigation done with `<a onClick>` and `<span onClick>` (no href, not focusable, no middle-click); status communicated mainly by colour; 10–11 px type; canvas pages (map, Studio, Ingest Bench) provide little non-visual equivalent; no skip link; modals/drawers have no focus management beyond the map markers.
9. **Four visual languages.** Light institutional pages, dark full-bleed Impact Map, dark glowing Studio and "paper" Ingest Bench each define their own tokens; the shell does not adapt. No global theme control.
10. **Loading and error handling is inconsistent.** Several pages swallow API failures (`.catch(() => null)`) and show a blank card; others show a warning box; the loading state is plain text without skeletons (except the map). The only global signal is the sidebar pill.

Also worth noting: the Ingest Bench (a demo) throws a TypeError on its first frames in the dev server.

### 7.2 Performance bottlenecks (measured locally, no AI key)

| Observation | Evidence (`docs/audit-screens/_metrics.json`) |
|---|---|
| All page loads settle in about 2.0–2.2 s (dev server, includes module loading and a deliberate 1.2 s settle wait in the script; not a meaningful absolute figure). | per-page `loadMs` |
| API calls are small and fast on one machine: p95 below ~200 ms, payloads 0.1–113 KB. Largest: `/api/priority-queue` 68 KB (the whole queue for 19 records, fetched on Counterparties twice in dev, on Inbox, and on Exposure Movers); `/api/graph/ego` 2-hop 113 KB; `/api/entities/{id}` about 100 KB. These will grow linearly with a larger universe because nothing is paginated. | `apiKB` per page |
| Slow calls: `POST /api/event/parse` first call 1.0–1.2 s (lazy PPR graph build), `POST /api/model-lab/calibration/run` 3.3 s (scipy optimisation, blocks the request), operator Studio runs depend on file size. | `slow` lists |
| The priority queue is rebuilt (enrich, classify, rank, decision) on every call; `/api/priority-queue` itself builds it twice (rows and summary). No response caching layer. Every analytic recomputes from memory per request: acceptable at 43 issuers, not at thousands. | `routers/priority.py`, `core/ccr_priority.py` |
| In-browser (GitHub Pages) mode downloads Pyodide plus numpy, scipy and scikit-learn before the first answer; a boot overlay covers this. Time not measured here. The backend source (`app/` and `data/`) is served as static files and executed in WASM. | `api/pyodideClient.ts`, `PyodideBootOverlay` |
| Production bundle about 3.6 MB on disk (docs: ~1.09 MB / 331 KB gzip main chunk; Cytoscape and Recharts dominate); no code splitting by route. | `frontend/dist`, `docs/LIMITATIONS.md` |
| Canvas animation loops (Impact Map, Studio, Ingest Bench with eight canvases) run continuously while a page is open. The Ingest Bench is the heaviest. | `canvas` counts |
| Brute-force nearest neighbours; the code states it does not scale past ~10,000 entities without an ANN index. | `docs/LIMITATIONS.md` |

### 7.3 Code-quality issues that affect a redesign

- **Untyped API layer:** every `api.*` method returns `any`; pages index into responses with `(r: any)`. Response shapes are documented only in the backend and in a few hand-written TypeScript interfaces (Impact Map, Distance Map, Studio). A redesign should first generate types from the OpenAPI schema.
- **Duplicated UI pieces:** `PriorityPill` / `PriorityTag` and priority colour maps exist in four pages; `Field`, `Collapsible`, "top-5 / show all" toggles and `<a onClick>` navigation are re-implemented per page; `RiskPath` and `Waterfall` are the only shared visual components besides badges.
- **Hard-coded values and business rules in the frontend:** control-flag thresholds (≥85% "near limit"), tier cut-offs (0.8/0.6/0.4) and their labels, slice(0,5) limits, hex colours in Cytoscape, default issuer ids and sample headlines, exposure-mover arithmetic, breach exposure-by-limit-type. These duplicate or pre-empt backend rules.
- **State and URL handling:** page-local state, mixed use of URL parameters (some pages read them, Relationships does not), `useEffect(..., [])` that deliberately omits dependencies, duplicated requests under React StrictMode in dev.
- **Backend coupling:** analytics read a global in-memory `STORE`; graphs are module-level singletons; the `ccr_priority` module also contains presentation copy (plain-English flag translations, decision text). Two counterparty datasets are loaded through different paths. The in-browser mode relies on `browser_dispatch.py` reproducing FastAPI validation; endpoint signatures with `Depends`, `Header` or `Request` would break it (guarded by a startup check).
- **Data model limits:** no time dimension for exposure, relationships or news; no scenario entity; no counterparty-counterparty edges; evidence quality is a label rather than a number; ownership data is empty.
- **Good practices to keep:** deterministic outputs (hash-stable responses, tested), layered separation of facts / derived / exposure, never inventing data (explicit "Unavailable"/"Not estimated"), request validation shared by server and browser, tests (43 backend modules, frontend unit tests, Playwright suites), per-field provenance badges, operator-only gating of ingestion.

### 7.4 What to reuse and what to rebuild

| Reuse as is (or nearly) | Rebuild or replace |
|---|---|
| Backend `core/` analytics (scoring, candidates, market, distance, ccr_priority, event_parser/graph/register, themes, backtest), the validation harness and the deterministic provider. Treat them as a service; fix data gaps rather than logic. | The Counterparty 360 page and the two-universe counterparty model (needs one counterparty master with a crosswalk to issuers). |
| `RiskPath`, `Waterfall` (score decomposition), `DataBadge`/provenance idea, `MetricDefinition` popover pattern. | All table-only pages (Inbox, Controls, Exposure Movers, Entity Explorer lists): convert to filterable lists plus charts and a detail panel. |
| `impactmap/` pure logic and `GeoStage` map (self-contained, tested, accessible markers). | Graph Explorer's rendering and interaction (names, labels, node inspector, filters, clustering). |
| Studio (`studio/`) and Ingest Bench (`ingest-bench/`) as separate operator surfaces with their own tokens; the event contract and SSE helpers. | Navigation and shell (grouping, global search, state in the URL, role-aware menu), and a single design-token system covering light and dark. |
| Pyodide static-build architecture, if a serverless public demo remains a goal. | The API client (generated types, caching/data-fetch library, pagination, error and loading primitives). |
| The idea of "graph nominates, exposure ranks" and the rule-matrix priority. | Theme Radar (axis handling, labels, minimum sample), Distance Map (differentiating metric), Model Lab (saved weights, rank-change view). |
| | New: scenario/shock engine, exposure time series, correlation views, live news pipeline, sentiment, ownership data. |

---

## 8. Open questions for the product owner

1. **Counterparty master:** should the 19 CCR records and 18 portfolio counterparties become one list? Is there a real crosswalk from a counterparty to its LEI, parent, guarantor and reference issuers? Which identifier is authoritative?
2. **Real data and hosting:** will the redesign connect real positions or counterparty data? If yes, what security controls, hosting, authentication and roles are required (the current app has none, and the standing rule is no confidential data on public hosting or external AI services)?
3. **Stress and shock scope:** which shocks (rate, FX, credit spread, equity, commodity, geopolitical), which measures to shock (PFE, NSE, collateral, limits) and who owns the model? Is "Not estimated" for financial impact still a hard requirement, or can scenario results show model output?
4. **Correlation:** which correlation is wanted (price-based, spread-based, factor-based, exposure-based), on which universe (14 issuers with prices is too few), at what horizon, and for which entities (issuers, counterparties, portfolios)?
5. **News:** which providers, licences and refresh cadence? Is sentiment required, and at what quality bar? Should news attach to counterparties directly or via issuers and themes? What recency half-life?
6. **Relationship sources:** which ownership, guarantor, supply-chain and "shared issuer" sources are acceptable and how fresh? Are curated criticality scores acceptable as an input, or should they be replaced by sourced evidence?
7. **LLM policy:** which model tasks are allowed (extraction, summarisation, explanation), under what data-handling terms, and with what human review? Should the Ingest Bench and Studio language-model stage be wired to real calls?
8. **Users and workflow:** who are the users (CCR analysts, relationship managers, reviewers)? Should the Inbox support assignment, status, comments and audit? Is export (CSV/PDF/slide) needed?
9. **Time and history:** is a point-in-time/historical view (as-of dates for exposure, relationships and events) in scope, given today's snapshot-only model?
10. **Priority rules:** are the POC thresholds (50 / 85 / 150 $mm etc.) and the driver cascade meant to be replaced by the institution's own policy? Who signs off on priority definitions?
11. **Coverage:** the event register covers one issuer and the price data 14 issuers. What is the target universe size (hundreds? thousands?), which would force the ANN, caching and pagination changes noted above?
12. **Operator tools:** should the Studio and Ingest Bench remain in the same product and navigation, or become a separate admin app? Is the Ingest Bench an operations screen or a demo?
13. **Unclear from the code:** how the dispatcher behaves under real concurrency in a hosted deployment (the app was only exercised single-user); the latency of AI-enabled mode (no key was available); behaviour of the live Studio path in this audit's environment (the operator switch was off, only the saved replay was seen); and the exact cause of the Ingest Bench TypeError (location identified, not investigated further).
