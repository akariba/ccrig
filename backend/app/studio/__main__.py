"""Operator CLI:  python -m app.studio <command> ...   (run from backend/; workspace = $CCRIG_STUDIO_DIR or ~/.ccrig-studio)

Reads a local file you name; it never fetches anything from the network. Output is JSON; refusals exit with status 2.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import acquire, config, pipeline, review
from .store import StudioStore


def _out(obj) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.studio", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", help="workspace directory (default: $CCRIG_STUDIO_DIR or ~/.ccrig-studio)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest", help="stage a CSV/JSON/parquet file for review")
    p.add_argument("file"); p.add_argument("--source-id", required=True); p.add_argument("--target", required=True)
    p.add_argument("--scope", default=""); p.add_argument("--classification", default="PUBLIC", choices=pipeline.CLASSIFICATIONS)
    p.add_argument("--operator", default="cli"); p.add_argument("--force-new", action="store_true")
    for name in ("show", "staging", "events"):
        q = sub.add_parser(name); q.add_argument("job_id")
    for name in ("approve", "reject"):
        q = sub.add_parser(name); q.add_argument("job_id"); q.add_argument("--reviewer", required=True); q.add_argument("--reason", required=True)
        if name == "approve":
            q.add_argument("--ack-mappings", action="store_true"); q.add_argument("--ack-changes", action="store_true"); q.add_argument("--ack-assertions", action="store_true")
    sub.add_parser("jobs"); sub.add_parser("datasets"); sub.add_parser("verify-ledger")
    q = sub.add_parser("releases"); q.add_argument("dataset"); q.add_argument("--scope", default="")
    q = sub.add_parser("export"); q.add_argument("dataset"); q.add_argument("--scope", default="")
    q = sub.add_parser("rollback"); q.add_argument("dataset"); q.add_argument("--scope", default=""); q.add_argument("--reviewer", required=True); q.add_argument("--reason", required=True)
    q = sub.add_parser("restore"); q.add_argument("dataset"); q.add_argument("--scope", default=""); q.add_argument("--release-id", type=int, required=True)
    q.add_argument("--reviewer", required=True); q.add_argument("--reason", required=True)
    q = sub.add_parser("discover", help="find, verify and stage recent events for a company from approved sources (needs CCRIG_DISCOVERY_NETWORK=1 for a live search)")
    q.add_argument("query"); q.add_argument("--window", type=int, default=180); q.add_argument("--limit", type=int, default=5); q.add_argument("--no-stage", action="store_true")
    q.add_argument("--as-of", help="YYYY-MM-DD (default: today, UTC)")
    sub.add_parser("providers"); sub.add_parser("runs"); sub.add_parser("relationships")
    q = sub.add_parser("report"); q.add_argument("job_id")
    q = sub.add_parser("source-add", help="store a copy of an approved-source page as evidence (no network)")
    q.add_argument("file"); q.add_argument("--url", required=True); q.add_argument("--published-date", required=True); q.add_argument("--title", required=True)
    q = sub.add_parser("run"); q.add_argument("run_id")
    a = ap.parse_args(argv)

    try:
        store = StudioStore(a.dir or config.studio_dir())
        if a.cmd == "ingest":
            path = Path(a.file)
            result = pipeline.ingest(store, path.read_bytes(), source_id=a.source_id, filename=path.name, target=a.target, scope=a.scope, classification=a.classification,
                                     operator=a.operator, force_new=a.force_new)
            job = result["job"]
            _out({"duplicate": result["duplicate"], "job_id": job["job_id"], "status": job["status"], "blocking": job["blocking"], "findings": job["findings_summary"], "elapsed_ms": job["elapsed_ms"]})
        elif a.cmd == "show":
            job = store.get_job(a.job_id)
            _out({"job": job, "findings": store.findings(a.job_id), "decisions": store.decisions(a.job_id)} if job else {"error": "NOT_FOUND"})
        elif a.cmd == "staging":
            _out(store.load_staging(a.job_id) or {"error": "NO_STAGING"})
        elif a.cmd == "events":
            _out(store.events(a.job_id))
        elif a.cmd == "approve":
            _out(review.approve(store, a.job_id, reviewer=a.reviewer, reason=a.reason, acknowledge_mappings=a.ack_mappings, acknowledge_changes=a.ack_changes, acknowledge_assertions=a.ack_assertions))
        elif a.cmd == "reject":
            _out(review.reject(store, a.job_id, reviewer=a.reviewer, reason=a.reason))
        elif a.cmd == "jobs":
            _out(store.list_jobs())
        elif a.cmd == "datasets":
            _out(store.list_current())
        elif a.cmd == "releases":
            _out({"current": store.current(a.dataset, a.scope), "releases": store.releases(a.dataset, a.scope)})
        elif a.cmd == "export":
            _out(review.export(store, a.dataset, a.scope))
        elif a.cmd == "rollback":
            _out(review.rollback(store, a.dataset, a.scope, reviewer=a.reviewer, reason=a.reason))
        elif a.cmd == "restore":
            _out(review.restore(store, a.dataset, a.scope, a.release_id, reviewer=a.reviewer, reason=a.reason))
        elif a.cmd == "discover":
            from datetime import date as _date
            from ..discovery import service as dservice

            out = dservice.run(store, a.query, window_days=a.window, limit=a.limit, stage=not a.no_stage, operator="cli", as_of=_date.fromisoformat(a.as_of) if a.as_of else None)
            _out(out)
        elif a.cmd == "report":
            from . import report as dreport

            _out(dreport.quality_report(store, a.job_id) or {"error": "NOT_FOUND"})
        elif a.cmd == "relationships":
            from . import impact, overlay

            edges, release = overlay.load(store)
            cur = store.current("reference_entities", "")
            refs = store.read_release(cur["release_id"])["rows"] if cur else []
            _out({"release": release, "edges": edges, "adoption_effect": impact.adoption_effect(edges, refs) if edges else None})
        elif a.cmd == "source-add":
            from . import relationships

            _out(relationships.add_source(store, Path(a.file).read_bytes(), url=a.url, published_date=a.published_date, title=a.title))
        elif a.cmd == "providers":
            from ..discovery import agent as dagent, net as dnet, providers as dprov

            _out({"network_enabled": dnet.network_enabled(), "ai_configured": dagent.configured_client() is not None,
                  "providers": [{"id": p.id, "label": p.label, "approved_source": p.source["id"], "entities": p.cfg["entities"]} for p in dprov.load_providers()]})
        elif a.cmd == "runs":
            _out(store.list_runs())
        elif a.cmd == "run":
            _out(store.load_run(a.run_id) or {"error": "NOT_FOUND"})
        elif a.cmd == "verify-ledger":
            _out(store.verify_chain())
    except (review.ReviewError, pipeline.BadRequest, config.UnsafeWorkspace, acquire.IngestRejected, ValueError) as exc:
        print(json.dumps({"error": getattr(exc, "code", type(exc).__name__), "message": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
