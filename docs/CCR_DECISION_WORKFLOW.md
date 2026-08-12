# CCR Decision Workflow

This document explains the product sequence CCRIG follows for every
counterparty investigation, and the boundaries that keep it honest.

## Why CCRIG is NOT a PFE engine

CCRIG's original strength is relationship discovery: given a counterparty,
issuer, or event, what else is it connected to, and why? A prior iteration
of this platform drifted toward presenting Potential Future Exposure (PFE)
as the primary output — "PFE mover dashboard." PFE is real and important,
but it is one MEASUREMENT inside a longer reasoning sequence, not the
question the platform should lead with. A senior analyst does not start
"PFE is $815mm" — they start "what is this counterparty connected to, and
how are we actually exposed before I even look at a number."

## The sequence

```
DISCOVER → UNDERSTAND → MEASURE → STRESS → CONTROL → DECIDE
```

| Step | Question | What it uses |
|---|---|---|
| 1. DISCOVER | What is this counterparty/issuer/event connected to? | Layer A (fact) + Layer B (derived relationship vector), sector, geography, supply chain, ownership, news/themes, market correlation, risk-factor transmission path |
| 2. UNDERSTAND | How are we actually exposed? | Product, netting set, collateral, notional, direction, reference entity/underlying — the economic route from counterparty to risk factor |
| 3. MEASURE | How material is the exposure? | RC, PFE, ΔPFE, NSE/stress, ΔNSE, settlement exposure, sensitivities (FX delta, DV01/IR01, CS01, equity delta) — each kept in its own unit, never merged |
| 4. STRESS | What happens if the risk actually moves? | Linked event + its risk-factor transmission path (no custom simulation engine — path-based reasoning only) |
| 5. CONTROL | Are we inside appetite and are controls working? | Typed limit (PFE_LIMIT / SETTLEMENT_LIMIT / STRESS_LIMIT), utilisation computed ONLY against the matching metric, headroom, breach, WWR, rating/watchlist, coverage owner |
| 6. DECIDE | What should the analyst do next? | The Decision object: recommended action, reasons, missing information, evidence, provenance |

This sequence is implemented literally in Counterparty 360
(`frontend/src/pages/Counterparty360.tsx`) and echoed in Event Studio's
post-Mode-1/Mode-2 output (steps 5-8) and the Daily Review's expandable row.

## Relationship vs. exposure

Two different objects, never collapsed into one score:

- **RelationshipVector(A, B)** (`core/scoring.py`) — 8 components (sector,
  geography, supply_chain, ownership, semantic/news, market_positive,
  market_negative, +missing/confidence tracking). A composite scalar is
  available as a VIEW over this vector, never the ground truth.
- **CCR exposure record** (`core/ccr_priority.py`) — PFE/NSE/RC/settlement
  exposure, sensitivities, limits, breaches. Entirely separate data, joined
  to relationship discovery only through `reference_entity_id` (Entity 360
  materiality panel) or nominated-issuer sets (Event Studio materiality
  join) — never merged into the relationship vector itself.

Graph/event relevance **nominates** candidates. Exposure and limit
materiality **determine** investigation priority. A large relatedness
score with negligible exposure ranks LOW; a moderate relationship with a
confirmed breach ranks CRITICAL.

## Correlation: three separate domains

See `core/correlation_domains.py`. Never merged into one "correlation
score":

1. **Issuer/market correlation** (Domain A) — `corr(NVDA returns, TSMC
   returns)`. Real price data, signed, used for relationship discovery.
   This is the correlation already used everywhere else in CCRIG
   (`core/market.py`).
2. **Cross-risk-factor transmission path** (Domain B) — `JPY → Japanese
   rates → UST yields → repo market → basis trades`. This is CURATED
   REFERENCE DATA (a hand-authored typed path attached to each event in
   `ccr_events.json`), not a computed correlation coefficient — no macro
   time-series data is bundled in this POC to compute one honestly.
3. **WWR diagnostic** (Domain C) — surfaces the explicit `wwr_flag`
   evidence on a CCR record, never inferred from exposure size. Answers
   "was wrong-way risk flagged, and why," not "here is a WWR statistic."

