"""The relationship network behind the Today hero, the Counterparty map and the Network page: one typed graph over what the dataset really holds.

Nodes: counterparties (the 19 CCR records and the 18 holdings-only counterparties; they share no ids), issuers, and risk factors.
Channels (each edge carries exactly one, with a strength 0-1 or null, a confidence 0-1 or null, a direction, and its evidence):
  exposure    counterparty -> issuer (portfolio holdings, or a CCR record's reference entity) and counterparty -> risk factor (its risk-factor path)
  supply      issuer -> issuer, SUPPLIES / LICENSES_TO fact edges; confidence from the evidence tier (documented 0.9, reported news 0.6)
  shared      counterparty <-> counterparty, weighted Jaccard of holdings (computed, never stored as a fact)
  comovement  issuer <-> issuer, |signed correlation of daily returns| >= STATISTICAL_EDGE_MIN_ABS_CORRELATION (only the 14 priced issuers)
  hidden      risk factor -> risk factor along a record's transmission path (graph-inferred, not a documented link)
  ownership   Studio-approved corporate-structure relations only; the canonical data has none (GLEIF reports no parents for any tracked entity)
Nothing here is invented: a missing strength or confidence stays null. Cluster halos are Louvain communities of the shared-issuer projection.
"""
from __future__ import annotations

from collections import defaultdict, deque
from functools import lru_cache

import networkx as nx

from . import ccr_priority, market
from .config import CCR_PRIORITY_THRESHOLDS, STATISTICAL_EDGE_MIN_ABS_CORRELATION
from .data import STORE
from .graph_builder import risk_factor_label

CHANNELS = ("ownership", "exposure", "supply", "shared", "comovement", "hidden")
CONFIDENCE_BY_EVIDENCE = {"WELL_DOCUMENTED_PUBLIC": 0.9, "REPORTED_NEWS": 0.6}      # spec 4.9, evidence tier only (no recency / corroboration data exists)
SHARED_MIN_JACCARD = 0.10
EXPOSURE_FULL_PCT = 0.5          # exposure_pct at which an exposure edge's strength reaches 1 (the largest holding in the data)
LOUVAIN_SEED = 7
STUDIO_CHANNEL = {"PARENT_OF": "ownership", "SUBSIDIARY_OF": "ownership", "GUARANTEES": "ownership", "AFFILIATED_WITH": "ownership",
                  "SUPPLIES": "supply", "LICENSES_TO": "supply", "FINANCES": "exposure"}

cp_id = lambda i: f"cp:{i}"          # noqa: E731
is_id = lambda i: f"is:{i}"          # noqa: E731
rf_id = lambda c: f"rf:{c}"          # noqa: E731


def _node_cp_ccr(r: dict) -> dict:
    flags = (r.get("decision") or {}).get("control_flags") or {}
    util = r.get("utilisation_pct")
    return {
        "id": cp_id(r["id"]), "kind": "counterparty", "ref": r["id"], "label": r["name"], "tag": r["name"], "universe": "ccr", "holdings_only": False,
        "sector": None, "counterparty_type": r.get("counterparty_type"), "product": r.get("product"), "priority": r["priority"], "owner": r.get("coverage_owner"),
        "utilisation_pct": util, "pfe": (r.get("exposure") or {}).get("pfe_current"), "delta_pfe": r.get("delta_pfe"),
        "rating": r.get("rating"), "outlook": None, "ews": None,
        "flags": {"wwr": bool(flags.get("wwr")), "overdue": bool(r.get("is_overdue")), "near_limit": util is not None and util >= CCR_PRIORITY_THRESHOLDS["high_utilisation_pct"],
                  "negative_outlook": None, "watchlist": bool(r.get("watchlist"))},
        "provenance": "synthetic",
    }


