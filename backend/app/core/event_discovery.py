"""Event discovery for a target entity: which approved-source events concern it, and how they connect to it.

This does NOT search the open web at request time. It selects from the approved-source
register (app/core/event_register.py), whose records were retrieved from approved sources
and verified by retrieval. That is what lets the same code run in FastAPI and in the
in-browser (Pyodide) build, and it makes every result reproducible: the same request
always returns the same events.

Selection rules, all reported back to the caller:
  1. admissible   - the record passes the register's policy (approved source, verified, real);
  2. recent       - published within `recency_days` before `as_of` (and not after it);
  3. relevant     - the target entity is named in the cited evidence (title or quote);
  4. ranked       - newest first, then DIRECT_SUBJECT (named in the title) before MENTIONED_IN_EVIDENCE;
  5. at most `limit` (<= 5) are returned. If fewer qualify, fewer are returned, with the reason.
Everything not returned is listed with the reason it was not.
"""
from datetime import date, timedelta

from . import event_entities, event_geo, event_graph, event_register as reg
from .data import STORE

MAX_LIMIT = 5
DEFAULT_RECENCY_DAYS = 180

GLOBAL_LIMITATIONS = [
    "Events are the verified publications in the approved-source register; the service does not search the live web, so an event "
    "that is not in the register cannot appear. The register covers NVIDIA only (pilot).",
    "Documented relationships show structural connectivity between entities. They do not show that an event affects NVIDIA, "
    "in which direction, or by how much; no impact magnitude is estimated.",
    "Map positions are approximate display points (city points and country centroids), not event epicentres or facility locations.",
]
FORWARD_LOOKING = ("plans", "planned", "expected", "expects", "targeting", "aims", "will ", "to build", "ramping")


def as_of_default() -> date:
    return date.fromisoformat(reg.load_register()["register"]["built_at"])


def _event_limitations(event: dict, relationships: dict, regions: list, location: dict) -> list:
    out = []
    for src in event["sources"]:
        policy = reg.source_policy(src["url"])
        out.append(f"Source ({src['publisher']}, {policy['tier'].replace('_', ' ').lower()}): {policy['limits']}")
    entities = relationships["entities"]
    unlinked = [e["name"] for e in entities if e["relationship_to_target"] == "NO_DOCUMENTED_PATH"]
    if unlinked:
        out.append("Named in the evidence with no documented relationship to the target in the platform's data: " + ", ".join(unlinked)
                   + ". That is a gap in the data, not evidence that no relationship exists.")
    if any(e["relationship_to_target"] == "DOCUMENTED_INDIRECT" for e in entities):
        out.append("An indirect path runs through documented relationships between other companies; the event does not state that "
                   "those relationships were involved.")
    if any(e["relationship_to_target"] in ("DOCUMENTED_DIRECT", "DOCUMENTED_INDIRECT") for e in entities):
        out.append("A documented relationship is not necessarily the relationship the event describes (see the evidence passages). "
                   "Its criticality is a curated judgement stored in the dataset, not a measured exposure.")
    if regions:
        out.append("Regions are countries named in the cited text (e.g. where a facility is planned); no facility-level location or "
                   "exposure is established.")
    if location.get("precision") == "country centroid":
        out.append("The source gives no city for this event; it is shown at a country centroid.")
    if any(any(w in ev["quote"] for w in FORWARD_LOOKING) for ev in event["evidence"]):
        out.append("The source contains forward-looking statements (plans, expectations, targets); these are not outcomes.")
    return out


def _passes_policy(event: dict):
    problems = reg.validate_event(event)
    return (not problems), problems


def _days_before(as_of: date, published: str) -> int:
    return (as_of - date.fromisoformat(published)).days


