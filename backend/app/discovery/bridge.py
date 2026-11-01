"""Read side of dynamic discovery for the Global Event Impact Map: the latest discovery run for an entity, presented in the same shape as the curated register.

Read-only. It only reads an existing Studio workspace, and only when the Studio is enabled; on the public/static deployment it says plainly that dynamic discovery is
not available there. It never starts a search and never simulates one.
"""
from __future__ import annotations

from datetime import date

from ..core import event_discovery
from ..core.data import STORE
from . import dedupe, shape

REVIEW_LABEL = {
    "PENDING_REVIEW": "MACHINE_VERIFIED_AWAITING_REVIEW",
    "APPROVED": "APPROVED",
    "REJECTED": "REJECTED",
}


def _base(entity_id: str, limit: int, recency_days: int, as_of: date) -> dict:
    e = STORE.entity(entity_id)
    return {"mode": "discovered", "entity": {"entity_id": entity_id, "name": e["name"], "ticker": e.get("ticker"), "country": e.get("country")},
            "query": {"limit": limit, "recency_days": recency_days, "as_of": as_of.isoformat(), "window": [as_of.isoformat(), as_of.isoformat()]},
            "events": [], "not_returned": [], "graph": {"nodes": [], "edges": [], "edge_types": []}, "limitations": shape.LIMITATIONS,
            "register": {"built_at": as_of.isoformat(), "coverage": "Dynamic discovery", "events_total": 0, "approved_sources": []}, "as_of_basis": "supplied by the caller"}


def unavailable(entity_id: str, reason: str, *, limit=5, recency_days=180, as_of: date | None = None, code: str = "UNAVAILABLE") -> dict:
    as_of = as_of or event_discovery.as_of_default()
    return {**_base(entity_id, limit, recency_days, as_of), "available": False, "unavailable_code": code, "explanation": reason,
            "curated_available": True, "provenance": None, "review": None}


def _store():
    from ..studio import config

    if not config.studio_enabled():
        return None, ("Dynamic discovery runs only on an operator machine or a private server with the Data Studio enabled. This deployment shows the curated register only; "
                      "nothing is searched live and no result is simulated.", "STUDIO_DISABLED")
    try:
        root = config.studio_dir()
    except config.UnsafeWorkspace as exc:
        return None, (str(exc), "UNSAFE_WORKSPACE")
    if not (root / "studio.db").exists():
        return None, ("The Data Studio has no workspace yet, so no discovery has been run.", "NO_WORKSPACE")
    from ..studio.store import StudioStore          # sqlite is imported only when a workspace exists (never in the static build)

    return StudioStore(root), None


def discovered_response(entity_id: str, *, limit: int = 5, recency_days: int = 180, as_of: date | None = None) -> dict:
    store, why = _store()
    if store is None:
        return unavailable(entity_id, why[0], limit=limit, recency_days=recency_days, as_of=as_of, code=why[1])
    run = store.latest_run(entity_id)
    if run is None:
        return unavailable(entity_id, f"No dynamic discovery has been run for {STORE.entity(entity_id)['name']} yet. An operator can run: python -m app.studio discover {entity_id}",
                           limit=limit, recency_days=recency_days, as_of=as_of, code="NO_RUN")
    run_date = date.fromisoformat(run["as_of"])
    job = store.get_job(run["staging_job_id"]) if run.get("staging_job_id") else None
    decisions = store.decisions(job["job_id"]) if job else []
    status = REVIEW_LABEL.get(job["status"], "STAGED_WITH_FINDINGS") if job else "NO_EVENTS"
    review = {"status": status, "job_id": job["job_id"] if job else None, "decisions": [{k: d[k] for k in ("decision", "reviewer", "reason", "at")} for d in decisions]}
    prov = {"run_id": run["run_id"], "ran_at": run["ran_at"], "as_of": run["as_of"], "window": run["window"], "providers": run["providers"], "funnel": run["funnel"], "ai": run["ai"],
            "selection_criteria": run["selection_criteria"], "relationship_candidates": run.get("relationship_candidates", []), "resolution": run["resolution"]}
    if status == "REJECTED":
        return {**unavailable(entity_id, f"The latest discovery run was rejected by {decisions[-1]['reviewer']}: {decisions[-1]['reason']}. Its events are not shown.", limit=limit,
                              recency_days=recency_days, as_of=run_date, code="REJECTED"), "provenance": prov, "review": review}
    if job and job["status"] not in ("PENDING_REVIEW", "APPROVED"):
        return {**unavailable(entity_id, "The latest discovery run did not pass the Studio's validation, so its events are not shown.", limit=limit, recency_days=recency_days,
                              as_of=run_date, code="VALIDATION_FAILED"), "provenance": prov, "review": review}
    meta = {"built_at": run["as_of"], "coverage": f"Dynamic discovery run {run['run_id']}", "events_total": len(run["events"]),
            "approved_sources": [{"id": s["id"], "domains": s["domains"], "tier": s["tier"], "limits": s["limits"]} for s in __import__("app.core.event_register", fromlist=["x"]).approved_sources()["sources"]]}
    out = event_discovery.discover_from_events(entity_id, [shape.register_event(r) for r in run["events"]], meta, limit=limit, recency_days=recency_days, as_of=as_of or run_date,
                                               as_of_basis="the date of the discovery run" if as_of is None else "supplied by the caller", admissible=shape.admissible,
                                               explainer=lambda *a: run["explanation"], limitations=shape.LIMITATIONS)
    run_exclusions = [{"id": None, "title": n["title"], "published_date": n.get("published_date") or "", "reason": f"{n['stage'].lower()}: {n['reason']}", "url": n.get("url")} for n in run["not_returned"] if n["stage"] != "SELECT"]
    for e in out["events"]:                                          # the events keep what the extractor recorded: which provider, which rule chose the category
        row = next(r for r in run["events"] if r["id"] == e["id"])
        e["discovery"] = {**row["discovery"], "review_status": status, "source_sha256": row["source_sha256"], "text_method": row["text_method"]}
    return {**out, "mode": "discovered", "available": True, "curated_available": True, "provenance": prov, "review": review,
            "not_returned": out["not_returned"] + run_exclusions}


