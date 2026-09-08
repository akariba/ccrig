from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from ..core.data import STORE
from ..core import candidates, scoring, market, paths as path_mod, ownership as ownership_mod, materiality
from ..core.graph_store import fact_neighbors, counterparties_exposed_to
from ..core.config import DEFAULT_WEIGHTS
from ..ai.provider import PROVIDER

router = APIRouter(prefix="/api/entities", tags=["entities"])


def _entity_summary(e):
    return {
        "id": e["id"], "name": e["name"], "node_type": e["node_type"], "sector": e.get("sector"),
        "industry": e.get("industry"), "country": e.get("country"), "region": e.get("region"),
        "ticker": e.get("ticker"), "has_market_data": e.get("has_market_data", False),
        "is_synthetic": e.get("is_synthetic", False),
    }


@router.get("")
def list_entities(sector: Optional[str] = None, country: Optional[str] = None,
                   node_type: Optional[str] = "Company/Issuer", q: Optional[str] = None,
                   limit: int = 200):
    out = []
    for eid in STORE.issuer_ids:
        e = STORE.entity(eid)
        if node_type and e["node_type"] != node_type:
            continue
        if sector and e.get("sector") != sector:
            continue
        if country and e.get("country") != country:
            continue
        if q and q.lower() not in e["name"].lower() and q.upper() != eid:
            continue
        out.append(_entity_summary(e))
    return {"count": len(out[:limit]), "results": out[:limit]}


@router.get("/{entity_id}")
def entity_360(entity_id: str, top_k: int = 10):
    entity_id = entity_id.upper()
    e = STORE.entity(entity_id)
    if not e or e["node_type"] != "Company/Issuer":
        raise HTTPException(404, f"Issuer '{entity_id}' not found")

    # --- Relationship summary (Layer B, candidate-gated) ---
    cand = candidates.generate_candidates(entity_id)
    ranked = scoring.rank_candidates(entity_id, cand["candidate_ids"], DEFAULT_WEIGHTS, top_k=top_k)
    relationship_summary = []
    for r in ranked["results"]:
        other = STORE.entity(r["b"])
        relationship_summary.append({
            "entity_id": r["b"], "name": other["name"], "composite_score": r["composite"]["score"],
            "component_values": r["composite"]["component_values"],
            "missing_components": r["composite"]["missing_components"],
        })

    # --- Factual vs derived links, explicitly separated ---
    fact_links = []
    for other_id, edges in fact_neighbors(entity_id).items():
        for edge in edges:
            fact_links.append({"other_entity": other_id, "other_name": STORE.entity(other_id)["name"], **edge})

    # --- Theme exposure ---
    theme_weights = STORE.entity_keyword_weights.get(entity_id, {})
    theme_exposure = sorted(
        [{"theme_id": t, "label": STORE.keywords_by_id[t]["label"], "weight": w} for t, w in theme_weights.items()
         if t in STORE.keywords_by_id],
        key=lambda x: -x["weight"],
    )

    # --- Market ---
    market_block = None
    if e.get("has_market_data"):
        series = market.price_series(entity_id)
        rolling = []
        for other_id in STORE.issuer_ids:
            if other_id == entity_id or not STORE.entity(other_id).get("has_market_data"):
                continue
            corr = market.signed_correlation(entity_id, other_id)
            if corr:
                rolling.append({"other_entity": other_id, "other_name": STORE.entity(other_id)["name"], **corr})
        rolling.sort(key=lambda r: -abs(r["full_sample_corr"]))
        market_block = {"price_series": series, "correlations": rolling[:15]}

    # --- Supply chain / ownership (directional) ---
    supply_chain = [l for l in fact_links if l["relation"] in ("SUPPLIES", "CUSTOMER_OF", "LICENSES_TO", "LICENSES_FROM")]
    ownership = [l for l in fact_links if l["relation"] in ("PARENT_OF", "SUBSIDIARY_OF")]

    # --- Counterparties (Layer C, joined last) ---
    cp_exposure = counterparties_exposed_to(entity_id)

    gleif = STORE.gleif_by_entity.get(entity_id)
    corporate_hierarchy = ownership_mod.ownership_summary_for_entity(
        entity_id, STORE.entities_raw, STORE.gleif_by_entity)

    return {
        "header": {**_entity_summary(e), "lei": gleif.get("lei") if gleif else None,
                    "gleif_legal_name": gleif.get("legal_name") if gleif else None,
                    "gleif_status": gleif.get("status") if gleif else None,
                    "data_freshness": "candidate generation + scoring computed at request time"},
        "relationship_summary": {
            "instrumentation": cand["instrumentation"],
            "scored_pair_count": ranked["scored_pair_count"],
            "retained_count": ranked["retained_count"],
            "top_related": relationship_summary,
        },
        "fact_links": fact_links,
        "supply_chain": supply_chain,
        "ownership": ownership,
        "corporate_hierarchy": corporate_hierarchy,
        "counterparty_materiality": {
            "note": "Synthetic CCR counterparties with a typed exposure referencing this issuer - connects "
                    "relationship discovery to actual CCR exposure materiality, not relatedness-score ranking.",
            "results": materiality.counterparties_for_reference_entity(entity_id),
        },
        "theme_exposure": theme_exposure,
        "market": market_block,
        "counterparties_exposed": cp_exposure,
        "evidence": {
            "fact_edge_sources": list({l.get("evidence_status") for l in fact_links if l.get("evidence_status")}),
            "gleif_record_present": gleif is not None,
        },
    }


@router.get("/{entity_id}/explain/{other_id}")
def explain_relationship(entity_id: str, other_id: str):
    entity_id, other_id = entity_id.upper(), other_id.upper()
    ea, eb = STORE.entity(entity_id), STORE.entity(other_id)
    if not ea or not eb:
        raise HTTPException(404, "entity not found")
    result = scoring.score_pair(entity_id, other_id)
    path = path_mod.fact_path_between(entity_id, other_id) or path_mod.theme_coincidence_path(entity_id, other_id) or path_mod.sector_peer_path(entity_id, other_id)
    explanation = PROVIDER.explain_relationship(ea["name"], eb["name"], result["vector"], result["composite"])
    path_explanation = PROVIDER.explain_path(path) if path else None
    return {"pair": result, "typed_path": path, "ai_explanation": explanation, "ai_path_explanation": path_explanation,
            "ai_mode": PROVIDER.mode}
