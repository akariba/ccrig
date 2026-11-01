# Relationship, holdings and CCR data integration

Three analytical domains, three different economic meanings. The Data Studio ingests each through its own contract and keeps them apart.

| Domain | Studio target | What a record means | What it is never taken to mean |
|---|---|---|---|
| Issuer relationship evidence | `relationship_evidence` | A typed, directed relationship between two issuers, with the source passage that supports it | An exposure, an impact, a criticality, or proof from mere co-occurrence |
| Portfolio holdings | `exposure_edges` (existing) | A portfolio counterparty holds an issuer, with a weight | A CCR exposure, or a relationship between issuers |
| Reference entities | `reference_entities` | A CCR counterparty's trade references (or is underlying to) an issuer; or a labelled inferred dependency | A direct holding; an inferred dependency is never presented as a trade link |
| CCR exposure | `ccr_exposures` | A measure (RC, PFE, NSE, settlement) for a counterparty and netting set, with currency, unit, as-of date, limit, source lineage | A converted, estimated or defaulted number; wrong-way risk |

The two counterparty populations (portfolio `CP_ALPHA`… and CCR `CP_HF_001`…) are resolved in their own universes: a portfolio id offered as a CCR counterparty (or the reverse) is refused as `WRONG_UNIVERSE`. They are never merged.

## Relationship evidence
Types and the meaning of the stored direction (source → target): `SUPPLIES` (supplier → customer), `LICENSES_TO` (licensor → licensee), `PARENT_OF` / `SUBSIDIARY_OF` (ownership), `FINANCES` (financier → borrower), `GUARANTEES` (guarantor → guaranteed), `AFFILIATED_WITH` (documented corporate affiliation; undirected, stored alphabetically).
Each row keeps its source document (URL, publisher, tier, publication date, stored SHA-256), the relevant date, the verbatim quotes, the assertion basis, and the verification result; it is re-verified against the stored document at staging.

**Co-occurrence is not a relationship.** A row is accepted only if (1) its quotes are found verbatim in the stored source, (2) one quote names both companies (deterministic entity rules), and (3) the words between the names carry a cue for the relation in an order consistent with the direction. A cue pointing the other way is `DIRECTION_CONFLICT` and is never flipped. If both companies are named but nothing states the relationship, the row is blocked (`UNSUPPORTED_RELATIONSHIP_ASSERTION`) unless the proposer declares it `PROPOSER_ASSERTED` with a written rationale; it is then staged with a warning and a reviewer must explicitly confirm it (`--ack-assertions`). A relationship running opposite to an existing canonical edge needs an explicit acknowledgement too.

## How approved evidence reaches CCRIG
Approval publishes a release in the Studio workspace. The canonical `fact_edges.json`, its in-memory graph, every score and every weight stay exactly as they were. A request that asks for it (`include_studio`) reads the approved evidence as an **overlay on a copy of the graph**:
* Graph Explorer: "Include Studio-approved relationships" draws approved edges in purple with their provenance (publisher, dates, quotes, source link, hash, basis) and notes that they carry no criticality.
* Event Impact Map: "Include approved relationships" lets documented paths use them (evidence status `STUDIO_APPROVED`, criticality empty). Without it the map is exactly what it was.
* On the public/static deployments there is no workspace: the overlay says it is unavailable and the canonical graph is shown.
Rollback or restore removes or returns the overlay immediately; the history of decisions stays.

## What approval changes, and what it does not (`python -m app.studio relationships`)
* Connectivity: issuers with a documented relationship, issuers without any, documented issuer pairs, connected groups, newly connected issuers (computed on copies; relationships outside the scoring types are shown in the graph but not counted).
* Coverage: which issuer pairs would gain a supply/ownership component **if** a person adopts the edge. Adoption requires a criticality judgement that is not assumed here, so `scoring_changed_by_approval` is always `false`.
* Genuinely linked counterparties: portfolio counterparties that hold either endpoint, and CCR records that reference either endpoint (master or approved reference entities).
* Gaps, stated every time: no holdings in a company, no CCR reference to it, no measured CCR exposure, and that wrong-way risk is not assessed.

## Data-quality report (`report JOB`, `GET /api/studio/jobs/{id}/report`)
Findings grouped into missing references, duplicate entities, broken joins, inconsistent units, orphan exposures and unsupported relationship assertions, with counts, examples and a verdict. CCR exposure rules include: one currency and unit per measure (never converted), limits compared only with their own measure (PFE↔PFE_LIMIT, settlement↔SETTLEMENT_LIMIT, NSE↔STRESS_LIMIT), utilization computed (a supplied value that disagrees is an error), a netting set belongs to one counterparty, a netting set missing from the CCR master is an orphan warning, no defaulted values.

## Promotion and rollback
Same Studio process for every domain: stage → report → named reviewer approves (with the explicit acknowledgements the findings require) → versioned release in the workspace → rollback/restore at any time (hash-verified, history kept). Nothing is written to a canonical dataset; a person adopts an export deliberately (and for relationships must add a criticality) through the build scripts, then runs the baseline check.

## Not done here (by design)
No weights or models changed; no criticality assigned; no exposure fabricated or converted; no wrong-way-risk interpretation; no confidential data connected to public hosting or external AI services (the Studio is operator-only and the overlay reads only a local workspace). Demonstration: `python scripts/relationship_demo.py`.