@lru_cache(maxsize=1)
def build() -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add_edge(source, target, channel, *, strength=None, confidence=None, directed=True, relation=None, evidence=None, provenance="derived", studio=False):
        if source == target or source not in nodes or target not in nodes:
            return                                                  # no self-loops, no dangling ends
        a, b = (source, target) if directed else tuple(sorted((source, target)))
        edges.append({"id": f"{channel}:{a}>{b}" + (f":{relation}" if relation else ""), "source": a, "target": b, "channel": channel, "strength": strength, "confidence": confidence,
                      "directed": directed, "relation": relation, "evidence": evidence or {}, "provenance": provenance, "studio": studio})

    rows = ccr_priority.build_priority_queue()
    for r in rows:
        nodes[cp_id(r["id"])] = _node_cp_ccr(r)
    for e in STORE.entities_raw:
        if e["node_type"] == "Counterparty":
            nodes[cp_id(e["id"])] = {"id": cp_id(e["id"]), "kind": "counterparty", "ref": e["id"], "label": e["name"], "tag": e["name"], "universe": "portfolio", "holdings_only": True,
                                     "sector": e.get("industry"), "priority": None, "utilisation_pct": None, "rating": None, "outlook": None, "ews": None,
                                     "flags": {"wwr": False, "overdue": False, "near_limit": False, "negative_outlook": None, "watchlist": False}, "provenance": "synthetic"}
        elif e["node_type"] == "Company/Issuer":
            nodes[is_id(e["id"])] = {"id": is_id(e["id"]), "kind": "issuer", "ref": e["id"], "label": e["name"], "tag": e.get("ticker") or e["id"], "group": e.get("sector"), "sector": e.get("sector"),
                                     "has_market_data": bool(e.get("has_market_data")), "provenance": "real" if not e.get("is_synthetic") else "synthetic"}
    for r in rows:
        for code in r.get("risk_factor_path") or []:
            nodes.setdefault(rf_id(code), {"id": rf_id(code), "kind": "factor", "ref": code, "label": risk_factor_label(code), "tag": risk_factor_label(code), "provenance": "derived"})

    # exposure: portfolio holdings, CCR reference entities, CCR risk-factor paths
    for x in STORE.exposure_edges:
        add_edge(cp_id(x["counterparty"]), is_id(x["issuer"]), "exposure", strength=round(min(1.0, x["exposure_pct"] / EXPOSURE_FULL_PCT), 4), relation=x["relation"],
                 evidence={"exposure_pct": x["exposure_pct"], "relation": x["relation"], "synthetic": True}, provenance="synthetic")
    for r in rows:
        if r.get("reference_entity_id"):
            add_edge(cp_id(r["id"]), is_id(r["reference_entity_id"]), "exposure", relation="REFERENCE_ENTITY", evidence={"relation": "REFERENCE_ENTITY", "product": r.get("product"), "synthetic": True}, provenance="synthetic")
        path = r.get("risk_factor_path") or []
        for code in dict.fromkeys(path):
            add_edge(cp_id(r["id"]), rf_id(code), "exposure", relation="RISK_FACTOR", evidence={"relation": "RISK_FACTOR", "product": r.get("product"), "synthetic": True}, provenance="synthetic")
        for a, b in zip(path, path[1:]):
            add_edge(rf_id(a), rf_id(b), "hidden", relation="TRANSMISSION", evidence={"relation": "TRANSMISSION", "note": "next step of the record's risk-factor transmission path (inferred, not documented)"}, provenance="derived")
    # supply
    for f in STORE.fact_edges:
        if f["relation"] in ("SUPPLIES", "LICENSES_TO"):
            add_edge(is_id(f["source"]), is_id(f["target"]), "supply", strength=f.get("criticality"), confidence=CONFIDENCE_BY_EVIDENCE.get(f.get("evidence_status")), relation=f["relation"],
                     evidence={"relation": f["relation"], "note": f.get("note"), "evidence_status": f.get("evidence_status"), "evidence_url": f.get("evidence_url")}, provenance="real")
    # shared issuer (weighted Jaccard over portfolio holdings)
    held: dict[str, dict[str, float]] = defaultdict(dict)
    for x in STORE.exposure_edges:
        held[x["counterparty"]][x["issuer"]] = held[x["counterparty"]].get(x["issuer"], 0) + x["exposure_pct"]
    cps = sorted(held)
    for i, a in enumerate(cps):
        for b in cps[i + 1:]:
            both = set(held[a]) & set(held[b])
            if not both:
                continue
            union = set(held[a]) | set(held[b])
            j = sum(min(held[a].get(k, 0), held[b].get(k, 0)) for k in union) / sum(max(held[a].get(k, 0), held[b].get(k, 0)) for k in union)
            if j >= SHARED_MIN_JACCARD:
                top = sorted(both, key=lambda k: (-min(held[a][k], held[b][k]), k))[:3]
                add_edge(cp_id(a), cp_id(b), "shared", strength=round(j, 4), directed=False, relation="SHARED_ISSUER", evidence={"jaccard": round(j, 4), "shared_issuers": [{"id": k, "name": nodes[is_id(k)]["label"]} for k in top], "shared_count": len(both)}, provenance="derived")
    # co-movement (only issuers with prices)
    priced = sorted(e["id"] for e in STORE.entities_raw if e["node_type"] == "Company/Issuer" and e.get("has_market_data"))
    for i, a in enumerate(priced):
        for b in priced[i + 1:]:
            c = market.signed_correlation(a, b)
            if c and abs(c["full_sample_corr"]) >= STATISTICAL_EDGE_MIN_ABS_CORRELATION:
                add_edge(is_id(a), is_id(b), "comovement", strength=round(abs(c["full_sample_corr"]), 4), directed=False, relation="CO_MOVEMENT",
                         evidence={"signed_correlation": c["full_sample_corr"], "n_obs": c["n_obs"], "source": c["source"]}, provenance="derived")

    uniq = {}
    for e in edges:
        k = (e["channel"], e["source"], e["target"], e["relation"])
        if k not in uniq or (e["strength"] or 0) > (uniq[k]["strength"] or 0):
            uniq[k] = e                                              # merge parallel duplicates, keep the strongest
    return {"nodes": nodes, "edges": sorted(uniq.values(), key=lambda e: e["id"])}


