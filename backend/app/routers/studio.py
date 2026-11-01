"""Public, read-only Studio endpoints: what the Studio is, what it accepts, and whether this deployment can run it.
Always available (also in the static Pyodide build, where it reports 'disabled'). Everything that writes lives in studio_ops.py and is only
registered when the operator enables the Studio."""
from dataclasses import asdict

from fastapi import APIRouter

from ..studio import acquire, config
from ..studio.contracts import CONTRACTS

router = APIRouter(prefix="/api/studio", tags=["studio"])


def _field(f):
    d = {"name": f.name, "type": f.type, "required": f.required}
    for k in ("enum", "min", "max", "pattern", "ref"):
        v = getattr(f, k)
        if v not in (None, ()):
            d[k] = list(v) if isinstance(v, tuple) else v
    if f.fields:
        d["fields"] = [_field(s) for s in f.fields]
    return d


@router.get("/status")
def status():
    enabled = config.studio_enabled()
    return {
        "enabled": enabled,
        "mode": "operator" if enabled else "disabled",
        "capabilities": {
            "read_contracts": True,
            "ingest_files": enabled, "review_and_approve": enabled, "rollback": enabled, "persistent_workspace": enabled,
            "static_site_note": "The GitHub Pages build is read-only: it cannot ingest, store or approve anything. Ingestion runs only on an operator's machine or a private server with CCRIG_ENABLE_STUDIO and an operator token.",
        },
        "formats": {"csv": True, "json": True, "parquet": acquire.parquet_supported()},
        "limits": {k: v for k, v in asdict(config.limits()).items() if k != "sample_rows"},
        "targets": sorted(CONTRACTS),
    }


@router.get("/contracts")
def contracts():
    return {"contracts": [
        {"name": c.name, "description": c.description, "key": list(c.key), "promotable": c.promotable, "scoped": c.scoped, "scope_ref": c.scope_ref,
         "canonical_file": c.canonical_file, "checks": list(c.checks), "notes": c.notes, "fields": [_field(f) for f in c.fields]}
        for c in CONTRACTS.values()]}
