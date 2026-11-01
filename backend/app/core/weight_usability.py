"""Which weighted components can produce a score at all.

`scoring.composite_score` drops components that have no value for a pair and
re-normalises the rest. If EVERY component the caller put weight on is
missing, nothing is left to average: the result is an empty ranking (or a
`None` score) that looks like "no related entities" rather than "this request
cannot be computed". This module explains that case so the API can say so.

It reads data and reports; it changes no score, weight or formula.
"""
from . import scoring
from .config import DEFAULT_WEIGHTS
from .data import STORE

COMPONENTS = tuple(DEFAULT_WEIGHTS)


def weighted_components(weights):
    return [k for k in COMPONENTS if (weights or {}).get(k, 0) > 0]


def dataset_unusable_components():
    """{component: reason} for components with no data anywhere in the dataset."""
    reasons = {}
    if not STORE.has_ownership_data:
        reasons["ownership"] = "no ownership (PARENT_OF / SUBSIDIARY_OF) relationships are loaded in this dataset"
    if sum(1 for i in STORE.issuer_ids if STORE.entity(i).get("has_market_data")) < 2:
        reasons["market_positive"] = reasons["market_negative"] = "fewer than two issuers have price history"
    if not any(e.get("relation") in scoring.SUPPLY_RELATIONS for e in STORE.fact_edges):
        reasons["supply_chain"] = "no supply-chain relationships are loaded in this dataset"
    return reasons


def dataset_problem(weights):
    """Message if all requested weight is on components with no data anywhere, else None."""
    wanted = weighted_components(weights)
    reasons = dataset_unusable_components()
    if wanted and all(k in reasons for k in wanted):
        why = "; ".join(f"{k}: {reasons[k]}" for k in wanted)
        usable = [k for k in COMPONENTS if k not in reasons]
        return (f"all of the requested weight is on components that have no data in this dataset ({why}). "
                f"Give weight to at least one of: {', '.join(usable)}")
    return None


def _why_missing(component, entity_id, other_ids):
    entity = STORE.entity(entity_id) or {}
    if component == "ownership":
        return "no ownership relationships are loaded in this dataset"
    if component in ("market_positive", "market_negative"):
        if not entity.get("has_market_data"):
            return f"{entity_id} has no price history"
        return "none of the compared entities has price history"
    if component == "supply_chain":
        return "no documented supply or licence relationship between them"
    return "no value could be computed"


def _present_components(entity_id, other_ids):
    present = set()
    for other in other_ids:
        comp = scoring.score_pair(entity_id, other, DEFAULT_WEIGHTS)["composite"]
        present |= {k for k, v in comp.get("component_values", {}).items() if v is not None}
    return present


def _explain(subject, wanted, entity_id, other_ids, scope):
    present = _present_components(entity_id, other_ids)
    why = "; ".join(f"{k}: {_why_missing(k, entity_id, other_ids)}" for k in wanted)
    usable = [k for k in COMPONENTS if k in present]
    return (f"Cannot calculate {subject} with these weights: every component you weighted "
            f"({', '.join(wanted)}) has no data {scope} ({why}). "
            f"Components that do have data here: {', '.join(usable) or 'none'}. "
            f"Give weight to at least one of those.")


def ranking_problem(entity_id, candidate_ids, weights):
    """Why no candidate of `entity_id` could be scored with `weights`."""
    if not candidate_ids:
        return f"Cannot calculate a ranking for {entity_id}: it has no candidate entities to compare."
    return _explain(f"a ranking for {entity_id}", weighted_components(weights), entity_id, candidate_ids,
                    f"for {entity_id} against any of its {len(candidate_ids)} candidates")


def pair_problem(a, b, weights):
    """Why the pair (a, b) has no score with `weights`."""
    return _explain(f"a score for {a} vs {b}", weighted_components(weights), a, [b], f"for the pair {a} / {b}")
