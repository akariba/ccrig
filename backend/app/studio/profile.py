"""Profiling: what is actually in a parsed table. Deterministic (the reference date is passed in, never read from the clock)."""
from __future__ import annotations

import json
import re
from datetime import date, datetime

from .config import Limits
from .resolve import exact_coverage

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")
_INT = re.compile(r"^[+-]?\d+$")
_FLOAT = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
ID_LIKE = ("id", "ticker", "symbol", "source", "target", "counterparty", "issuer", "entity", "entity_id", "reference_entity_id", "lei")


def kind_of(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (dict, list)):
        return "object"
    s = str(value).strip()
    if s.lower() in ("true", "false"):
        return "bool"
    if _DATE.match(s):
        return "date"
    if _DATETIME.match(s):
        return "datetime"
    if _INT.match(s):
        return "int"
    if _FLOAT.match(s):
        return "float"
    return "str"


def _parse_date(s: str):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def profile(columns: list, rows: list, *, as_of: date, limits: Limits, parse_findings: list | None = None) -> dict:
    n = len(rows)
    cols = []
    for c in columns:
        vals = [r.get(c) for r in rows]
        present = sum(1 for r in rows if c in r)
        nonnull = [v for v in vals if v is not None]
        kinds: dict = {}
        for v in nonnull:
            kinds[kind_of(v)] = kinds.get(kind_of(v), 0) + 1
        main = max(kinds, key=lambda k: (kinds[k], k)) if kinds else "null"
        if set(kinds) == {"int", "float"}:
            main = "float"
        mixed = {k: v for k, v in kinds.items()} if len(kinds) > 1 and set(kinds) != {"int", "float"} else {}
        distinct = {_canon(v) for v in nonnull}
        rec = {
            "name": c, "inferred_type": main, "null_count": n - len(nonnull), "null_pct": round(100.0 * (n - len(nonnull)) / n, 2) if n else 0.0,
            "distinct": len(distinct), "present_in_rows_pct": round(100.0 * present / n, 2) if n else 0.0, "mixed_types": mixed,
            "max_chars": max((len(str(v)) for v in nonnull), default=0),
            "examples": [json.loads(x) for x in sorted(distinct)[:3]],
        }
        if main in ("int", "float"):
            nums = []
            for v in nonnull:
                try:
                    nums.append(float(v))
                except (TypeError, ValueError):
                    pass
            if nums:
                rec["min"], rec["max"] = min(nums), max(nums)
        if main in ("date", "datetime"):
            ds = sorted(d for d in (_parse_date(str(v)) for v in nonnull) if d)
            if ds:
                rec["min"], rec["max"] = ds[0].isoformat(), ds[-1].isoformat()
                rec["age_days"] = (as_of - ds[-1]).days
        if c.lower() in ID_LIKE or c.lower().endswith("_id"):
            rec["identifier_coverage"] = exact_coverage(nonnull)
        cols.append(rec)

    row_keys = [_canon(r) for r in rows]
    dup = n - len(set(row_keys))
    freshness = [{"column": c["name"], "earliest": c["min"], "latest": c["max"], "age_days": c["age_days"]} for c in cols if "age_days" in c]
    inconsistencies = []
    for c in cols:
        if c["mixed_types"]:
            inconsistencies.append({"code": "MIXED_TYPES", "column": c["name"], "types": c["mixed_types"]})
        if 0 < c["present_in_rows_pct"] < 100:
            inconsistencies.append({"code": "PARTIAL_COLUMN", "column": c["name"], "present_in_rows_pct": c["present_in_rows_pct"]})
    for f in parse_findings or []:
        if f["code"] in ("RAGGED_ROW", "DUPLICATE_HEADER", "EMPTY_HEADER", "DUPLICATE_JSON_KEY"):
            inconsistencies.append({"code": f["code"], "message": f["message"]})
    pick = sorted({0, 1, 2, n // 2, n // 2 + 1, n - 3, n - 2, n - 1} & set(range(n)))[: limits.sample_rows]
    return {
        "rows": n, "columns": len(columns), "duplicate_rows": dup, "duplicate_rate_pct": round(100.0 * dup / n, 2) if n else 0.0,
        "column_profiles": cols, "schema_inconsistencies": inconsistencies, "freshness": freshness, "as_of": as_of.isoformat(),
        "sample_rows": [{"row": i + 1, "values": rows[i]} for i in pick],
    }
