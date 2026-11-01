"""Staging: turn validated, resolved rows into a reviewable proposal and compare it with (a) the previous approved Studio release and
(b) the canonical dataset, read-only. Nothing here writes to a canonical file."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ..core.config import DATA_DIR, RAW_PRICES_DIR
from .contracts import Contract
from .store import canonical_json, sha256_text

SAMPLE_CAP = 50


def key_of(contract: Contract, row: dict) -> tuple:
    return tuple(row.get(k) for k in contract.key)


def key_text(key: tuple) -> str:
    return "|".join("" if k is None else str(k) for k in key)


def _norm(v):
    if isinstance(v, float):
        return round(v, 12)
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [_norm(x) for x in v]
    return v


def project(contract: Contract, row: dict) -> dict:
    """The contract's fields only, normalised for comparison (nested objects limited to their contract sub-fields)."""
    out = {}
    for f in contract.fields:
        v = row.get(f.name)
        if f.type == "object" and isinstance(v, dict):
            v = {s.name: v.get(s.name) for s in f.fields}
        out[f.name] = _norm(v)
    return out


def canonical_rows(contract: Contract, scope: str, ticker: str | None = None) -> list | None:
    """The canonical dataset's rows, projected to the contract, or None when no canonical copy exists for this scope."""
    if contract.canonical_file:
        path = DATA_DIR / contract.canonical_file
        if not path.exists():
            return None
        doc = json.loads(path.read_text("utf-8"))
        return [project(contract, r) for r in doc.get(contract.canonical_list_key, [])]
    if contract.name == "prices" and ticker:
        for path in sorted(Path(RAW_PRICES_DIR).glob(f"{ticker}_price_history*.csv")):
            with open(path, encoding="utf-8", newline="") as fh:
                return [{"date": r["date"], "close": _norm(float(r["close"]))} for r in csv.DictReader(fh)]
    return None


def diff(contract: Contract, proposed: list, base: list | None) -> dict:
    """Classify each proposed row against a base dataset (merge semantics: rows absent from the proposal are untouched, never deleted)."""
    if base is None:
        return {"available": False}
    index = {key_of(contract, r): r for r in base}
    new = changed = unchanged = 0
    samples = []
    for r in proposed:
        k = key_of(contract, r)
        old = index.get(k)
        if old is None:
            new += 1
            continue
        a, b = project(contract, old), project(contract, r)
        if a == b:
            unchanged += 1
        else:
            changed += 1
            if len(samples) < SAMPLE_CAP:
                samples.append({"key": key_text(k), "fields": {f: {"was": a[f], "proposed": b[f]} for f in a if a[f] != b[f]}})
    return {"available": True, "base_rows": len(base), "new": new, "changed": changed, "unchanged": unchanged, "changed_samples": samples}


def merge(contract: Contract, base_rows: list, proposed: list) -> list:
    merged = {key_of(contract, r): project(contract, r) for r in base_rows}
    for r in proposed:
        merged[key_of(contract, r)] = project(contract, r)
    return [merged[k] for k in sorted(merged, key=lambda k: tuple("" if x is None else str(x) for x in k))]


def content_hash(rows: list) -> str:
    return sha256_text(canonical_json(rows))


def build_staging(contract: Contract, *, job_id: str, scope: str, proposed: list, excluded: list, mappings: list, previous_release: dict | None,
                  previous_rows: list | None, canonical: list | None) -> dict:
    proposed_clean = [project(contract, r) for r in proposed]
    merged = merge(contract, previous_rows or [], proposed)
    vs_prev = diff(contract, proposed, previous_rows if previous_release else [])
    vs_prev["release_id"] = previous_release["release_id"] if previous_release else None
    vs_prev["version"] = previous_release["version"] if previous_release else None
    return {
        "job_id": job_id, "dataset": contract.name, "scope": scope, "mode": "merge", "proposed_rows": proposed_clean, "excluded_rows": excluded, "mappings": mappings,
        "base_release_id": previous_release["release_id"] if previous_release else None, "vs_previous_release": vs_prev, "vs_canonical": diff(contract, proposed, canonical),
        "merged_rows": len(merged), "merged_hash": content_hash(merged), "proposed_hash": content_hash(proposed_clean),
    }
