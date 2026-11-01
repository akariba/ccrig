"""Geographic mapping for events: where an event is, which regions its evidence names, where an entity sits.

Three different things are never conflated:
* the EVENT LOCATION: the place the source itself gives (a press-release
  dateline, or the issuing agency's country) with the basis quoted;
* REGIONS MENTIONED: countries named in the cited passages (a facility,
  a market) - reported with the passage, never inferred;
* ENTITY POSITION: the entity's headquarters country (dataset field).
Every coordinate is an approximate display position (see data/events/gazetteer.json)
and every position says whether it is a city point or a country centroid.
"""
import re

from .data import STORE
from .event_register import gazetteer

PRECISION = {"city": "approximate city point", "country": "country centroid"}


def _place(key: str):
    p = gazetteer().get(key)
    if not p:
        return None
    return {"key": key, "label": p["label"], "kind": p["kind"], "lat": p["lat"], "lon": p["lon"],
            "country": p.get("country"), "precision": PRECISION[p["kind"]]}


def event_location(event: dict) -> dict:
    """The event's own place, with its stated basis; `mapped` is False (and nothing is plotted) if it cannot be placed."""
    loc = event.get("location") or {}
    place = _place(loc.get("gazetteer_key", ""))
    if not place:
        return {"mapped": False, "reason": loc.get("unmapped_reason") or f"place '{loc.get('gazetteer_key')}' is not in the gazetteer", "basis": loc.get("basis")}
    return {"mapped": True, **place, "basis": loc["basis"], "basis_text": loc.get("basis_text")}



def _country_aliases() -> list:
    """[(alias, key)] for countries, longest first ('South Korea' before 'Korea')."""
    pairs = [(a, key) for key, p in gazetteer().items() if p["kind"] == "country" for a in p.get("aliases", [])]
    return sorted(pairs, key=lambda t: (-len(t[0]), t[0]))


def regions_mentioned(event: dict) -> list:
    """Countries named in the cited passages, each with the passage it came from.
    Matching is case-sensitive on word boundaries, longest name first."""
    out, seen = [], set()
    for i, ev in enumerate(event["evidence"]):
        text, taken = ev["quote"], []
        for alias, key in _country_aliases():
            pattern = r"(?<![A-Za-z])" + re.escape(alias) + r"(?![A-Za-z])"
            for m in re.finditer(pattern, text):
                if any(m.start() < e and s < m.end() for s, e in taken):
                    continue
                taken.append((m.start(), m.end()))
                if key in seen:
                    continue
                seen.add(key)
                place = _place(key)
                out.append({**place, "matched_text": m.group(0), "ref": f"evidence[{i}]", "quote": text})
    return out


def entity_position(entity_id: str):
    """Headquarters-country centroid of a dataset issuer; None if its country is not in the gazetteer."""
    entity = STORE.entity(entity_id)
    if not entity:
        return None
    for key, p in gazetteer().items():
        if p["kind"] == "country" and p.get("country") == entity.get("country"):
            return {**_place(key), "basis": f"headquarters country of {entity['name']} (dataset field 'country')"}
    return None
