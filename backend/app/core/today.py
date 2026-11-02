"""Payloads for the Today command center, the Counterparty page and the health panels. Everything is computed from the dataset on request;
a figure the data cannot support is None with a reason, never a placeholder number. Results are cached per (as_of, watchlist)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from functools import lru_cache

import networkx as nx

from . import ccr_priority, event_discovery, network, propagation, reaches
from .config import AI_ENABLED, AI_MODEL, CCR_PRIORITY_THRESHOLDS
from .data import STORE

NEAR_LIMIT = CCR_PRIORITY_THRESHOLDS["high_utilisation_pct"]
PRIORITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFORMATIONAL": 4}
SOURCE_SLA_DAYS = {"prices": 3, "news": 14, "register": 30, "limits": 1, "gleif": 90}      # POC service levels, labelled as such in the response
LIMIT_APPLIES_TO = {"PFE_LIMIT": "pfe", "STRESS_LIMIT": "nse", "SETTLEMENT_LIMIT": "settlement"}      # a limit is only ever compared with the measure it is a limit on
NOT_AVAILABLE = {
    "rating": "No rating is recorded for any counterparty in this dataset.",
    "history": "Only a previous and a current snapshot exist; there is no exposure history to chart.",
    "ews": "The news early-warning score is not built yet.",
    "links_dated": "Relationships carry no creation date, so 'new this week' cannot be counted.",
}


def _rows(ids: list[str] | None = None) -> list[dict]:
    rows = ccr_priority.build_priority_queue()                      # already sorted: priority, then |delta PFE|
    return [r for r in rows if not ids or r["id"] in ids]


def default_watchlist(n: int = 10) -> list[str]:
    return [r["id"] for r in _rows()[:n]]


def _node_degree(nid: str) -> int:
    return sum(1 for e in network.build()["edges"] if nid in (e["source"], e["target"]))


@lru_cache(maxsize=1)
def pagerank_rank() -> dict[str, dict]:
    """Weighted PageRank over the whole network, ranked among counterparties (spec 4.2, simplified: one centrality, no blend)."""
    g = network.build()
    h = nx.Graph()
    h.add_nodes_from(g["nodes"])
    for e in g["edges"]:
        h.add_edge(e["source"], e["target"], weight=propagation.edge_weight(e) or 0.01)
    pr = nx.pagerank(h, weight="weight", alpha=0.85, max_iter=200)
    cps = sorted((n for n in g["nodes"] if n.startswith("cp:")), key=lambda n: (-pr[n], n))
    return {n: {"rank": i + 1, "of": len(cps), "score": round(pr[n], 5)} for i, n in enumerate(cps)}


def _kpis(rows: list[dict]) -> list[dict]:
    count = lambda f: sum(1 for r in rows if f(r))     # noqa: E731
    k = lambda id, label, value, note=None, **kw: {"id": id, "label": label, "value": value, "spark": None, "delta": None, "note": note, "provenance": "synthetic", **kw}   # noqa: E731
    return [k("critical", "Critical", count(lambda r: r["priority"] == "CRITICAL"), severity="crit"),
            k("high", "High", count(lambda r: r["priority"] == "HIGH"), severity="high"),
            k("overdue", "Overdue breaches", count(lambda r: r["is_overdue"]), severity="crit"),
            k("near_limit", "Limits at or above 85%", count(lambda r: r["utilisation_pct"] is not None and r["utilisation_pct"] >= NEAR_LIMIT), severity="high"),
            k("wwr", "Wrong-way-risk flags", count(lambda r: r["decision"]["control_flags"].get("wwr")), severity="med"),
            k("new_links", "New links in 7 days", None, NOT_AVAILABLE["links_dated"], provenance="derived")]


def _heatmap(rows: list[dict], hero: dict | None) -> dict:
    g = network.build()
    scens = propagation.scenarios()
    cols = [{"id": s["id"], "label": s["label"], "shock": s["shock"]} for s in scens]
    if hero:
        cols.append({"id": f"DEFAULT:{hero['id']}", "label": f"{hero['name']} defaults", "shock": [network.cp_id(hero["id"])]})
    results = [propagation.propagate(g["edges"], c["shock"]) for c in cols]
    return {"scenarios": [{"id": c["id"], "label": c["label"]} for c in cols],
            "rows": [{"id": r["id"], "name": r["name"], "values": [round(res.get(network.cp_id(r["id"]), {"distress": 0.0})["distress"], 3) for res in results]} for r in rows],
            "index_label": propagation.LABEL, "provenance": "derived"}


def _concentration() -> dict:
    by_cp: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for x in STORE.exposure_edges:
        by_cp[x["counterparty"]][(STORE.entity(x["issuer"]) or {}).get("sector") or "Other"] += x["exposure_pct"]
    totals: dict[str, float] = defaultdict(float)
    for cp in by_cp.values():
        for s, v in cp.items():
            totals[s] += v
    sectors = sorted(totals, key=lambda s: (-totals[s], s))
    cps = sorted(by_cp, key=lambda c: (-sum(by_cp[c].values()), c))[:10]
    return {"sectors": sectors, "unit": "% of the counterparty's holdings", "universe": "holdings-only counterparties (the CCR records carry no holdings)",
            "rows": [{"id": c, "name": STORE.entity(c)["name"], "values": [round(100 * by_cp[c].get(s, 0), 1) for s in sectors]} for c in cps], "provenance": "synthetic"}


def _event_row(ev: dict, kind: str) -> dict:
    ids = [e["entity_id"] for e in ev.get("entities", [])]
    return {"id": ev["id"], "title": ev["title"], "date": ev["published_date"], "category": ev.get("category"), "badge": "Verified" if kind == "register" else None, "source": ev["sources"][0]["publisher"] if ev.get("sources") else None,
            "severity": None, "reaches": reaches.reaches_for(ids)}


def market_events(as_of: date, limit: int = 8) -> list[dict]:
    out = []
    issuer = reaches.primary_issuer()
    if issuer:
        for ev in event_discovery.discover(issuer, limit=event_discovery.MAX_LIMIT, recency_days=730, as_of=as_of)["events"]:
            out.append(_event_row(ev, "register"))
    for d in STORE.news_all:
        if d["date"] <= as_of.isoformat():
            out.append({"id": d["id"], "title": d["title"], "date": d["date"], "category": "News", "badge": "Sample" if d.get("is_synthetic") else "Reported", "source": d.get("source"),
                        "severity": None, "reaches": reaches.reaches_for([i for i in d.get("entities", []) if network.is_id(i) in network.build()["nodes"]])})
    out.sort(key=lambda e: (e["date"], e["id"]), reverse=True)
    return out[:limit]


def map_entity(watchlist: list[str]) -> dict:
    """The issuer for the embedded world map: the watchlist's most-exposed issuer that has register events, else the register's own issuer."""
    g = network.build()
    score: dict[str, float] = defaultdict(float)
    for e in g["edges"]:
        if e["channel"] == "exposure" and e["target"].startswith("is:") and e["source"][3:] in watchlist:
            score[e["target"][3:]] += e["strength"] or 0.5
    for issuer in sorted(score, key=lambda i: (-score[i], i)):
        if event_discovery.discover(issuer, limit=1, recency_days=730)["events"]:
            return {"entity_id": issuer, "name": STORE.entity(issuer)["name"], "basis": "the watchlist's most-exposed issuer with register events"}
    p = reaches.primary_issuer()
    return {"entity_id": p, "name": STORE.entity(p)["name"] if p else None, "basis": "the issuer the approved-source register covers"}


def _top_exposures(rows: list[dict]) -> list[dict]:
    ranked = sorted(rows, key=lambda r: (r["utilisation_pct"] is None, -(r["utilisation_pct"] or 0), r["id"]))[:8]
    return [{"id": r["id"], "name": r["name"], "priority": r["priority"], "utilisation_pct": r["utilisation_pct"], "pfe": r["exposure"].get("pfe_current"), "delta_pfe": r["delta_pfe"], "rating": r["rating"], "outlook": None,
             "limit_type": (r.get("limit") or {}).get("limit_type"), "wwr": bool(r["decision"]["control_flags"].get("wwr")), "overdue": bool(r["is_overdue"])} for r in ranked]


def _hero_candidate(rows: list[dict]) -> dict | None:
    """The most severe watched counterparty that has at least one recorded link (a default with no links propagates nowhere)."""
    g = network.build()
    linked = {n for e in g["edges"] for n in (e["source"], e["target"])}
    ordered = sorted(rows, key=lambda r: (PRIORITY_RANK[r["priority"]], -(r["utilisation_pct"] or 0), r["id"]))
    for r in ordered:
        if network.cp_id(r["id"]) in linked:
            return {"id": r["id"], "name": r["name"], "priority": r["priority"]}
    return None


def _summary(rows: list[dict], hero: dict | None, top: dict | None) -> tuple[str, str]:
    crit = [r for r in rows if r["priority"] == "CRITICAL"]
    high = [r for r in rows if r["priority"] == "HIGH"]
    head = f"{len(crit)} critical and {len(high)} high-priority counterparties across {len(rows)} watched."
    parts = []
    if top:
        why = [f"utilisation {top['utilisation_pct']}% of its limit"] if top["utilisation_pct"] is not None else []
        if top["overdue"]: why.append("an overdue breach")
        parts.append(f"{top['name']} is {top['priority'].lower()}" + (f": {', '.join(why)}." if why else "."))
        if top["id"] != (hero or {}).get("id") and hero is not None:
            parts.append(f"It has no recorded relationships, so a default there cannot propagate; the most severe linked name is {hero['name']}.")
    wwr = sum(1 for r in rows if r["decision"]["control_flags"].get("wwr"))
    if wwr:
        parts.append(f"{wwr} watched counterparties carry wrong-way-risk flags.")
    cl = network.clusters()
    if cl:
        parts.append(f"The largest group of counterparties holding the same issuers is '{cl[0]['name']}' ({cl[0]['size']} names).")
    return head, " ".join(parts[:3])


@lru_cache(maxsize=32)
def _today(as_of: str, watchlist: tuple) -> dict:
    ids = list(watchlist) or default_watchlist()
    rows = _rows(ids)
    top = _top_exposures(rows)
    top_row = min(top, key=lambda t: (PRIORITY_RANK[t["priority"]], -(t["utilisation_pct"] or 0), t["id"])) if top else None
    hero = _hero_candidate(rows)
    head, summary = _summary(rows, hero, top_row)
    return {"as_of": as_of, "data_as_of": max((r["limit"].get("as_of_date") or "" for r in rows), default=None) or None, "history_note": NOT_AVAILABLE["history"],
            "scope": {"watchlist": [r["id"] for r in rows], "count": len(rows), "line": f"{len(rows)} watched counterparties · synthetic exposure data"},
            "headline": head, "summary": summary, "summary_kind": "template", "kpis": _kpis(rows), "simulate": hero, "top_critical": {"id": top_row["id"], "name": top_row["name"]} if top_row else None,
            "top_exposures": top, "stress_heatmap": _heatmap(rows, hero), "market_events": market_events(date.fromisoformat(as_of)), "concentration": _concentration(),
            "ratings": {"available": False, "reason": NOT_AVAILABLE["rating"],
                        "flags": {"wwr": sum(1 for r in rows if r["decision"]["control_flags"].get("wwr")), "overdue": sum(1 for r in rows if r["is_overdue"]), "near_limit": sum(1 for r in rows if (r["utilisation_pct"] or 0) >= NEAR_LIMIT),
                                  "watchlist": sum(1 for r in rows if r["watchlist"]), "negative_outlook": None}},
            "map_entity": map_entity([r["id"] for r in rows]), "clusters": network.clusters()}


def today(as_of: str, watchlist: list[str]) -> dict:
    return _today(as_of, tuple(watchlist))


# ------------------------------------------------------------------ the counterparty page
def cp_page(raw_id: str) -> dict | None:
    g = network.build()
    nid = network.cp_id(raw_id)
    node = g["nodes"].get(nid)
    if not node:
        return None
    row = next((r for r in _rows() if r["id"] == raw_id), None)
    rank = pagerank_rank().get(nid)
    incident = [e for e in g["edges"] if nid in (e["source"], e["target"])]
    links = []
    for e in incident:
        other = e["target"] if e["source"] == nid else e["source"]
        links.append({"edge_id": e["id"], "node_id": other, "name": g["nodes"][other]["label"], "kind": g["nodes"][other]["kind"], "channel": e["channel"], "strength": e["strength"], "confidence": e["confidence"], "directed": e["directed"],
                      "direction": None if not e["directed"] else ("out" if e["source"] == nid else "in"), "relation": e["relation"], "evidence": e["evidence"]})
    links.sort(key=lambda l: (-(l["strength"] or 0), l["name"]))
    mix: dict[str, float] = defaultdict(float)
    for l in links:
        mix[l["channel"]] += l["strength"] if l["strength"] is not None else 0.5
    total = sum(mix.values()) or 1
    res = {"id": raw_id, "node_id": nid, "name": node["label"], "universe": node["universe"], "holdings_only": node["holdings_only"],
           "systemic_rank": rank, "channel_mix": {c: round(v / total, 4) for c, v in sorted(mix.items())}, "links": links, "not_available": {k: v for k, v in NOT_AVAILABLE.items() if k != "links_dated"}}
    sc = []
    for s in propagation.scenarios():
        r = propagation.propagate(g["edges"], s["shock"]).get(nid)
        sc.append({"id": s["id"], "label": s["label"], "distress": round(r["distress"], 3) if r else 0.0, "hop": r["hop"] if r else None})
    res["stress"] = {"scenarios": sc, "index_label": propagation.LABEL, "provenance": "derived"}
    ev = []
    for e in market_events(date.today(), limit=40):
        hit = next((r for r in e["reaches"] if r["id"] == raw_id), None)
        if hit:
            ev.append({**e, "link": "direct" if hit["hops"] == 0 else "via a linked name", "via": hit["via"]})
    res["events"] = ev
    res["events_entity"] = reaches.primary_issuer()
    if row:
        d = row["decision"]
        res["header"] = {"priority": row["priority"], "counterparty_type": row["counterparty_type"], "legal_entity": row["legal_entity"], "product": row["product"], "rating": row["rating"], "outlook": None, "owner": row["coverage_owner"],
                         "flags": {"wwr": bool(d["control_flags"].get("wwr")), "overdue": bool(row["is_overdue"]), "near_limit": (row["utilisation_pct"] or 0) >= NEAR_LIMIT, "watchlist": bool(row["watchlist"])}}
        res["kpis"] = {"pfe": row["exposure"].get("pfe_current"), "delta_pfe": row["delta_pfe"], "utilisation_pct": row["utilisation_pct"], "limit_type": (row["limit"] or {}).get("limit_type"), "limit_value": (row["limit"] or {}).get("limit_value"),
                       "headroom": row["headroom"], "rating": row["rating"], "ews": None, "decision": d["decision"], "driver": row["driver"]}
        ex = row["exposure"]
        res["exposure_series"] = {"points": [{"label": "Previous", "pfe": ex.get("pfe_previous"), "nse": ex.get("nse_previous"), "rc": ex.get("rc_previous")}, {"label": "Current", "pfe": ex.get("pfe_current"), "nse": ex.get("nse_current"), "rc": ex.get("rc_current")}],
                                  "limit": {"type": (row["limit"] or {}).get("limit_type"), "value": (row["limit"] or {}).get("limit_value"), "applies_to": LIMIT_APPLIES_TO.get((row["limit"] or {}).get("limit_type"))}, "breach": row.get("breach") if row["is_breach"] else None,
                                  "unit": "$mm", "note": NOT_AVAILABLE["history"], "provenance": "synthetic"}
        res["decision"] = {"decision": d["decision"], "reasons": d["decision_reasons"], "missing_information": d["missing_information"], "suggested_action": row.get("suggested_action")}
    else:
        res["header"] = {"priority": None, "counterparty_type": None, "legal_entity": None, "product": None, "rating": None, "outlook": None, "owner": None, "flags": node["flags"], "sector": node.get("sector")}
        res["kpis"] = None
        res["exposure_series"] = None
        res["decision"] = None
        held = [{"issuer": l["name"], "exposure_pct": l["evidence"].get("exposure_pct"), "relation": l["relation"]} for l in links if l["channel"] == "exposure" and l["kind"] == "issuer"]
        res["holdings"] = held
    return res


# ------------------------------------------------------------------ health panels
def source_freshness(as_of: date) -> dict:
    from . import market

    price_last = max((str(rows[-1][0]) for rows in STORE.prices.values() if rows), default=None)
    limits = max((r["limit"].get("as_of_date") or "" for r in _rows()), default="") or None
    gleif = None
    try:
        from .ownership import load_gleif_level2_cache

        gleif = max((v.get("retrieved_at", "")[:10] for v in load_gleif_level2_cache().values() if isinstance(v, dict)), default=None) or None
    except Exception:       # noqa: BLE001 - freshness must never break the page
        gleif = None
    from . import event_register as reg

    items = [("prices", "Daily prices (public CSV)", price_last, "real"), ("news", "News corpus", max((d["date"] for d in STORE.news_all), default=None), "mixed"),
             ("register", "Approved-source event register", reg.load_register()["register"]["built_at"], "real"), ("limits", "CCR limits and exposure snapshot", limits, "synthetic"), ("gleif", "GLEIF legal-entity records", gleif, "real")]
    out = []
    for key, label, d, prov in items:
        age = (as_of - date.fromisoformat(str(d)[:10])).days if d else None
        sla = SOURCE_SLA_DAYS[key]
        out.append({"id": key, "label": label, "last_data": str(d)[:10] if d else None, "age_days": age, "sla_days": sla, "status": "unknown" if age is None else "stale" if age > sla else "ok", "provenance": prov})
    _ = market
    return {"as_of": as_of.isoformat(), "sla_note": "Service levels are proof-of-concept constants, not agreed targets.", "sources": out, "stale": sum(1 for s in out if s["status"] == "stale")}


def model_connections() -> dict:
    return {"providers": [{"id": "deterministic", "label": "Deterministic rules", "kind": "deterministic", "status": "active", "model": None, "note": "Always on; no network."},
                          {"id": "openai-compatible", "label": "OpenAI-compatible model", "kind": "model", "status": "connected" if AI_ENABLED else "not configured", "model": AI_MODEL if AI_ENABLED else None,
                           "note": "Rewrites explanations and summaries; never scores anything." if AI_ENABLED else "Set AI_BASE_URL, AI_API_KEY and AI_MODEL to connect one."}],
            "usage": {"available": False, "reason": "There is no assistant audit log yet, so token use, p95 latency and error rate are not recorded."}}
