"""Typed validation against a target contract, then cross-record consistency. Findings are recorded; nothing is repaired silently."""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime

from .config import Limits
from .contracts import DOCUMENTED, Contract, Field

_FLOAT = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_INT = re.compile(r"^[+-]?\d+$")
_URL = re.compile(r"^https://[^\s/]+(/\S*)?$")


class Findings:
    """Collects findings, keeps exact counts per code, and caps the stored detail."""

    def __init__(self, limits: Limits):
        self.items: list = []
        self.counts: Counter = Counter()
        self.cap = limits.max_findings

    def add(self, stage, severity, code, message, **extra):
        self.counts[(severity, code)] += 1
        if len(self.items) < self.cap:
            self.items.append({"stage": stage, "severity": severity, "code": code, "message": message, **{k: v for k, v in extra.items() if v is not None}})

    def extend(self, items):
        for f in items:
            self.counts[(f["severity"], f["code"])] += 1
            if len(self.items) < self.cap:
                self.items.append(f)

    def summary(self) -> dict:
        errors = sum(n for (s, _), n in self.counts.items() if s == "ERROR")
        warns = sum(n for (s, _), n in self.counts.items() if s == "WARN")
        return {"errors": errors, "warnings": warns, "by_code": {f"{s}:{c}": n for (s, c), n in sorted(self.counts.items())},
                "truncated": max(0, sum(self.counts.values()) - len(self.items)), "blocking": errors > 0}


def _clip(v, n=80):
    s = repr(v) if not isinstance(v, str) else v
    return s if len(s) <= n else s[: n - 1] + "…"


