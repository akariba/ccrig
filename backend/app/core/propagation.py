"""Deterministic contagion over the relationship network (spec 4.1, DebtRank-style, kept deliberately simple).

Shocked nodes start at distress 1. At each hop a node that was first reached in the previous hop passes
    distress(next) = max over its reached neighbours of  distress(u) * channel_weight * confidence * strength * HOP_DECAY
Every node propagates once (the hop it is first reached), up to MAX_HOPS. Edges carry flow both ways (a failing issuer hurts its holders; a failing
counterparty hurts what it is linked to). A missing confidence counts as 1 (not penalised) and a missing strength as 0.5 (neutral).
The result is a PROPAGATION INDEX between 0 and 1: it ranks who is reached and how strongly. It is NOT a loss estimate and carries no currency.
Limit use: utilisation_after = utilisation * (1 + distress * UTILISATION_SENSITIVITY); the sensitivity is a synthetic, configurable constant.
"""
from __future__ import annotations

from . import network
from .config import CCR_PRIORITY_THRESHOLDS

CHANNEL_WEIGHTS = {"ownership": 1.0, "exposure": 0.8, "supply": 0.6, "shared": 0.5, "comovement": 0.3, "hidden": 0.2}
HOP_DECAY = 0.8
MAX_HOPS = 3
UTILISATION_SENSITIVITY = 0.5
LABEL = "Propagation index (0-1): a ranking of who is reached and how strongly. Not a loss estimate."


def edge_weight(e: dict, weights: dict[str, float] = CHANNEL_WEIGHTS) -> float:
    c = e["confidence"] if e["confidence"] is not None else 1.0
    s = e["strength"] if e["strength"] is not None else 0.5
    return weights.get(e["channel"], 0.0) * c * s


def propagate(edges: list[dict], shocked: list[str], max_hops: int = MAX_HOPS, decay: float = HOP_DECAY, weights: dict[str, float] = CHANNEL_WEIGHTS) -> dict[str, dict]:
    """-> {node_id: {"distress": float, "hop": int, "via": parent_id|None, "channel": str|None}} for every node reached (including the shocked ones)."""
    adj = network.adjacency(edges)
    reached = {s: {"distress": 1.0, "hop": 0, "via": None, "channel": None} for s in sorted(set(shocked))}
    frontier = sorted(reached)
    for hop in range(1, max_hops + 1):
        cand: dict[str, dict] = {}
        for u in frontier:
            for e in adj.get(u, []):
                v = e["target"] if e["source"] == u else e["source"]
                if v in reached:
                    continue
                d = reached[u]["distress"] * edge_weight(e, weights) * decay
                if d > 0 and (v not in cand or d > cand[v]["distress"] or (d == cand[v]["distress"] and u < cand[v]["via"])):
                    cand[v] = {"distress": d, "hop": hop, "via": u, "channel": e["channel"]}
        for v in sorted(cand):
            reached[v] = {**cand[v], "distress": round(cand[v]["distress"], 4)}
        frontier = sorted(cand)
        if not frontier:
            break
    return reached


def path_to(reached: dict[str, dict], node: str) -> list[str]:
    out = [node]
    while reached[out[-1]]["via"] is not None:
        out.append(reached[out[-1]]["via"])
    return out[::-1]


def run(shock_ids: list[str], max_hops: int = MAX_HOPS, as_label: str = "") -> dict:
    g = network.build()
    unknown = [s for s in shock_ids if s not in g["nodes"]]
    reached = propagate(g["edges"], [s for s in shock_ids if s in g["nodes"]], max_hops)
    out_nodes, crossing_85, crossing_100 = [], [], []
    for nid in sorted(reached, key=lambda n: (-reached[n]["distress"], reached[n]["hop"], n)):
        n, r = g["nodes"][nid], reached[nid]
        row = {"id": nid, "label": n["label"], "kind": n["kind"], "distress": r["distress"], "hop": r["hop"], "via": r["via"], "channel": r["channel"], "path": [g["nodes"][p]["label"] for p in path_to(reached, nid)]}
        util = n.get("utilisation_pct")
        if n["kind"] == "counterparty" and util is not None:
            after = round(util * (1 + r["distress"] * UTILISATION_SENSITIVITY), 1)
            row.update(utilisation_before=util, utilisation_after=after)
            if after >= 100 and util < 100:
                crossing_100.append(nid)
            elif after >= CCR_PRIORITY_THRESHOLDS["high_utilisation_pct"] and util < CCR_PRIORITY_THRESHOLDS["high_utilisation_pct"]:
                crossing_85.append(nid)
        out_nodes.append(row)
    shocked_labels = [g["nodes"][s]["label"] for s in shock_ids if s in g["nodes"]]
    return {"label": as_label or ", ".join(shocked_labels), "shocked": [s for s in shock_ids if s in g["nodes"]], "unknown": unknown, "max_hops": max_hops,
            "nodes": out_nodes, "names_reached": sum(1 for r in reached.values() if r["hop"] > 0), "hops_reached": max((r["hop"] for r in reached.values()), default=0),
            "counterparties_reached": sum(1 for n in out_nodes if n["kind"] == "counterparty" and n["hop"] > 0),
            "crossing_100": crossing_100, "crossing_85": crossing_85,
            "index_label": LABEL, "method": {"hop_decay": HOP_DECAY, "channel_weights": CHANNEL_WEIGHTS, "utilisation_sensitivity": UTILISATION_SENSITIVITY, "sensitivity_is": "synthetic, configurable"},
            "provenance": "derived"}


# Scenario presets: the CCR scenario labels (each shocks the first risk factor of its chain) plus two single-factor shocks that most records are exposed to.
def scenarios() -> list[dict]:
    from .data import STORE

    g = network.build()
    out = []
    for ev in STORE.ccr_events:
        if ev["id"] == "NONE" or not ev.get("risk_factor_path"):
            continue
        node = network.rf_id(ev["risk_factor_path"][0])
        if node in g["nodes"]:
            out.append({"id": ev["id"], "label": ev["label"], "description": ev.get("description"), "shock": [node], "kind": "scenario"})
    for code, label in (("INTEREST_RATE", "Interest-rate shock"), ("EQUITY", "Equity shock")):
        if network.rf_id(code) in g["nodes"]:
            out.append({"id": f"RF_{code}", "label": label, "description": f"Distress starts at the {code} risk factor.", "shock": [network.rf_id(code)], "kind": "risk_factor"})
    return out
