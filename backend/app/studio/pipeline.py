"""The ingestion pipeline: acquire -> parse -> profile -> validate -> resolve -> check -> stage.

Each stage records start/completion/failure events with real counts and elapsed time. A job ends PENDING_REVIEW (a person decides next),
PROFILED_ONLY (profile_only target), REJECTED_INPUT (refused before trusting the content) or FAILED (unexpected error, details recorded).
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timezone

from . import acquire
from .config import limits as default_limits
from .contracts import CONTRACTS
from .profile import profile
from .resolve import AMBIGUOUS, MAPPED, RESOLVED, canonical_index, resolve_distinct
from .stage import build_staging, canonical_rows
from .store import StudioStore
from .validate import Findings, consistency, row_has_error, type_rows

TOOL_VERSION = "studio-1"
CLASSIFICATIONS = ("PUBLIC", "INTERNAL", "CONFIDENTIAL")
_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9_.\-]{1,63}$")


class BadRequest(ValueError):
    """The caller's parameters are invalid (not a problem with the data)."""


def _check_params(source_id, target, scope, classification):
    if not _SOURCE_ID.match(source_id or ""):
        raise BadRequest("source_id must be 2-64 characters: lowercase letters, digits, '.', '_' or '-'")
    if target not in CONTRACTS:
        raise BadRequest(f"unknown target '{target}'; choose one of {sorted(CONTRACTS)}")
    contract = CONTRACTS[target]
    if contract.scoped and not scope:
        raise BadRequest(f"target '{target}' needs a scope ({contract.scope_ref} id)")
    if not contract.scoped and scope:
        raise BadRequest(f"target '{target}' does not take a scope")
    if classification not in CLASSIFICATIONS:
        raise BadRequest(f"classification must be one of {list(CLASSIFICATIONS)}")
    return contract


class _Timer:
    """Records one stage: STARTED, then COMPLETED with counts or FAILED with details; exposes elapsed milliseconds."""

    def __init__(self, store: StudioStore, job_id: str, stage: str):
        self.store, self.job_id, self.stage, self.counts = store, job_id, stage, {}

    def __enter__(self):
        self.t0 = time.monotonic()
        self.store.add_event(self.job_id, self.stage, "STARTED")
        return self

    def __exit__(self, etype, exc, tb):
        ms = round((time.monotonic() - self.t0) * 1000)
        if etype is None:
            self.store.add_event(self.job_id, self.stage, "COMPLETED", counts=self.counts, elapsed_ms=ms)
            return False
        info = {"type": etype.__name__, "code": getattr(exc, "code", None), "message": str(getattr(exc, "message", None) or exc)[:300]}
        self.store.add_event(self.job_id, self.stage, "FAILED", message=info["message"], counts=self.counts, elapsed_ms=ms, error=info)
        return False