def coerce(field: Field, value, *, from_text: bool):
    """Return (typed_value, error_code, message). A missing value is None with no error here (requiredness is checked by the caller)."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None, None, None
    t = field.type
    if t in ("str", "enum", "url"):
        if not isinstance(value, str):
            return None, "WRONG_TYPE", f"expected text, got {type(value).__name__}"
        v = value.strip()
        if t == "enum" and v not in field.enum:
            return None, "INVALID_ENUM", f"'{_clip(v)}' is not one of {list(field.enum)}"
        if t == "url" and not _URL.match(v):
            return None, "INVALID_URL", f"'{_clip(v)}' is not an https URL"
        if field.pattern and not re.match(field.pattern, v):
            return None, "PATTERN_MISMATCH", f"'{_clip(v)}' does not match {field.pattern}"
        return v, None, None
    if t in ("float", "int"):
        if isinstance(value, bool):
            return None, "WRONG_TYPE", "a boolean is not a number"
        if isinstance(value, (int, float)):
            num = value
        elif isinstance(value, str) and (_FLOAT.match(value.strip()) if t == "float" else _INT.match(value.strip())):
            num = float(value) if t == "float" else int(value)
        else:
            return None, "WRONG_TYPE", f"'{_clip(value)}' is not a valid {t}"
        if isinstance(num, float) and (math.isnan(num) or math.isinf(num)):
            return None, "NOT_FINITE", "NaN and infinity are not valid values"
        if t == "int" and isinstance(num, float) and not num.is_integer():
            return None, "WRONG_TYPE", f"'{num}' is not a whole number"
        num = float(num) if t == "float" else int(num)
        if field.min is not None and num < field.min:
            return None, "OUT_OF_RANGE", f"{num} is below the minimum {field.min}"
        if field.max is not None and num > field.max:
            return None, "OUT_OF_RANGE", f"{num} is above the maximum {field.max}"
        return num, None, None
    if t == "bool":
        if isinstance(value, bool):
            return value, None, None
        s = str(value).strip().lower()
        if s in ("true", "1"):
            return True, None, None
        if s in ("false", "0"):
            return False, None, None
        return None, "WRONG_TYPE", f"'{_clip(value)}' is not true/false"
    if t == "date":
        s = str(value).strip()
        try:
            datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return None, "INVALID_DATE", f"'{_clip(s)}' is not a real YYYY-MM-DD date"
        return s, None, None
    return None, "UNSUPPORTED_TYPE", t


def _type_object(field: Field, value, row, findings: Findings, *, from_text: bool):
    if value is None:
        return None
    if not isinstance(value, dict):
        findings.add("VALIDATE", "ERROR", "WRONG_TYPE", f"'{field.name}' must be an object", row=row, field=field.name)
        return None
    out = {}
    for sub in field.fields:
        typed, code, msg = coerce(sub, value.get(sub.name), from_text=from_text)
        if code:
            findings.add("VALIDATE", "ERROR", code, f"{field.name}.{sub.name}: {msg}", row=row, field=f"{field.name}.{sub.name}", value=_clip(value.get(sub.name)))
        out[sub.name] = typed
    for extra in sorted(set(value) - {s.name for s in field.fields}):
        findings.add("VALIDATE", "WARN", "UNKNOWN_SUBFIELD", f"'{field.name}.{extra}' is not part of the contract and is ignored", row=row, field=f"{field.name}.{extra}")
    return out


def type_rows(contract: Contract, columns: list, rows: list, row_numbers: list, findings: Findings, *, fmt: str) -> list:
    """Schema compatibility + per-value typing. Returns typed rows carrying '_row' (the source row number); only contract fields survive."""
    if not contract.fields:
        return []
    names = contract.field_names()
    missing = [f.name for f in contract.fields if f.required and f.name not in columns]
    for name in missing:
        findings.add("VALIDATE", "ERROR", "MISSING_REQUIRED_COLUMN", f"the source has no '{name}' column, which '{contract.name}' requires", field=name)
    for col in columns:
        if col and col not in names:
            findings.add("VALIDATE", "WARN", "UNKNOWN_COLUMN", f"column '{col}' is not part of the '{contract.name}' contract; it is ignored and never promoted", field=col)
    if missing:
        return []
    from_text = fmt == "csv"
    typed_rows = []
    for rec, num in zip(rows, row_numbers):
        out = {"_row": num}
        for f in contract.fields:
            raw = rec.get(f.name)
            if f.type == "object":
                if from_text and raw not in (None, ""):
                    findings.add("VALIDATE", "ERROR", "OBJECT_NEEDS_JSON", f"'{f.name}' is a nested object; supply it in a JSON file", row=num, field=f.name)
                    val = None
                else:
                    val = _type_object(f, raw, num, findings, from_text=from_text)
            else:
                val, code, msg = coerce(f, raw, from_text=from_text)
                if code:
                    findings.add("VALIDATE", "ERROR", code, f"{f.name}: {msg}", row=num, field=f.name, value=_clip(raw))
                    val = None
            if val is None and f.required and f.type != "object" and (raw is None or str(raw).strip() == ""):
                findings.add("VALIDATE", "ERROR", "MISSING_REQUIRED_VALUE", f"'{f.name}' is required", row=num, field=f.name)
            out[f.name] = val
        typed_rows.append(out)
    return typed_rows


def row_has_error(findings_items, row) -> bool:
    return any(f.get("row") == row and f["severity"] == "ERROR" for f in findings_items)


def _key(contract: Contract, r: dict):
    return tuple(r.get(k) for k in contract.key)


def consistency(contract: Contract, rows: list, findings: Findings, *, as_of: date) -> list:
    """Duplicates and cross-record rules on rows whose references are already resolved. Returns the rows that may be proposed."""
    if not contract.key:
        return rows
    groups: dict = {}
    for r in rows:
        groups.setdefault(_key(contract, r), []).append(r)
    kept = []
    comparable = lambda r: {k: v for k, v in r.items() if k != "_row"}  # noqa: E731
    for key, grp in groups.items():
        if any(v is None for v in key):
            continue                                         # incomplete keys already carry their own errors
        if len(grp) == 1:
            kept.append(grp[0])
        elif all(comparable(g) == comparable(grp[0]) for g in grp):
            findings.add("CHECK", "WARN", "DUPLICATE_IDENTICAL", f"record {list(key)} appears {len(grp)} times with identical values; one copy is kept", row=grp[1]["_row"])
            kept.append(grp[0])
        else:
            findings.add("CHECK", "ERROR", "DUPLICATE_CONFLICT", f"record {list(key)} appears {len(grp)} times with different values (rows {[g['_row'] for g in grp]}); none is proposed", row=grp[0]["_row"])
    kept.sort(key=lambda r: r["_row"])
    for name in contract.checks:
        _CHECKS[name](contract, kept, findings, as_of)
    return kept


def _no_self_loop(c, rows, findings, as_of):
    for r in rows:
        if r.get("source") and r["source"] == r.get("target"):
            findings.add("CHECK", "ERROR", "SELF_LOOP", f"'{r['source']}' cannot be related to itself", row=r["_row"])


def _documented_needs_link(c, rows, findings, as_of):
    for r in rows:
        if r.get("evidence_status") in DOCUMENTED and not r.get("evidence_url"):
            findings.add("CHECK", "ERROR", "DOCUMENTED_WITHOUT_LINK", f"status {r['evidence_status']} needs an https evidence_url; use UNVERIFIED if there is none", row=r["_row"])


def _synthetic_not_documented(c, rows, findings, as_of):
    for r in rows:
        if r.get("is_synthetic") is True and r.get("evidence_status") in DOCUMENTED:
            findings.add("CHECK", "ERROR", "SYNTHETIC_CLAIMS_DOCUMENTED", "a synthetic relationship cannot be labelled documented or reported", row=r["_row"])


def _holdings_total(c, rows, findings, as_of):
    totals: Counter = Counter()
    for r in rows:
        if r.get("counterparty") and r.get("exposure_pct") is not None:
            totals[r["counterparty"]] += r["exposure_pct"]
    for cp, total in sorted(totals.items()):
        if total > 1.0 + 1e-9:
            findings.add("CHECK", "ERROR", "HOLDINGS_EXCEED_100", f"holdings of {cp} add up to {total:.4f}, more than 100%")


def _limit_consistency(c, rows, findings, as_of):
    for r in rows:
        lim = r.get("limit")
        if not lim:
            continue
        if lim.get("limit_type") and lim.get("limit_value") is None:
            findings.add("CHECK", "ERROR", "LIMIT_VALUE_MISSING", f"limit type {lim['limit_type']} has no value", row=r["_row"])
        if not lim.get("limit_type") and lim.get("limit_value") is not None:
            findings.add("CHECK", "ERROR", "LIMIT_TYPE_MISSING", "a limit value without a limit type cannot be used (a bare number is never compared with an exposure)", row=r["_row"])


def _price_series(c, rows, findings, as_of):
    pts = [(r["date"], r["close"], r["_row"]) for r in rows if r.get("date") and r.get("close") is not None]
    if any(a[0] > b[0] for a, b in zip(pts, pts[1:])):
        findings.add("CHECK", "WARN", "NOT_SORTED", "dates are not in ascending order in the source (they are sorted for staging)")
    pts.sort()
    prev = None
    for d, close, num in pts:
        dd = date.fromisoformat(d)
        if close <= 0:
            findings.add("CHECK", "ERROR", "NON_POSITIVE_PRICE", f"close {close} on {d} is not a price", row=num)
        if dd > as_of:
            findings.add("CHECK", "ERROR", "FUTURE_DATE", f"{d} is after the ingestion date {as_of.isoformat()}", row=num)
        if prev:
            gap = (dd - prev[0]).days
            if gap > 10:
                findings.add("CHECK", "WARN", "DATE_GAP", f"{gap} calendar days between {prev[0].isoformat()} and {d}", row=num)
            if prev[1] > 0 and abs(close / prev[1] - 1) > 0.35:
                findings.add("CHECK", "WARN", "OUTLIER_RETURN", f"close moved {100 * (close / prev[1] - 1):+.1f}% from the previous row on {d}", row=num)
        prev = (dd, close)


_CHECKS = {"no_self_loop": _no_self_loop, "documented_needs_link": _documented_needs_link, "synthetic_not_documented": _synthetic_not_documented,
           "holdings_total": _holdings_total, "limit_consistency": _limit_consistency, "price_series": _price_series}
