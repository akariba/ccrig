"""Daily Priority Queue + Breaches & Actions (BUILD_MANDATE CCR reorientation).

Synthetic CCR decision data only - never confidential/real bank data.
Priority is a deterministic rule cascade (core/ccr_priority.py), never a
naked 0-1 ML/AI score.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from ..core import ccr_priority
from ..core.config import CCR_PRIORITY_THRESHOLDS

router = APIRouter(prefix="/api", tags=["priority"])


@router.get("/priority-queue")
def priority_queue(priority: Optional[str] = None, driver: Optional[str] = None):
    rows = ccr_priority.build_priority_queue()
    if priority:
        rows = [r for r in rows if r["priority"] == priority.upper()]
    if driver:
        rows = [r for r in rows if r["driver"] == driver.upper()]

    all_rows = ccr_priority.build_priority_queue()
    summary = {
        "critical": sum(1 for r in all_rows if r["priority"] == "CRITICAL"),
        "high": sum(1 for r in all_rows if r["priority"] == "HIGH"),
        "medium": sum(1 for r in all_rows if r["priority"] == "MEDIUM"),
        "low": sum(1 for r in all_rows if r["priority"] == "LOW"),
        "informational": sum(1 for r in all_rows if r["priority"] == "INFORMATIONAL"),
        "overdue_breaches": sum(1 for r in all_rows if r["is_overdue"]),
        "model_or_data_items": sum(1 for r in all_rows if r["driver"] in ccr_priority.ROUTED_NOT_ESCALATED_DRIVERS),
    }
    return {"summary": summary, "count": len(rows), "results": rows,
            "thresholds": CCR_PRIORITY_THRESHOLDS,
            "note": "Synthetic CCR decision data (SYNTHETIC_CCR_DECISION_DATA) - illustrative POC only, fictional "
                    "counterparties, not real positions or real institutions. Priority thresholds are POC_HEURISTIC, "
                    "not real risk appetite."}


@router.get("/priority-queue/{counterparty_id}")
def priority_detail(counterparty_id: str):
    rows = ccr_priority.build_priority_queue()
    match = next((r for r in rows if r["id"] == counterparty_id.upper()), None)
    if not match:
        raise HTTPException(404, f"CCR counterparty '{counterparty_id}' not found")
    return match


@router.get("/breaches")
def breaches(status: Optional[str] = None):
    rows = [r for r in ccr_priority.build_priority_queue() if r["is_breach"]]
    if status == "overdue":
        rows = [r for r in rows if r["is_overdue"]]
    elif status == "within_sla":
        rows = [r for r in rows if not r["is_overdue"]]
    return {"count": len(rows), "results": rows}
