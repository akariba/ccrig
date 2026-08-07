"""Candidate generation BEFORE expensive pair scoring (BUILD_MANDATE
section 9). We never compute a dense N x N matrix and then sparsify -
candidates are unioned from five bounded sources and only THAT bounded set
is ever scored. Every call returns instrumentation counts so the UI can
show theoretical / candidate / scored / retained pair counts.
"""
from .data import STORE
from .graph_store import fact_neighbors
from .semantic import SEMANTIC
from . import market
from .config import (
    CANDIDATE_SEMANTIC_NN, CANDIDATE_THEME_NN, CANDIDATE_MARKET_NN,
    CANDIDATE_CATEGORY_BLOCK_MAX,
)


def _category_block(entity_id):
    e = STORE.entity(entity_id)
    if not e:
        return []
    peers = [eid for eid in STORE.browsable_ids
             if eid != entity_id and STORE.entity(eid)["sector"] == e["sector"]]
    return peers[:CANDIDATE_CATEGORY_BLOCK_MAX]


def _theme_neighbors(entity_id, top_k):
    weights = STORE.entity_keyword_weights.get(entity_id, {})
    if not weights:
        return []
    my_themes = set(weights.keys())
    scored = []
    for other in STORE.browsable_ids:
        if other == entity_id:
            continue
        other_weights = STORE.entity_keyword_weights.get(other, {})
        shared = my_themes & set(other_weights.keys())
        if not shared:
            continue
        score = sum(min(weights[t], other_weights[t]) for t in shared)
        scored.append((other, score))
    scored.sort(key=lambda x: -x[1])
    return [eid for eid, _ in scored[:top_k]]


def generate_candidates(entity_id):
    """Returns dict: sources -> list of candidate ids, union list, and
    instrumentation counts. This is THE gate: only entities appearing here
    are ever passed to scoring.score_pair()."""
    if entity_id not in STORE.entities_by_id:
        return None

    fact_neighs = list(fact_neighbors(entity_id).keys())
    category_block = _category_block(entity_id)
    semantic_neighs = [eid for eid, _ in SEMANTIC.nearest(entity_id, CANDIDATE_SEMANTIC_NN)]
    theme_neighs = _theme_neighbors(entity_id, CANDIDATE_THEME_NN)
    market_neighs = market.market_neighbors(entity_id, CANDIDATE_MARKET_NN)

    # Exposure-graph counterparties are surfaced separately (Counterparty
    # 360 / Event Studio exposure join) - NOT unioned into the relatedness
    # candidate set, so we never mix exposure % with relatedness units.
    sources = {
        "factual_neighbors": fact_neighs,
        "category_block": [c for c in category_block if c not in fact_neighs],
        "semantic_nn": semantic_neighs,
        "theme_nn": theme_neighs,
        "market_nn": market_neighs,
    }
    union = []
    seen = set()
    for src_name, ids in sources.items():
        for eid in ids:
            if eid not in seen and eid != entity_id:
                seen.add(eid)
                union.append(eid)

    n_browsable = len(STORE.browsable_ids)
    theoretical_pairs_for_entity = n_browsable - 1
    return {
        "entity_id": entity_id,
        "sources": sources,
        "candidate_ids": union,
        "instrumentation": {
            "theoretical_pair_count": theoretical_pairs_for_entity,
            "candidate_count": len(union),
            "reduction_ratio": round(1 - (len(union) / theoretical_pairs_for_entity), 4) if theoretical_pairs_for_entity else 0,
        },
    }
