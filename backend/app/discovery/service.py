"""Event discovery run: resolve the entity, search approved providers, retrieve, extract, deduplicate, verify, select up to five, and stage the evidence for review.

Every stage records real counts and timings in the Studio ledger. If a provider is unavailable the run says so; nothing is simulated.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from ..core import event_discovery, event_register as reg
from ..studio import pipeline
from ..studio.pipeline import _Timer
from ..studio.store import StudioStore, canonical_json
from . import agent, dedupe, extract, net, providers as prov, verify
from .shape import LIMITATIONS, admissible, register_event
from .entity import build_query, resolve_entity

SELECTION_CRITERIA = [
    "Eligible: the source host is on the approved list, the retrieved text contains the quoted passages, the title and the publication date, and the company is named in the cited evidence.",
    "Excluded: scenarios and hypotheticals, general background without a dated announcement, duplicate reports of the same event, and anything outside the recency window.",
    "Ranking: newest publication first; ties go to events that name the company in the title, then to the more authoritative source (issuer, then regulator, then related party), then to more verified passages.",
    "At most five are returned. This is NOT a ranking by financial impact or importance: no impact model exists, and none is estimated.",
]
def host_policy_ok(host: str) -> bool:
    return prov.host_ok(host)


def to_row(c: extract.Candidate, raw_sha: str, run_id: str) -> dict:
    d = c.doc
    day = d.retrieved_at[:10]
    return {
        "id": c.id, "entity_id": c.entity_id, "kind": "REAL_EVENT", "title": c.title, "category": c.category,
        "published_date": c.published_date, "event_date": c.event_date, "event_date_basis": c.event_date_basis,
        "location": {k: v for k, v in c.location.items() if v is not None},
        "source_url": d.final_url, "source_publisher": d.publisher, "source_tier": d.tier, "approved_source_id": d.approved_source_id, "source_title": d.title,
        "source_published_date": d.published_date, "retrieved_at": day, "source_sha256": raw_sha, "text_method": d.text_method,
        "evidence_quotes": list(c.evidence_quotes),
        "verification": {**c.verification, "checked_at": day},
        "discovery": {"provider_id": d.provider_id, "category_method": c.category_method, "also_reported_by": list(c.also_reported_by)},
    }


def explain(entity: dict, n: int, limit: int, recency_days: int, as_of: date, not_returned: list, total: int) -> str:
    name = entity["name"]
    if total == 0 or n == 0:
        return (f"Dynamic discovery found no verified event naming {name} within {recency_days} days of {as_of.isoformat()} in the approved sources it could search. "
                "None are invented; see the provider status and the exclusions for what was looked at.")
    skipped = [r for r in not_returned if "is not named" not in r["reason"]]
    if n < limit:
        return (f"Returned {n} verified event(s), fewer than the {limit} requested: only {n} met every rule within {recency_days} days of {as_of.isoformat()}. "
                f"{len(skipped)} other candidate(s) were excluded (see not_returned). No events were added to fill the count.")
    return f"Returned the {n} newest verified events naming {name} within {recency_days} days of {as_of.isoformat()}; the others are listed with the reason they were not returned."


def run_explanation(name: str, n: int, limit: int, window_days: int, as_of: date, funnel: dict, statuses: list) -> str:
    unavailable = [s for s in statuses if s["status"] in ("UNAVAILABLE", "ERROR")]
    searched = [s["label"] for s in statuses if s["status"] == "SEARCHED"]
    where = "searched " + ", ".join(searched) if searched else "could not search any approved source"
    head = (f"Dynamic discovery {where}. {funnel['listed_by_providers']} item(s) were listed, {funnel['excluded_before_retrieval']} were not retrieved (unapproved host or outside the window), "
            f"{funnel['retrieved']} were retrieved and {funnel['candidates_extracted']} passed extraction and verification.")
    if n == 0:
        tail = f" No verified event naming {name} within {window_days} days of {as_of.isoformat()} was found. None are invented."
    elif n < limit:
        tail = f" Returned {n} verified event(s), fewer than the {limit} requested; no event was added to fill the count."
    else:
        tail = f" Returned the {n} newest verified events naming {name}."
    return head + tail + (" Provider unavailable: " + "; ".join(f"{s['label']} ({s['reason']})" for s in unavailable) + "." if unavailable else "") + " Every exclusion is listed with its reason."


def run(store: StudioStore, text: str, *, transport=None, client="auto", as_of: date | None = None, window_days: int = 180, limit: int = 5, operator: str = "operator",
        provider_list=None, stage: bool = True) -> dict:
    as_of = as_of or datetime.now(timezone.utc).date()
    window_start = as_of - timedelta(days=window_days)
    limit = max(1, min(limit, event_discovery.MAX_LIMIT))
    resolution = resolve_entity(text)
    base = {"mode": "dynamic_discovery", "as_of": as_of.isoformat(), "window": [window_start.isoformat(), as_of.isoformat()], "window_days": window_days, "limit": limit,
            "selection_criteria": SELECTION_CRITERIA, "limitations": LIMITATIONS, "resolution": resolution.as_dict()}
    if resolution.status != "RESOLVED":
        return {**base, "status": "ENTITY_" + resolution.status, "run_id": None, "entity": None, "selected_event_ids": [], "providers": [], "explanation":
                (f"'{text}' could not be resolved to one canonical company ({resolution.reason}). Nothing was searched.")}
    query = build_query(resolution.entity_id)
    entity = {"entity_id": query.entity_id, "name": query.name, "ticker": query.ticker, "country": query.country}
    transport = transport or net.HttpTransport(host_policy_ok)
    client = agent.configured_client() if client == "auto" else client
    plist = provider_list if provider_list is not None else prov.load_providers()
    key = hashlib.sha256(f"{query.entity_id}|{as_of}|{window_days}|{limit}".encode()).hexdigest()[:8]
    run_id = f"disc-{query.entity_id.lower()}-{as_of.isoformat()}-{key}"
    rejections, statuses, docs = [], [], []
    store.add_event(run_id, "DISCOVER", "STARTED", message=f"{text} -> {query.entity_id}", counts={"limit": limit, "window_days": window_days})

    with _Timer(store, run_id, "DISCOVER_SEARCH") as st:
        listed = 0
        for p in plist:
            s = {"id": p.id, "label": p.label, "approved_source": p.source["id"]}
            if not p.applies(query.entity_id):
                statuses.append({**s, "status": "NOT_APPLICABLE", "reason": f"configured for {', '.join(p.cfg['entities'])} only; not used for {query.entity_id}"})
                continue
            try:
                refs, excluded, notes = p.search(query, transport, window_start=window_start, as_of=as_of)
            except net.FetchRefused as exc:
                statuses.append({**s, "status": "UNAVAILABLE", "reason": f"{exc.code}: {exc.message}"})
                continue
            except (ValueError, KeyError) as exc:                 # a provider returned something unusable: report, do not guess
                statuses.append({**s, "status": "ERROR", "reason": f"{type(exc).__name__}: {str(exc)[:120]}"})
                continue
            listed += len(refs) + len(excluded)
            statuses.append({**s, "status": "SEARCHED", "reason": "; ".join(notes), "listed": len(refs) + len(excluded), "excluded_before_retrieval": len(excluded), "to_retrieve": len(refs)})
            rejections += [{"stage": "SEARCH", **{k: x.get(k) for k in ("reason", "url", "title", "published_date")}} for x in excluded]
            for ref in refs:
                try:
                    docs.append((p, p.retrieve(ref, transport)))
                except net.FetchRefused as exc:
                    rejections.append({"stage": "RETRIEVE", "reason": f"{exc.code}: {exc.message}", "url": ref.url, "title": ref.title, "published_date": ref.published_date})
        st.counts = {"providers_searched": sum(1 for s in statuses if s["status"] == "SEARCHED"), "items_listed": listed, "documents_retrieved": len(docs)}

    gaz = reg.gazetteer()
    cands, ai = [], {"configured": client is not None, "used_on_documents": 0, "category_suggestions": 0, "extra_quotes_accepted": 0, "dropped": []}
    rel_candidates = []
    with _Timer(store, run_id, "DISCOVER_EXTRACT") as st:
        for p, doc in docs:
            cand, rej = extract.extract(doc, query, gaz)
            if rej:
                rejections.append({"stage": rej.stage, **{k: getattr(rej, k) for k in ("reason", "url", "title", "published_date")}})
                continue
            r = agent.refine(client, text=doc.text, candidate=cand, query=query)
            if r["used"]:
                ai["used_on_documents"] += 1
                if r["category"] and r["category"] != cand.category:
                    cand.category, cand.category_method = r["category"], "AI suggestion, validated against the allowed categories"
                    ai["category_suggestions"] += 1
                before = list(cand.evidence_quotes)
                for q in r["quotes"]:
                    if q not in cand.evidence_quotes and len(cand.evidence_quotes) < 4:
                        cand.evidence_quotes.append(q)
                if cand.evidence_quotes != before:                   # added passages are verified exactly like the extractor's own, or they are discarded
                    again = verify.verify_candidate(text=doc.text, method=doc.text_method, published_date=cand.published_date, title=doc.title, quotes=cand.evidence_quotes,
                                                    basis_text=cand.location.get("basis_text"), record=json.loads(doc.raw) if doc.text_method == "api_json" else None)
                    if again["problems"]:
                        cand.evidence_quotes = before
                    else:
                        again["verification"]["checked_at"] = doc.retrieved_at
                        cand.verification = again["verification"]
                        ai["extra_quotes_accepted"] += len(cand.evidence_quotes) - len(before)
                for rel in r["relationships"]:
                    rel_candidates.append({**rel, "event_id": cand.id, "source_url": doc.final_url})
            ai["dropped"] += [{**d, "event_id": cand.id} for d in r["dropped"]]
            cands.append(cand)
        st.counts = {"candidates": len(cands), "rejected": len([x for x in rejections if x["stage"] in ("CLASSIFY", "RELEVANCE", "VERIFY", "EXTRACT")])}
    with _Timer(store, run_id, "DISCOVER_DEDUPE") as st:
        primaries, dup = dedupe.dedupe(cands)
        rejections += dup
        st.counts = {"events": len(primaries), "duplicates_collapsed": len(dup)}

    rows, raw_sha = [], {}
    with _Timer(store, run_id, "DISCOVER_VERIFY") as st:
        for c in primaries:
            sha = hashlib.sha256(c.doc.raw).hexdigest()
            store.put_raw(c.doc.raw)
            raw_sha[c.id] = sha
            rows.append(to_row(c, sha, run_id))
        st.counts = {"events_with_stored_evidence": len(rows)}

    meta = {"built_at": as_of.isoformat(), "coverage": f"Dynamic discovery run {run_id}", "events_total": len(rows), "approved_sources": [
        {"id": s["id"], "domains": s["domains"], "tier": s["tier"], "limits": s["limits"]} for s in reg.approved_sources()["sources"]]}
    with _Timer(store, run_id, "DISCOVER_SELECT") as st:
        result = event_discovery.discover_from_events(query.entity_id, [register_event(r) for r in rows], meta, limit=limit, recency_days=window_days, as_of=as_of,
                                                      admissible=admissible, explainer=explain, limitations=LIMITATIONS)
        selected_ids = [e["id"] for e in result["events"]]
        st.counts = {"selected": len(selected_ids), "not_returned": len(result["not_returned"])}
    selected_rows = [r for r in rows if r["id"] in set(selected_ids)]
    selected_rows.sort(key=lambda r: selected_ids.index(r["id"]))

    staging_job = None
    status = "NO_EVENTS" if not selected_rows else "STAGED"
    if stage and selected_rows:
        payload = canonical_json({"discovered_events": selected_rows}).encode("utf-8")
        out = pipeline.ingest(store, payload, source_id=f"discovery-{query.entity_id.lower()}", filename=f"discovered-{query.entity_id}-{as_of.isoformat()}.json",
                              target="discovered_events", scope=query.entity_id, classification="PUBLIC", operator=operator, as_of=as_of)
        staging_job = out["job"]["job_id"]
        status = "STAGED_WITH_FINDINGS" if out["job"]["blocking"] else "STAGED"

    funnel = {"listed_by_providers": sum(s.get("listed", 0) for s in statuses), "excluded_before_retrieval": sum(s.get("excluded_before_retrieval", 0) for s in statuses),
              "retrieved": len(docs), "candidates_extracted": len(cands), "after_deduplication": len(primaries), "selected": len(selected_rows)}
    record = {
        **base, "run_id": run_id, "status": status, "entity": entity, "query": query.as_dict(), "providers": statuses, "funnel": funnel, "ai": {
            **ai, "mode": ("AI-assisted extraction; every suggestion was re-verified deterministically" if ai["used_on_documents"] else
                           "deterministic extraction only (no language model was configured or reachable)" if not client else "AI configured but unused or unreachable; deterministic extraction stood")},
        "selected_event_ids": selected_ids, "events": selected_rows, "not_returned": sorted(rejections + [{"stage": "SELECT", **{k: r[k] for k in ("title", "published_date", "reason")}, "url": None} for r in result["not_returned"]],
                                                                                             key=lambda r: (r.get("published_date") or "", r.get("url") or ""), reverse=True),
        "relationship_candidates": rel_candidates, "explanation": run_explanation(entity["name"], len(selected_rows), limit, window_days, as_of, funnel, statuses), "staging_job_id": staging_job, "ran_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    store.save_run(record)
    store.add_event(run_id, "DISCOVER", "COMPLETED", message=status, counts=funnel)
    return record
