"""Model Lab (BUILD_MANDATE section 19): live, explicitly-exploratory
recomputation of the relationship vector/composite with user-editable
weights. Explicitly NOT a production-calibrated model.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
from ..core.data import STORE
from ..core import candidates, scoring, calibration
from ..core.config import WEIGHT_PRESETS, DEFAULT_WEIGHTS

router = APIRouter(prefix="/api/model-lab", tags=["model-lab"])


@router.get("/presets")
def presets():
    return {"presets": WEIGHT_PRESETS, "default_weights": DEFAULT_WEIGHTS,
            "disclaimer": "These are heuristic starting weights for exploration, not a calibrated production model.",
            "component_availability": {
                "ownership": "N/A - unavailable in this dataset (0 PARENT_OF/SUBSIDIARY_OF fact edges; "
                              "reserved for future GLEIF Level-2 parent relationships). The ownership weight "
                              "is never a live signal here - it is always excluded and remaining weights "
                              "renormalised, exactly like any other missing component.",
            }}


class ScoreRequest(BaseModel):
    entity_id: str
    weights: Optional[Dict[str, float]] = None
    preset: Optional[str] = None
    top_k: int = 15


@router.post("/score")
def score(req: ScoreRequest):
    entity_id = req.entity_id.upper()
    if entity_id not in STORE.entities_by_id:
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    weights = req.weights
    if req.preset and req.preset in WEIGHT_PRESETS:
        weights = WEIGHT_PRESETS[req.preset]["weights"]
    weights = weights or DEFAULT_WEIGHTS

    cand = candidates.generate_candidates(entity_id)
    ranked = scoring.rank_candidates(entity_id, cand["candidate_ids"], weights, top_k=req.top_k)
    return {
        "entity_id": entity_id,
        "weights_used": weights,
        "instrumentation": cand["instrumentation"],
        "scored_pair_count": ranked["scored_pair_count"],
        "retained_count": ranked["retained_count"],
        "results": [{"entity_id": r["b"], "name": STORE.entity(r["b"])["name"],
                      "score": r["composite"]["score"], "component_values": r["composite"]["component_values"],
                      "missing_components": r["composite"]["missing_components"]} for r in ranked["results"]],
    }


class PairRequest(BaseModel):
    a: str
    b: str
    weights: Optional[Dict[str, float]] = None
    preset: Optional[str] = None


@router.post("/pair")
def pair(req: PairRequest):
    a, b = req.a.upper(), req.b.upper()
    if a not in STORE.entities_by_id or b not in STORE.entities_by_id:
        raise HTTPException(404, "entity not found")
    weights = req.weights
    if req.preset and req.preset in WEIGHT_PRESETS:
        weights = WEIGHT_PRESETS[req.preset]["weights"]
    result = scoring.score_pair(a, b, weights or DEFAULT_WEIGHTS)
    return result


# ---------------------------------------------------------------------------
# Experimental Anchor Calibration (POC weak-supervision demonstration).
# Never mutates DEFAULT_WEIGHTS / presets - the caller (Model Lab UI) decides
# whether to use the returned calibrated_weights for subsequent /score or
# /pair calls; nothing is silently applied server-side.
# ---------------------------------------------------------------------------
@router.get("/calibration/anchors")
def calibration_anchors():
    return calibration.list_anchors()


class CalibrateRequest(BaseModel):
    starting_weights: Optional[Dict[str, float]] = None
    gamma: float = calibration.DEFAULT_GAMMA
    lam: float = calibration.DEFAULT_LAMBDA


@router.post("/calibration/run")
def calibration_run(req: CalibrateRequest):
    return calibration.run_calibration(req.starting_weights, req.gamma, req.lam)


class MarketAgreementRequest(BaseModel):
    weights: Optional[Dict[str, float]] = None
    top_k: int = 5


@router.post("/calibration/market-agreement")
def calibration_market_agreement(req: MarketAgreementRequest):
    return calibration.market_agreement_diagnostic(req.weights, req.top_k)
