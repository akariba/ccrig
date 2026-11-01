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
