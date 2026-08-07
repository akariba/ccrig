"""Graph Explorer backing endpoint (BUILD_MANDATE section 16). Always
returns a BOUNDED ego graph around a seed entity - it never draws the
entire universe by default. Fact / derived / exposure layers are returned
as separately-tagged edge lists so the frontend can toggle them
independently instead of visually merging Layer A/B/C.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from ..core.data import STORE
from ..core.graph_store import FACT_GRAPH, exposure_of_counterparty, counterparties_exposed_to
from ..core import candidates, scoring
from ..core.config import DEFAULT_WEIGHTS

router = APIRouter(prefix="/api/graph", tags=["graph"])


def _node_obj(eid):
    e = STORE.entity(eid)
    if not e:
        return {"id": eid, "name": eid, "node_type": "Unknown"}
    return {"id": eid, "name": e["name"], "node_type": e["node_type"], "sector": e.get("sector"),
            "country": e.get("country"), "is_synthetic": e.get("is_synthetic", False),
            "has_market_data": e.get("has_market_data", False)}


@router.get("/ego/{entity_id}")
def ego_graph(entity_id: str, hops: int = 1, top_k: int = 8, min_score: float = 0.1,
              layers: str = "fact,derived,exposure",
              node_types: Optional[str] = None):
    entity_id = entity_id.upper()
    if entity_id not in STORE.entities_by_id:
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    hops = max(1, min(hops, 2))
    active_layers = set(layers.split(","))
    allowed_types = set(node_types.split(",")) if node_types else None

    nodes = {entity_id: _node_obj(entity_id)}
    edges = []

    def add_edge(src, tgt, relation, layer, weight, directed, evidence=None):
        edges.append({"source": src, "target": tgt, "relation": relation, "layer": layer,
                       "weight": weight, "directed": directed, "evidence": evidence})

    frontier = [entity_id]
    visited = {entity_id}
    for hop_i in range(hops):
        next_frontier = []
        for node in frontier:
            if "fact" in active_layers:
                for _, tgt, data in FACT_GRAPH.out_edges(node, data=True):
                    if allowed_types and STORE.entity(tgt)["node_type"] not in allowed_types:
                        continue
                    nodes.setdefault(tgt, _node_obj(tgt))
                    add_edge(node, tgt, data["relation"], "FACT", data.get("criticality", 1.0), True,
                              {"evidence_status": data.get("evidence_status"), "evidence_url": data.get("evidence_url"),
                               "note": data.get("note")})
                    if tgt not in visited:
                        next_frontier.append(tgt)
                        visited.add(tgt)
                for src, _, data in FACT_GRAPH.in_edges(node, data=True):
                    if allowed_types and STORE.entity(src)["node_type"] not in allowed_types:
                        continue
                    nodes.setdefault(src, _node_obj(src))
                    add_edge(src, node, data["relation"], "FACT", data.get("criticality", 1.0), True,
                              {"evidence_status": data.get("evidence_status"), "evidence_url": data.get("evidence_url"),
                               "note": data.get("note")})
                    if src not in visited:
                        next_frontier.append(src)
                        visited.add(src)

            if "derived" in active_layers and node in STORE.browsable_ids:
                cand = candidates.generate_candidates(node)
                if cand:
                    ranked = scoring.rank_candidates(node, cand["candidate_ids"], DEFAULT_WEIGHTS, top_k=top_k)
                    for r in ranked["results"]:
                        score = r["composite"]["score"]
                        if score is None or score < min_score:
                            continue
                        other = r["b"]
                        if allowed_types and STORE.entity(other)["node_type"] not in allowed_types:
                            continue
                        nodes.setdefault(other, _node_obj(other))
                        add_edge(node, other, "STRUCTURALLY_RELATED", "DERIVED", score, False,
                                  {"component_values": r["composite"]["component_values"],
                                   "missing_components": r["composite"]["missing_components"]})
                        if other not in visited:
                            next_frontier.append(other)
                            visited.add(other)

            if "exposure" in active_layers:
                e = STORE.entity(node)
                if e and e["node_type"] == "Counterparty":
                    for xe in exposure_of_counterparty(node):
                        issuer = xe["issuer"]
                        nodes.setdefault(issuer, _node_obj(issuer))
                        add_edge(node, issuer, xe["relation"], "EXPOSURE", xe.get("exposure_pct", 0), True,
                                  {"is_synthetic": True})
                elif e and e["node_type"] == "Company/Issuer":
                    for cp_edge in counterparties_exposed_to(node):
                        cp = cp_edge["counterparty"]
                        nodes.setdefault(cp, _node_obj(cp))
                        add_edge(cp, node, cp_edge["relation"], "EXPOSURE", cp_edge.get("exposure_pct", 0), True,
                                  {"is_synthetic": True})
        frontier = next_frontier
        if not frontier:
            break

    return {
        "center": entity_id,
        "hops": hops,
        "active_layers": sorted(active_layers),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": list(nodes.values()),
        "edges": edges,
        "legend": {
            "FACT": "Layer A - factual, sourced, directional relations (solid arrow)",
            "DERIVED": "Layer B - computed similarity/relatedness (dashed, symmetric)",
            "EXPOSURE": "Layer C - synthetic counterparty exposure (dotted arrow, counterparty -> issuer)",
        },
        "bounded_by_default": True,
    }
