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
