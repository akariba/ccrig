from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from ..core import event_parser
from ..ai.provider import PROVIDER

router = APIRouter(prefix="/api/event", tags=["event"])


class EventParseRequest(BaseModel):
    text: str
    max_hops: int = 2
    min_score: float = 0.05
    sector: Optional[str] = None
    geography: Optional[str] = None
    top_k: int = 15


@router.post("/parse")
def parse_event(req: EventParseRequest):
    result = event_parser.parse_event(
        req.text, max_hops=req.max_hops, min_score=req.min_score,
        sector=req.sector, geography=req.geography, top_k=req.top_k,
    )
    result["ai_summary"] = PROVIDER.summarize_event(result)
    result["ai_mode"] = PROVIDER.mode
    return result


@router.get("/sample-scenarios")
def sample_scenarios():
    """The 6 required preloaded sample scenarios (BUILD_MANDATE section 28).
    Each is a raw query string the frontend feeds into /api/search or
    /api/event/parse - none are pre-baked; every one runs the live pipeline."""
    return {
        "scenarios": [
            {"id": "entity_ibm", "label": "IBM", "query": "IBM", "query_type": "entity"},
            {"id": "theme_taiwan", "label": "Taiwan", "query": "Taiwan", "query_type": "theme_or_geography"},
            {"id": "theme_ai_bubble", "label": "AI bubble", "query": "AI bubble", "query_type": "theme"},
            {"id": "event_taiwan_eq", "label": "Taiwan earthquake",
             "query": "A major earthquake in Taiwan disrupts semiconductor fabrication facilities.", "query_type": "event"},
            {"id": "event_russia_ukraine", "label": "Russia-Ukraine escalation",
             "query": "Russia-Ukraine escalation raises energy and defense risks.", "query_type": "event"},
            {"id": "event_bank_stress", "label": "Regional bank funding stress",
             "query": "Regional bank funding stress after a major bank failure.", "query_type": "event"},
        ]
    }
