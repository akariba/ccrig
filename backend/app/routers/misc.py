"""Scenario Replay / Backtest Prototype, Data & Provenance Explorer,
Scalability simulator, and health/AI-mode endpoints grouped together since
each is a small, mostly read-only surface over its core module."""
from fastapi import APIRouter, HTTPException
from ..core import backtest as backtest_mod
from ..core import provenance as provenance_mod
from ..core import scalability as scalability_mod
from ..ai.provider import PROVIDER
from ..core.config import AI_ENABLED, AI_MODEL

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/health")
def health():
    return {"status": "ok", "ai_mode": PROVIDER.mode, "ai_enabled": AI_ENABLED,
            "ai_model": AI_MODEL if AI_ENABLED else None}


@router.get("/backtest/scenarios")
def backtest_scenarios():
    return {"scenarios": backtest_mod.list_scenarios()}


@router.get("/backtest/run")
def backtest_run(scenario_id: str = "taiwan_earthquake_2026"):
    result = backtest_mod.run_backtest(scenario_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.get("/provenance")
def provenance():
    return provenance_mod.registry()


@router.get("/provenance/coverage")
def provenance_coverage():
    return {"rows": provenance_mod.coverage_by_entity()}


@router.get("/scalability/simulate")
def scalability_simulate():
    return scalability_mod.full_report()