def _key(url: str | None, title: str) -> tuple:
    return (dedupe.canonical_url(url) if url else "", " ".join(sorted(dedupe.tokens(title))))


def compare(entity_id: str, *, limit: int = 5, recency_days: int = 180, as_of: date | None = None) -> dict:
    """Curated register vs the latest dynamic discovery for one entity: counts, overlap (same source document), and what each side has that the other lacks."""
    curated = event_discovery.discover(entity_id, limit=limit, recency_days=recency_days, as_of=as_of)
    disc = discovered_response(entity_id, limit=limit, recency_days=recency_days, as_of=as_of)

    def brief(e):
        return {"id": e["id"], "title": e["title"], "published_date": e["published_date"], "url": e["sources"][0]["url"], "location": e["location"].get("label") if e["location"].get("mapped") else None,
                "category": e["category"]}

    c_events, d_events = [brief(e) for e in curated["events"]], [brief(e) for e in disc["events"]]
    c_urls = {dedupe.canonical_url(e["url"]): e for e in c_events}
    d_urls = {dedupe.canonical_url(e["url"]): e for e in d_events}
    both = [{"curated": c_urls[u], "discovered": d_urls[u]} for u in sorted(c_urls) if u in d_urls]
    return {
        "entity": curated["entity"], "basis": "events are matched when they cite the same source document (the URL, ignoring query strings and trailing slashes)",
        "curated": {"label": "Curated register (reproducible fallback and regression benchmark)", "available": True, "count": len(c_events), "events": c_events,
                    "as_of": curated["query"]["as_of"], "coverage": curated["register"]["coverage"]},
        "discovered": {"label": "Dynamic discovery (approved sources, machine-verified)", "available": disc["available"], "count": len(d_events), "events": d_events, "as_of": disc["query"]["as_of"],
                       "reason_unavailable": None if disc["available"] else disc["explanation"], "review_status": (disc.get("review") or {}).get("status"),
                       "run_id": (disc.get("provenance") or {}).get("run_id")},
        "overlap": {"in_both": both, "only_curated": [c_urls[u] for u in sorted(c_urls) if u not in d_urls], "only_discovered": [d_urls[u] for u in sorted(d_urls) if u not in c_urls]},
        "how_they_differ": [
            "The curated register is a fixed, human-reviewed set built on a stated date. It does not change, which makes it the benchmark and the fallback.",
            "Dynamic discovery reads the configured approved sources at the time an operator runs it, so it can include newer events the register lacks, and can miss older ones outside its window or provider coverage.",
            "Both use the same selection rules and the same documented-relationship graph; neither estimates impact.",
        ],
    }
