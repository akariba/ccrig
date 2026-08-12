"""Three explicitly SEPARATE correlation/dependence concepts. Never merged
into one "correlation score" - a scalar like "JPY correlates with UST 0.7"
collapses three different reasoning tasks into one number and loses the
transmission mechanism.

DOMAIN A - ISSUER / MARKET CORRELATION
    corr(NVDA returns, TSMC returns). Used for relationship discovery /
    risk-factor similarity between two tradeable issuers. Backed by
    core/market.py::signed_correlation - REAL price data, sign preserved,
    never abs()'d away. This is the domain already used everywhere else in
    CCRIG (Entity 360, Graph Explorer, Model Lab) - this module does not
    reimplement it, just labels it explicitly as Domain A.

DOMAIN B - CROSS-RISK-FACTOR TRANSMISSION PATH
    JPY -> Japanese rates -> UST yields -> repo market -> basis trades.
    This is economic REASONING about how a shock propagates between named
    risk factors, not a numeric correlation matrix - no macro time-series
    data is bundled in this POC to compute one honestly, so this is
    CURATED_REFERENCE_DATA (hand-authored transmission paths attached to
    ccr_events.json), not a derived statistic. Never presented as a
    correlation coefficient.

DOMAIN C - WWR DIAGNOSTIC
    Whether a counterparty's own credit risk is correlated with the value
    of its exposure/collateral to Citi (wrong-way risk). This POC never
    invents a WWR statistic - it only surfaces the explicit wwr_flag
    evidence already present on a CCR record (set by
    scripts/build_ccr_dataset.py, never inferred), attached to that
    record's risk_factor_path so an analyst can see WHY wrong-way risk was
    flagged, not just THAT it was.
"""
from . import market as market_mod
from . import ccr_priority


def issuer_market_correlation(entity_a, entity_b):
    """DOMAIN A. Thin, explicitly-labelled wrapper over the existing
    core/market.py signed correlation - included here only so callers can
    request it by domain name and get a domain tag back."""
    corr = market_mod.signed_correlation(entity_a, entity_b)
    if corr is None:
        return None
    return {**corr, "domain": "ISSUER_MARKET_CORRELATION"}


def risk_factor_transmission_path(event_id):
    """DOMAIN B. Returns the curated (not computed) risk-factor chain for a
    named event, e.g. ["JPY", "JAPAN_RATES", "UST_YIELD", "REPO_MARKET",
    "TREASURY_BASIS"]. Never a numeric correlation - a typed path."""
    from .data import STORE
    for e in STORE.ccr_events:
        if e["id"] == event_id:
            return {"event_id": event_id, "path": e.get("risk_factor_path", []),
                     "domain": "RISK_FACTOR_TRANSMISSION_PATH", "source_type": "CURATED_REFERENCE_DATA"}
    return None


def wwr_diagnostic(counterparty_id):
    """DOMAIN C. Surfaces the explicit wwr_flag evidence (never inferred)
    for one CCR record, alongside its risk_factor_path, so an analyst can
    see the reasoning, not a fabricated WWR score."""
    rows = ccr_priority.build_priority_queue()
    match = next((r for r in rows if r["id"] == counterparty_id), None)
    if not match:
        return None
    flagged = bool(match.get("driver_evidence", {}).get("wwr_flag"))
    return {
        "counterparty_id": counterparty_id,
        "domain": "WWR_DIAGNOSTIC",
        "wwr_flagged": flagged,
        "basis": "explicit wwr_flag evidence (never inferred from exposure size)" if flagged else "no WWR evidence flag set",
        "risk_factor_path": match.get("risk_factor_path", []),
        "collateral": match.get("collateral"),
    }
