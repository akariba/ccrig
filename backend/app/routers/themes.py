from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from typing import Annotated, List, Optional
from pydantic import BaseModel, Field, StringConstraints, field_validator
from ..core import config
from ..core import themes as theme_mod
from ..ai.provider import PROVIDER

router = APIRouter(prefix="/api/themes", tags=["themes"])


@router.get("")
def list_themes(q: Optional[str] = Query(None, max_length=100), kind: Optional[str] = Query(None, max_length=100)):
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


_Tag = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class IngestDocument(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
    date: str = Field(description="ISO date, YYYY-MM-DD")
    title: str = Field(min_length=1, max_length=300)
    snippet: str = Field(min_length=1, max_length=5000)
    entities: Optional[List[_Tag]] = Field(None, max_length=50)
    keywords: Optional[List[_Tag]] = Field(None, max_length=50)
    source: Optional[str] = Field(None, max_length=100)
    url: Optional[str] = Field(None, max_length=500, pattern=r"^[Hh][Tt][Tt][Pp][Ss]?://\S+$")
    is_synthetic: Optional[bool] = True

    @field_validator("date")
    @classmethod
    def _iso_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("must be an ISO date (YYYY-MM-DD)")
        return v

    @field_validator("title", "snippet")
    @classmethod
    def _not_blank(cls, v):
        if not v.strip():
            raise ValueError("must not be blank")
        return v

    @field_validator("is_synthetic")
    @classmethod
    def _always_synthetic(cls, v):
        if v is False:
            raise ValueError("ingested documents are always labelled synthetic/unverified in this POC; "
                             "omit is_synthetic or set it to true")
        return v


@router.post("/ingest")
def ingest_document(doc: IngestDocument):
    """Minimal ingestion path (POC scope): append one news document to the
    live corpus and invalidate the discovery cache. No internet-feed
    integration - this only proves that NEW text can make a NEW concept
    emerge on the next /api/themes/discover call.

    Disabled unless CCRIG_ENABLE_INGEST=1 (it writes to process-wide state
    that every viewer shares). Ingested text is always stored as synthetic /
    unverified; ids are unique and the number of documents is bounded."""
    if not config.INGEST_ENABLED:
        raise HTTPException(403, "Document ingestion is disabled. Set CCRIG_ENABLE_INGEST=1 to enable it "
                                 "(demo/POC use only: ingested text is always labelled synthetic).")
    try:
        stored = theme_mod.ingest_news_document({k: v for k, v in doc.model_dump().items() if v is not None})
    except (theme_mod.DuplicateDocument, theme_mod.IngestCapacityReached) as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"ingested": stored, "news_corpus_size": len(theme_mod.STORE.news_all)}
