"""Typed transmission paths between an event, the entities it names, and a target entity.

Three kinds of link are kept apart on purpose and never merged into one number:

* MENTIONS            event -> entity, evidenced by a quoted passage of the source;
* DOCUMENTED_RELATION entity -> entity, a typed, directed fact edge from the platform's
                      relationship data (supply, licence, ownership) with its evidence status;
* MENTIONS_REGION     event -> country named in the cited text.

Graph proximity (hops), profile similarity and statistical correlation are NOT used
here. A path says "these entities are connected by these documented relationships",
not "this event moves that company". Impact is reported as NOT_ESTIMATED, separately
from the relationship evidence, until a method for it is validated.
"""
from .graph_store import FACT_GRAPH

DOCUMENTED_RELATIONS = ("SUPPLIES", "LICENSES_TO", "PARENT_OF", "SUBSIDIARY_OF")
MAX_HOPS = 2
MAX_PATHS_PER_ENTITY = 3
CRITICALITY_MEANING = ("curated 0-1 judgement of how dependent the relationship is, stored in the dataset; "
                       "not a measured exposure and not an impact estimate")

IMPACT_NOT_ESTIMATED = {
    "status": "NOT_ESTIMATED",
    "estimate": None,
    "reason": "No method for the size of an event's effect on a company has been validated in this platform, so none is estimated. "
              "What is shown is relationship evidence (what is documented) and what the source says.",
}
EXPOSURE_NOT_AVAILABLE = {
    "status": "NOT_AVAILABLE",
    "reason": "The platform holds no verified exposure data for these entities. Its counterparty exposures are synthetic and are not used here.",
}


def _documented_neighbours(node: str):
    for _, target, data in FACT_GRAPH.out_edges(node, data=True):
        if data["relation"] in DOCUMENTED_RELATIONS:
            yield target, data, "FORWARD"
    for source, _, data in FACT_GRAPH.in_edges(node, data=True):
        if data["relation"] in DOCUMENTED_RELATIONS:
            yield source, data, "REVERSE"


def _hop(current: str, nxt: str, data: dict, direction: str) -> dict:
    return {
        "type": "DOCUMENTED_RELATION", "relation": data["relation"], "from": current, "to": nxt,
        "traversal": "WITH_STORED_DIRECTION" if direction == "FORWARD" else "AGAINST_STORED_DIRECTION",
        "stored_edge": {"source": data["source"], "target": data["target"]},
        "criticality": data.get("criticality"), "criticality_meaning": CRITICALITY_MEANING,
        "evidence_status": data.get("evidence_status"), "evidence_url": data.get("evidence_url"), "note": data.get("note"),
    }


def documented_paths(source: str, target: str, max_hops: int = MAX_HOPS) -> list:
    """The shortest documented paths from `source` to `target` (all of the minimum length, at most
    MAX_PATHS_PER_ENTITY, in a fixed order). Each is a list of hops; [] if none within `max_hops`."""
    if source == target or source not in FACT_GRAPH or target not in FACT_GRAPH:
        return []
    found = []
    stack = [(source, [], {source})]
    while stack:
        node, hops, seen = stack.pop()
        if len(hops) >= max_hops:
            continue
        for nxt, data, direction in _documented_neighbours(node):
            if nxt in seen:
                continue
            path = hops + [_hop(node, nxt, data, direction)]
            if nxt == target:
                found.append(path)
            else:
                stack.append((nxt, path, seen | {nxt}))
    if not found:
        return []
    shortest = min(len(p) for p in found)
    keep = [p for p in found if len(p) == shortest]
    keep.sort(key=lambda p: (-sum((h["criticality"] or 0) for h in p), [h["to"] for h in p], [h["relation"] for h in p]))
    return keep[:MAX_PATHS_PER_ENTITY]


def classify(entity_id: str, target: str, paths: list) -> str:
    if entity_id == target:
        return "SELF"
    if not paths:
        return "NO_DOCUMENTED_PATH"
    return "DOCUMENTED_DIRECT" if len(paths[0]) == 1 else "DOCUMENTED_INDIRECT"


def _explain(entity: str, target: str, cls: str, paths: list) -> str:
    if cls == "SELF":
        return f"{target} is named in the cited evidence."
    if cls == "NO_DOCUMENTED_PATH":
        return (f"{entity} is named in the cited evidence, but the platform's relationship data holds no documented relationship "
                f"between {entity} and {target} within {MAX_HOPS} hops. That is an absence in the data, not evidence that none exists.")
    first = paths[0]
    chain = " -> ".join([first[0]["from"]] + [h["to"] for h in first])
    kind = "directly" if cls == "DOCUMENTED_DIRECT" else f"indirectly, through {len(first)} documented relationships"
    return f"{entity} is connected to {target} {kind} ({chain})."


def build_event_relationships(event_id: str, resolved: list, target: str) -> dict:
    """For one event: each resolved entity's documented connection to `target`, and the flat list of
    typed paths event -> entity [-> entity] -> target."""
    entities, flat = [], []
    for rec in resolved:
        eid = rec["entity_id"]
        paths = documented_paths(eid, target)
        cls = classify(eid, target, paths)
        entities.append({"entity_id": eid, "name": rec["name"], "country": rec["country"], "mentions": rec["mentions"],
                         "role": "TARGET" if eid == target else "MENTIONED", "relationship_to_target": cls,
                         "explanation": _explain(eid, target, cls, paths)})
        mention = {"type": "MENTIONS", "from": f"event:{event_id}", "to": eid, "evidence": rec["mentions"][0]}
        if cls == "SELF":
            flat.append({"id": f"{event_id}|{eid}|direct", "relationship_type": "DIRECT_MENTION", "entity_id": eid, "steps": [mention]})
        for i, path in enumerate(paths):
            flat.append({"id": f"{event_id}|{eid}|{i}",
                         "relationship_type": "DOCUMENTED_DIRECT" if len(path) == 1 else "DOCUMENTED_INDIRECT",
                         "entity_id": eid, "steps": [mention] + path})
    return {"target": target, "entities": entities, "paths": flat,
            "impact": dict(IMPACT_NOT_ESTIMATED), "verified_exposure": dict(EXPOSURE_NOT_AVAILABLE)}