def ingest(store: StudioStore, data: bytes, *, source_id: str, filename: str, target: str, scope: str = "", classification: str = "PUBLIC",
           operator: str = "unknown", force_new: bool = False, as_of: date | None = None, limits=None) -> dict:
    """Run one source through the pipeline. Returns {"job": ..., "duplicate": bool}. Identical resubmissions return the existing job unless force_new."""
    contract = _check_params(source_id, target, scope, classification)
    limits = limits or default_limits()
    as_of = as_of or datetime.now(timezone.utc).date()
    filename = acquire.safe_filename(filename)
    sha = acquire.sha256_hex(data)
    scope_input = scope
    if contract.scoped:
        early = canonical_index().resolve(scope, contract.scope_ref or "entity")
        if early.status == RESOLVED:
            scope = early.entity_id          # 'skhy' and 'SKHY' are the same dataset; the manifest keeps what the operator typed
    store.register_source(source_id, classification)

    existing = store.find_existing(source_id, sha, target, scope)
    if existing and not force_new:
        store.add_event(existing["job_id"], "SUBMIT", "RESUBMITTED", message="identical content from the same source for the same target; no new job was created")
        return {"job": store.get_job(existing["job_id"]), "duplicate": True}
    job = store.new_job(source_id=source_id, filename=filename, fmt=None, sha=sha, nbytes=len(data), target=target, scope=scope, classification=classification,
                        operator=operator, supersedes=existing["job_id"] if existing else None)
    job_id, t_start = job["job_id"], time.monotonic()
    store.add_event(job_id, "JOB", "STARTED", message=f"{filename} -> {target}{('/' + scope) if scope else ''}", counts={"bytes": len(data)})
    findings = Findings(limits)

    def finish(status, **extra):
        elapsed = round((time.monotonic() - t_start) * 1000)
        summary = findings.summary()
        store.add_findings(job_id, findings.items)
        store.update_job(job_id, status=status, blocking=int(summary["blocking"]), elapsed_ms=elapsed, findings_summary=summary, **extra)
        store.add_event(job_id, "JOB", "COMPLETED" if status in ("PENDING_REVIEW", "PROFILED_ONLY") else "FAILED", message=status, elapsed_ms=elapsed,
                        counts={"errors": summary["errors"], "warnings": summary["warnings"]})
        return {"job": store.get_job(job_id), "duplicate": False}

    try:
        # ---------------- ACQUIRE
        with _Timer(store, job_id, "ACQUIRE") as st:
            fmt = acquire.sniff(data, filename, limits)
            store.put_raw(data)
            manifest = {"job_id": job_id, "source_id": source_id, "filename": filename, "format": fmt, "sha256": sha, "bytes": len(data), "received_at": store.clock(),
                        "classification": classification, "operator": operator, "tool_version": TOOL_VERSION, "target": target, "scope": scope, "scope_input": scope_input,
                        "limits": {"max_bytes": limits.max_bytes, "max_rows": limits.max_rows, "max_columns": limits.max_columns, "max_depth": limits.max_depth}}
            store.update_job(job_id, format=fmt, manifest=manifest)
            st.counts = {"bytes": len(data)}
        # ---------------- PARSE
        with _Timer(store, job_id, "PARSE") as st:
            parsed = acquire.parse(fmt, data, limits, contract.canonical_list_key)
            findings.extend(parsed.findings)
            st.counts = {"rows": len(parsed.rows), "columns": len(parsed.columns)}
        # ---------------- PROFILE
        with _Timer(store, job_id, "PROFILE") as st:
            prof = profile(parsed.columns, parsed.rows, as_of=as_of, limits=limits, parse_findings=parsed.findings)
            store.update_job(job_id, profile=prof)
            st.counts = {"rows": prof["rows"], "duplicate_rows": prof["duplicate_rows"], "schema_inconsistencies": len(prof["schema_inconsistencies"])}
        if not contract.promotable:
            return finish("PROFILED_ONLY")
        # ---------------- VALIDATE (types, required values, source-to-destination compatibility)
        with _Timer(store, job_id, "VALIDATE") as st:
            typed = type_rows(contract, parsed.columns, parsed.rows, parsed.row_numbers, findings, fmt=fmt)
            scope_id = scope
            if contract.scoped:
                res = canonical_index().resolve(scope, contract.scope_ref or "entity")
                if res.status == RESOLVED:
                    scope_id = res.entity_id
                else:
                    findings.add("VALIDATE", "ERROR", "SCOPE_UNRESOLVED", f"scope '{scope}': {res.reason or res.status.lower()}")
            st.counts = {"typed_rows": len(typed), "errors": findings.summary()["errors"]}
        # ---------------- RESOLVE (exact identifiers first; explicit unresolved/ambiguous outcomes)
        with _Timer(store, job_id, "RESOLVE") as st:
            mappings, outcome = _resolve_rows(contract, typed, findings)
            st.counts = {"distinct_identifiers": outcome["distinct"], "resolved": outcome["resolved"], "mapped": outcome["mapped"], "ambiguous": outcome["ambiguous"], "unresolved": outcome["unresolved"]}
        # ---------------- CHECK (duplicates and cross-record consistency)
        with _Timer(store, job_id, "CHECK") as st:
            clean = [r for r in typed if not row_has_error(findings.items, r["_row"])]
            proposed = consistency(contract, clean, findings, as_of=as_of)
            excluded = [{"row": r["_row"], "reasons": sorted({f["code"] for f in findings.items if f.get("row") == r["_row"] and f["severity"] == "ERROR"})}
                        for r in typed if r not in proposed]
            if not proposed and not findings.summary()["blocking"]:
                findings.add("CHECK", "ERROR", "EMPTY_PROPOSAL", "no row survived validation, so there is nothing to stage")
            st.counts = {"proposed_rows": len(proposed), "excluded_rows": len(excluded)}
        # ---------------- STAGE (preview against previous approved release and canonical data)
        with _Timer(store, job_id, "STAGE") as st:
            current = store.current(contract.name, scope_id)
            prev_rows = store.read_release(current["release_id"])["rows"] if current else None
            ticker = (canonical_index().entities.get(scope_id) or {}).get("ticker") if contract.scoped else None
            staging = build_staging(contract, job_id=job_id, scope=scope_id, proposed=proposed, excluded=excluded, mappings=mappings, previous_release=current,
                                    previous_rows=prev_rows, canonical=canonical_rows(contract, scope_id, ticker))
            store.save_staging(job_id, staging)
            st.counts = {"new_vs_previous": staging["vs_previous_release"]["new"], "changed_vs_previous": staging["vs_previous_release"]["changed"],
                         "changed_vs_canonical": staging["vs_canonical"].get("changed")}
        return finish("PENDING_REVIEW", content_hash=staging["merged_hash"])
    except acquire.IngestRejected as exc:
        findings.add("ACQUIRE", "ERROR", exc.code, exc.message)
        return finish("REJECTED_INPUT", error_code=exc.code, error_message=exc.message)
    except Exception as exc:  # noqa: BLE001 - recorded with its type; the job is marked FAILED and nothing is promoted
        findings.add("PIPELINE", "ERROR", "UNEXPECTED_ERROR", f"{type(exc).__name__}: {str(exc)[:200]}")
        return finish("FAILED", error_code="UNEXPECTED_ERROR", error_message=f"{type(exc).__name__}: {str(exc)[:300]}")


