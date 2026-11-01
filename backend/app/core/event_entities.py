"""Entity resolution for event evidence: names in cited passages -> dataset issuers.

Precision over recall, because a wrong link would draw a false relationship on
the map. Every resolution carries the passage it came from, the matched text
and the rule that matched, so it can be audited.

Rules (data in data/events/entity_aliases.json):
* only the passages the register cites (title + evidence quotes) are searched -
  never a whole page;
* only real issuers are candidates (never the synthetic counterparties);
* a name must start with a capital letter in the text (so "oracle", "arm" the
  verb and "meta-analysis" do not match) and sit on word boundaries
  ("Unimicron" does not contain "Micron");
* bare exchange tickers resolve only as an uppercase token that is not part of
  a product name ("RTX Spark", "NVIDIA RTX" are products; "RTX Corporation" is
  the company);
* brand names resolve to the parent that owns them (Google Cloud -> Alphabet),
  stated with a reason, and ambiguous group names ('Samsung') are denied.
"""
import json
import re
from functools import lru_cache

from . import event_parser
from .data import STORE
from .event_register import EVENTS_DIR

_PRODUCT_NEIGHBOUR = re.compile(r"^\s+(?:[A-Z][A-Za-z0-9]*|\d)")
_CAP_WORD_BEFORE = re.compile(r"[A-Z][A-Za-z0-9]*\s+$")


@lru_cache(maxsize=1)
def _config() -> dict:
    return json.loads((EVENTS_DIR / "entity_aliases.json").read_text())


@lru_cache(maxsize=1)
def _matchers() -> list:
    """[(entity_id, alias, regex, kind)] longest alias first, so 'Samsung Electronics' wins over any shorter overlap."""
    cfg = _config()
    out = []
    for eid in STORE.issuer_ids:
        entity = STORE.entity(eid)
        ticker = (entity.get("ticker") or "").lower()
        for alias in event_parser._entity_aliases(entity):
            if alias in cfg["denied_aliases"]:
                continue
            kind = "TICKER" if alias == ticker else "NAME"
            out.append((eid, alias, re.compile(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", re.I), kind))
    for eid, items in cfg["brand_aliases"].items():
        for item in items:
            alias = item["alias"]
            out.append((eid, alias.lower(), re.compile(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])"), "BRAND"))
    out.sort(key=lambda m: (-len(m[1]), m[1], m[0]))
    return out


def _acceptable(kind: str, alias: str, text: str, start: int, end: int) -> bool:
    matched = text[start:end]
    if kind == "TICKER":
        if matched != matched.upper() or len(matched) < 2:
            return False                                   # a ticker must be written as one
    elif kind == "NAME" and not matched[0].isupper():
        return False                                       # proper noun, not a common word
    short = len(alias) <= 4
    if kind in ("TICKER", "NAME") and short:
        if _PRODUCT_NEIGHBOUR.match(text[end:]) or _CAP_WORD_BEFORE.search(text[:start]):
            return False                                   # "RTX Spark", "NVIDIA RTX": a product name
    rule = _config()["require_following"].get(alias)
    if rule and not re.match(rule["pattern"], text[end:]):
        return False
    return True


def resolve_text(text: str) -> list:
    """Mentions in one passage: [{entity_id, matched_text, alias, rule, start, end}] in order of appearance."""
    taken, found = [], []
    for eid, alias, regex, kind in _matchers():
        for m in regex.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue                                   # inside a longer, already-resolved name
            if not _acceptable(kind, alias, text, m.start(), m.end()):
                continue
            taken.append((m.start(), m.end()))
            found.append({"entity_id": eid, "matched_text": text[m.start():m.end()], "alias": alias,
                          "rule": {"NAME": "NAME_MATCH", "BRAND": "BRAND_ALIAS", "TICKER": "TICKER_TOKEN"}[kind],
                          "start": m.start(), "end": m.end()})
    return sorted(found, key=lambda x: x["start"])


def passages(event: dict) -> list:
    """The passages entity resolution is allowed to read: the title, then each cited quote."""
    return [{"ref": "title", "text": event["title"]}] + [
        {"ref": f"evidence[{i}]", "text": ev["quote"], "source_id": ev["source_id"]} for i, ev in enumerate(event["evidence"])]


def resolve_event(event: dict) -> list:
    """One record per resolved entity: [{entity_id, name, country, mentions:[{ref, matched_text, rule, quote}]}], by first appearance."""
    by_entity = {}
    for p in passages(event):
        for m in resolve_text(p["text"]):
            rec = by_entity.setdefault(m["entity_id"], {"entity_id": m["entity_id"], "mentions": []})
            rec["mentions"].append({"ref": p["ref"], "matched_text": m["matched_text"], "rule": m["rule"], "quote": p["text"]})
    out = []
    for eid, rec in by_entity.items():
        entity = STORE.entity(eid)
        out.append({**rec, "name": entity["name"], "country": entity.get("country"), "sector": entity.get("sector")})
    return out


def resolve_query(query: str) -> list:
    """Entities a user's search text refers to: [{entity_id, name, ticker, matched_text}] (issuers only)."""
    q = query.strip()
    if not q:
        return []
    seen, out = set(), []
    for eid in STORE.issuer_ids:
        e = STORE.entity(eid)
        names = {eid.lower(), (e.get("ticker") or "").lower(), e["name"].lower()} | set(event_parser._entity_aliases(e))
        if q.lower() in names or any(q.lower() == n for n in names):
            seen.add(eid)
            out.append({"entity_id": eid, "name": e["name"], "ticker": e.get("ticker"), "matched_text": q})
    if not out:                                            # whole-word name search, e.g. "nvidia corp"
        for m in resolve_text(q) or resolve_text(q.title()):
            if m["entity_id"] not in seen:
                seen.add(m["entity_id"])
                e = STORE.entity(m["entity_id"])
                out.append({"entity_id": m["entity_id"], "name": e["name"], "ticker": e.get("ticker"), "matched_text": m["matched_text"]})
    return out
