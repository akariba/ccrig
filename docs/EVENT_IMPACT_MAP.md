# Global Event Impact Map (pilot: NVIDIA)

Search a company, see up to five recent, **verifiable** events about it on a world map, and for each one
the source evidence, the documented relationships that connect the entities it names to the company, and
what that analysis cannot say.

## What is real, what is not

| Item | Status |
|---|---|
| Events | Real publications retrieved from approved primary sources and verified by retrieval (`data/events/events_nvidia.json`). Nothing is generated, simulated or hypothetical; such records are rejected by the register's policy. |
| Relationships | The platform's documented fact edges (supply, licence, ownership) with their evidence status. Not inferred from the event text. |
| Positions | Approximate display points (city points / country centroids) with the precision always shown. Not event epicentres, not facility locations. |
| **Impact** | **Not estimated.** No method is validated, so `impact.status = NOT_ESTIMATED` for every event. Relationship evidence is shown separately. |
| Exposure | **Not available.** The platform's counterparty exposures are synthetic and are not used. |

## Data flow

```
approved_sources.json ──► scripts/event_register.py build  (network, developer tool)
                              │  fetch source, confirm date + title + location basis, extract passages verbatim
                              ▼
                     events_nvidia.json  (committed data: what the app serves; `verify` re-checks it)
                              │
   GET /api/impact-map/{entity}/events  (pure, offline - identical in FastAPI and Pyodide)
      1. admissible?  event_register.validate_event  (approved https domain + tier, REAL_EVENT, verified by retrieval, place + basis)
      2. recent?      published within recency_days before as_of (default 180 days; as_of defaults to the register's build date)
      3. relevant?    event_entities.resolve_event names the entity in the CITED passages
      4. ranked       newest first; named-in-title before named-in-evidence; at most 5
      5. enrich       event_geo (location, regions mentioned) + event_graph (typed paths) + limitations
```

If fewer than five events qualify, fewer are returned and `explanation` says why; every record that was not
returned is listed in `not_returned` with its reason. Nothing is added to fill the count.

## Typed paths

A path is `event -> entity [-> entity] -> target`. Its links are of exactly three kinds and are never merged into a number:

* `MENTIONS` - the event's cited text names the entity (the quote and the rule that matched are attached);
* `DOCUMENTED_RELATION` - a stored, directed fact edge (e.g. `TSM SUPPLIES NVDA`), with `traversal` saying whether the path
  follows or runs against the stored direction, the evidence status/URL, and a **criticality that is a curated judgement,
  not a measured exposure**;
* `MENTIONS_REGION` - the cited text names a country.

Relationship classes per named entity: `SELF`, `DOCUMENTED_DIRECT` (1 hop), `DOCUMENTED_INDIRECT` (2 hops through other
companies), `NO_DOCUMENTED_PATH` (named, but the data holds no documented relationship - an absence in the data, not proof
none exists; no path is drawn). Graph proximity, profile similarity and statistical correlation are not used anywhere on this page.

## Entity resolution (precision first)

Only the cited passages are read. Names must be capitalised proper nouns on word boundaries; tickers resolve only as
uppercase tokens that are not part of a product name ("NVIDIA RTX Spark" is not RTX Corporation); brand names resolve to
their parent with the reason recorded (`data/events/entity_aliases.json`); "Samsung Electro-Mechanics" is not Samsung Electronics.
Synthetic counterparties are never candidates.

## Adding or refreshing events

1. Add a spec to `scripts/event_register.py` (URL on an approved domain + anchors identifying the passages to cite).
2. `python scripts/event_register.py build` - it refuses anything it cannot verify (date, title, location basis, every quote verbatim).
3. Review the diff of `data/events/events_nvidia.json`, then `python -m validation.impact_snapshot --write` if the change is intended.
4. `python scripts/event_register.py verify` re-checks the committed register against the live sources (run it periodically; sources can change).

Approved sources are configured in `data/events/approved_sources.json`. Press, analyst and social-media sources are not approved in the MVP.

## Known limitations

* Coverage is the register: NVIDIA only, 8 events. The page does not search the live web, so a real event that is not in the register cannot appear.
* All approved sources are first-party (the issuer, a counterparty's newsroom, a regulator): statements are promotional and unverified for truth.
* Documented relationships are structural. A path does not say the event affects the company, in which direction, or by how much.
* Many named companies in the evidence are not in the platform's dataset (Amkor, IBIDEN, KYEC, SPIL, Unimicron, Synopsys, ...), so they cannot be connected.

## The page (frontend)

`/event-impact-map` ("Event Impact Map" in the sidebar). Code: `pages/GlobalEventImpactMap.tsx`, `components/GeoStage.tsx` (the map),
`impactmap/globe.ts` (pure globe geometry) and `impactmap/model.ts` (pure scene, cable and category logic); all tested without a browser.

**Rendering architecture.** A 2D canvas with real Natural Earth coastlines bundled with the app (`world-atlas` 110m, then 50m loaded
lazily; drawn with `d3-geo`), HTML buttons for markers (so they are keyboard- and screen-reader accessible), no tiles, no external map
service and no WebGL. Evaluated and rejected for now: MapLibre GL / deck.gl (WebGL; would need a vector-tile source or a bundled style,
roughly 1 MB or more of extra JavaScript, and a software-rendering fallback), because nothing here needs more than ~30 arcs and ~20
markers and a 2D canvas behaves identically in the FastAPI deployment, on GitHub Pages and in headless test browsers.

- Two projections: an interactive **globe** (orthographic, default; drag to rotate, +/- to zoom, "Frame" to re-centre) and a **flat**
  Equal Earth map that shows every marker at once (`?view=flat`).
- Selecting an event glides the camera to frame that event and the companies connected to it. Markers that would sit behind the globe are
  hidden and counted ("n markers are on the far side"); the Top 5 list always reaches every event.
- Cables come only from the API graph and follow the real great circle between the two real positions (height depends on distance only).
  A particle travels only along a documented relationship, in its stored direction, and an arrowhead marks that direction.
  Unselected paths stay faint; the selected event's paths are bright.
- Event markers are all one size. Colour is the event's explicit register category and nothing else. Glow, pulse and line thickness
  encode nothing. Company nodes are shown at their headquarters country (approximate, not a facility); the searched company is the hub.
- Overlapping markers are fanned apart in screen space with a hairline to the true position; the selected event's callout picks the
  side that overlaps the fewest other markers.
- Motion: the render loop runs only while the camera, a cable fade or a particle is moving, stops after 25 s without interaction,
  pauses when the tab is hidden or the map is off screen, and never runs with `prefers-reduced-motion`. An "Animation" switch turns
  particles and camera glides off. If a 2D canvas is unavailable the list and evidence panel still work.

Verification: `npm test` (node:test, logic), `node e2e/browser-e2e.mjs dev|static` (real Edge, both deployment modes),
`node e2e/visual-shots.mjs <tag>` (screenshots at four viewport sizes).

### Known gaps
- The "global impact map design concept" referred to in the brief was not supplied to this work, so the visual design is original
  rather than derived from it.
- The "Neural Cable Graph" is used as a technique only (gradient bezier cables, travelling pulses, glow on selected routes). Its random
  colours, jitter and invented readouts are deliberately not reused: every visual state here is derived from API data.
