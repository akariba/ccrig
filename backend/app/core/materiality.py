"""Business-materiality join: connects graph/event-nominated issuers to the
synthetic CCR exposure dataset (core/ccr_priority.py), so a candidate
surfaced by relationship discovery (Entity 360 relatedness, Event Studio
Mode 1/Mode 2) is ranked by REAL exposure materiality, not by the
discovery score itself.

"Graph/event relevance nominates candidates. Exposure and limit
materiality determine investigation priority."
"""
from . import ccr_priority


def _all_enriched_classified():
    return ccr_priority.build_priority_queue()  # already enrich+classify+sort


def counterparties_for_reference_entity(entity_id):
    """Entity 360 materiality panel: synthetic CCR counterparties with a
    typed exposure whose reference_entity_id matches this issuer."""
    return [r for r in _all_enriched_classified() if r.get("reference_entity_id") == entity_id]


def materiality_join(relevant_issuer_ids):
    """Event Studio materiality join: for every graph/event-nominated
    issuer, attach any synthetic CCR counterparty with a typed exposure
    referencing it, each carrying its own priority/driver/reasons. Rows
    are re-sorted by priority (CRITICAL > HIGH > MEDIUM > LOW), NOT by
    the event/PPR score that nominated the underlying issuer."""
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFORMATIONAL": 4}
    rows = [r for r in _all_enriched_classified() if r.get("reference_entity_id") in set(relevant_issuer_ids)]
    rows.sort(key=lambda r: (order[r["priority"]], -(abs(r["delta_pfe"]) if r["delta_pfe"] is not None else 0)))
    return rows