def discover(entity_id: str, *, limit: int = MAX_LIMIT, recency_days: int = DEFAULT_RECENCY_DAYS, as_of: date | None = None) -> dict:
    """Events concerning `entity_id`, with sources, locations, entities, typed paths and limitations. See module docstring."""
    limit = max(1, min(limit, MAX_LIMIT))
    as_of = as_of or as_of_default()
    entity = STORE.entity(entity_id)
    register = reg.load_register()
    window_start = as_of - timedelta(days=recency_days)

    eligible, not_returned = [], []
    for event in register["events"]:
        stub = {"id": event["id"], "title": event["title"], "published_date": event["published_date"]}
        ok, problems = _passes_policy(event)
        if not ok:
            not_returned.append({**stub, "reason": "inadmissible: " + "; ".join(problems)})
            continue
        resolved = event_entities.resolve_event(event)
        if entity_id not in {r["entity_id"] for r in resolved}:
            not_returned.append({**stub, "reason": f"{entity['name']} is not named in the cited evidence"})
            continue
        published = date.fromisoformat(event["published_date"])
        if published > as_of:
            not_returned.append({**stub, "reason": f"published after the as-of date ({as_of.isoformat()})"})
        elif published < window_start:
            not_returned.append({**stub, "reason": f"published {_days_before(as_of, event['published_date'])} days before the as-of date; "
                                                   f"the recency window is {recency_days} days"})
        else:
            eligible.append((event, resolved))

    def rank(item):
        event, _ = item
        direct = 0 if entity_id in {m["entity_id"] for m in event_entities.resolve_text(event["title"])} else 1
        return (-date.fromisoformat(event["published_date"]).toordinal(), direct, event["id"])

    eligible.sort(key=rank)
    returned, overflow = eligible[:limit], eligible[limit:]
    for event, _ in overflow:
        not_returned.append({"id": event["id"], "title": event["title"], "published_date": event["published_date"],
                             "reason": f"qualifies, but ranks below the limit of {limit} (newest first)"})

    events = [_present(event, resolved, entity_id) for event, resolved in returned]
    return {
        "entity": {"entity_id": entity_id, "name": entity["name"], "ticker": entity.get("ticker"), "country": entity.get("country")},
        "query": {"limit": limit, "recency_days": recency_days, "as_of": as_of.isoformat(),
                  "window": [window_start.isoformat(), as_of.isoformat()]},
        "as_of_basis": "the register's build date" if as_of == as_of_default() else "supplied by the caller",
        "register": {"built_at": register["register"]["built_at"], "coverage": register["register"]["coverage"],
                     "events_total": len(register["events"]), "approved_sources": [
                         {"id": s["id"], "domains": s["domains"], "tier": s["tier"], "limits": s["limits"]} for s in reg.approved_sources()["sources"]]},
        "events": events,
        "not_returned": sorted(not_returned, key=lambda r: (r["published_date"], r["id"]), reverse=True),
        "explanation": _explain(entity, len(events), limit, recency_days, as_of, not_returned, len(register["events"])),
        "graph": build_graph(events, entity_id),
        "limitations": GLOBAL_LIMITATIONS,
    }


def _present(event: dict, resolved: list, target: str) -> dict:
    location = event_geo.event_location(event)
    regions = event_geo.regions_mentioned(event)
    relationships = event_graph.build_event_relationships(event["id"], resolved, target)
    primary = event["sources"][0]
    return {
        "id": event["id"], "title": event["title"], "category": event["category"],
        "relevance": "DIRECT_SUBJECT" if target in {m["entity_id"] for m in event_entities.resolve_text(event["title"])} else "MENTIONED_IN_EVIDENCE",
        "published_date": event["published_date"], "event_date": event["event_date"], "event_date_basis": event["event_date_basis"],
        "location": location, "regions_mentioned": regions,
        "sources": [{k: s[k] for k in ("id", "publisher", "url", "title", "published_date", "tier", "retrieved_at")} for s in event["sources"]],
        "evidence": [{"source_id": ev["source_id"], "quote": ev["quote"], "url": primary["url"]} for ev in event["evidence"]],
        "verification": event["verification"],
        "entities": relationships["entities"], "paths": relationships["paths"],
        "impact": relationships["impact"], "verified_exposure": relationships["verified_exposure"],
        "limitations": _event_limitations(event, relationships, regions, location),
    }


