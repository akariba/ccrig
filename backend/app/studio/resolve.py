"""Entity resolution against the CANONICAL entity master (read-only).

Ladder, first hit wins, never fuzzy:
  EXACT_ID        the value is a canonical id                                   -> RESOLVED
  NORMALIZED_ID   same after trimming and upper-casing, and unique              -> RESOLVED (mapping recorded)
  TICKER          equals exactly one entity's ticker (case-insensitive)         -> MAPPED   (reviewer must acknowledge)
  NAME_EXACT      equals exactly one entity's name (case/punctuation-folded)    -> MAPPED
  ALIAS           an approved brand alias (data/events/entity_aliases.json)     -> MAPPED
Everything else is explicit: AMBIGUOUS (several candidates listed), UNRESOLVED (with a reason), or a refusal for a value that belongs to a
different universe (CCR counterparty ids are never resolved as portfolio counterparties) or is a denied alias.
No similarity score, no suggestion is ever applied.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

from ..core.config import DATA_DIR

RESOLVED, MAPPED, AMBIGUOUS, UNRESOLVED = "RESOLVED", "MAPPED", "AMBIGUOUS", "UNRESOLVED"
_KIND_TYPES = {"entity": None, "issuer": ("Company/Issuer",), "portfolio_counterparty": ("Counterparty",)}


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(text).lower())).strip()


def _load(rel: str, default):
    try:
        with open(DATA_DIR / rel, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


@dataclass
class Resolution:
    value: str
    status: str
    entity_id: str | None = None
    rule: str | None = None
    reason: str = ""
    candidates: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"value": self.value, "status": self.status, "entity_id": self.entity_id, "rule": self.rule, "reason": self.reason, "candidates": self.candidates}


class EntityIndex:
    def __init__(self, entities: list, ccr_ids: set, aliases: dict):
        self.entities = {e["id"]: e for e in entities}
        self.ccr_ids = ccr_ids
        self.by_norm: dict = {}
        self.by_ticker: dict = {}
        self.by_name: dict = {}
        for e in entities:
            self.by_norm.setdefault(e["id"].strip().upper(), []).append(e["id"])
            if e.get("ticker"):
                self.by_ticker.setdefault(str(e["ticker"]).strip().upper(), []).append(e["id"])
            self.by_name.setdefault(_fold(e["name"]), []).append(e["id"])
        self.by_alias: dict = {}
        self.alias_reason: dict = {}
        for eid, names in (aliases.get("brand_aliases") or {}).items():
            if eid in self.entities:
                for n in names:
                    text, why = (n.get("alias"), n.get("reason", "")) if isinstance(n, dict) else (n, "")
                    self.by_alias.setdefault(_fold(text), []).append(eid)
                    self.alias_reason[(_fold(text), eid)] = why
        self.denied = {_fold(a) for a in (aliases.get("denied_aliases") or {})}

    def _allowed(self, eid: str, kind: str) -> bool:
        types = _KIND_TYPES.get(kind)
        return types is None or self.entities[eid].get("node_type") in types

    def resolve(self, value, kind: str = "entity") -> Resolution:
        raw = "" if value is None else str(value)
        v = raw.strip()
        if not v:
            return Resolution(raw, UNRESOLVED, rule="EMPTY", reason="empty identifier")
        if v in self.entities:
            if self._allowed(v, kind):
                return Resolution(raw, RESOLVED, v, "EXACT_ID")
            return Resolution(raw, UNRESOLVED, rule="WRONG_KIND", reason=f"'{v}' is a {self.entities[v].get('node_type')}, expected {kind.replace('_', ' ')}")
        if v in self.ccr_ids and kind == "portfolio_counterparty":
            return Resolution(raw, UNRESOLVED, rule="WRONG_UNIVERSE", reason=f"'{v}' belongs to the CCR counterparty dataset; it is a different universe from portfolio holdings and is never merged with it")
        hits = [i for i in self.by_norm.get(v.upper(), []) if self._allowed(i, kind)]
        if len(hits) == 1:
            return Resolution(raw, RESOLVED, hits[0], "NORMALIZED_ID", "matched after trimming and upper-casing")
        if len(hits) > 1:
            return Resolution(raw, AMBIGUOUS, rule="NORMALIZED_ID", reason="several entities share this normalised id", candidates=sorted(hits))
        for rule, table, key in (("TICKER", self.by_ticker, v.upper()), ("NAME_EXACT", self.by_name, _fold(v)), ("ALIAS", self.by_alias, _fold(v))):
            if rule == "ALIAS" and key in self.denied:
                return Resolution(raw, UNRESOLVED, rule="DENIED_ALIAS", reason=f"'{v}' is a deliberately denied alias (it names more than one distinct company)")
            hits = [i for i in table.get(key, []) if self._allowed(i, kind)]
            if len(hits) == 1:
                why = {"TICKER": "exact ticker", "NAME_EXACT": "exact entity name", "ALIAS": "approved brand alias"}[rule]
                if rule == "ALIAS" and self.alias_reason.get((key, hits[0])):
                    why += f": {self.alias_reason[(key, hits[0])]}"
                return Resolution(raw, MAPPED, hits[0], rule, why)
            if len(hits) > 1:
                return Resolution(raw, AMBIGUOUS, rule=rule, reason=f"{rule.lower().replace('_', ' ')} matches several entities", candidates=sorted(hits))
        return Resolution(raw, UNRESOLVED, rule="NO_MATCH", reason="no canonical entity matches this identifier")


@lru_cache(maxsize=1)
def canonical_index() -> EntityIndex:
    entities = (_load("entities.json", {}) or {}).get("entities", [])
    ccr = {c["id"] for c in (_load("ccr_counterparties.json", {}) or {}).get("counterparties", [])}
    return EntityIndex(entities, ccr, _load("events/entity_aliases.json", {}) or {})


def resolve_distinct(values, kind: str, index: EntityIndex | None = None) -> dict:
    """value -> Resolution for each distinct value (deterministic order)."""
    index = index or canonical_index()
    return {v: index.resolve(v, kind) for v in sorted({("" if x is None else str(x)) for x in values})}


def exact_coverage(values, index: EntityIndex | None = None) -> dict:
    """Identifier coverage for profiling: the share of distinct non-null values that are canonical ids EXACTLY (no mapping)."""
    index = index or canonical_index()
    distinct = {str(v).strip() for v in values if v not in (None, "")}
    hit = sum(1 for v in distinct if v in index.entities)
    return {"distinct": len(distinct), "exact_canonical": hit, "pct": round(100.0 * hit / len(distinct), 2) if distinct else None}
