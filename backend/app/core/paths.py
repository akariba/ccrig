"""Typed path grammar (BUILD_MANDATE section 15). The path itself is always
deterministic and inspectable - built purely from already-computed facts,
themes and exposure edges. Only the natural-language EXPLANATION of a path
may be produced by the AI provider (see ai/provider.py), and even then only
by summarising the exact path object returned here - never inventing hops.

Grammar patterns implemented:
  P1  EVENT -> CONCEPT -> COMPANY                       (theme relevance)
  P2  EVENT -> CONCEPT -> COMPANY -> SUPPLIES/CUSTOMER_OF -> COMPANY   (supply-chain propagation)
  P3  EVENT -> CONCEPT -> COMPANY -> ISSUER_EXPOSURE -> COUNTERPARTY   (counterparty relevance)
  P4  EVENT -> COUNTRY -> COMPANY (OPERATES_IN / INCORPORATED_IN)      (geographic propagation)
  P5  COMPANY -> SECTOR -> COMPANY                                    (peer/category path)
  P6  COMPANY -> THEME -> COMPANY                                     (thematic co-mention path)
"""
from .data import STORE
from .graph_store import FACT_GRAPH, EXPOSURE_GRAPH

SUPPLY_RELATIONS = {"SUPPLIES", "CUSTOMER_OF", "LICENSES_TO", "LICENSES_FROM"}


def theme_relevance_path(theme_id, entity_id):
    e = STORE.entity(entity_id)
    kw = STORE.keywords_by_id.get(theme_id)
    if not e or not kw:
        return None
    weight = STORE.entity_keyword_weights.get(entity_id, {}).get(theme_id)
    if weight is None:
        return None
    return {
        "pattern": "P1_EVENT_CONCEPT_COMPANY",
        "hops": [
            {"type": "CONCEPT", "id": theme_id, "label": kw["label"]},
            {"type": "COMPANY", "id": entity_id, "label": e["name"], "edge": "RELEVANT_TO", "weight": weight},
        ],
    }


def supply_chain_propagation_paths(theme_id, direct_entity_id, max_hops=2):
    """From a directly-theme-relevant company, walk fact supply edges
    outward up to max_hops, preserving direction at every hop."""
    paths = []
    frontier = [(direct_entity_id, [])]
    visited = {direct_entity_id}
    for _hop in range(max_hops):
        next_frontier = []
        for node, trail in frontier:
            for _, tgt, data in FACT_GRAPH.out_edges(node, data=True):
                if data["relation"] not in SUPPLY_RELATIONS or tgt in visited:
                    continue
                new_trail = trail + [{"from": node, "to": tgt, "relation": data["relation"],
                                       "criticality": data.get("criticality"), "evidence_status": data.get("evidence_status"),
                                       "evidence_url": data.get("evidence_url"), "direction": "FORWARD"}]
                paths.append({
                    "pattern": "P2_EVENT_CONCEPT_COMPANY_SUPPLY_COMPANY",
                    "theme_id": theme_id, "root": direct_entity_id, "hops": new_trail,
                })
                next_frontier.append((tgt, new_trail))
                visited.add(tgt)
            for src, _, data in FACT_GRAPH.in_edges(node, data=True):
                if data["relation"] not in SUPPLY_RELATIONS or src in visited:
                    continue
                new_trail = trail + [{"from": src, "to": node, "relation": data["relation"],
                                       "criticality": data.get("criticality"), "evidence_status": data.get("evidence_status"),
                                       "evidence_url": data.get("evidence_url"), "direction": "REVERSE"}]
                paths.append({
                    "pattern": "P2_EVENT_CONCEPT_COMPANY_SUPPLY_COMPANY",
                    "theme_id": theme_id, "root": direct_entity_id, "hops": new_trail,
                })
                next_frontier.append((src, new_trail))
                visited.add(src)
        frontier = next_frontier
        if not frontier:
            break
    return paths


def counterparty_exposure_paths(issuer_id):
    """Layer C join, applied AFTER issuer relevance is already known
    (mandate: exposure joined after relevance, never before)."""
    paths = []
    for src, _, data in EXPOSURE_GRAPH.in_edges(issuer_id, data=True):
        paths.append({
            "pattern": "P3_ISSUER_EXPOSURE_COUNTERPARTY",
            "issuer": issuer_id,
            "counterparty": src,
            "relation": data["relation"],
            "exposure_pct": data.get("exposure_pct"),
            "is_synthetic": data.get("is_synthetic", True),
        })
    return paths


def geographic_paths(country, max_entities=25):
    paths = []
    for e in STORE.entities_raw:
        if e.get("country") == country and e["node_type"] == "Company/Issuer":
            paths.append({
                "pattern": "P4_EVENT_COUNTRY_COMPANY",
                "country": country,
                "company": e["id"],
                "label": e["name"],
                "relation": "INCORPORATED_IN_OR_OPERATES_IN",
            })
            if len(paths) >= max_entities:
                break
    return paths


def sector_peer_path(a, b):
    ea, eb = STORE.entity(a), STORE.entity(b)
    if not ea or not eb or ea["sector"] != eb["sector"]:
        return None
    return {"pattern": "P5_COMPANY_SECTOR_COMPANY", "hops": [
        {"from": a, "sector": ea["sector"], "to": b},
    ]}


def theme_coincidence_path(a, b):
    wa = STORE.entity_keyword_weights.get(a, {})
    wb = STORE.entity_keyword_weights.get(b, {})
    shared = sorted(set(wa.keys()) & set(wb.keys()), key=lambda t: -min(wa[t], wb[t]))
    if not shared:
        return None
    return {"pattern": "P6_COMPANY_THEME_COMPANY", "hops": [
        {"from": a, "to": b, "shared_themes": shared[:5]},
    ]}


def fact_path_between(a, b, max_hops=2):
    """Deterministic BFS over the FACT graph (both directions) up to
    max_hops, returning the shortest typed path if any."""
    if a == b:
        return None
    frontier = [(a, [])]
    visited = {a}
    for _ in range(max_hops):
        next_frontier = []
        for node, trail in frontier:
            neighbors = []
            for _, tgt, data in FACT_GRAPH.out_edges(node, data=True):
                neighbors.append((tgt, data, "FORWARD"))
            for src, _, data in FACT_GRAPH.in_edges(node, data=True):
                neighbors.append((src, data, "REVERSE"))
            for nxt, data, direction in neighbors:
                if nxt in visited:
                    continue
                new_trail = trail + [{"from": node, "to": nxt, "relation": data["relation"], "direction": direction,
                                       "evidence_status": data.get("evidence_status"), "evidence_url": data.get("evidence_url")}]
                if nxt == b:
                    return {"pattern": "FACT_PATH", "hops": new_trail}
                next_frontier.append((nxt, new_trail))
                visited.add(nxt)
        frontier = next_frontier
        if not frontier:
            break
    return None
