"""Data & Provenance Explorer backing logic (BUILD_MANDATE section 20).
Every dataset is explicitly tagged REAL_PUBLIC_DATA / SYNTHETIC_POC_DATA /
DERIVED_DATA / AI_ASSISTED_EXTRACTION with record counts, so the UI can
render an honest inventory instead of a generic "data sources" page.
"""
from datetime import date
from .data import STORE


def registry():
    n_issuers = len(STORE.issuer_ids)
    n_cps = len(STORE.counterparty_ids)
    n_market = sum(1 for i in STORE.issuer_ids if STORE.entity(i).get("has_market_data"))
    fact_by_status = {}
    for fe in STORE.fact_edges:
        fact_by_status[fe["evidence_status"]] = fact_by_status.get(fe["evidence_status"], 0) + 1
    gleif_hits = len(STORE.gleif_by_entity)

    return {
        "generated_at": date.today().isoformat(),
        "sources": [
            {
                "id": "market_prices",
                "name": "Bundled daily price history (public market data)",
                "classification": "REAL_PUBLIC_DATA",
                "record_count": n_market,
                "coverage_note": f"{n_market}/{n_issuers} issuers have bundled OHLC history; SKHY has a short/sparse real sample (~20 rows from 2026-07-10).",
                "last_update": "2026-08-06",
                "source_type": "market",
            },
            {
                "id": "gleif_lei",
                "name": "GLEIF Legal Entity Identifier records (fetched live)",
                "classification": "REAL_PUBLIC_DATA",
                "record_count": gleif_hits,
                "coverage_note": f"Live-fetched from api.gleif.org for {gleif_hits}/{n_issuers} issuers at build time; used for LEI/legal name/country cross-checks in Entity 360. No parent/child LEI relationships bundled in this POC pass.",
                "last_update": "build-time",
                "source_type": "registry",
            },
            {
                "id": "news_real",
                "name": "Curated real public news headlines (with source URLs)",
                "classification": "REAL_PUBLIC_DATA",
                "record_count": len(STORE.news_real),
                "coverage_note": "Headline + short snippet + canonical URL only (no full-article redistribution). Sources include Bloomberg, Reuters, CNBC, TrendForce, Fortune, White House fact sheets.",
                "last_update": "2026-08",
                "source_type": "news",
            },
            {
                "id": "news_synthetic",
                "name": "Synthetic narrative news corpus",
                "classification": "SYNTHETIC_POC_DATA",
                "record_count": len(STORE.news_synthetic),
                "coverage_note": "Generated to give the Theme Radar enough density for a convincing demo; every document is tagged source_type=SYNTHETIC_NARRATIVE and is_synthetic=true.",
                "last_update": "build-time",
                "source_type": "news",
            },
            {
                "id": "fact_edges",
                "name": "Factual relations (supply chain, licensing, sector, geography)",
                "classification": "REAL_PUBLIC_DATA (well-documented + reported) with a small SYNTHETIC subset",
                "record_count": len(STORE.fact_edges),
                "coverage_note": f"Evidence-status breakdown: {fact_by_status}",
                "last_update": "2026-08",
                "source_type": "reference",
            },
            {
                "id": "counterparties",
                "name": "Synthetic counterparty book",
                "classification": "SYNTHETIC_POC_DATA",
                "record_count": n_cps,
                "coverage_note": "All 18 counterparties and all 80 exposure edges are entirely synthetic and clearly flagged is_synthetic=true throughout the API and UI.",
                "last_update": "build-time",
                "source_type": "exposure",
            },
            {
                "id": "derived_relationships",
                "name": "Derived relationship vectors (Layer B)",
                "classification": "DERIVED_DATA",
                "record_count": None,
                "coverage_note": "Computed on demand by candidate generation + scoring pipelines from the sources above; never persisted as a separate ground-truth table.",
                "last_update": "runtime",
                "source_type": "derived",
            },
            {
                "id": "ai_assisted_extraction",
                "name": "AI-assisted entity/theme/event extraction and explanations",
                "classification": "AI_ASSISTED_EXTRACTION",
                "record_count": None,
                "coverage_note": "DeterministicProvider (regex/keyword) always available offline; optional OpenAI-compatible provider only if AI_BASE_URL/AI_API_KEY/AI_MODEL are set. Used for parsing/labelling/explanation only, never bulk pairwise scoring.",
                "last_update": "runtime",
                "source_type": "ai",
            },
        ],
        "totals": {
            "issuers": n_issuers,
            "counterparties": n_cps,
            "issuers_with_market_data": n_market,
            "fact_edges": len(STORE.fact_edges),
            "exposure_edges": len(STORE.exposure_edges),
            "keywords_themes": len(STORE.keywords),
            "news_real": len(STORE.news_real),
            "news_synthetic": len(STORE.news_synthetic),
        },
    }


def coverage_by_entity():
    rows = []
    for eid in STORE.browsable_ids:
        e = STORE.entity(eid)
        rows.append({
            "entity_id": eid,
            "name": e["name"],
            "node_type": e["node_type"],
            "has_market_data": e.get("has_market_data", False),
            "has_gleif_record": eid in STORE.gleif_by_entity,
            "fact_edge_count": len([f for f in STORE.fact_edges if f["source"] == eid or f["target"] == eid]),
            "theme_count": len(STORE.entity_keyword_weights.get(eid, {})),
            "is_synthetic": e.get("is_synthetic", False),
        })
    return rows
