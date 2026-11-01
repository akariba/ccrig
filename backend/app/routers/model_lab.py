"""Model Lab (BUILD_MANDATE section 19): live, explicitly-exploratory
recomputation of the relationship vector/composite with user-editable
weights. Explicitly NOT a production-calibrated model.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from ..request_validation import EntityId, Weights, Preset, MAX_TOP_K
from ..core.data import STORE
from ..core import candidates, scoring, calibration, weight_usability
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
    entity_id: EntityId
    weights: Optional[Weights] = None
    preset: Optional[Preset] = None
    top_k: int = Field(15, ge=1, le=MAX_TOP_K)


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
    if ranked["scored_pair_count"] == 0:
        # An empty ranking here means "nothing could be computed", not "nothing is related".
        raise HTTPException(422, weight_usability.ranking_problem(entity_id, cand["candidate_ids"], weights))
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
    a: EntityId
    b: EntityId
    weights: Optional[Weights] = None
    preset: Optional[Preset] = None


@router.post("/pair")
def pair(req: PairRequest):
    a, b = req.a.upper(), req.b.upper()
    if a not in STORE.entities_by_id or b not in STORE.entities_by_id:
        raise HTTPException(404, "entity not found")
    weights = req.weights
    if req.preset and req.preset in WEIGHT_PRESETS:
        weights = WEIGHT_PRESETS[req.preset]["weights"]
    weights = weights or DEFAULT_WEIGHTS
    result = scoring.score_pair(a, b, weights)
    if result["composite"]["score"] is None:
        raise HTTPException(422, weight_usability.pair_problem(a, b, weights))
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
    starting_weights: Optional[Weights] = None
    gamma: float = Field(calibration.DEFAULT_GAMMA, gt=0, le=1000, allow_inf_nan=False)
    lam: float = Field(calibration.DEFAULT_LAMBDA, ge=0, le=1000, allow_inf_nan=False)


@router.post("/calibration/run")
def calibration_run(req: CalibrateRequest):
    return calibration.run_calibration(req.starting_weights, req.gamma, req.lam)


class MarketAgreementRequest(BaseModel):
    weights: Optional[Weights] = None
    top_k: int = Field(5, ge=1, le=MAX_TOP_K)


@router.post("/calibration/market-agreement")
def calibration_market_agreement(req: MarketAgreementRequest):
    return calibration.market_agreement_diagnostic(req.weights, req.top_k)