## Product taxonomy

`backend/data/product_taxonomy.json` (`CURATED_REFERENCE_DATA`) is generic
domain metadata about product TYPES — what risk factors and sensitivities
a product family generically carries (IRS → INTEREST_RATE/DV01, TRS →
EQUITY+CREDIT/EQUITY_DELTA, REPO → RATES+COLLATERAL+FUNDING, CDS →
CREDIT_SPREAD/CS01, etc.). It is never a counterparty's actual position —
it lets the platform explain *why* a risk factor moving would affect a
given product, without repricing anything.

## Limit-type semantics (critical fix)

Every limit carries an explicit `limit_type`. Utilisation is **only ever**
computed against the metric that matches:

```
PFE_LIMIT        -> utilisation = PFE_current / limit_value
SETTLEMENT_LIMIT -> utilisation = settlement_exposure / limit_value
STRESS_LIMIT     -> utilisation = NSE_current / limit_value
None (no limit on file) -> utilisation = None ("Unavailable"), never
    silently computed off whatever number happens to be present.
```

The previous implementation computed `RC / limit` unconditionally and
called the result "utilisation," and computed `excess = PFE - limit` for
every breach regardless of what the limit actually measured. Both are
fixed in `core/ccr_priority.py::enrich()`.

## Driver taxonomy

`NEW_TRADE`, `MATURED_TRADE`, `MARKET_MOVE`, `MTM_MOVE`, `COLLATERAL_CHANGE`,
`NETTING_CHANGE`, `MODEL_RECALIBRATION`, `MODEL_COVERAGE_CHANGE`,
`DATA_ISSUE`, `DATA_SOURCING_ISSUE`, `VOLATILITY_UPDATE`, `RECOVERY_CHANGE`,
`REPLACEMENT_COST_MOVE`, `NON_NETTED_EXPOSURE`, `WWR_RELATED`,
`LIMIT_BREACH`, `SIMULATION_NOISE`, `SMALL_MOVE`, `UNKNOWN`.

Every classification requires an explicit evidence flag
(`core/ccr_priority.py::classify_driver`) — a size-only heuristic is never
sufficient. In particular, `SIMULATION_NOISE` requires an explicit
`simulation_noise_confirmed_flag` (a documented diagnostic); a small,
evidence-free move is labelled `SMALL_MOVE` (honest about size) or
`UNKNOWN` (honest about not knowing), never asserted to be noise.

## Priority rule matrix

`core/ccr_priority.py::compute_priority()`. All numeric cut-offs live in
`core/config.py::CCR_PRIORITY_THRESHOLDS`, explicitly labelled
`POC_HEURISTIC` and surfaced to the API/UI as such — never presented as
real risk appetite.

```
CRITICAL  if confirmed material breach significantly overdue,
             OR confirmed WWR + utilisation >= high_utilisation_pct,
             OR utilisation >= 100% against the matching limit type
INFORMATIONAL  if no confirmed exposure metric at all (discovery-only)
LOW       if exposure is immaterial (below both abs-PFE and utilisation
             thresholds) - even with a live event nomination
HIGH      if a real-risk driver (MARKET_MOVE/MTM_MOVE/WWR_RELATED/
             NEW_TRADE/NON_NETTED_EXPOSURE) with a material move or high
             utilisation, OR a fresh (non-overdue) breach
MEDIUM    if a routed-not-escalated driver (MODEL_RECALIBRATION/
             DATA_ISSUE/NETTING_CHANGE/COLLATERAL_CHANGE/RECOVERY_CHANGE/
             VOLATILITY_UPDATE/MODEL_COVERAGE_CHANGE/DATA_SOURCING_ISSUE/
             REPLACEMENT_COST_MOVE), or a material move without a driver
             match, or a fallback default
```

## The Decision object

Every CCR record carries one (`core/ccr_priority.py::build_decision`):

