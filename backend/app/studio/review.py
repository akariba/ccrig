"""Human review: approve, reject, roll back, restore, export. Approval publishes a versioned release inside the Studio workspace only;
no canonical dataset is touched and no scoring input changes. Every refusal carries a stable code."""
from __future__ import annotations

from .contracts import CONTRACTS
from .stage import canonical_json, content_hash, merge
from .store import StudioStore


class ReviewError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _who(reviewer: str, reason: str):
    reviewer, reason = (reviewer or "").strip(), (reason or "").strip()
    if not reviewer or len(reviewer) > 80:
        raise ReviewError("REVIEWER_REQUIRED", "a reviewer name (1-80 characters) is required", 422)
    if not reason or len(reason) > 1000:
        raise ReviewError("REASON_REQUIRED", "a reason (1-1000 characters) is required", 422)
    return reviewer, reason


def _pending(store: StudioStore, job_id: str) -> dict:
    job = store.get_job(job_id)
    if not job:
        raise ReviewError("NOT_FOUND", f"no job {job_id}", 404)
    if job["status"] != "PENDING_REVIEW":
        raise ReviewError("NOT_PENDING", f"job {job_id} is {job['status']}, not PENDING_REVIEW")
    return job


def approve(store: StudioStore, job_id: str, *, reviewer: str, reason: str, acknowledge_mappings: bool = False, acknowledge_changes: bool = False, acknowledge_assertions: bool = False) -> dict:
    reviewer, reason = _who(reviewer, reason)
    job = _pending(store, job_id)
    if job["blocking"]:
        raise ReviewError("BLOCKED_BY_FINDINGS", f"job has {job['findings_summary']['errors']} blocking finding(s); correct the source and resubmit")
    contract = CONTRACTS[job["target"]]
    if not contract.promotable:
        raise ReviewError("PROFILE_ONLY", "this target is profile-only and cannot be promoted")
    staging = store.load_staging(job_id)
    if not staging:
        raise ReviewError("NO_STAGING", "the staged proposal is missing")
    needs_ack = [m for m in staging["mappings"] if m["requires_acknowledgement"]]
    if needs_ack and not acknowledge_mappings:
        raise ReviewError("MAPPINGS_NOT_ACKNOWLEDGED", f"{len(needs_ack)} entity mapping(s) were applied by ticker, name or alias; acknowledge them to approve")
    asserted = staging.get("assertions_to_confirm") or []
    if asserted and not acknowledge_assertions:
        raise ReviewError("ASSERTIONS_NOT_ACKNOWLEDGED", f"{len(asserted)} relationship(s) are asserted by the proposer from quoted text with no explicit wording; the reviewer must confirm them (acknowledge_assertions)")
    reverse = [e for e in (staging.get("graph_effect") or {}).get("edges", []) if e.get("reverse_edge_in_canonical")]
    if reverse and not acknowledge_changes:
        raise ReviewError("CHANGES_NOT_ACKNOWLEDGED", f"{len(reverse)} proposed relationship(s) run opposite to an existing canonical edge; acknowledge to approve")
    changed_prev, changed_canon = staging["vs_previous_release"].get("changed", 0), staging["vs_canonical"].get("changed", 0) or 0
    if (changed_prev or changed_canon) and not acknowledge_changes:
        raise ReviewError("CHANGES_NOT_ACKNOWLEDGED", f"{changed_prev} row(s) differ from the previous approved release and {changed_canon} from the canonical dataset; acknowledge the changes to approve")
    scope = staging["scope"]
    current = store.current(contract.name, scope)
    if (current["release_id"] if current else None) != staging["base_release_id"]:
        raise ReviewError("STALE_BASE", "the approved state changed after this job was staged; resubmit it (force_new) to stage against the current state")
    prev_rows = store.read_release(current["release_id"])["rows"] if current else []
    merged = merge(contract, prev_rows, staging["proposed_rows"])
    chash = content_hash(merged)
    if current and current["content_hash"] == chash:
        raise ReviewError("ALREADY_CURRENT", "approving this would publish exactly the current approved state; nothing to do")
    version = store.next_version(contract.name, scope)
    lineage = {k: job_id for k in (canonical_json([r.get(f) for f in contract.key]) for r in staging["proposed_rows"])}
    doc = {"dataset": contract.name, "scope": scope, "version": version, "job_id": job_id, "source_sha256": job["sha256"], "rows": merged,
           "approved_by": reviewer, "approved_at": store.clock(), "lineage_of_this_job": sorted(lineage)}
    path = store.write_release_file(contract.name, scope, version, doc)         # file first; the database commit below makes it real
    detail = {"acknowledge_mappings": acknowledge_mappings, "acknowledge_changes": acknowledge_changes, "changed_vs_previous": changed_prev, "changed_vs_canonical": changed_canon,
              "mappings": len(staging["mappings"]), "base_release_id": staging["base_release_id"], "acknowledge_assertions": acknowledge_assertions,
              "assertions_confirmed": asserted}
    rid = store.commit_release(dataset=contract.name, scope=scope, job_id=job_id, version=version, content_hash=chash, path=path, rows=len(merged), reviewer=reviewer, reason=reason, detail=detail)
    return {"release_id": rid, "dataset": contract.name, "scope": scope, "version": version, "rows": len(merged), "content_hash": chash,
            "note": "Published to the Studio workspace only. Canonical datasets and scoring inputs are unchanged."}


