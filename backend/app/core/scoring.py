"""Relationship feature VECTOR + configurable weighted composite
(BUILD_MANDATE section 7). We NEVER store a single scalar as the ground
truth relationship - `score_pair()` always returns the full decomposed
vector; the scalar `composite_score` is one VIEW over it, computed with
whatever weights are supplied (Model Lab lets the user change them live).
"""
from .data import STORE
from .graph_store import FACT_GRAPH
from .semantic import SEMANTIC
from . import market
from .config import DEFAULT_WEIGHTS

SUPPLY_RELATIONS = {"SUPPLIES", "CUSTOMER_OF", "LICENSES_TO", "LICENSES_FROM"}
OWNERSHIP_RELATIONS = {"PARENT_OF", "SUBSIDIARY_OF"}


def _sector_similarity(a, b):
    ea, eb = STORE.entity(a), STORE.entity(b)
    if not ea or not eb:
        return None
    if ea["sector"] == eb["sector"]:
        return 1.0
    return 0.0


def _geography_similarity(a, b):
    ea, eb = STORE.entity(a), STORE.entity(b)
    if not ea or not eb:
        return None
    if ea["country"] == eb["country"]:
        return 1.0
    if ea.get("region") == eb.get("region"):
        return 0.5
    return 0.0


def _supply_chain(a, b):
    """Directional. Returns (forward_dependency, reverse_dependency, edges)
    where forward = a depends on / relates to b via an outgoing supply-type
    fact edge, reverse = via an incoming one. Direction is preserved and
    surfaced separately - never collapsed into one undirected number."""
    edges = []
    forward = 0.0
    reverse = 0.0
    if FACT_GRAPH.has_edge(a, b):
        for key, data in FACT_GRAPH.get_edge_data(a, b).items():
            if data["relation"] in SUPPLY_RELATIONS:
                forward = max(forward, data.get("criticality", 0.5))
                edges.append({**data, "direction": f"{a}->{b}"})
    if FACT_GRAPH.has_edge(b, a):
        for key, data in FACT_GRAPH.get_edge_data(b, a).items():
            if data["relation"] in SUPPLY_RELATIONS:
                reverse = max(reverse, data.get("criticality", 0.5))
                edges.append({**data, "direction": f"{b}->{a}"})
    if not edges:
        return None, None, []
    return forward, reverse, edges


def _ownership(a, b):
    edges = []
    if FACT_GRAPH.has_edge(a, b):
        for key, data in FACT_GRAPH.get_edge_data(a, b).items():
            if data["relation"] in OWNERSHIP_RELATIONS:
                edges.append({**data, "direction": f"{a}->{b}"})
    if FACT_GRAPH.has_edge(b, a):
        for key, data in FACT_GRAPH.get_edge_data(b, a).items():
            if data["relation"] in OWNERSHIP_RELATIONS:
                edges.append({**data, "direction": f"{b}->{a}"})
    if not edges:
        return None, edges
    return 1.0, edges


def _news_cooccurrence(a, b):
    wa = STORE.entity_keyword_weights.get(a, {})
    wb = STORE.entity_keyword_weights.get(b, {})
    if not wa or not wb:
        return None
    shared = set(wa.keys()) & set(wb.keys())
    if not shared:
        return 0.0
    num = sum(min(wa[t], wb[t]) for t in shared)
    denom = (sum(wa.values()) * sum(wb.values())) ** 0.5
    if denom == 0:
        return 0.0
    return min(1.0, num / denom * len(shared))


def feature_vector(a, b):
    """Full decomposed relationship feature vector for pair (a, b).
    Any component that cannot be computed (missing data) is None, not 0 -
    callers must treat None as MISSING, not as evidence of no relationship."""
    fwd, rev, supply_edges = _supply_chain(a, b)
    own_val, own_edges = _ownership(a, b)
    corr = market.signed_correlation(a, b)

    vec = {
        "sector_similarity": _sector_similarity(a, b),
        "geography_similarity": _geography_similarity(a, b),
        "semantic_similarity": SEMANTIC.similarity(a, b),
        "news_theme_similarity": _news_cooccurrence(a, b),
        "supply_chain_forward": fwd,
        "supply_chain_reverse": rev,
        "supply_chain_edges": supply_edges,
        "ownership": own_val,
        "ownership_edges": own_edges,
        "market_positive": corr["positive_channel"] if corr else None,
        "market_negative": corr["negative_channel"] if corr else None,
        "market_detail": corr,
        "freshness": "current",
    }
    return vec


def composite_score(vec, weights=None, round_output=True):
    """Weighted composite VIEW over the vector. Missing components are
    excluded and remaining weights re-normalised (missing-data handling,
    shown explicitly in the Model Lab UI).

    round_output=False returns raw unrounded floats - used only by
    core/calibration.py, whose gradient-based optimiser needs sub-1e-4
    sensitivity that the display-oriented 4dp rounding would otherwise
    quantise away. Every other caller keeps the rounded (default) output."""
    w = weights or DEFAULT_WEIGHTS
    component_map = {
        "sector": vec.get("sector_similarity"),
        "geography": vec.get("geography_similarity"),
        "supply_chain": max(
            [v for v in [vec.get("supply_chain_forward"), vec.get("supply_chain_reverse")] if v is not None],
            default=None,
        ),
        "ownership": vec.get("ownership"),
        "semantic": vec.get("semantic_similarity"),
        "news": vec.get("news_theme_similarity"),
        "market_positive": vec.get("market_positive"),
        "market_negative": vec.get("market_negative"),
    }
    available = {k: v for k, v in component_map.items() if v is not None}
    missing = [k for k in component_map if k not in available]
    # "ownership" is not just missing for this pair - the dataset has zero
    # PARENT_OF/SUBSIDIARY_OF edges at all, so it can never be a live signal
    # here. Surface that explicitly rather than letting it look like an
    # ordinary per-pair gap (BUILD_MANDATE: never let an unavailable
    # component misleadingly imply it affects the score).
    ownership_status = "available" if STORE.has_ownership_data else "N/A (no ownership data in dataset)"
    if not available:
        return {"score": None, "missing_components": missing, "used_weights": {}, "ownership_status": ownership_status}
    weight_sum = sum(w.get(k, 0) for k in available)
    if weight_sum == 0:
        return {"score": None, "missing_components": missing, "used_weights": {}, "ownership_status": ownership_status}
    used_weights = {k: w.get(k, 0) / weight_sum for k in available}
    score = sum(available[k] * used_weights[k] for k in available)
    return {
        "score": round(score, 4) if round_output else score,
        "component_values": component_map,
        "missing_components": missing,
        "used_weights": {k: (round(v, 4) if round_output else v) for k, v in used_weights.items()},
        "raw_weights": w,
        "ownership_status": ownership_status,
    }


def score_pair(a, b, weights=None):
    vec = feature_vector(a, b)
    comp = composite_score(vec, weights)
    return {"a": a, "b": b, "vector": vec, "composite": comp}


def rank_candidates(entity_id, candidate_ids, weights=None, top_k=None):
    scored = []
    for cid in candidate_ids:
        result = score_pair(entity_id, cid, weights)
        if result["composite"]["score"] is not None:
            scored.append(result)
    scored.sort(key=lambda r: -r["composite"]["score"])
    retained = scored[:top_k] if top_k else scored
    return {
        "scored_pair_count": len(scored),
        "retained_count": len(retained),
        "results": retained,
    }
