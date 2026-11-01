"""What approved relationship evidence would change: graph connectivity, analytical coverage and the genuinely linked counterparties, plus every gap.

Pure read-only computation over the canonical datasets and the approved evidence. It never adopts anything, never touches a score, and never turns a
relationship into an exposure: where no exposure data exists it says so.
"""
from __future__ import annotations

import networkx as nx

from ..core import scoring
from ..core.data import STORE
from ..core.graph_store import EXPOSURE_GRAPH, FACT_GRAPH

SCORING_RELATIONS = set(scoring.SUPPLY_RELATIONS) | set(scoring.OWNERSHIP_RELATIONS) | {"SUPPLIES", "LICENSES_TO", "PARENT_OF", "SUBSIDIARY_OF"}


def edge_effect(rows: list) -> dict:
    """For staging: what each proposed edge is relative to the canonical graph (new edge / evidence for an existing edge / reverse of an existing edge)."""
    from .overlay import group_edges

    out = []
    for e in group_edges(rows):
        s, rel, t = e["source"], e["relation"], e["target"]
        exists = FACT_GRAPH.has_edge(s, t, key=rel)
        reverse = FACT_GRAPH.has_edge(t, s, key=rel)
        status = "EVIDENCE_FOR_CANONICAL_EDGE" if exists else "NEW_EDGE"
        out.append({"source": s, "relation": rel, "target": t, "status": status, "reverse_edge_in_canonical": reverse and not exists,
                    "canonical_evidence_status": FACT_GRAPH.get_edge_data(s, t, rel).get("evidence_status") if exists else None,
                    "canonical_has_evidence_url": bool(FACT_GRAPH.get_edge_data(s, t, rel).get("evidence_url")) if exists else None,
                    "evidence_documents": len(e["evidence"]),
                    "used_by_scoring_if_adopted": rel in SCORING_RELATIONS})
    return {"edges": out, "new_edges": sum(1 for x in out if x["status"] == "NEW_EDGE"), "evidence_only": sum(1 for x in out if x["status"] != "NEW_EDGE")}


def _issuer_graph(extra_edges: list) -> nx.Graph:
    g = nx.Graph()
    g.add_nodes_from(STORE.issuer_ids)
    issuers = set(STORE.issuer_ids)
    for a, b, d in FACT_GRAPH.edges(data=True):
        if d["relation"] in SCORING_RELATIONS and a in issuers and b in issuers:
            g.add_edge(a, b)
    for e in extra_edges:
        if e["relation"] in SCORING_RELATIONS and e["source"] in issuers and e["target"] in issuers:
            g.add_edge(e["source"], e["target"])
    return g


def _metrics(g: nx.Graph) -> dict:
    comps = [c for c in nx.connected_components(g)]
    return {"issuers_with_a_documented_relationship": sum(1 for n in g if g.degree(n) > 0), "issuers_without_any": sum(1 for n in g if g.degree(n) == 0),
            "documented_issuer_pairs": g.number_of_edges(), "connected_groups_of_two_or_more": sum(1 for c in comps if len(c) > 1), "largest_group_size": max((len(c) for c in comps), default=0)}


def adoption_effect(edges: list, approved_reference_rows: list | None = None) -> dict:
    """`edges` are overlay edges (grouped approved evidence)."""
    new = [e for e in edges if not FACT_GRAPH.has_edge(e["source"], e["target"], key=e["relation"])]
    before, after = _issuer_graph([]), _issuer_graph(new)
    mb, ma = _metrics(before), _metrics(after)
    newly_connected = sorted(n for n in after if after.degree(n) > 0 and before.degree(n) == 0)
    scored = [e for e in new if e["relation"] in SCORING_RELATIONS]
    ends = sorted({x for e in new for x in (e["source"], e["target"])})
    holders = {}
    for iss in ends:
        holders[iss] = sorted(({"counterparty": cp, "relation": d["relation"], "exposure_pct": d.get("exposure_pct")} for cp, _, d in EXPOSURE_GRAPH.in_edges(iss, data=True)), key=lambda x: x["counterparty"])
    ccr_refs = {iss: [{"ccr_counterparty": c["id"], "product": c.get("product"), "kind": "reference_entity_id in the CCR master"} for c in STORE.ccr_counterparties if c.get("reference_entity_id") == iss] for iss in ends}
    for r in approved_reference_rows or []:
        if r["reference_entity_id"] in ends:
            ccr_refs[r["reference_entity_id"]].append({"ccr_counterparty": r["counterparty_id"], "product": r["product"], "kind": f"approved {r['link_kind'].lower()}"})
    linked = []
    for e in new:
        for end, role in ((e["source"], "source"), (e["target"], "target")):
            for h in holders[end]:
                linked.append({"counterparty": h["counterparty"], "holds": end, "role_in_new_relationship": role, "exposure_pct": h["exposure_pct"], "holding_kind": h["relation"],
                               "meaning": f"holds {end}, which the approved relationship connects to {e['target'] if role == 'source' else e['source']}; a documented link, not a measured exposure to that company"})
    gaps = []
    for e in new:
        for end in (e["source"], e["target"]):
            if not holders[end]:
                gaps.append(f"No portfolio counterparty in the holdings data holds {end}, so no holdings-based exposure to it can be traced through this relationship.")
            if not ccr_refs[end]:
                gaps.append(f"No CCR record references {end} as a trade reference entity, so no CCR exposure is linked to it.")
    gaps.append("No measured CCR exposure (PFE, RC, NSE, settlement) is attributed to any company named in an approved relationship; a link between companies is not an exposure amount.")
    gaps.append("Wrong-way risk is not assessed: no methodology is applied, and a documented relationship is not interpreted as wrong-way risk.")
    return {
        "new_edges": [{"source": e["source"], "relation": e["relation"], "target": e["target"], "first_documented": e["first_documented"], "evidence_documents": len(e["evidence"])} for e in new],
        "evidence_for_existing_edges": [{"source": e["source"], "relation": e["relation"], "target": e["target"], "evidence_documents": len(e["evidence"])} for e in edges if e not in new],
        "connectivity": {"canonical": mb, "with_approved": ma, "newly_connected_issuers": newly_connected,
                         "note": "Counts issuers connected by supply, licensing or ownership relationships (the relationships scoring uses). Relationships of other types (financing, guarantees, affiliation) are shown in the graph but do not enter this count."},
        "analytical_coverage": {"issuer_pairs_gaining_a_supply_or_ownership_component": [[e["source"], e["target"]] for e in scored], "count": len(scored),
                                "scoring_changed_by_approval": False,
                                "note": "Approving evidence changes no score and no weight. If a person later adopts an edge into the canonical dataset it must be given a criticality judgement (none is assumed here); only then would the pair's relationship-scoring component exist."},
        "linked_counterparties": {"portfolio_holdings": linked, "ccr_reference_entities": ccr_refs},
        "gaps": sorted(set(gaps)),
    }
