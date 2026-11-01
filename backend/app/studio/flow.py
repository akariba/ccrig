"""The processing-flow view of the Studio: the recorded pipeline as eight stages, a structured event contract, and a per-job projection.

Nothing here runs or simulates anything. It reads what the pipeline and the review mechanism already persisted (the hash-chained ledger, findings, staging, decisions,
releases) and shapes it for display:

    SOURCE -> PARSE -> PROFILE -> VALIDATE -> RESOLVE -> EVIDENCE -> REVIEW -> PROMOTE

Every structured event is derived from exactly one persisted ledger row (`id` is its sequence number; `hash` is the ledger hash), so the display can be compared with the
backend history event by event. A few ledger rows expand into several structured events (e.g. an approval is a REVIEW event and a PROMOTE event); those carry ids such as
"41" and "41.1". Metrics that were not measured are reported as unavailable, never estimated.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..core import event_entities
from ..core.config import BACKEND_DIR
from . import acquire, overlay, relationships
from .config import limits as default_limits
from .contracts import CONTRACTS, RELATION_SEMANTICS
from .store import StudioStore

STAGES = [("SOURCE", "Source"), ("PARSE", "Parse"), ("PROFILE", "Profile"), ("VALIDATE", "Validate"), ("RESOLVE", "Resolve"),
          ("EVIDENCE", "Evidence"), ("REVIEW", "Review"), ("PROMOTE", "Promote")]
STAGE_IDS = [s for s, _ in STAGES]
PIPE_TO_STAGE = {"ACQUIRE": "SOURCE", "PARSE": "PARSE", "PROFILE": "PROFILE", "VALIDATE": "VALIDATE", "RESOLVE": "RESOLVE", "CHECK": "EVIDENCE", "STAGE": "EVIDENCE"}

# Stage states. QUEUED is the absence of any event.
RUNNING, COMPLETED, WARNINGS, FAILED, FAILED_CHECKS = "RUNNING", "COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED", "FAILED_CHECKS"
AWAITING, BLOCKED, APPROVED, REJECTED, ROLLED_BACK, SKIPPED, QUEUED = "AWAITING_REVIEW", "BLOCKED", "APPROVED", "REJECTED", "ROLLED_BACK", "SKIPPED", "QUEUED"

UNAVAILABLE_METRICS = [
    {"metric": "throughput", "reason": "records per second were not measured; the pipeline records stage durations and record counts only"},
    {"metric": "latency_percentiles", "reason": "a single run has no latency distribution"},
    {"metric": "model_usage", "reason": "no language model takes part in this pipeline; parsing, validation, resolution and evidence checks are deterministic"},
    {"metric": "quality_score", "reason": "the Studio reports findings, not a composite score"},
]

# ------------------------------------------------------------------ the stored scenario
FIXTURES = BACKEND_DIR / "tests" / "fixtures" / "discovery"
SCENARIOS = {
    "oracle-nvidia": {
        "id": "oracle-nvidia", "title": "NVIDIA -> Oracle (supplier relationship)",
        "description": "The stored excerpt of the NVIDIA/Oracle release of 27 Oct 2026 (recorded from nvidianews.nvidia.com; nothing is fetched). Two claims are made about it: that the "
                       "two companies merely appear together, and that NVIDIA supplies Oracle.",
        "page_marker": "oracle", "published_date": "2026-10-27",
        "title_text": "NVIDIA and Oracle Expand NVIDIA Vera Rubin to Multi-Gigawatt Scale and Bring NVIDIA Vera CPU to Oracle Cloud Infrastructure",
        "quote": ("NVIDIA and Oracle today announced plans to expand Oracle Cloud Infrastructure (OCI) Superclusters with NVIDIA Vera Rubin NVL72 systems to multi-gigawatt scale, "
                  "supporting growing customer demand for AI training, inference and agentic applications."),
        "source": "NVDA", "target": "ORCL", "relation": "SUPPLIES", "as_of": "2026-10-27",
        "claims": {
            "cooccurrence": {"label": "Claim A: the two companies appear in the same sentence", "source_id": "rel-naive", "assertion": {},
                             "meaning": "Declares the relationship as stated by the text, with no wording that states it. Co-occurrence is not a relationship."},
            "asserted": {"label": "Claim B: NVIDIA supplies Oracle, asserted by the proposer", "source_id": "rel-asserted",
                         "assertion": {"basis": "PROPOSER_ASSERTED", "cue": None, "direction_basis": "NVIDIA is the supplier; Oracle deploys NVIDIA systems",
                                       "rationale": "The release describes OCI Superclusters built with NVIDIA Vera Rubin NVL72 systems: Oracle deploys NVIDIA's systems, which makes NVIDIA its supplier."},
                         "meaning": "Declares the relationship with a written rationale because the sentence does not say 'supplies'. A reviewer must confirm it explicitly."},
        },
    }
}


class FlowError(ValueError):
    pass


def _page(scn: dict):
    import json as _json

    manifest = _json.loads((FIXTURES / "manifest.json").read_text())
    url = next((u for u in manifest["pages"] if scn["page_marker"] in u), None)
    if not url:
        raise FlowError("the stored source page is not available in this deployment")
    path = FIXTURES / manifest["pages"][url]
    return url, path.read_bytes()


def scenarios_status() -> list:
    out = []
    for scn in SCENARIOS.values():
        try:
            url, raw = _page(scn)
            ok = True
        except Exception:  # noqa: BLE001 - reported as unavailable, not an error
            url, raw, ok = None, b"", False
        out.append({"id": scn["id"], "title": scn["title"], "description": scn["description"], "available": ok, "source_url": url, "bytes": len(raw), "published_date": scn["published_date"],
                    "claims": [{"id": k, "label": v["label"], "meaning": v["meaning"]} for k, v in scn["claims"].items()],
                    "note": None if ok else "The stored excerpt is not shipped with this deployment."})
    return out


def scenario_preview(scenario_id: str) -> dict:
    """What the operator can inspect before starting: the stored page's identity and the companies deterministically found in its text. Reads only; stores nothing."""
    scn = SCENARIOS.get(scenario_id)
    if not scn:
        raise FlowError(f"unknown scenario {scenario_id}")
    from ..discovery import providers
    import hashlib

    url, raw = _page(scn)
    text = providers.to_text(raw, "html_text")
    return {"id": scn["id"], "title": scn["title"], "source_url": url, "source_title": scn["title_text"], "published_date": scn["published_date"], "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw), "text_chars": len(text), "quote": scn["quote"], "quote_found_verbatim": scn["quote"] in text, **mentions_of_text(text)}


def run_scenario(store: StudioStore, scenario_id: str, claim: str, *, operator: str = "operator", force_new: bool = False) -> dict:
    """Store the excerpt as evidence and submit the chosen claim through the ordinary pipeline. Returns {job, duplicate, source}."""
    import json as _json

    from . import pipeline

    scn = SCENARIOS.get(scenario_id)
    if not scn:
        raise FlowError(f"unknown scenario {scenario_id}")
    c = scn["claims"].get(claim)
    if not c:
        raise FlowError(f"unknown claim {claim}; choose one of {sorted(scn['claims'])}")
    url, raw = _page(scn)
    src = relationships.add_source(store, raw, url=url, published_date=scn["published_date"], title=scn["title_text"])
    row = {"id": f"rel-{scn['source'].lower()}-{scn['relation'].lower()}-{scn['target'].lower()}-{src['source_sha256'][:6]}", "source": scn["source"], "target": scn["target"],
           "relation": scn["relation"], "relationship_as_of": scn["as_of"], "evidence_quotes": [scn["quote"]], "source_url": src["source_url"], "source_publisher": src["source_publisher"],
           "source_tier": src["source_tier"], "approved_source_id": src["approved_source_id"], "source_title": src["source_title"], "source_published_date": src["source_published_date"],
           "retrieved_at": src["retrieved_at"], "source_sha256": src["source_sha256"], "text_method": src["text_method"], "assertion": c["assertion"],
           "verification": {**src["verification"], "quotes_total": 1, "quotes_found": 1}, "is_synthetic": False}
    data = _json.dumps({"rows": [row]}, sort_keys=True).encode()
    out = pipeline.ingest(store, data, source_id=c["source_id"], filename=f"{c['source_id']}.json", target="relationship_evidence", classification="PUBLIC",
                          operator=operator, force_new=force_new)
    return {**out, "scenario": scenario_id, "claim": claim, "source": {k: src[k] for k in ("source_url", "source_title", "source_published_date", "source_tier", "source_sha256")}}


# ------------------------------------------------------------------ what each domain supports, stated plainly
def support_matrix() -> list:
    """Per typed domain: how far the Studio takes it TODAY. Having a contract does not mean a domain is fully ingestible."""
    rows = [
        ("relationship_evidence", "Relationship evidence", "SUPPORTED",
         "Contract, source storage, quote re-verification, direction and co-occurrence rules, review with explicit acknowledgement, release, rollback and a read-only overlay in the Graph Explorer and the Event Impact Map.",
         "Approved relationships carry no criticality and never change a score; adopting one into canonical data is a deliberate, separate step."),
        ("discovered_events", "Event evidence", "PARTIAL",
         "Contract, ingestion, verification against stored sources, review, release and rollback. Event discovery runs stage events into the same review queue.",
         "Approved event releases are consumed by the Impact Map's dynamic-discovery mode, not by this page's overlay view; no impact is estimated."),
        ("reference_entities", "Reference entities", "PARTIAL",
         "Contract and checks (link kinds are kept apart from holdings); approved rows feed the linked-counterparty report.",
         "No graph overlay; a trade reference is never presented as a holding."),
        ("exposure_edges", "Portfolio holdings", "PARTIAL",
         "Contract, validation, issuer resolution, review, release, rollback and export.",
         "Approved holdings are not read by analytics until a person adopts the export; the portfolio and CCR counterparty populations are never merged."),
        ("ccr_exposures", "CCR exposures and limits", "PARTIAL",
         "Contract with typed measures, units, currencies, netting sets, limits, utilization and as-of dates; consistency and orphan checks; review and release.",
         "No measured exposure values are bundled, nothing is converted or defaulted, and no wrong-way risk is assessed from positions."),
        ("ccr_counterparties", "CCR counterparty master", "PARTIAL", "Contract, validation, review and release.", "Not read by analytics until a person adopts the export."),
        ("fact_edges", "Canonical fact edges", "PARTIAL", "Contract, validation, review and release.", "Not read by scoring until a person adopts the export."),
        ("entities", "Entity master", "PARTIAL", "Contract, validation, review and release.", "Not read by analytics until a person adopts the export."),
        ("prices", "Price history", "PARTIAL", "Contract, validation, review and release.", "Not read by analytics until a person adopts the export."),
        ("profile_only", "Any other table", "PROFILE_ONLY", "Profiled (types, completeness, duplicates) and never promoted.", "Nothing is released."),
    ]
    present = {c for c in CONTRACTS}
    out = [{"dataset": d, "label": l, "level": lv, "supported": s, "limits": lim, "contract": d in present} for d, l, lv, s, lim in rows if d in present]
    fmts = [{"format": "CSV and JSON tables", "level": "SUPPORTED", "note": "Parsed deterministically with hard size, depth and content limits."},
            {"format": "Parquet", "level": "SUPPORTED" if acquire.parquet_supported() else "UNSUPPORTED", "note": "Needs the optional parquet reader on the server."},
            {"format": "PDF, Word, scanned images, web pages as raw uploads", "level": "UNSUPPORTED", "note": "Refused on upload. Web-page evidence enters only through 'source-add' as stored evidence that rows then quote."},
            {"format": "Databases, APIs, live feeds", "level": "UNSUPPORTED", "note": "The Studio never connects to external systems on a user's behalf."}]
    return {"domains": out, "formats": fmts}


# ------------------------------------------------------------------ the structured event contract
def _destination(store: StudioStore, release_id) -> dict | None:
    rel = store.get_release(release_id) if release_id else None
    if not rel:
        return None
    return {"dataset": rel["dataset"], "scope": rel["scope"], "version": rel["version"], "release_id": rel["release_id"], "rows": rel["rows"],
            "kind": "STUDIO_OVERLAY" if rel["dataset"] == overlay.DATASET else "STUDIO_WORKSPACE_RELEASE", "canonical_data_modified": False}


def _records(pipe: str, counts: dict, ctx: dict) -> dict | None:
    c = counts or {}
    if pipe == "ACQUIRE":
        return {"unit": "bytes", "processed": c.get("bytes"), "accepted": c.get("bytes"), "rejected": 0}
    if pipe == "PARSE":
        ctx["rows"] = c.get("rows")
        return {"unit": "rows", "processed": c.get("rows"), "accepted": c.get("rows"), "rejected": 0, "columns": c.get("columns")}
    if pipe == "PROFILE":
        return {"unit": "rows", "processed": c.get("rows"), "accepted": c.get("rows"), "rejected": 0, "duplicate_rows": c.get("duplicate_rows")}
    if pipe == "VALIDATE":
        total = ctx.get("rows")
        typed = c.get("typed_rows")
        return {"unit": "rows", "processed": total, "accepted": typed, "rejected": (total - typed) if isinstance(total, int) and isinstance(typed, int) else None}
    if pipe == "RESOLVE":
        ok = (c.get("resolved") or 0) + (c.get("mapped") or 0)
        return {"unit": "identifiers", "processed": c.get("distinct_identifiers"), "accepted": ok, "rejected": (c.get("ambiguous") or 0) + (c.get("unresolved") or 0)}
    if pipe == "CHECK":
        prop, exc = c.get("proposed_rows") or 0, c.get("excluded_rows") or 0
        ctx["proposed"], ctx["check_rows"] = prop, prop + exc
        return {"unit": "rows", "processed": prop + exc, "accepted": prop, "rejected": exc}
    if pipe == "STAGE":
        prop = ctx.get("proposed")
        return {"unit": "rows", "processed": prop, "accepted": prop, "rejected": 0}
    return None


def structure(store: StudioStore, raw_events: list) -> list:
    """Persisted ledger rows -> structured events (see the module docstring). `raw_events` must be in ledger order and complete per job for record counts to carry forward."""
    jobs: dict = {}
    ctxs: dict = {}
    out: list = []

    def job_of(jid):
        if jid not in jobs:
            jobs[jid] = store.get_job(jid) if jid else None
        return jobs[jid]

    for r in raw_events:
        j = job_of(r["job_id"])
        ctx = ctxs.setdefault(r["job_id"], {})
        base = {"id": str(r["seq"]), "seq": r["seq"], "hash": r["hash"], "job_id": r["job_id"], "source_id": j["source_id"] if j else None, "source_sha256": j["sha256"] if j else None,
                "ts": r["ts"], "pipeline_stage": r["stage"], "message": r.get("message") or "", "elapsed_ms": r.get("elapsed_ms"), "error": r.get("error"),
                "stage_id": None, "state": None, "records": None, "resolution": None, "evidence": None, "review_state": None, "destination": None, "validation": None, "counts": r.get("counts")}

        def emit(n, **kw):
            out.append({**base, "id": base["id"] if n == 0 else f"{base['id']}.{n}", **kw})

        stage, kind, counts = r["stage"], r["kind"], r.get("counts") or {}
        if stage in PIPE_TO_STAGE:
            sid = PIPE_TO_STAGE[stage]
            if kind == "STARTED":
                emit(0, type="STAGE_STARTED", stage_id=sid, state=RUNNING)
            elif kind == "COMPLETED":
                rec = _records(stage, counts, ctx)
                extra = {}
                if stage == "RESOLVE":
                    extra["resolution"] = {k: counts.get(k) for k in ("distinct_identifiers", "resolved", "mapped", "ambiguous", "unresolved")}
                if stage == "STAGE" and j:
                    extra["evidence"] = {"references": evidence_references(store, j)}
                if stage == "CHECK":                                                    # EVIDENCE has two recorded steps; it completes when staging does
                    emit(0, type="STEP_COMPLETED", stage_id=sid, state=RUNNING, records=rec)
                else:
                    emit(0, type="STAGE_COMPLETED", stage_id=sid, state=COMPLETED, records=rec, **extra)
            elif kind == "FAILED":
                emit(0, type="STAGE_FAILED", stage_id=sid, state=FAILED)
        elif stage == "JOB":
            if kind == "STARTED":
                emit(0, type="JOB_STARTED")
            elif kind in ("COMPLETED", "FAILED") and j:
                n = 0
                final = (r.get("message") or j["status"]).strip()            # the status as of this event (the job may have been decided since)
                emit(n, type="JOB_COMPLETED" if kind == "COMPLETED" else "JOB_FAILED")
                by_stage: dict = {}
                rows_in_error = {f.get("row") for f in store.findings(j["job_id"]) if f.get("stage") == "CHECK" and f["severity"] == "ERROR" and f.get("row") is not None}
                for f in store.findings(j["job_id"]):
                    sid = PIPE_TO_STAGE.get(f.get("stage") or "", "SOURCE" if (f.get("stage") in ("PIPELINE", "ACQUIRE")) else None)
                    if sid:
                        d = by_stage.setdefault(sid, {"errors": 0, "warnings": 0, "codes": {}})
                        d["errors" if f["severity"] == "ERROR" else "warnings"] += 1
                        d["codes"][f["code"]] = d["codes"].get(f["code"], 0) + 1
                for sid in STAGE_IDS:
                    if sid in by_stage:
                        d = by_stage[sid]
                        n += 1
                        rec = None
                        if sid == "EVIDENCE" and rows_in_error and ctx.get("check_rows") is not None:        # a proposed row with an error finding is not accepted
                            total = ctx["check_rows"]
                            rec = {"unit": "rows", "processed": total, "accepted": max(0, total - len(rows_in_error)), "rejected": min(total, len(rows_in_error))}
                        emit(n, type="VALIDATION_RESULT", stage_id=sid, state=FAILED_CHECKS if d["errors"] else WARNINGS, validation=d, records=rec)
                if final == "PENDING_REVIEW":
                    n += 1
                    if j["blocking"]:
                        emit(n, type="REVIEW_BLOCKED", stage_id="REVIEW", state=BLOCKED, review_state=BLOCKED, message=f"{j['findings_summary']['errors']} blocking finding(s): this proposal cannot be approved")
                        n += 1
                        emit(n, type="STAGE_SKIPPED", stage_id="PROMOTE", state=SKIPPED, message="nothing is promoted while the proposal is blocked")
                    else:
                        emit(n, type="REVIEW_AWAITING", stage_id="REVIEW", state=AWAITING, review_state=AWAITING, message="waiting for a named reviewer")
                elif final == "PROFILED_ONLY":
                    for sid in ("VALIDATE", "RESOLVE", "EVIDENCE", "REVIEW", "PROMOTE"):
                        n += 1
                        emit(n, type="STAGE_SKIPPED", stage_id=sid, state=SKIPPED, message="profile-only target: profiled, never promoted")
                else:
                    failed = ctx.get("failed_stage")
                    start = STAGE_IDS.index(failed) + 1 if failed in STAGE_IDS else 0
                    for sid in STAGE_IDS[start:]:
                        n += 1
                        emit(n, type="STAGE_SKIPPED", stage_id=sid, state=SKIPPED, message=f"not reached: {final.lower().replace('_', ' ')}")
        elif stage == "SUBMIT":
            emit(0, type="DUPLICATE_SUBMISSION")
        elif stage == "REVIEW":
            rid = counts.get("release_id") or counts.get("to_release")
            if kind == "APPROVED":
                emit(0, type="REVIEW_APPROVED", stage_id="REVIEW", state=APPROVED, review_state=APPROVED)
                emit(1, type="PROMOTED", stage_id="PROMOTE", state=COMPLETED, destination=_destination(store, rid), review_state=APPROVED,
                     records={"unit": "rows", "processed": counts.get("rows"), "accepted": counts.get("rows"), "rejected": 0})
            elif kind == "REJECTED":
                emit(0, type="REVIEW_REJECTED", stage_id="REVIEW", state=REJECTED, review_state=REJECTED)
                emit(1, type="STAGE_SKIPPED", stage_id="PROMOTE", state=SKIPPED, message="rejected by the reviewer: nothing was promoted")
            elif kind in ("ROLLED_BACK", "RESTORED"):
                dest = _destination(store, counts.get("from_release"))
                emit(0, type=kind, stage_id="PROMOTE", state=ROLLED_BACK if kind == "ROLLED_BACK" else COMPLETED, destination=dest, review_state=APPROVED if kind == "RESTORED" else ROLLED_BACK)
        # remember where a job stopped, for the skipped-stage events above
        if stage in PIPE_TO_STAGE and kind == "FAILED":
            ctx["failed_stage"] = PIPE_TO_STAGE[stage]
        if stage in PIPE_TO_STAGE:
            ctx["last_stage"] = PIPE_TO_STAGE[stage]
    return out


def evidence_references(store: StudioStore, job: dict) -> list:
    """The stored source documents the submitted rows cite (relationship evidence only), from the rows as submitted."""
    refs: dict = {}
    for row in input_rows(store, job)[0]:
        sha = row.get("source_sha256") if isinstance(row, dict) else None
        if isinstance(sha, str) and sha not in refs:
            refs[sha] = {"source_sha256": sha, "source_url": row.get("source_url"), "source_publisher": row.get("source_publisher"), "source_tier": row.get("source_tier"),
                         "source_published_date": row.get("source_published_date")}
    return list(refs.values())


def input_rows(store: StudioStore, job: dict):
    """(rows, row_numbers) exactly as submitted, parsed again from the stored raw bytes; empty when the content was refused."""
    if not job.get("sha256") or not job.get("format") or job["target"] not in CONTRACTS:
        return [], []
    try:
        parsed = acquire.parse(job["format"], store.read_raw(job["sha256"]), default_limits(), CONTRACTS[job["target"]].canonical_list_key)
        return parsed.rows, parsed.row_numbers
    except Exception:  # noqa: BLE001 - a refused or damaged upload simply has no readable rows
        return [], []


# ------------------------------------------------------------------ mentions
def mentions_of_text(text: str, *, cap: int = 60) -> dict:
    found = event_entities.resolve_text(text)
    names: dict = {}
    items = []
    for m in found:
        eid = m["entity_id"]
        if eid not in names:
            ent = event_entities.STORE.entity(eid)
            names[eid] = {"entity_id": eid, "name": ent["name"], "ticker": ent.get("ticker"), "count": 0}
        names[eid]["count"] += 1
        if len(items) < cap:
            lo, hi = max(0, m["start"] - 70), min(len(text), m["end"] + 70)
            items.append({"entity_id": eid, "matched_text": m["matched_text"], "rule": m["rule"], "start": m["start"], "end": m["end"], "context": text[lo:hi], "context_offset": m["start"] - lo})
    return {"mentions": items, "mention_total": len(found), "entities": sorted(names.values(), key=lambda e: (-e["count"], e["entity_id"])),
            "note": "Companies are found by the platform's deterministic name, brand and ticker rules. A mention is not a relationship."}


def source_documents(store: StudioStore, job: dict) -> list:
    from ..discovery import providers

    docs = []
    for ref in evidence_references(store, job):
        doc = dict(ref)
        try:
            raw = store.read_raw(ref["source_sha256"])
            text = providers.to_text(raw, "html_text")
            doc.update({"stored": True, "bytes": len(raw), "text_chars": len(text), **mentions_of_text(text)})
        except Exception as exc:  # noqa: BLE001
            doc.update({"stored": False, "problem": f"{type(exc).__name__}: {str(exc)[:120]}", "mentions": [], "entities": [], "mention_total": 0})
        docs.append(doc)
    return docs


# ------------------------------------------------------------------ assessments (relationship evidence)
def assessments(store: StudioStore, job: dict, staging: dict | None) -> list:
    if job["target"] != overlay.DATASET:
        return []
    from ..discovery import providers

    rows, nums = input_rows(store, job)
    findings = store.findings(job["job_id"])
    texts: dict = {}
    out = []
    for row, n in zip(rows, nums):
        if not isinstance(row, dict):
            continue
        sha, quotes = row.get("source_sha256"), row.get("evidence_quotes") or []
        if sha not in texts:
            try:
                texts[sha] = providers.to_text(store.read_raw(sha), row.get("text_method") or "html_text")
            except Exception:  # noqa: BLE001
                texts[sha] = None
        per_quote = []
        for q in quotes if isinstance(quotes, list) else []:
            ok = all(isinstance(row.get(k), str) for k in ("relation", "source", "target")) and isinstance(q, str)
            a = relationships.analyse(row.get("relation"), row.get("source"), row.get("target"), q) if ok else {}
            spans, between = [], None
            if ok:
                ms = [m for m in event_entities.resolve_text(q) if m["entity_id"] in (row["source"], row["target"])]
                spans = [{"entity_id": m["entity_id"], "start": m["start"], "end": m["end"], "role": "source" if m["entity_id"] == row["source"] else "target"} for m in ms]
                if a.get("both"):
                    first = {m["entity_id"]: m for m in reversed(ms)}
                    lo, hi = sorted((first[row["source"]], first[row["target"]]), key=lambda m: m["start"])
                    between = q[lo["end"]:hi["start"]]
            per_quote.append({"quote": q, "found_in_stored_source": (q in texts[sha]) if texts[sha] is not None and isinstance(q, str) else None, **a, "spans": spans, "between": between})
        mine = [f for f in findings if f.get("row") == n]
        errs = [f for f in mine if f["severity"] == "ERROR"]
        warn = [f for f in mine if f["severity"] == "WARN"]
        if errs:
            verdict, why = "REJECTED", errs[0]["message"]
        elif any(f["code"] == "NO_EXPLICIT_CUE" for f in warn):
            verdict, why = "ASSERTED_NEEDS_ACKNOWLEDGEMENT", next(f["message"] for f in warn if f["code"] == "NO_EXPLICIT_CUE")
        else:
            verdict, why = "SUPPORTED_EXPLICIT", "the quoted wording states the relationship in the stated direction"
        sem = RELATION_SEMANTICS.get(row.get("relation"))
        out.append({"row": n, "source": row.get("source"), "relation": row.get("relation"), "target": row.get("target"), "semantics": sem, "as_of": row.get("relationship_as_of"),
                    "assertion": row.get("assertion") or {}, "quotes": per_quote, "verdict": verdict, "why": why,
                    "findings": [{"severity": f["severity"], "code": f["code"], "message": f["message"]} for f in mine]})
    return out


# ------------------------------------------------------------------ the projection
def _connections(stages: dict) -> list:
    def n(s, k):
        return (stages[s].get("records") or {}).get(k)

    texts = {
        ("SOURCE", "PARSE"): lambda: f"the stored raw file ({(stages['SOURCE'].get('outputs') or {}).get('bytes')} bytes, hash-addressed)",
        ("PARSE", "PROFILE"): lambda: f"{n('PARSE', 'processed')} parsed rows",
        ("PROFILE", "VALIDATE"): lambda: f"{n('PROFILE', 'processed')} rows with their profile",
        ("VALIDATE", "RESOLVE"): lambda: f"{n('VALIDATE', 'accepted')} typed rows ({n('VALIDATE', 'rejected')} rejected on the way)",
        ("RESOLVE", "EVIDENCE"): lambda: f"rows with resolved identifiers ({n('RESOLVE', 'accepted')} of {n('RESOLVE', 'processed')} identifiers accepted)",
        ("EVIDENCE", "REVIEW"): lambda: f"{n('EVIDENCE', 'accepted')} proposed rows and {n('EVIDENCE', 'rejected')} excluded, with the staged comparison",
        ("REVIEW", "PROMOTE"): lambda: "the approved proposal, published as a versioned release",
    }
    out = []
    for (a, b), fn in texts.items():
        sa, sb = stages[a]["state"], stages[b]["state"]
        ran = sa in (COMPLETED, WARNINGS, FAILED_CHECKS, APPROVED, ROLLED_BACK)
        if b == "REVIEW":                                         # the approval gate: data arrives and either waits, is held, or is decided
            state = "AWAITING" if sb == AWAITING else "HELD" if sb == BLOCKED else "FLOWED" if sb in (APPROVED, REJECTED) else "IDLE"
        elif a == "REVIEW":
            state = "FLOWED" if sb in (COMPLETED, ROLLED_BACK) else "HELD" if sb == SKIPPED and sa in (BLOCKED, REJECTED) else "IDLE"
        else:
            state = "FLOWED" if ran and sb not in (QUEUED, SKIPPED) else "HELD" if ran and sb == SKIPPED else "IDLE"
        try:
            what = fn()
        except Exception:  # noqa: BLE001
            what = None
        out.append({"from": a, "to": b, "state": state, "what": what if state != "IDLE" else None})
    return out


def project(store: StudioStore, job_id: str) -> dict | None:
    job = store.get_job(job_id)
    if not job:
        return None
    raw = store.events(job_id)
    events = structure(store, raw)
    contract = CONTRACTS.get(job["target"])
    staging = store.load_staging(job_id)
    findings = store.findings(job_id)
    decisions = store.decisions(job_id)

    st = {sid: {"id": sid, "label": label, "state": QUEUED, "started_at": None, "finished_at": None, "duration_ms": None, "records": None, "events": [], "findings": [], "resolution": None, "evidence": None, "destination": None, "message": None}
          for sid, label in STAGES}
    for e in events:
        sid = e["stage_id"]
        if not sid:
            continue
        s = st[sid]
        s["events"].append(e["id"])
        if e["state"] and not (e["type"] == "VALIDATION_RESULT" and s["state"] == FAILED):      # a stage that failed outright stays FAILED
            s["state"] = e["state"]
        if e["type"] == "STAGE_STARTED" and not s["started_at"]:
            s["started_at"] = e["ts"]
        s["finished_at"] = e["ts"] if e["state"] not in (RUNNING,) or e["type"] == "STEP_COMPLETED" else s["finished_at"]
        if e["elapsed_ms"] is not None and e["type"] in ("STAGE_COMPLETED", "STAGE_FAILED"):
            s["duration_ms"] = (s["duration_ms"] or 0) + e["elapsed_ms"]
        if e["type"] == "STEP_COMPLETED" and e["elapsed_ms"] is not None:
            s["duration_ms"] = (s["duration_ms"] or 0) + e["elapsed_ms"]
        for k in ("records", "resolution", "evidence", "destination"):
            if e.get(k):
                s[k] = e[k]
        if e["message"] and e["type"] in ("STAGE_SKIPPED", "REVIEW_BLOCKED", "REVIEW_AWAITING"):
            s["message"] = e["message"]
    for f in findings:
        sid = PIPE_TO_STAGE.get(f.get("stage") or "", "SOURCE" if f.get("stage") in ("PIPELINE", "ACQUIRE") else None)
        if sid:
            st[sid]["findings"].append({"severity": f["severity"], "code": f["code"], "message": f["message"], "row": f.get("row"), "field": f.get("field")})

    manifest = job.get("manifest") or {}
    profile = job.get("profile") or {}
    st["SOURCE"]["inputs"] = {"filename": job["filename"], "declared_target": job["target"], "classification": job["classification"], "operator": job["operator"]}
    st["SOURCE"]["outputs"] = {"format": job["format"], "bytes": job["bytes"], "sha256": job["sha256"], "stored": "hash-addressed raw file in the operator workspace"}
    st["PARSE"]["inputs"] = {"format": job["format"], "bytes": job["bytes"]}
    st["PARSE"]["outputs"] = {"rows": (st["PARSE"]["records"] or {}).get("processed"), "columns": (st["PARSE"]["records"] or {}).get("columns")}
    st["PROFILE"]["outputs"] = {k: profile.get(k) for k in ("rows", "duplicate_rows", "schema_inconsistencies") if k in profile}
    st["VALIDATE"]["inputs"] = {"contract": job["target"], "key": list(contract.key) if contract else None, "checks": list(contract.checks) if contract else None}
    st["RESOLVE"]["inputs"] = {"universe": "issuer / portfolio / CCR identifiers are resolved in their own universes and never merged", "rule": "exact identifiers first; never fuzzy"}
    if staging:
        st["RESOLVE"]["outputs"] = {"mappings": staging.get("mappings") or []}
        st["EVIDENCE"]["outputs"] = {"proposed_rows": len(staging.get("proposed_rows") or []), "excluded_rows": staging.get("excluded") or [], "vs_previous_release": staging.get("vs_previous_release"),
                                     "vs_canonical": staging.get("vs_canonical"), "graph_effect": staging.get("graph_effect"), "assertions_to_confirm": staging.get("assertions_to_confirm")}
    st["REVIEW"]["inputs"] = {"decisions": [{"decision": d["decision"], "reviewer": d["reviewer"], "reason": d["reason"], "at": d["at"], "detail": d["detail"]} for d in decisions]}

    # the job's overall state; a job that never recorded its end is INTERRUPTED once a stage failed or nothing has been recorded for two minutes
    state = {"PENDING_REVIEW": BLOCKED if job["blocking"] else AWAITING, "APPROVED": APPROVED, "REJECTED": REJECTED, "REJECTED_INPUT": "REFUSED", "FAILED": FAILED, "PROFILED_ONLY": "PROFILED_ONLY"}.get(job["status"])
    if job["status"] == "ACQUIRING":
        age = (datetime.now(timezone.utc) - datetime.strptime(raw[-1]["ts"] if raw else job["updated_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)).total_seconds()
        state = "INTERRUPTED" if (any(s["state"] == FAILED for s in st.values()) or age > 120) else RUNNING
    if st["PROMOTE"]["state"] == ROLLED_BACK:
        state = ROLLED_BACK

    review = {"state": st["REVIEW"]["state"], "decisions": st["REVIEW"]["inputs"]["decisions"], "requires": None, "can_approve": False, "blocked_because": None}
    if job["status"] == "PENDING_REVIEW" and staging:
        mappings = [m for m in (staging.get("mappings") or []) if m.get("requires_acknowledgement")]
        reverse = [e for e in (staging.get("graph_effect") or {}).get("edges", []) if e.get("reverse_edge_in_canonical")]
        changed = (staging["vs_previous_release"].get("changed", 0) or 0) + (staging["vs_canonical"].get("changed", 0) or 0)
        review["requires"] = {"acknowledge_assertions": bool(staging.get("assertions_to_confirm")), "acknowledge_mappings": bool(mappings), "acknowledge_changes": bool(changed or reverse),
                              "assertions_to_confirm": staging.get("assertions_to_confirm") or []}
        review["can_approve"] = not job["blocking"]
        if job["blocking"]:
            review["blocked_because"] = [{"code": f["code"], "message": f["message"]} for f in findings if f["severity"] == "ERROR"][:6]

    out = {"job": {k: job[k] for k in ("job_id", "source_id", "filename", "format", "sha256", "bytes", "target", "scope", "classification", "operator", "status", "blocking", "created_at", "updated_at", "elapsed_ms", "error_code", "error_message", "duplicate_of")},
           "state": state, "stages": [st[s] for s in STAGE_IDS], "connections": None, "events": events, "review": review,
           "source_documents": source_documents(store, job) if job["target"] == overlay.DATASET else [], "assessments": assessments(store, job, staging),
           "quality": {"summary": job.get("findings_summary"), "findings": findings[:200]},
           "proposal": _proposal(staging), "destination": destination(store, job, staging),
           "metrics": {"measured": {"job_elapsed_ms": job["elapsed_ms"], "stage_ms": {s: st[s]["duration_ms"] for s in STAGE_IDS if st[s]["duration_ms"] is not None},
                                    "bytes": job["bytes"], "rows_parsed": (st["PARSE"]["records"] or {}).get("processed")}, "unavailable": UNAVAILABLE_METRICS},
           "ledger": store.verify_chain(), "recorded": False}
    out["connections"] = _connections(st)
    out["manifest"] = {k: manifest.get(k) for k in ("received_at", "tool_version", "limits", "scope_input")}
    return out


def _proposal(staging: dict | None) -> list:
    """The typed, directed relationships the job proposes, with their provenance."""
    if not staging or staging.get("dataset") != overlay.DATASET:
        return []
    out = []
    for r in staging.get("proposed_rows") or []:
        out.append({"source": r["source"], "relation": r["relation"], "target": r["target"], "semantics": RELATION_SEMANTICS.get(r["relation"]), "as_of": r["relationship_as_of"],
                    "provenance": {k: r.get(k) for k in ("source_url", "source_publisher", "source_tier", "source_title", "source_published_date", "retrieved_at", "source_sha256", "text_method")},
                    "quotes": r["evidence_quotes"], "assertion": r["assertion"], "verification": r["verification"], "is_synthetic": r["is_synthetic"]})
    return out


def destination(store: StudioStore, job: dict, staging: dict | None) -> dict:
    """Where an approved job's data lives now, and whether the canonical data was touched (never)."""
    contract = CONTRACTS.get(job["target"])
    dest = {"dataset": job["target"], "kind": "STUDIO_OVERLAY" if job["target"] == overlay.DATASET else "STUDIO_WORKSPACE_RELEASE", "canonical_data_modified": False, "status": "NOT_PROMOTED",
            "current_release": None, "edges": [], "links": [], "adoption": None}
    if not contract or not contract.promotable:
        dest["status"] = "NOT_PROMOTABLE"
        return dest
    current = store.current(job["target"], job["scope"] or "")
    rels = store.releases(job["target"], job["scope"] or "")
    mine = [r for r in rels if r["job_id"] == job["job_id"]]
    if current:
        dest["current_release"] = {k: current[k] for k in ("release_id", "version", "rows", "approved_by", "created_at", "content_hash")}
    if mine:
        dest["released_as"] = [{k: r[k] for k in ("release_id", "version", "status", "approved_by", "created_at")} for r in mine]
    if job["target"] != overlay.DATASET:
        dest["status"] = ("LIVE" if current and any(r["release_id"] == current["release_id"] for r in mine) else ("ROLLED_BACK" if mine else "NOT_PROMOTED"))
        return dest
    keys = {(r["source"], r["relation"], r["target"]) for r in (staging or {}).get("proposed_rows") or []}
    edges, release = overlay.load(store)
    live = [e for e in edges if (e["source"], e["relation"], e["target"]) in keys]
    dest["edges"] = [{"source": e["source"], "relation": e["relation"], "target": e["target"], "visible_in_overlay": True} for e in live]
    if live:
        dest["status"] = "LIVE_IN_OVERLAY"
        ends = sorted({x for e in live for x in (e["source"], e["target"])})
        dest["links"] = [{"label": f"Graph Explorer: {t}, approved relationships on", "href": f"/graph?id={t}&studio=1", "testid": f"open-graph-{t}"} for t in ends if t != live[0]["source"]] + [
            {"label": "Event Impact Map, dynamic discovery, approved relationships on", "href": "/event-impact-map?source=discovered&studio=1", "testid": "open-impact-map"}]
        try:
            from . import impact

            cur = store.current("reference_entities", "")
            refs = store.read_release(cur["release_id"])["rows"] if cur else []
            eff = impact.adoption_effect(edges, refs)
            dest["adoption"] = {"connectivity": {k: eff["connectivity"].get(k) for k in ("canonical", "with_approved", "newly_connected_issuers")},
                                "scoring_changed_by_approval": eff["analytical_coverage"]["scoring_changed_by_approval"], "linked_counterparties": eff["linked_counterparties"], "gaps": eff["gaps"]}
        except Exception as exc:  # noqa: BLE001 - the effect report is advisory; the overlay status above stands on its own
            dest["adoption_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    elif mine:
        dest["status"] = "ROLLED_BACK" if (not current or current["release_id"] not in {r["release_id"] for r in mine}) else "SUPERSEDED"
    return dest
