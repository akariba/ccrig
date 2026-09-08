"""Mode 2 ranking for Event Studio: relation-aware Personalized PageRank
over Layer A (fact) + Layer B (derived) edges ONLY.

BUILD_MANDATE explicitly forbids mixing exposure percentages (Layer C) with
relationship-score units inside the same propagation network, so the
EXPOSURE graph is intentionally excluded here - it is joined afterwards,
once, by event_parser/routers when producing "relevant counterparties".

DebtRank-style network propagation on the real economic/exposure network is
listed by the mandate as an experimental-panel-only feature and has NOT
been implemented in this POC (see docs/LIMITATIONS.md) - it must never run
on semantic/derived edges, and we did not want a half-correct version.
"""
import networkx as nx
from .data import STORE
from .graph_store import FACT_GRAPH
from . import scoring, candidates
from .config import DEFAULT_WEIGHTS

_PPR_GRAPH_CACHE = None


def _build_relation_graph():
    """Issuer-only structural graph. Counterparties are deliberately
    excluded from PPR's node set: EVENT -> concepts/entities -> issuer
    relationships -> relevant issuers is a Layer A/B propagation, and a
    counterparty must reach the result set ONLY through the explicit
    Layer C exposure join performed afterwards in event_parser.py, never
    by ranking structurally in the same way as an issuer/entity."""
    g = nx.DiGraph()
    for eid in STORE.issuer_ids:
        g.add_node(eid)

    # Layer A: fact edges, both directions get a propagation weight (a
    # shock can travel either way through a supply relationship) but we
    # tag which direction was the ORIGINAL factual direction.
    for u, v, data in FACT_GRAPH.edges(data=True):
        if u not in g or v not in g:
            continue
        w = data.get("criticality", 0.5)
        g.add_edge(u, v, weight=max(w, g.get_edge_data(u, v, {}).get("weight", 0)), layer="FACT")
        g.add_edge(v, u, weight=max(w * 0.6, g.get_edge_data(v, u, {}).get("weight", 0)), layer="FACT_REVERSE")

    # Layer B: derived candidate-scored edges (general preset), bounded by
    # candidate generation exactly like every other consumer of scoring.py.
    # generate_candidates() can still surface counterparties as candidates
    # (it draws on the shared browsable_ids sector/theme/semantic blocks),
    # so we explicitly drop any candidate that isn't an issuer before it
    # can become a PPR edge/node.
    for eid in STORE.issuer_ids:
        cand = candidates.generate_candidates(eid)
        if not cand:
            continue
        ranked = scoring.rank_candidates(eid, cand["candidate_ids"], DEFAULT_WEIGHTS, top_k=8)
        for r in ranked["results"]:
            other = r["b"]
            if other not in g:
                continue
            score = r["composite"]["score"]
            if score and score > 0.05:
                existing = g.get_edge_data(eid, other, {}).get("weight", 0)
                g.add_edge(eid, other, weight=max(score, existing), layer="DERIVED")
    return g


def get_relation_graph():
    global _PPR_GRAPH_CACHE
    if _PPR_GRAPH_CACHE is None:
        _PPR_GRAPH_CACHE = _build_relation_graph()
    return _PPR_GRAPH_CACHE


def personalized_pagerank(seed_entities, top_k=15, damping=0.85):
    g = get_relation_graph()
    seeds = [s for s in seed_entities if s in g]
    if not seeds:
        return {"error": "no valid seed entities in relation graph", "results": []}
    personalization = {n: (1.0 / len(seeds) if n in seeds else 0.0) for n in g.nodes}
    try:
        scores = nx.pagerank(g, alpha=damping, personalization=personalization, weight="weight", max_iter=200)
    except nx.PowerIterationFailedConvergence:
        scores = nx.pagerank(g, alpha=damping, personalization=personalization, weight="weight", max_iter=1000, tol=1e-4)
    ranked = sorted(((n, s) for n, s in scores.items() if n not in seeds), key=lambda x: -x[1])
    return {
        "seeds": seeds,
        "method": "relation_aware_personalized_pagerank",
        "damping": damping,
        "results": [{"entity_id": n, "ppr_score": round(s, 6)} for n, s in ranked[:top_k]],
    }
