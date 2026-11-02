"""Which counterparties does an event reach? Counterparties with exposure (or a CCR reference entity) on a company the event names, and,
one step further, on a company those companies supply or license. Read from the relationship network; nothing is estimated."""
from __future__ import annotations

from functools import lru_cache

from . import network
from .data import STORE


def reaches_for(entity_ids: list[str], limit: int = 8) -> list[dict]:
    g = network.build()
    best: dict[str, dict] = {}
    issuers = [network.is_id(i) for i in dict.fromkeys(entity_ids) if network.is_id(i) in g["nodes"]]
    adj = network.adjacency(g["edges"])

    def holders(issuer: str):
        for e in adj.get(issuer, []):
            if e["channel"] == "exposure":
                other = e["source"] if e["target"] == issuer else e["target"]
                if other.startswith("cp:"):
                    yield other, e

    def consider(cp: str, e: dict, via: str, hops: int):
        row = {"id": g["nodes"][cp]["ref"], "node_id": cp, "name": g["nodes"][cp]["label"], "via": g["nodes"][via]["label"], "hops": hops, "channel": "exposure" if hops == 0 else "supply",
               "strength": e["strength"], "universe": g["nodes"][cp]["universe"]}
        old = best.get(cp)
        if old is None or (row["hops"], -(row["strength"] or 0)) < (old["hops"], -(old["strength"] or 0)):
            best[cp] = row

    for issuer in issuers:
        for cp, e in holders(issuer):
            consider(cp, e, issuer, 0)
    for issuer in issuers:                                   # one step through a documented supply / licence relationship
        for e in adj.get(issuer, []):
            if e["channel"] == "supply":
                other = e["target"] if e["source"] == issuer else e["source"]
                for cp, ex in holders(other):
                    if cp not in best:
                        consider(cp, ex, other, 1)
    return sorted(best.values(), key=lambda r: (r["hops"], -(r["strength"] or 0), r["name"]))[:limit]


@lru_cache(maxsize=1)
def primary_issuer() -> str | None:
    """The issuer the approved-source register is about: the one named by the most of its events (ties by id)."""
    from . import event_discovery

    best = None
    for i in sorted(STORE.issuer_ids):
        n = len(event_discovery.discover(i, limit=event_discovery.MAX_LIMIT, recency_days=730)["events"])
        if n and (best is None or n > best[0]):
            best = (n, i)
    return best[1] if best else None
