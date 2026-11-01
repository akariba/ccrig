"""Global Event Impact Map API (pilot: NVIDIA).

    GET /api/impact-map/search?q=            which entity does the query mean, and does the register cover it
    GET /api/impact-map/{entity_id}/events   up to five verified, approved-source events with typed paths
    GET /api/impact-map/register             the register's policy and its own admissibility check

All of it is pure and offline (no network at request time), so it runs unchanged in the
in-browser (Pyodide) build. See docs/EVENT_IMPACT_MAP.md.
"""
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from ..core import event_discovery, event_entities
from ..core.data import STORE
from ..request_validation import MAX_ID_CHARS

router = APIRouter(prefix="/api/impact-map", tags=["impact-map"])


def _issuer_or_404(entity_id: str) -> str:
    entity_id = entity_id.upper()
    entity = STORE.entity(entity_id)
    if not entity or entity["node_type"] != "Company/Issuer":
        raise HTTPException(404, f"Issuer '{entity_id}' not found")
    return entity_id


@router.get("/search")
def search(q: str = Query(..., min_length=1, max_length=100)):
    matches = event_entities.resolve_query(q)
    out = []
    for m in matches:
        result = event_discovery.discover(m["entity_id"], limit=event_discovery.MAX_LIMIT, recency_days=730)
        out.append({**m, "event_coverage": len(result["events"]) > 0,
                    "events_in_register": len(result["events"]) + len([r for r in result["not_returned"] if "ranks below" in r["reason"]])})
    return {"query": q, "matches": out,
            "message": None if out else f"No issuer matches '{q}'. Nothing is guessed: try a company name or ticker."}


@router.get("/register")
def register():
    return event_discovery.register_overview()


def _when(as_of):
    if as_of is None:
        return None
    try:
        return date.fromisoformat(as_of)
    except ValueError:
        raise HTTPException(422, f"as_of '{as_of}' is not a real calendar date (use YYYY-MM-DD)")


@router.get("/{entity_id}/compare")
def compare(entity_id: str,
            limit: int = Query(5, ge=1, le=event_discovery.MAX_LIMIT),
            recency_days: int = Query(event_discovery.DEFAULT_RECENCY_DAYS, ge=1, le=730),
            as_of: Optional[str] = Query(None, min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$")):
    """Curated register vs the latest dynamic discovery, side by side."""
    from ..discovery import bridge

    return bridge.compare(_issuer_or_404(entity_id), limit=limit, recency_days=recency_days, as_of=_when(as_of))


@router.get("/{entity_id}/events")
def events(entity_id: str,
           limit: int = Query(5, ge=1, le=event_discovery.MAX_LIMIT),
           recency_days: int = Query(event_discovery.DEFAULT_RECENCY_DAYS, ge=1, le=730),
           as_of: Optional[str] = Query(None, min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$"),
           mode: Literal["curated", "discovered"] = Query("curated"),
           include_studio: bool = False):
    """mode=curated (default): the approved-source register. mode=discovered: the latest dynamic discovery run, if this deployment can run one."""
    entity_id = _issuer_or_404(entity_id)
    when = _when(as_of)
    graph, studio = None, None
    if include_studio:
        from ..studio import overlay

        ov = overlay.approved(True)
        graph = overlay.merged_graph(ov["edges"]) if ov["edges"] else None
        studio = {"requested": True, "available": ov["available"], "reason": ov["reason"], "release": ov["release"],
                  "edges_added": sum(1 for e in ov["edges"] if not e["in_canonical"]),
                  "note": "Paths may use approved relationships that are not in the canonical dataset; they are marked with evidence status STUDIO_APPROVED and carry no criticality."}
    if mode == "discovered":
        from ..discovery import bridge

        out = bridge.discovered_response(entity_id, limit=limit, recency_days=recency_days, as_of=when, graph=graph)
    else:
        out = event_discovery.discover(entity_id, limit=limit, recency_days=recency_days, as_of=when, graph=graph)
    return {**out, "studio_overlay": studio} if studio else out
