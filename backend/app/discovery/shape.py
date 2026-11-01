"""Pure, dependency-light helpers shared by the discovery run and by the read-only map bridge (this module must import nothing heavy: the static
Pyodide build loads the bridge, and it has no network, sqlite or SSL)."""
from __future__ import annotations

import json

from ..core import event_register as reg

LIMITATIONS = [
    "Only the configured approved providers are searched. Coverage depends on them, and the absence of an event does not mean nothing happened.",
    "Hosts that are not on the approved list (for example company blogs and news sites) are never retrieved.",
    "Machine verification proves the retrieved source contains the quoted text, date, title and dateline. It is not independent corroboration and does not make a statement true.",
    "Documented relationships show structural connectivity in the platform's data. They do not show that an event affects the company, in which direction, or by how much; no impact magnitude is estimated.",
    "A location is shown only when the source itself prints one (a dateline, or the issuing country for a government notice). It is never assumed from a headquarters.",
]


def register_event(row: dict) -> dict:
    """A staged/approved row in the register's own shape, so the curated machinery (entities, places, graph paths) applies unchanged."""
    loc = dict(row["location"])
    return {
        "id": row["id"], "kind": row["kind"], "title": row["title"], "category": row["category"], "published_date": row["published_date"], "event_date": row["event_date"],
        "event_date_basis": row["event_date_basis"], "location": loc,
        "sources": [{"id": "s1", "publisher": row["source_publisher"], "url": row["source_url"], "title": row.get("source_title") or row["title"],
                     "published_date": row["source_published_date"], "tier": row["source_tier"], "approved_source_id": row["approved_source_id"], "retrieved_at": row["retrieved_at"]}],
        "evidence": [{"source_id": "s1", "quote": q} for q in row["evidence_quotes"]],
        "verification": {**row["verification"], "http_status": 200},
    }


def admissible(event: dict):
    """The register's own admissibility rules; an event whose place the source does not evidence is still admissible (it is simply not plotted)."""
    probe = json.loads(json.dumps(event))
    if not probe["location"].get("gazetteer_key"):
        probe["location"] = {"gazetteer_key": next(iter(reg.gazetteer())), "basis": probe["location"].get("basis") or "unmapped"}
    problems = reg.validate_event(probe)
    return (not problems), problems


