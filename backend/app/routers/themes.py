from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
from ..core import themes as theme_mod
from ..ai.provider import PROVIDER

router = APIRouter(prefix="/api/themes", tags=["themes"])


@router.get("")
def list_themes(q: Optional[str] = None, kind: Optional[str] = None):
    results = theme_mod.all_themes(q)
    if kind:
        results = [t for t in results if t["kind"].lower() == kind.lower()]
    return {
        "count": len(results),
        "curated_count": sum(1 for t in results if t["kind"] == "CURATED_THEME"),
        "discovered_count": sum(1 for t in results if t["kind"] == "DISCOVERED_THEME"),
        "results": results,
    }


@router.get("/{theme_id}")
def theme_detail(theme_id: str):
    detail = theme_mod.theme_detail(theme_id.upper())
    if not detail:
        raise HTTPException(404, f"Theme '{theme_id}' not found")
    top_terms = [detail["label"]] + detail["covered_entities"][:3]
    ai_label = PROVIDER.label_theme(top_terms)
    return {**detail, "ai_suggested_label": ai_label, "ai_mode": PROVIDER.mode}


@router.post("/discover")
def force_discover():
    """Force the concept-discovery pipeline to re-run over the current live
    news corpus (STORE.news_all) - proves the discovered-theme set is
    recomputed from text, not hard-coded."""
    theme_mod.invalidate_discovery_cache()
    discovered = theme_mod.discover_themes()
    return {"discovered_count": len(discovered), "results": discovered}


class IngestDocument(BaseModel):
    id: str
    date: str
    title: str
    snippet: str
    entities: Optional[list] = None
    keywords: Optional[list] = None
    source: Optional[str] = None
    url: Optional[str] = None
    is_synthetic: Optional[bool] = True


@router.post("/ingest")
def ingest_document(doc: IngestDocument):
    """Minimal ingestion path (POC scope): append one news document to the
    live corpus and invalidate the discovery cache. No internet-feed
    integration - this only proves that NEW text can make a NEW concept
    emerge on the next /api/themes/discover call."""
    stored = theme_mod.ingest_news_document({k: v for k, v in doc.dict().items() if v is not None})
    return {"ingested": stored, "news_corpus_size": len(theme_mod.STORE.news_all)}
