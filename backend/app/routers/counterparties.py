from fastapi import APIRouter, HTTPException
from ..core.data import STORE
from ..core.graph_store import exposure_of_counterparty
from ..core import candidates, scoring, paths as path_mod
from ..core.config import DEFAULT_WEIGHTS

router = APIRouter(prefix="/api/counterparties", tags=["counterparties"])


@router.get("")
def list_counterparties():
    out = []
    for cid in STORE.counterparty_ids:
        e = STORE.entity(cid)
        out.append({"id": cid, "name": e["name"], "industry": e.get("industry"),
                     "country": e.get("country"), "region": e.get("region"), "is_synthetic": True})
    return {"count": len(out), "results": out, "note": "ALL counterparties in this POC are SYNTHETIC - clearly flagged is_synthetic=true."}


@router.get("/{cp_id}")
def counterparty_360(cp_id: str):
    cp_id = cp_id.upper()
    e = STORE.entity(cp_id)
    if not e or e["node_type"] != "Counterparty":
        raise HTTPException(404, f"Counterparty '{cp_id}' not found")

    holdings = exposure_of_counterparty(cp_id)
    total_exposure = sum(h.get("exposure_pct", 0) for h in holdings)

    concentration_sector = {}
    concentration_theme = {}
    for h in holdings:
        issuer = STORE.entity(h["issuer"])
        if not issuer:
            continue
        sec = issuer.get("sector") or "Unknown"
        concentration_sector[sec] = concentration_sector.get(sec, 0) + h.get("exposure_pct", 0)
        for theme_id, w in STORE.entity_keyword_weights.get(h["issuer"], {}).items():
            concentration_theme[theme_id] = concentration_theme.get(theme_id, 0) + h.get("exposure_pct", 0) * w

    top_themes = sorted(concentration_theme.items(), key=lambda x: -x[1])[:8]

    # direct vs indirect exposure paths: direct = held issuer directly;
    # indirect = related-to-a-held-issuer via Layer A/B (one more hop),
    # kept in separate units from direct exposure_pct.
    held_issuers = {h["issuer"] for h in holdings}
    indirect = []
    for issuer_id in held_issuers:
        cand = candidates.generate_candidates(issuer_id)
        if not cand:
            continue
        ranked = scoring.rank_candidates(issuer_id, cand["candidate_ids"], DEFAULT_WEIGHTS, top_k=5)
        for r in ranked["results"]:
            if r["b"] not in held_issuers and r["composite"]["score"] and r["composite"]["score"] > 0.3:
                indirect.append({
                    "via_direct_holding": issuer_id, "indirect_entity": r["b"],
                    "relatedness_score": r["composite"]["score"],
                    "note": "This is a RELATEDNESS score (Layer B units), NOT an exposure percentage (Layer C units) - never sum these with exposure_pct.",
                })

    return {
        "header": {"id": cp_id, "name": e["name"], "industry": e.get("industry"), "country": e.get("country"),
                    "region": e.get("region"), "is_synthetic": True,
                    "synthetic_disclaimer": "This counterparty and ALL its exposures are entirely synthetic POC data, not a real fund/institution."},
        "direct_holdings": holdings,
        "total_direct_exposure_pct": round(total_exposure, 4),
        "concentration_by_sector": concentration_sector,
        "concentration_by_theme_top8": [{"theme_id": t, "label": STORE.keywords_by_id[t]["label"], "weighted_exposure": round(v, 4)}
                                          for t, v in top_themes if t in STORE.keywords_by_id],
        "indirect_relationships": indirect[:20],
        "risk_cluster_note": "Risk clustering is approximated here by sector/theme concentration; no dedicated clustering "
                              "algorithm (e.g. community detection) is run in this POC pass - see docs/LIMITATIONS.md.",
    }