def _resolve_rows(contract, typed: list, findings: Findings):
    """Resolve every reference field. Only canonical ids (exact, or exact after trim/upper-case) are applied silently; other mappings are recorded for the reviewer."""
    ref_fields = [f for f in contract.fields if f.ref]
    mappings: dict = {}
    stats = {"distinct": 0, "resolved": 0, "mapped": 0, "ambiguous": 0, "unresolved": 0}
    for f in ref_fields:
        values = [r.get(f.name) for r in typed if r.get(f.name)]
        outcomes = resolve_distinct(values, f.ref)
        stats["distinct"] += len(outcomes)
        for v, res in outcomes.items():
            if res.status == RESOLVED:
                stats["resolved"] += 1
                if res.rule != "EXACT_ID":
                    mappings.setdefault((f.name, v), res)
            elif res.status == MAPPED:
                stats["mapped"] += 1
                mappings[(f.name, v)] = res
            elif res.status == AMBIGUOUS:
                stats["ambiguous"] += 1
            else:
                stats["unresolved"] += 1
        counts: dict = {}
        for r in typed:
            v = r.get(f.name)
            if not v:
                continue
            res = outcomes[str(v)]
            if res.status in (RESOLVED, MAPPED):
                counts[(f.name, str(v))] = counts.get((f.name, str(v)), 0) + 1
                r[f.name] = res.entity_id
            else:
                code = "AMBIGUOUS_ENTITY" if res.status == AMBIGUOUS else "UNRESOLVED_ENTITY"
                findings.add("RESOLVE", "ERROR", code, f"{f.name} '{v}': {res.reason}", row=r["_row"], field=f.name, rule=res.rule, candidates=res.candidates or None)
        for (name, v), res in sorted(mappings.items()):
            if name == f.name and res.status == MAPPED:
                findings.add("RESOLVE", "WARN", "ENTITY_MAPPED", f"{name} '{v}' -> {res.entity_id} by {res.rule.lower().replace('_', ' ')} ({counts.get((name, v), 0)} rows); a reviewer must acknowledge this mapping", field=name)
    out = [{"field": n, "value": v, "entity_id": res.entity_id, "rule": res.rule, "status": res.status, "reason": res.reason, "requires_acknowledgement": res.status == MAPPED}
           for (n, v), res in sorted(mappings.items())]
    return out, stats
