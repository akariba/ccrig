"""Step 1-2 of discovery: resolve what the user typed to ONE canonical issuer (or say why not), then collect the names, aliases and identifiers used to search."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..core import event_entities
from ..core.config import DATA_DIR
from ..core.data import STORE
from ..studio.resolve import AMBIGUOUS, MAPPED, RESOLVED, UNRESOLVED, EntityIndex, canonical_index

_LEGAL = re.compile(r"[\s,]+(corporation|corp\.?|incorporated|inc\.?|plc|ltd\.?|limited|co\.?|company|n\.v\.?|ag|s\.a\.?|aktiengesellschaft|lp|llc)\.?$", re.I)
_PAREN = re.compile(r"\(([^)]{2,20})\)")


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def core_name(name: str) -> str:
    """'NVIDIA Corporation' -> 'NVIDIA'; 'Taiwan Semiconductor Manufacturing Co (TSMC)' -> 'Taiwan Semiconductor Manufacturing'."""
    n = _PAREN.sub("", name).strip()
    for _ in range(2):
        n = _LEGAL.sub("", n).strip(" ,&")
    return n


@dataclass
class Resolution:
    status: str                                   # RESOLVED | AMBIGUOUS | UNRESOLVED
    query: str
    entity_id: str | None = None
    rule: str | None = None
    reason: str = ""
    candidates: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"status": self.status, "query": self.query, "entity_id": self.entity_id, "rule": self.rule, "reason": self.reason, "candidates": self.candidates}


def resolve_entity(text: str, index: EntityIndex | None = None) -> Resolution:
    """Exact-first, never fuzzy: canonical id / ticker / name / approved alias, then the entity's core name (legal suffix removed), then the platform's search names."""
    index = index or canonical_index()
    q = (text or "").strip()
    if not q:
        return Resolution(UNRESOLVED, q, rule="EMPTY", reason="type a company name or ticker")
    r = index.resolve(q, "issuer")
    if r.status in (RESOLVED, MAPPED):
        return Resolution(RESOLVED, q, r.entity_id, r.rule, r.reason)
    if r.status == AMBIGUOUS:
        return Resolution(AMBIGUOUS, q, rule=r.rule, reason=r.reason, candidates=r.candidates)
    if r.rule == "DENIED_ALIAS":
        return Resolution(UNRESOLVED, q, rule=r.rule, reason=r.reason)
    hits = sorted({eid for eid, e in index.entities.items() if e.get("node_type") == "Company/Issuer" and _fold(core_name(e["name"])) == _fold(q)})
    if len(hits) == 1:
        return Resolution(RESOLVED, q, hits[0], "CORE_NAME", "matches the company's name without its legal suffix")
    if len(hits) > 1:
        return Resolution(AMBIGUOUS, q, rule="CORE_NAME", reason="several companies share this name", candidates=hits)
    found = sorted({m["entity_id"] for m in event_entities.resolve_query(q)})
    if len(found) == 1:
        return Resolution(RESOLVED, q, found[0], "SEARCH_NAME", "matches the platform's search names for this company")
    if len(found) > 1:
        return Resolution(AMBIGUOUS, q, rule="SEARCH_NAME", reason="several companies match", candidates=found)
    return Resolution(UNRESOLVED, q, rule="NO_MATCH", reason="not in the approved canonical universe; the Studio will not search for a company it cannot identify")


@dataclass
class EntityQuery:
    entity_id: str
    name: str
    ticker: str | None
    country: str | None
    terms: list                                    # strings used to search sources and to prefilter results
    aliases: list                                  # [{alias, reason}] approved brand aliases
    identifiers: dict

    def as_dict(self) -> dict:
        return {"entity_id": self.entity_id, "name": self.name, "ticker": self.ticker, "country": self.country, "terms": self.terms, "aliases": self.aliases, "identifiers": self.identifiers}


def build_query(entity_id: str) -> EntityQuery:
    e = STORE.entity(entity_id)
    aliases_cfg = json.loads((DATA_DIR / "events" / "entity_aliases.json").read_text())
    aliases = [a for a in aliases_cfg.get("brand_aliases", {}).get(entity_id, [])]
    terms = []
    for t in [core_name(e["name"]), *_PAREN.findall(e["name"]), *(a["alias"] for a in aliases)]:
        t = t.strip()
        if len(t) >= 4 and t.lower() not in {x.lower() for x in terms}:
            terms.append(t)
    return EntityQuery(entity_id, e["name"], e.get("ticker"), e.get("country"), terms, aliases,
                       {"entity_id": entity_id, "ticker": e.get("ticker"), "note": "tickers identify the company but are not used as search terms (too ambiguous)"})