def _explain(entity: dict, n: int, limit: int, recency_days: int, as_of: date, not_returned: list, total: int) -> str:
    name = entity["name"]
    if total == 0:
        return "The register contains no events."
    related = [r for r in not_returned if "is not named" not in r["reason"]]
    if n == 0:
        if len(related) == 0:
            return (f"No event in the approved-source register names {name}. The register covers NVIDIA only (pilot), "
                    "so no events are returned; none are invented.")
        return (f"No event within {recency_days} days of {as_of.isoformat()} qualifies for {name}; "
                f"{len(related)} related record(s) were excluded (see not_returned for each reason). None are invented.")
    if n < limit:
        return (f"Returned {n} event(s), fewer than the {limit} requested: only {n} verified event(s) naming {name} fall within "
                f"{recency_days} days of {as_of.isoformat()} in the approved-source register. {len(related)} other record(s) "
                f"were excluded (see not_returned). No events were added to fill the count.")
    extra = [r for r in related if "ranks below the limit" in r["reason"]]
    return (f"Returned the {n} most recent verified events naming {name} within {recency_days} days of {as_of.isoformat()}."
            + (f" {len(extra)} more qualify but rank below the limit." if extra else ""))


def build_graph(events: list, target: str) -> dict:
    """Nodes and typed edges for the map. Node positions are display positions with their precision."""
    nodes, edges = {}, {}

    def entity_node(eid: str):
        if f"entity:{eid}" not in nodes:
            e = STORE.entity(eid)
            pos = event_geo.entity_position(eid)
            nodes[f"entity:{eid}"] = {"id": f"entity:{eid}", "type": "ENTITY", "entity_id": eid, "label": e["name"], "ticker": e.get("ticker"),
                                      "role": "TARGET" if eid == target else "ENTITY", "position": pos}
        return f"entity:{eid}"

    entity_node(target)
    for ev in events:
        nodes[f"event:{ev['id']}"] = {"id": f"event:{ev['id']}", "type": "EVENT", "event_id": ev["id"], "label": ev["title"],
                                      "published_date": ev["published_date"], "position": ev["location"] if ev["location"]["mapped"] else None,
                                      "mapped": ev["location"]["mapped"]}
        for ent in ev["entities"]:
            nid = entity_node(ent["entity_id"])
            edges.setdefault(f"MENTIONS|{ev['id']}|{ent['entity_id']}", {
                "id": f"MENTIONS|{ev['id']}|{ent['entity_id']}", "type": "MENTIONS", "source": f"event:{ev['id']}", "target": nid,
                "event_ids": [ev["id"]], "evidence": ent["mentions"][0]})
        for region in ev["regions_mentioned"]:
            rid = f"region:{region['key']}"
            nodes.setdefault(rid, {"id": rid, "type": "REGION", "label": region["label"], "position": {k: region[k] for k in ("key", "label", "lat", "lon", "precision", "kind", "country")}})
            edges.setdefault(f"MENTIONS_REGION|{ev['id']}|{region['key']}", {
                "id": f"MENTIONS_REGION|{ev['id']}|{region['key']}", "type": "MENTIONS_REGION", "source": f"event:{ev['id']}", "target": rid,
                "event_ids": [ev["id"]], "evidence": {"ref": region["ref"], "matched_text": region["matched_text"], "quote": region["quote"]}})
        for path in ev["paths"]:
            for step in path["steps"]:
                if step["type"] != "DOCUMENTED_RELATION":
                    continue
                key = f"DOCUMENTED_RELATION|{step['stored_edge']['source']}|{step['stored_edge']['target']}|{step['relation']}"
                a, b = entity_node(step["stored_edge"]["source"]), entity_node(step["stored_edge"]["target"])
                edge = edges.setdefault(key, {"id": key, "type": "DOCUMENTED_RELATION", "relation": step["relation"], "source": a, "target": b,
                                              "criticality": step["criticality"], "criticality_meaning": step["criticality_meaning"],
                                              "evidence_status": step["evidence_status"], "evidence_url": step["evidence_url"], "note": step["note"],
                                              "event_ids": []})
                if ev["id"] not in edge["event_ids"]:
                    edge["event_ids"].append(ev["id"])
    return {"nodes": sorted(nodes.values(), key=lambda n: n["id"]), "edges": sorted(edges.values(), key=lambda e: e["id"]),
            "edge_types": {
                "MENTIONS": "the event's cited text names this entity (quoted evidence)",
                "MENTIONS_REGION": "the event's cited text names this country",
                "DOCUMENTED_RELATION": "a typed, directed relationship from the platform's relationship data; criticality is a curated judgement, not an exposure"}}


def register_overview() -> dict:
    problems = reg.validate_register()
    register = reg.load_register()
    return {"register": register["register"], "events_total": len(register["events"]), "inadmissible": problems,
            "approved_sources": reg.approved_sources()["sources"], "policy": reg.approved_sources()["policy"]}
