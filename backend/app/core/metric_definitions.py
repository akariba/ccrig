"""Central Metric Definition Registry (Phase 4, workstream C).

One canonical explanation per derived/technical measure shown anywhere in
the UI. A metric must not be explained differently on different pages -
every "Definition" / "How calculated?" affordance in the frontend reads
from this registry via GET /api/metric-definitions, never a page-local
paragraph of methodology text.

Not every entry has a formula - some are semantic/status concepts (e.g.
WWR_STATUS). `formula` is None in those cases, never a fabricated one.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    label: str
    short_description: str
    category: str
    meaning: str
    what_it_is_not: list[str] = field(default_factory=list)
    formula: str | None = None
    inputs: list[str] = field(default_factory=list)
    units: str | None = None
    source: str | None = None
    limitations: list[str] = field(default_factory=list)


_DEFINITIONS: list[MetricDefinition] = [
    MetricDefinition(
        id="MARKET_CORRELATION", label="Market correlation", category="RELATIONSHIP",
        short_description="Signed historical return co-movement between two entities.",
        formula="ρ(A,B) = Cov(r_A, r_B) / (σ_A · σ_B)",
        inputs=["aligned historical daily returns for A and B"],
        meaning="Signed Pearson correlation coefficient, -1 to +1. Sign is always preserved - "
                "a strong inverse relationship is reported as a large negative number, never abs()'d.",
        what_it_is_not=["causality", "exposure", "default probability", "credit quality"],
        source="core/market.py, real public price history where available",
        limitations=["requires overlapping price history for both entities",
                     "full-sample, rolling (30d), and stress-window (10d) variants may differ materially"],
    ),
    MetricDefinition(
        id="COMPOSITE_RELATEDNESS", label="Composite relatedness (relationship ranking)", category="RELATIONSHIP",
        short_description="A ranking indicator combining available relationship channels - not a factual graph edge.",
        formula="R(A,B) = Σ(w_k · f_k(A,B)) / Σ(w_k for available k)",
        inputs=["sector match", "geography", "supply chain", "ownership", "semantic similarity",
                "news co-occurrence", "market correlation (positive/negative channel)"],
        meaning="A weighted average over whichever relationship components are available for the pair, "
                "used to RANK candidate relationships. Missing components are excluded from the sum, never "
                "treated as zero, and remaining weights are renormalized.",
        what_it_is_not=["probability", "exposure percentage", "default probability", "confidence",
                         "causal strength", "a factual graph edge (see RANKED_ONLY in graph/edgeLabels.ts)"],
        source="core/scoring.py composite_score()",
    ),
    MetricDefinition(
        id="RELATIONSHIP_COMPONENT_CONTRIBUTION", label="Relationship score waterfall contribution", category="RELATIONSHIP",
        short_description="Exact decomposition of one component's contribution to the composite relatedness score.",
        formula="Contribution_k = (w_k · f_k) / Σ(w_available); Σ(Contribution_k) = Composite Relatedness",
        meaning="A direct arithmetic decomposition of the composite-relatedness formula - each bar's width IS "
                "its share of the final score, reconciling exactly (mod display rounding).",
        what_it_is_not=["a SHAP value or other statistical feature-attribution estimate"],
        source="core/scoring.py composite_score() -> 'waterfall'",
    ),
    MetricDefinition(
        id="PPR_RELEVANCE", label="Personalized PageRank (PPR) relevance", category="EVENT_METHODOLOGY",
        short_description="Network candidate relevance for event/graph discovery - not a risk measure.",
        formula="r = α·Pᵀr + (1-α)·s",
        meaning="Relation-aware Personalized PageRank over the structural+derived relationship graph, seeded "
                "from event-detected entities. Used only to NOMINATE candidate entities for further investigation.",
        what_it_is_not=["risk", "exposure", "PFE", "probability", "default probability", "a graph edge type or strength"],
        source="core/event_parser.py Mode 2",
    ),
    MetricDefinition(
        id="MODE1_TRAVERSAL", label="Mode 1 bounded typed-path traversal", category="EVENT_METHODOLOGY",
        short_description="Candidate nomination via explicit bounded graph-path traversal, decayed per hop.",
        formula="score = criticality_hop1 × 0.65 × criticality_hop2 × 0.65 × ... (0.65 decay per hop, current implementation)",
        meaning="Traverses the FACT graph outward from event-detected entities up to a hop bound, decaying "
                "relevance 0.65x per hop. Nominates candidate entities via explicit typed paths.",
        what_it_is_not=["financial exposure or risk magnitude", "comparable in units to Mode 2 (PPR)"],
        source="core/event_parser.py Mode 1",
    ),
    MetricDefinition(
        id="PFE", label="Potential Future Exposure (PFE)", category="EXPOSURE",
        short_description="Potential future exposure measure supplied by the CCR scenario dataset.",
        meaning="A PFE figure as recorded in the synthetic business scenario data for a counterparty's position. "
                "CCRIG does not calculate authoritative production PFE - it consumes and displays supplied values.",
        what_it_is_not=["current MTM/replacement cost (see RC)", "stress/NSE", "a relationship score"],
        units="currency (as supplied, typically $mm)",
        source="SYNTHETIC_BUSINESS_SCENARIO_DATA (ccr_counterparties.json)",
    ),
    MetricDefinition(
        id="DELTA_PFE", label="Δ PFE", category="EXPOSURE",
        short_description="Change in supplied PFE between the two observation points on file.",
        formula="ΔPFE = PFE_t - PFE_(t-1)",
        meaning="A large move can come from trade activity, market moves, model recalibration, or a data issue - "
                "see the record's driver classification. Magnitude alone does not imply which.",
        what_it_is_not=["automatically evidence of credit deterioration"],
        units="currency",
    ),
    MetricDefinition(
        id="RC", label="Replacement Cost (RC) / current exposure", category="EXPOSURE",
        short_description="Current mark-to-market / replacement-cost exposure measure, as supplied.",
        meaning="The current-exposure figure recorded for a position - kept in its own units, never combined "
                "with PFE or stress/NSE.",
        what_it_is_not=["PFE", "stress/NSE"],
        units="currency",
    ),
    MetricDefinition(
        id="STRESS_NSE", label="Stress / NSE", category="EXPOSURE",
        short_description="The stress-scenario exposure measure as recorded in the scenario dataset.",
        meaning="This POC dataset uses a single generic field to represent stress/NSE-style exposure; the "
                "source records do not distinguish separate stress-test and NSE methodologies.",
        what_it_is_not=["PFE", "RC", "a defined split between 'stress' and 'NSE' as separate metrics"],
        units="currency",
        limitations=["one synthetic field serves as the generic stress/NSE representation - documented limitation, "
                     "not silently merged into PFE"],
    ),
    MetricDefinition(
        id="DELTA_STRESS_NSE", label="Δ Stress / NSE", category="EXPOSURE",
        short_description="Change in the stress/NSE exposure measure between observation points.",
        formula="ΔStress = Stress_t - Stress_(t-1)",
        meaning="Same driver-attribution caveat as ΔPFE applies - see the record's classified driver.",
        units="currency",
    ),
    MetricDefinition(
        id="LIMIT_UTILISATION", label="Limit utilisation", category="CONTROL",
        short_description="Matching exposure metric divided by the matching limit - only when types align.",
        formula="Utilisation = MatchingExposureMetric / MatchingLimit",
        meaning="PFE_LIMIT is compared only to PFE; STRESS_LIMIT only to stress/NSE; SETTLEMENT_LIMIT only to "
                "settlement exposure. If no matching metric exists for the limit's type, utilisation is Unavailable.",
        what_it_is_not=["a universal exposure ratio independent of limit type",
                         "computed by comparing RC to a PFE limit, or PFE to a settlement limit"],
        source="core/ccr_priority.py enrich()",
    ),
    MetricDefinition(
        id="HEADROOM", label="Headroom", category="CONTROL",
        short_description="Remaining capacity under a limit, only when the metric types match.",
        formula="Headroom = Limit - MatchingExposureMetric",
        meaning="Only computed when the limit's metric type has a corresponding available exposure figure; "
                "otherwise reported as Unavailable, never estimated from a mismatched metric.",
        units="currency",
    ),
    MetricDefinition(
        id="EQUITY_DELTA", label="Equity delta", category="SENSITIVITY",
        short_description="Sensitivity of the position's value to a move in the underlying equity.",
        meaning="Approximate value change per unit move in the underlying equity price, as supplied by the scenario data.",
        units="currency per 1.0 move in underlying (as supplied)",
    ),
    MetricDefinition(
        id="FX_DELTA", label="FX delta", category="SENSITIVITY",
        short_description="Sensitivity of the position's value to a move in the relevant FX rate.",
        meaning="Approximate value change per unit move in the relevant FX rate, as supplied by the scenario data.",
        units="currency per unit FX move (as supplied)",
    ),
    MetricDefinition(
        id="DV01", label="DV01 / IR01", category="SENSITIVITY",
        short_description="Approximate value change for a one-basis-point move in interest rates.",
        meaning="Preserves the dataset's own field naming (DV01 vs IR01) rather than normalizing to one term.",
        units="currency per 1bp",
    ),
    MetricDefinition(
        id="CS01", label="CS01", category="SENSITIVITY",
        short_description="Approximate value change for a one-basis-point move in credit spread.",
        meaning="Approximate value change for a one-basis-point widening/tightening of the reference entity's credit spread.",
        units="currency per 1bp",
    ),
    MetricDefinition(
        id="WWR_STATUS", label="Wrong-way risk (WWR) status", category="CONTROL",
        short_description="Whether exposure is believed to move adversely with counterparty/collateral quality.",
        meaning="A categorical evidence state, not a modeled probability.",
        formula=None,
        inputs=["CONFIRMED_FROM_SCENARIO", "INDICATIVE", "NOT_IDENTIFIED", "INSUFFICIENT_DATA"],
        what_it_is_not=["a numeric WWR probability or score unless one is explicitly modeled (none is, in this POC)"],
    ),
    MetricDefinition(
        id="THEME_VELOCITY", label="Theme velocity", category="THEME_DISCOVERY",
        short_description="Rate of change in thematic attention - a discovery metric, not a risk measure.",
        formula="Velocity = (Recent - Prior) / Prior  (Prior=0 handled explicitly, never divides by zero)",
        meaning="Measures acceleration in mentions/attention for a theme.",
        what_it_is_not=["a credit risk score", "PD", "PFE", "exposure"],
    ),
    MetricDefinition(
        id="THEME_COVERAGE", label="Theme coverage", category="THEME_DISCOVERY",
        short_description="Number of entities associated with a theme.",
        meaning="Breadth of thematic association across the entity universe - a discovery metric.",
        what_it_is_not=["a risk measure"],
    ),
    MetricDefinition(
        id="THEME_REACH", label="Theme reach", category="THEME_DISCOVERY",
        short_description="Number of counterparties connected to a theme through exposure context.",
        meaning="How far a theme's entity associations extend into actual CCR exposure - still a discovery "
                "metric, not a materiality or risk ranking.",
        what_it_is_not=["a risk measure", "a materiality ranking"],
    ),
    MetricDefinition(
        id="DRIVER_CLASSIFICATION", label="Driver classification", category="CONTROL",
        short_description="Evidence-based explanation of why an exposure/control metric changed.",
        meaning="A deterministic precedence cascade over explicit boolean evidence flags (e.g. new_trade_flag, "
                "market_move_flag) - never inferred from move size alone. 'Simulation noise' specifically "
                "requires an explicit confirmation flag; a small move without one is labeled SMALL_MOVE, not noise.",
        what_it_is_not=["a risk score", "an ML/AI-inferred label"],
        source="core/ccr_priority.py classify_driver()",
    ),
]

_BY_ID = {d.id: d for d in _DEFINITIONS}


def get_metric_definition(metric_id: str) -> MetricDefinition | None:
    return _BY_ID.get(metric_id.upper())


def list_metric_definitions() -> list[MetricDefinition]:
    return list(_DEFINITIONS)
