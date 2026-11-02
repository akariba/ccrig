# Redesign status

The redesign follows the v1 spec (2026-11-01), built from `docs/SITE_AUDIT.md`. One phase is one branch and one PR; nothing here is pushed or merged without approval.

| Phase | Branch | State |
|---|---|---|
| 0. Foundations | `phase3/redesign-foundations` | **Done, local** (this document) |
| 1. Data model | — | Not started |
| 2. Core analytics | — | Not started |
| 3. Counterparty, Relationship, Today | — | Not started |
| 4. Network | — | Not started |
| 5. Events & News | — | Not started |
| 6. Stress & Co-movement | — | Not started |
| 7. Ask the graph and polish | — | Not started |

## Phase 0: what exists now

**Shell** (`src/ui/AppShell.tsx`, `TopBar.tsx`): sidebar with the 7 workspaces and a lower group (Models, Data sources, and Admin items when the operator switch is on); top bar with the command palette (Ctrl/⌘ K), watchlist chips and editor, as-of date, theme toggle (system / light / dark) and a backend/mode pill; skip link; per-route document titles (`src/app/pages.ts` is the single list behind labels, URLs and titles). Shared inspector drawer (`InspectorDrawer.tsx`, focus-trapped, Esc closes, "Open full page").

**Routes** (`src/App.tsx`, lazy-loaded per workspace):

| New route | Hosts today | Planned |
|---|---|---|
| `/` Today | tabs: Inbox, Exposure movers, Controls (the old pages) | Phase 3 |
| `/network` | tabs: Graph, Search relationships, Distance map | Phase 4 |
| `/cp`, `/cp/:id` | Counterparty 360 (id now in the path) | Phase 3 |
| `/issuer`, `/issuer/:id` | Entity 360 | Phase 3 |
| `/rel`, `/rel/:a/:b` | a working pair picker + the existing explanation (score, typed path, waterfall, signed correlation) | Phase 3 |
| `/events` | tabs: Analyse a headline, Map, Themes | Phase 5 |
| `/stress`, `/comovement` | an honest "planned for Phase 6" page (nothing simulated) | Phase 6 |
| `/models` | tabs: Weights, Backtest | Phase 7 |
| `/admin/sources`, `/admin/studio`, `/admin/ingest` | Data & Provenance, Data Intelligence Studio, Ingest Bench | kept |
| `/admin/ui` | the design system on one page | — |
| `*` | old address → new home with its parameters (15 mappings, `src/app/redirects.ts`), otherwise a 404 page | — |

**State in the URL**: tab (`?tab=`), watchlist (`wl=`, only when customised) and as-of (`asof=`, only when set) are in the URL and survive reload; each tab starts with a clean query. `src/lib/urlStateCore.ts` + `useUrlState.ts` (zod-validated) are the building blocks for page filters from Phase 3.

**Design system** (`src/design/tokens.css`, `src/ui/`): one token set for light and dark (neutrals, accent, severity, relationship channels, provenance); old variable names are aliased so legacy pages follow the theme. Components: `AppShell`, `CommandPalette`, `InspectorDrawer`, `KpiTile`, `SeverityPill`, `ChannelChip`, `ProvenanceBadge`, `DataTable` (sort, filter, column picker, windowed rendering past 150 rows, sticky header, row expand, CSV), `FilterBar`, `Tabs` (arrow keys), `Skeleton`, `EmptyState`, `ErrorState`, `Timeline`, `Heatmap`, `PropagationFlow` (ECharts, lazy, "View as table" and PNG export on every chart), `NetworkCanvas` (Cytoscape + fcose, list view).

**Data layer**: TanStack Query (`src/api/query.ts`) over the existing client for health, the CCR queue, search index and operator mode; OpenAPI exported by `backend/scripts/export_openapi.py` and turned into `src/api/schema.d.ts` by `npm run gen:api`.

**Fixes made on the way**: Ingest Bench no longer throws on its first frame (a first-frame timestamp could run time backwards) and stops drawing while the tab is hidden; the relationship search reads `?q=` (breadcrumb links now restore it); Inbox, Exposure Movers and Controls show an error with Retry instead of an unhandled rejection; legacy page titles became `h2` under the workspace `h1`.

## Deviations from the spec, and why

