"""Real corporate ownership from GLEIF Level-2 (relationship) data.

BUILD_MANDATE: ownership must come from real, sourced facts or be marked
unavailable - never fabricated. backend/scripts/fetch_gleif_level2.py
fetches direct-parent/ultimate-parent relationships for every entity in
gleif_sample.json via the real GLEIF API and caches the result to
backend/data/gleif_level2_cache.json, so normal app startup never depends
on network access.

This module turns that cache into FACT_GRAPH edges (PARENT_OF/SUBSIDIARY_OF)
- but ONLY when BOTH ends of a relationship are entities we actually track
(matched by LEI), and ONLY using data GLEIF itself reported. As of this
build, all 40 LEI-bearing entities in this dataset are top-of-house public
companies with ZERO reported parent (verified live against api.gleif.org) -
so build_ownership_fact_edges() correctly returns an EMPTY list for the
live app. That is the honest result, not a bug: do not invent a parent
relationship to make this list non-empty. See gleif_level2_demo.json /
tests/test_ownership.py for a proof that the mapping logic itself works
correctly, demonstrated on a real external GLEIF parent/child pair.

Scoring convention (core/scoring.py::_ownership), documented explicitly
per BUILD_MANDATE - NOT a probability:
    criticality 1.0  = direct parent/subsidiary (GLEIF relationship_type
                        IS_DIRECTLY_CONSOLIDATED_BY)
    criticality 0.6  = shared/ultimate parent only, no direct link (GLEIF
                        relationship_type IS_ULTIMATELY_CONSOLIDATED_BY,
                        no matching direct-parent edge) - a weaker but
                        still meaningful ownership signal
"""
import json
from .config import DATA_DIR

DIRECT_CRITICALITY = 1.0
ULTIMATE_ONLY_CRITICALITY = 0.6


def load_gleif_level2_cache():
    path = DATA_DIR / "gleif_level2_cache.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _lei_to_entity_id(gleif_by_entity):
    """gleif_by_entity: {entity_id: {"lei": ..., ...}} (core/data.py::DataStore
    fuzzy-matches gleif_sample.json's name-keyed records onto our entity ids
    at startup; entities.json itself carries no "lei" field)."""
    return {rec["lei"]: eid for eid, rec in gleif_by_entity.items() if rec and rec.get("lei")}


def build_ownership_fact_edges(gleif_by_entity, gleif_cache=None):
    """Returns a list of fact-edge dicts (same shape as scripts/build_dataset.py
    FACT_EDGES entries) for every GLEIF-reported parent relationship where
    BOTH the child and the parent LEI match an entity we track. Direct
    parent relationships take priority over ultimate-only ones for the same
    pair (a direct link is strictly more informative)."""
    cache = gleif_cache if gleif_cache is not None else load_gleif_level2_cache()
    lei_to_id = _lei_to_entity_id(gleif_by_entity)

    edges = []
    seen_pairs = set()
    for entity_name, rec in cache.items():
        if not rec or "error" in rec:
            continue
        child_lei = rec.get("lei")
        child_id = lei_to_id.get(child_lei)
        if not child_id:
            continue

        direct = rec.get("direct_parent")
        ultimate = rec.get("ultimate_parent")

        chosen, criticality = None, None
        if direct and lei_to_id.get(direct["parent_lei"]):
            chosen, criticality = direct, DIRECT_CRITICALITY
        elif ultimate and lei_to_id.get(ultimate["parent_lei"]):
            chosen, criticality = ultimate, ULTIMATE_ONLY_CRITICALITY

        if not chosen:
            continue
        parent_id = lei_to_id[chosen["parent_lei"]]
        pair_key = (child_id, parent_id)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        edges.append({
            "source": child_id,
            "target": parent_id,
            "relation": "SUBSIDIARY_OF",
            "criticality": criticality,
            "note": f"GLEIF-reported {chosen['relationship_type']} relationship.",
            "evidence_status": "REAL_PUBLIC_DATA",
            "gleif_child_lei": chosen["child_lei"],
            "gleif_parent_lei": chosen["parent_lei"],
            "gleif_relationship_type": chosen["relationship_type"],
            "source_type": "GLEIF",
        })
    return edges


def ownership_summary_for_entity(entity_id, entities_raw, gleif_by_entity, gleif_cache=None):
    """Entity 360 corporate-hierarchy panel data: direct parent, ultimate
    parent (if different from direct), and any tracked subsidiaries - each
    with GLEIF provenance, or explicitly None/empty if GLEIF reported none."""
    cache = gleif_cache if gleif_cache is not None else load_gleif_level2_cache()
    lei_to_id = _lei_to_entity_id(gleif_by_entity)
    id_to_lei = {v: k for k, v in lei_to_id.items()}
    entities_by_id = {e["id"]: e for e in entities_raw}

    def _describe(lei):
        eid = lei_to_id.get(lei)
        return {"lei": lei, "entity_id": eid, "name": entities_by_id.get(eid, {}).get("name"),
                "tracked": eid is not None}

    my_lei = id_to_lei.get(entity_id)
    rec = None
    for r in cache.values():
        if r and r.get("lei") == my_lei:
            rec = r
            break

    direct_parent = _describe(rec["direct_parent"]["parent_lei"]) if rec and rec.get("direct_parent") else None
    ultimate_parent = _describe(rec["ultimate_parent"]["parent_lei"]) if rec and rec.get("ultimate_parent") else None

    subsidiaries = []
    for other_name, other_rec in cache.items():
        if not other_rec:
            continue
        dp = other_rec.get("direct_parent")
        if dp and dp.get("parent_lei") == my_lei:
            subsidiaries.append(_describe(other_rec["lei"]))

    return {
        "entity_id": entity_id,
        "lei": my_lei,
        "direct_parent": direct_parent,
        "ultimate_parent": ultimate_parent if ultimate_parent != direct_parent else None,
        "subsidiaries": subsidiaries,
        "has_any_ownership_data": bool(direct_parent or ultimate_parent or subsidiaries),
        "source": "GLEIF",
        "note": "No GLEIF-reported parent/subsidiary relationship for this entity." if not (direct_parent or ultimate_parent or subsidiaries) else None,
    }
