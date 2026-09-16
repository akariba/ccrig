import dataclasses

from fastapi import APIRouter, HTTPException, Query

from ..core.data import STORE
from ..core.distance import compute_counterparty_distances

router = APIRouter(prefix="/api/distance-map", tags=["distance-map"])


@router.get("/counterparties")
def list_counterparties():
    """Counterparty list for the Distance Map's left-panel selector - the
    same portfolio-holdings counterparty universe as /api/counterparties."""
    out = []
    for cid in STORE.counterparty_ids:
        e = STORE.entity(cid)
        out.append({
            "counterparty_id": cid, "name": e["name"], "sector": e.get("sector"),
            "country": e.get("country"), "is_synthetic": e.get("is_synthetic", True),
        })
    return {"count": len(out), "results": out}


@router.get("/counterparty/{cp_id}")
def get_distances(
    cp_id: str,
    min_rho: float = Query(default=0.0, ge=0.0, le=1.0),
    max_hops: int = Query(default=2, ge=1, le=3),
):
    result = compute_counterparty_distances(cp_id, max_hops=max_hops, min_rho=min_rho)
    if result is None:
        raise HTTPException(404, f"Counterparty '{cp_id}' not found")
    return dataclasses.asdict(result)
