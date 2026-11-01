"""Scenario Replay / Backtest Prototype, Data & Provenance Explorer,
Scalability simulator, and health/AI-mode endpoints grouped together since
each is a small, mostly read-only surface over its core module."""
from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Query
from ..core import backtest as backtest_mod
from ..core import provenance as provenance_mod
from ..core import scalability as scalability_mod
from ..core import metric_definitions as metric_definitions_mod
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
def backtest_run(scenario_id: str = Query("taiwan_earthquake_2026", min_length=1, max_length=64)):
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


@router.get("/metric-definitions")
def metric_definitions():
    """The single canonical source every 'Definition' / 'How calculated?'
    UI affordance reads from - a metric must never be explained differently
    on two different pages."""
    return {"results": [asdict(d) for d in metric_definitions_mod.list_metric_definitions()]}


@router.get("/metric-definitions/{metric_id}")
def metric_definition(metric_id: str):
    d = metric_definitions_mod.get_metric_definition(metric_id)
    if not d:
        raise HTTPException(404, f"No metric definition for '{metric_id}'")
    return asdict(d)