def studio_edges(nodes: dict) -> tuple[list[dict], dict]:
    """Approved Data Studio relationships as edges (operator deployments only), plus the overlay status. Never part of the canonical graph."""
    from ..studio import overlay

    ov = overlay.approved(True)
    out = []
    for e in ov["edges"]:
        s, t = is_id(e["source"]), is_id(e["target"])
        if s in nodes and t in nodes:
            ev = e["evidence"]
            out.append({"id": f"studio:{s}>{t}:{e['relation']}", "source": s, "target": t, "channel": STUDIO_CHANNEL.get(e["relation"], "ownership"), "strength": None, "confidence": None, "directed": True,
                        "relation": e["relation"], "provenance": "ai", "studio": True, "evidence": {"relation": e["relation"], "studio_evidence": [{k: x[k] for k in ("source_url", "source_publisher", "source_published_date", "quotes", "source_sha256")} for x in ev]}})
    return out, {"requested": True, "available": ov["available"], "reason": ov["reason"], "release": ov["release"], "edges_added": len(out)}


def adjacency(edges: list[dict]) -> dict[str, list[dict]]:
    adj: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        adj[e["source"]].append(e); adj[e["target"]].append(e)
    return adj


def subgraph(seeds: list[str], hops: int, channels: set[str] | None = None, extra_edges: list[dict] | None = None, limit: int = 400) -> dict:
    g = build()
    edges = [e for e in g["edges"] + (extra_edges or []) if not channels or e["channel"] in channels]
    if not seeds:
        keep = set(g["nodes"])
    else:
        adj, seen, frontier = adjacency(edges), {s: 0 for s in seeds if s in g["nodes"]}, deque(s for s in seeds if s in g["nodes"])
        while frontier:
            u = frontier.popleft()
            if seen[u] >= hops:
                continue
            for e in adj[u]:
                v = e["target"] if e["source"] == u else e["source"]
                if v not in seen and len(seen) < limit:
                    seen[v] = seen[u] + 1; frontier.append(v)
        keep = set(seen)
    return {"nodes": [g["nodes"][i] for i in sorted(keep)], "edges": [e for e in edges if e["source"] in keep and e["target"] in keep]}


@lru_cache(maxsize=1)
def clusters() -> list[dict]:
    """Louvain communities of the shared-issuer projection (counterparties that look independent but hold the same issuers). Deterministic (fixed seed)."""
    g = build()
    h = nx.Graph()
    for e in g["edges"]:
        if e["channel"] == "shared":
            h.add_edge(e["source"], e["target"], weight=e["strength"])
    if h.number_of_edges() == 0:
        return []
    comms = [sorted(c) for c in nx.community.louvain_communities(h, weight="weight", seed=LOUVAIN_SEED) if len(c) >= 2]
    comms.sort(key=lambda c: (-len(c), c[0]))
    out = []
    for n, members in enumerate(comms, 1):
        weight_by_issuer: dict[str, float] = defaultdict(float)
        holders: dict[str, int] = defaultdict(int)
        for m in members:
            for x in STORE.exposure_edges:
                if cp_id(x["counterparty"]) == m:
                    weight_by_issuer[x["issuer"]] += x["exposure_pct"]; holders[x["issuer"]] += 1
        by_sector: dict[str, float] = defaultdict(float)
        for i, w in weight_by_issuer.items():
            by_sector[g["nodes"][is_id(i)].get("sector") or "Other"] += w
        sector = max(by_sector, key=lambda s: (by_sector[s], s)) if by_sector else "Mixed"
        shared = sorted((i for i, k in holders.items() if k >= 2), key=lambda i: (-weight_by_issuer[i], i))
        out.append({"id": f"cl:{n}", "name": f"{sector} holders", "members": members, "size": len(members), "dominant_channel": "shared",
                    "shared_issuers": [{"id": is_id(i), "name": g["nodes"][is_id(i)]["label"]} for i in shared[:5]], "provenance": "derived",
                    "method": f"Louvain communities (seed {LOUVAIN_SEED}) of the shared-issuer projection; named by the sector with the most weighted holdings"})
    return out