```python
{
  "context": "POST_TRADE",
  "counterparty_id": "...",
  "decision": "INVESTIGATE",
  "priority": "HIGH",
  "reasons": [...],
  "driver": "MARKET_MOVE",
  "driver_evidence": [...],
  "relationship_paths": ["JPY", "JAPAN_RATES", "UST_YIELD", ...],
  "control_flags": {"is_breach": false, "is_overdue": false, "wwr": false, "watchlist": false},
  "missing_information": ["rating"],
  "recommended_owner": "J. Ferris",
  "evidence": "<analyst explanation>",
  "provenance": "DERIVED_DATA",
}
```

This is the common output layer every consumer reads: Daily Review,
Counterparty 360's DECIDE section, Event Studio's materiality join,
Breaches & Actions. AI never populates this object — it is entirely
deterministic.

## Data domains and provenance

- **`SYNTHETIC_CCR_DECISION_DATA`** (`backend/data/ccr_counterparties.json`,
  `ccr_events.json`, `ccr_model_impacts.json`) — fictional counterparties
  mirroring realistic CCR scenario shapes. No real institution, government,
  or confidential position is represented anywhere in this repository.
- **`CURATED_REFERENCE_DATA`** (`backend/data/product_taxonomy.json`) —
  generic product-type metadata, committed to git (it's domain knowledge,
  not anyone's position).
- **`REAL_PUBLIC_DATA`** — everything already legitimate in CCRIG:
  issuer master, sectors, GLEIF LEI/hierarchy, public market prices, public
  news, public supply-chain facts (unchanged by this redesign).
- A fourth domain, **`USER_PROVIDED_INTERNAL_SAMPLE_DATA`**, was
  *deliberately not implemented*. See "What was declined" below.

## Provider abstraction

`core/ccr_provider.py` defines `CCRDataProvider` (an ABC with
`get_counterparty_master`, `get_exposure_metrics`, `get_exposure_movers`,
`get_stress_movers`, `get_sensitivities`, `get_trades`,
`get_netting_sets`, `get_collateral`, `get_limits`, `get_breaches`,
`get_model_impacts`, `get_full_records`). `InternalSampleCCRProvider` is
the only implementation — it reads the local synthetic dataset. A future
`ProductionCCRProvider` would implement the same interface against real
internal systems; this file does not invent real endpoints or schemas, it
only defines the shape a production implementation would need to satisfy
so the rest of the platform (driver classifier, priority engine, Decision
object, every UI page) keeps working unchanged.

## Pre-trade (architecture only, not implemented)

Target future flow, once a real `ProductionCCRProvider` exists:

```
PROPOSED TRADE → COUNTERPARTY → existing relationships/concentrations
  → PRODUCT/UNDERLYING → RISK FACTORS
  → incremental PFE/stress/headroom (from the real provider, not computed here)
  → CONTROL (limit/collateral/WWR)
  → DECISION SUPPORT (APPROVE / CONDITIONS / RESIZE / REPRICE REVIEW /
     COLLATERAL / ESCALATE / DECLINE)
```

No custom PFE/NSE engine or repricer is built for this, now or later —
that number must come from a real risk system via the provider interface.

## What was declined, and why

The original request for this redesign included specific real,
confidential-looking data — real institution names (JPMorgan Chase, UBS
Group, BNP Paribas, Citadel) and real sovereign governments, with specific
PFE/exposure/breach figures, explicitly labelled as an internal Citi
dataset. That data was **not** used anywhere in this repository, including
locally/gitignored, because:

1. Real, named-institution credit-exposure figures are non-public
   financial information about real third parties regardless of where
   they're stored — "gitignored" does not change what the data *is*.
2. It directly contradicted the platform's own standing requirement
   (confirmed at the end of every prior implementation pass): "Confidential
   Citi data introduced: NO."

Every scenario SHAPE from that request (a repo-driven PFE jump, a
recovery-rate-driven stress move, a non-netted triparty collateral case, a
settlement breach with an unknown root cause, an equity-delta swing from
index futures, a portfolio-level model-run impact summary) was preserved
and implemented with fictional counterparties, so the full business realism
and driver taxonomy is intact without any real institution appearing
anywhere in the codebase.
