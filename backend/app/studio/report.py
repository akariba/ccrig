"""Data-quality report for a staged job, grouped by the kinds of problem an analyst cares about. Pure read of the job's recorded findings."""
from __future__ import annotations

CATEGORIES = {
    "missing_references": "Identifiers that could not be resolved to a canonical entity, or required values/columns that are absent",
    "duplicate_entities": "The same record appearing more than once in the source (identical copies are collapsed; conflicting ones block)",
    "broken_joins": "Links to the wrong population, a netting set or CCR record that does not match the master, or evidence that is missing from the store",
    "inconsistent_units": "Currency, unit or limit/utilization values that cannot be compared (values are never converted or defaulted)",
    "orphan_exposures": "Exposures attached to a counterparty or netting set that the CCR master does not contain",
    "unsupported_relationship_assertions": "Relationships the quoted evidence does not establish: co-occurrence only, no supporting wording, a conflicting direction, or evidence not found in the source",
    "other": "Any other finding",
}
_BY_CODE = {
    "missing_references": {"MISSING_REQUIRED_VALUE", "MISSING_REQUIRED_COLUMN", "SCOPE_UNRESOLVED", "AMBIGUOUS_ENTITY", "NO_EVIDENCE_STORE"},
    "duplicate_entities": {"DUPLICATE_CONFLICT", "DUPLICATE_IDENTICAL", "DUPLICATE_HEADER", "DUPLICATE_JSON_KEY"},
    "broken_joins": {"NETTING_SET_CONFLICT", "PRODUCT_NOT_IN_CCR_MASTER", "DIFFERS_FROM_CCR_MASTER", "EVIDENCE_MISSING", "EVIDENCE_CORRUPT", "SELF_RELATIONSHIP", "SELF_LOOP", "INFERRED_WITHOUT_BASIS"},
    "inconsistent_units": {"INCONSISTENT_UNITS", "UTILIZATION_MISMATCH", "LIMIT_MEASURE_MISMATCH", "LIMIT_VALUE_MISSING", "LIMIT_TYPE_MISSING", "UTILIZATION_WITHOUT_LIMIT", "ZERO_LIMIT"},
    "orphan_exposures": {"ORPHAN_NETTING_SET"},
    "unsupported_relationship_assertions": {"CO_OCCURRENCE_ONLY", "UNSUPPORTED_RELATIONSHIP_ASSERTION", "DIRECTION_CONFLICT", "CUE_NOT_FOUND", "NO_EXPLICIT_CUE", "CUE_FOUND_BUT_NOT_DECLARED",
                                            "EVIDENCE_NOT_FOUND", "SYNTHETIC_RELATIONSHIP", "RELATIONSHIP_DATE_AFTER_SOURCE", "SYMMETRIC_NOT_ORDERED", "DOCUMENTED_WITHOUT_LINK", "SYNTHETIC_CLAIMS_DOCUMENTED"},
}


def categorize(finding: dict, target: str) -> str:
    code = finding["code"]
    if code == "UNRESOLVED_ENTITY":
        if finding.get("rule") in ("WRONG_UNIVERSE", "WRONG_KIND"):
            return "broken_joins"
        return "orphan_exposures" if target == "ccr_exposures" and finding.get("field") == "counterparty_id" else "missing_references"
    for cat, codes in _BY_CODE.items():
        if code in codes:
            return cat
    return "other"


def quality_report(store, job_id: str) -> dict | None:
    job = store.get_job(job_id)
    if not job:
        return None
    findings = store.findings(job_id, limit=5000)
    cats = {c: {"description": d, "errors": 0, "warnings": 0, "examples": []} for c, d in CATEGORIES.items()}
    for f in findings:
        c = cats[categorize(f, job["target"])]
        c["errors" if f["severity"] == "ERROR" else "warnings"] += 1
        if len(c["examples"]) < 5:
            c["examples"].append({k: f[k] for k in ("severity", "code", "message", "row", "field") if f.get(k) is not None})
    summary = job["findings_summary"] or {}
    staging = store.load_staging(job_id) or {}
    return {
        "job_id": job_id, "target": job["target"], "scope": job["scope"], "status": job["status"], "source": {"source_id": job["source_id"], "filename": job["filename"], "sha256": job["sha256"]},
        "blocking": job["blocking"], "errors": summary.get("errors", 0), "warnings": summary.get("warnings", 0),
        "profile": {"rows": (job["profile"] or {}).get("rows"), "proposed_rows": len(staging.get("proposed_rows", [])), "excluded_rows": len(staging.get("excluded_rows", []))},
        "categories": {k: v for k, v in cats.items() if v["errors"] or v["warnings"]},
        "clean_categories": [k for k, v in cats.items() if not (v["errors"] or v["warnings"]) and k != "other"],
        "graph_effect": staging.get("graph_effect"),
        "verdict": ("Blocked: correct the source and resubmit." if job["blocking"] else
                    "No blocking findings. Warnings need a reviewer's explicit acknowledgement before approval." if summary.get("warnings") else "No findings."),
    }
