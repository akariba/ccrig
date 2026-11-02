"""Today, Counterparty page, relationship network, stress and health panels. All read-only and offline; the same code runs in the in-browser build.

    GET  /api/today                      the command-center payload for a watchlist
    GET  /api/cp/{id}                    one counterparty (either universe)
    GET  /api/network/graph              nodes, edges and cluster halos for a scope (watchlist / ego / all)
    GET  /api/stress/scenarios           the scenario presets
    POST /api/stress/run                 deterministic propagation (a propagation index, not a loss estimate)
    GET  /api/health/{pipeline,sources,models}
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..core import network, propagation, today as today_mod
from ..core.config import AI_ENABLED  # noqa: F401  (documented: the models panel reads the provider settings, never the key)
from ..request_validation import MAX_ID_CHARS

router = APIRouter(prefix="/api", tags=["today"])
_DATE = r"^\d{4}-\d{2}-\d{2}$"


def _ids(csv: Optional[str]) -> list[str]:
    return [p.strip() for p in (csv or "").split(",") if p.strip()][:60]


def _as_of(v: Optional[str]) -> str:
    if not v:
        return date.today().isoformat()
    try:
        date.fromisoformat(v)
    except ValueError:
        raise HTTPException(422, "as_of must be a calendar date (YYYY-MM-DD)")
    return v


@router.get("/today")
def today(as_of: Optional[str] = Query(None, min_length=10, max_length=10, pattern=_DATE), watchlist: Optional[str] = Query(None, max_length=1200)):
    return today_mod.today(_as_of(as_of), _ids(watchlist))


@router.get("/cp/{cp_id}")
def counterparty_page(cp_id: str):
    out = today_mod.cp_page(cp_id.strip())
    if out is None:
        raise HTTPException(404, f"Counterparty '{cp_id}' not found")
    return out


@router.get("/network/graph")
def network_graph(scope: str = Query("watchlist", pattern="^(watchlist|ego|all)$"), ids: Optional[str] = Query(None, max_length=1200), center: Optional[str] = Query(None, max_length=MAX_ID_CHARS),
                  hops: int = Query(2, ge=1, le=3), channels: Optional[str] = Query(None, max_length=200), include_studio: bool = False):
    g = network.build()
    want = {c for c in _ids(channels) if c in network.CHANNELS} or None
    if scope == "all":
        seeds: list[str] = []
    elif scope == "ego":
        if not center:
            raise HTTPException(422, "scope=ego needs a center")
        seeds = [center if center in g["nodes"] else (network.cp_id(center) if network.cp_id(center) in g["nodes"] else network.is_id(center))]
        if seeds[0] not in g["nodes"]:
            raise HTTPException(404, f"'{center}' is not in the network")
    else:
        seeds = [network.cp_id(i) for i in (_ids(ids) or today_mod.default_watchlist())]
    studio, extra = None, None
    if include_studio:
        extra, studio = network.studio_edges(g["nodes"])
    sub = network.subgraph(seeds, hops, want, extra)
    keep = {n["id"] for n in sub["nodes"]}
    cl = [c for c in network.clusters() if sum(1 for m in c["members"] if m in keep) >= 2]
    out = {"scope": scope, "seeds": seeds, "hops": hops, "nodes": sub["nodes"], "edges": sub["edges"], "clusters": cl, "channels": list(network.CHANNELS), "node_count": len(sub["nodes"]), "edge_count": len(sub["edges"])}
    if studio is not None:
        out["studio_overlay"] = studio
    return out


@router.get("/stress/scenarios")
def stress_scenarios():
    return {"scenarios": propagation.scenarios(), "index_label": propagation.LABEL}


class StressRequest(BaseModel):
    shock: list[str] = Field(min_length=1, max_length=5)
    max_hops: int = Field(propagation.MAX_HOPS, ge=1, le=4)
    label: str = Field("", max_length=120)


@router.post("/stress/run")
def stress_run(req: StressRequest):
    ids = [network.cp_id(s) if network.cp_id(s) in network.build()["nodes"] else s for s in req.shock]
    out = propagation.run(ids, req.max_hops, req.label)
    if not out["shocked"]:
        raise HTTPException(404, "None of the shocked nodes is in the network")
    return out


@router.get("/health/pipeline")
def health_pipeline():
    return {"available": False, "operator_only": True, "stages": [],
            "reason": "Ingestion state comes from the operator Data Studio and its ledger, which need the operator token. This deployment shows none."}


@router.get("/health/sources")
def health_sources(as_of: Optional[str] = Query(None, min_length=10, max_length=10, pattern=_DATE)):
    return today_mod.source_freshness(date.fromisoformat(_as_of(as_of)))


@router.get("/health/models")
def health_models():
    return today_mod.model_connections()