def reject(store: StudioStore, job_id: str, *, reviewer: str, reason: str) -> dict:
    reviewer, reason = _who(reviewer, reason)
    _pending(store, job_id)
    store.reject_job(job_id, reviewer, reason)
    return {"job_id": job_id, "status": "REJECTED"}


def _dataset(dataset: str, scope: str):
    if dataset not in CONTRACTS or not CONTRACTS[dataset].promotable:
        raise ReviewError("UNKNOWN_DATASET", f"'{dataset}' is not a promotable dataset", 404)


def rollback(store: StudioStore, dataset: str, scope: str = "", *, reviewer: str, reason: str) -> dict:
    """Return to the previous approved state (or to 'no approved state' from the first release). History is kept."""
    reviewer, reason = _who(reviewer, reason)
    _dataset(dataset, scope)
    current = store.current(dataset, scope)
    if not current:
        raise ReviewError("NOTHING_TO_ROLL_BACK", "there is no approved release for this dataset")
    target = current["parent_release_id"]
    if target is not None:
        store.read_release(target)                                                # the older snapshot must still verify before we rely on it
    store.switch_current(dataset=dataset, scope=scope, target_release_id=target, reviewer=reviewer, reason=reason, kind="ROLLED_BACK")
    after = store.current(dataset, scope)
    return {"dataset": dataset, "scope": scope, "rolled_back_release": current["release_id"], "current": ({"release_id": after["release_id"], "version": after["version"]} if after else None)}


def restore(store: StudioStore, dataset: str, scope: str, release_id: int, *, reviewer: str, reason: str) -> dict:
    """Make an earlier release current again (it is hash-verified first). Newer releases are marked ROLLED_BACK, not deleted."""
    reviewer, reason = _who(reviewer, reason)
    _dataset(dataset, scope)
    rel = store.get_release(release_id)
    if not rel or rel["dataset"] != dataset or rel["scope"] != scope:
        raise ReviewError("NOT_FOUND", f"no release {release_id} for {dataset}", 404)
    store.read_release(release_id)
    store.switch_current(dataset=dataset, scope=scope, target_release_id=release_id, reviewer=reviewer, reason=reason, kind="RESTORED")
    return {"dataset": dataset, "scope": scope, "current": {"release_id": release_id, "version": rel["version"]}}


def export(store: StudioStore, dataset: str, scope: str = "") -> dict:
    """The current approved rows, shaped like the canonical file for the dataset, for a person to adopt deliberately. Nothing is written to canonical data."""
    _dataset(dataset, scope)
    current = store.current(dataset, scope)
    if not current:
        raise ReviewError("NO_APPROVED_STATE", "there is no approved release for this dataset", 404)
    doc = store.read_release(current["release_id"])
    contract = CONTRACTS[dataset]
    shaped = {contract.canonical_list_key: doc["rows"]} if contract.canonical_list_key else {"rows": doc["rows"]}
    return {"dataset": dataset, "scope": scope, "version": current["version"], "release_id": current["release_id"], "content_hash": current["content_hash"],
            "approved_by": current["approved_by"], "canonical_shape": shaped,
            "warning": "Approved in the Studio workspace only. Analytics read the canonical files until a person adopts this export."}