1. **Watchlist and as-of drive nothing yet.** They are real shell state (URL + local storage) but no page filters by them until the data model (Phase 1) and the pages that use them (Phase 3+) exist. The as-of picker's tooltip says so.
2. **Admin items are hidden unless the operator switch is on**, as specified, but "Data sources" stays in the lower group because provenance badges link to it and the public site has no other way to reach it.
3. **Types from OpenAPI are generated with `npx openapi-typescript@7.13.0`, not installed**, because that package's peer range stops at TypeScript 5 and the repo is on 6. Most endpoints return untyped dictionaries, so the generated types are thin until response models are added in Phase 1.
4. **The palette has no "events" entries** (there is no endpoint that lists events); counterparties (CCR and portfolio), issuers, themes and pages are indexed. Events join in Phase 5.
5. **Recharts and the Graph Explorer's Cytoscape page are untouched.** Recharts goes away when its two pages are rebuilt (Theme Radar in Phase 5, Entity page in Phase 3).
6. **Scenario loss estimates (`CCRIG_ALLOW_SCENARIO_ESTIMATES`) are not built and will not be without a decision.** A standing project rule says "do not add financial-impact estimates"; the spec allows one behind a flag, labelled illustrative. Please confirm before Phase 6.
7. **The spec file itself is not in the repository.** This status page and `docs/SITE_AUDIT.md` are the only records; say if you want the spec committed as `docs/REDESIGN_SPEC.md`.

## Verification (Phase 0)

Screenshots: `docs/redesign-screens/phase0-*.png` (Today in light and dark, palette, drawer, design gallery in both themes, Events & News map tab, 390 px).

| Check | Result |
|---|---|
| Backend suite (pinned libraries) | 882 passed, 1 skipped; analytics baseline "OK: no drift" (backend changed only by adding `scripts/export_openapi.py`) |
| Frontend unit tests | 68 passed (10 new: URL state, table sort/filter/window, CSV, search ranking, 15 redirects) |
| `tsc -b`, `oxlint` | clean; 11 warnings, the existing limit, none in new code |
| Dev build, static build, `verify:static` | pass; main bundle 257 KB (was about 1.09 MB), ECharts 674 KB loaded only when a chart opens |
| Browser, dev (old journeys through the new shell) | 94/94 |
| Browser, static (Pyodide) | 90/90 |
| Browser, Studio against an operator backend | 36/36 |
| Browser, Ingest Bench | 19/19 (24/24 with the live stream) |
| Browser, new `e2e/shell-e2e.mjs` | 48/48, repeated runs, with the operator switch on and off |

## Found and fixed during verification

`shell-e2e.mjs` caught an intermittent `Maximum update depth exceeded` (about 1 run in 4) while typing a long headline into the command palette on a busy page. It came from state being set inside effects on every keystroke. The palette now derives that state in the event handler and reads its recent-searches list once when it opens, and the search index is built by the shell instead of inside the palette. A 30-iteration stress loop of the same steps went from 2 failures in the first 8 iterations to none in 30.

## Known gaps

- Lighthouse accessibility is not measured yet (Phase 7 target: 90 or more). Basic checks are in the shell e2e: real links and buttons, skip link, focus trap, keyboard tabs, named controls.
- Legacy pages inside the workspaces still have 10-11 px text and `<a onClick>` links; they are replaced page by page in Phases 3-5.


# CR-3: Today command center, Counterparty page, advanced nodes, world map

Branch `redesign/cr-3-command-center` (from `phase3/redesign-foundations`). Built from the brief and the repo as it is: the mockup (`docs/design/ccrig-console-mockup.html`), `docs/REDESIGN_SPEC.md`, and the CR-1/CR-2 work it refers to are **not in the repository**, so the visuals follow the written description of the brief and every panel that needs data the repo lacks says "Unavailable" and why.

## What changed

- **Tokens** (`design/tokens.css`): the "petrol chart" palette (dark) and a matching light theme with the same names; chart-grid background, mono section headers with an accent square, 5 px radii, glow only for critical items, the selection and simulations. The map, Studio hosts and legacy pages follow the tokens; the forced dark skin of the map is gone.
- **`NetworkCanvas`** (`ui/NetworkCanvas/`): Canvas 2D, pure modules (`layout`, `drawNodes`, `drawEdges`, `labels`, `hitTest`, `adapters`, `palette`). Counterparty glyph (utilisation arc with 85/100 zones and over-limit tick, channel-mix ring, rating core in the priority colour, W ! ▲ ↓ badges, EWS pulse), hexagon issuers, diamond factors, collision-free boxed tags at constant screen size, curved channel-coloured edges (width = strength, opacity = confidence, particles on directed channels, dashed shimmer on derived ones, arrows on strong directed edges, merged parallels, no self-loops), cluster halos, hover focus, click select, Ctrl/⌘-wheel zoom, mouse-only pan, double-click reset, force and radial-ego layouts, contagion heat with a ripple at the shock, `highlight(ids)`, node guide, list view, keyboard (arrows, +, −, 0). 2,000 nodes lay out in about 200 ms; drawing stops off screen, while the tab is hidden, and entirely under reduced motion.
- **Backend** (`core/network.py`, `propagation.py`, `reaches.py`, `today.py`, `routers/today.py`): `GET /api/today`, `/api/cp/{id}`, `/api/network/graph`, `/api/stress/scenarios`, `POST /api/stress/run`, `/api/health/{pipeline,sources,models}`, and `include_reaches=true` on `/api/impact-map/{id}/events`. One typed graph over what the data really holds (exposure, supply, shared issuer, co-movement, hidden transmission, and Studio-approved ownership), Louvain clusters of the shared-issuer projection, a deterministic propagation index (not a loss estimate), cached per `as_of` and watchlist.
- **Today** (`/`): hero (date, scope, headline and template summary, Simulate / Open / Node guide / World map, live network with cluster halos and channel toggles), six KPI tiles, the existing map embedded in compact mode with a Reaches row, top exposures, stress heatmap (cell opens Stress), market events, concentration, ratings and flags, data and AI health. The old Inbox, Exposure movers and Controls remain at `/?tab=…`.
- **Counterparty** (`/cp/:id`): header, six KPIs, radial/force relationship map, inspector, all-relationships table synced with the map and the URL (`?node=`), exposure vs limit, stress by scenario, risk stories (the former cluster stories), events and news with an embedded map filtered to the events that reach this name.
- **Network**: the Cytoscape Graph Explorer is replaced by the new canvas with filter rail, inspector, node and cluster tables, and the Studio-overlay toggle. Cytoscape, react-cytoscapejs and cytoscape-fcose are removed from the bundle. Recharts stays (Entity page price chart and Theme Radar still use it).
- **Stress** (`/stress`): a first working version (preset or counterparty default, propagation table, heat on the network).

## Changes inside the existing map

All additive and opt-in: `GeoStage` gains `variant="compact"` (drops the overview/zoom/frame chrome and the legend) and reads its sea, land, coast and limb colours from tokens (with a theme key in its layer cache, so a theme switch repaints); `GlobalEventImpactMap` gains `variant`, `entityId` and `eventIds` props, a Reaches block in the evidence panel and "reaches N counterparties" under each list item. Events are fetched with `include_reaches=true`, which is off by default on the API so the recorded impact-map baseline is byte-identical. The compact map does not set the full-bleed class on the page. Nothing else in the map changed; its browser checks pass unmodified.

## Deviations from the brief

1. **Assistant drawer (§5) is not built**: no assistant, tools or audit log exist. `NetworkCanvas.highlight(ids)` is the hook it would call and is tested; "Ask CCRIG about this name" is a disabled button that says why. Token use, p95 latency and error rate say Unavailable.
2. **No new data was invented**: ratings, outlooks, EWS, 12-month exposure history, link dates ("new links in 7 days") and the rating ladder are Unavailable. Exposure vs limit shows the two real snapshots and says so. KPI sparklines are absent for the same reason.
3. **A minimal contagion analytic was added** (propagation index, spec 4.1) because Simulate and the stress heatmap need something deterministic; its channel weights, hop decay and utilisation multiplier are documented constants. It is labelled "Propagation index, not a loss estimate" everywhere and produces no currency figure.
4. **Systemic rank** is one weighted PageRank, not the spec's blend. **Clusters** are named by dominant sector (no cluster names exist in the data).
5. **Simulate** targets the most severe watched counterparty that has at least one recorded link, because the top critical name has none (a default there propagates nowhere, which the summary says).
6. **Confirm link** is stored in this browser only (no `link_reviews` store exists); the inspector says so.
7. **`--surface`** is a solid colour; the translucent `rgba(10,25,37,.86)` is `--surface-glass` (popups over it would be see-through).
8. **Two counterparty universes** (19 CCR records, 18 holdings-only) still share no ids; both appear in the network, the holdings-only ones without limit, rating or priority.
9. **Today's pipeline stages** need the operator token and say so on the public site (no unauthenticated read of operator state).

## Fixed on the way

The analytics baseline recorded today's date (`provenance.generated_at`), so it failed every day after it was recorded; the wall-clock field is now masked in the snapshot (that one value only; no analytic changed). The Inbox, Exposure movers and Controls pages no longer leave a failed request unhandled.

## Verification (CR-3)

Backend 927 passed, 1 skipped (45 new: 22 tests for the network, clusters, propagation, reaches, endpoints and the Studio overlay, and 23 new server-versus-browser parity cases); baseline "OK: no drift". Frontend unit 80 passed (12 new for the canvas); lint 9 warnings (limit 11); builds and `verify:static` (133 request cases in real Pyodide) pass. Browser: dev 94/94 (map checks unmodified), static 90/90 (one timing flake in the flat-projection check on the first of two runs), Studio 36/36 and Ingest Bench 24/24 against an operator backend, shell 48/48, and the new `e2e/cr3-e2e.mjs` 45/45. Screenshots: `docs/redesign-screens/cr-3/` (1440 and 390 px, dark and light).
