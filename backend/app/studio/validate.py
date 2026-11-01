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
        if field.type == "list" and field.min_items and value is None:
            return None, None, None
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
    if t == "list":
        if not isinstance(value, list):
            return None, "WRONG_TYPE", "expected a list"
        item = Field("item", field.item)
        out = []
        for i, v in enumerate(value):
            typed, code, msg = coerce(item, v, from_text=from_text)
            if code or typed is None:
                return None, code or "MISSING_REQUIRED_VALUE", f"item {i + 1}: {msg or 'empty'}"
            out.append(typed)
        if len(out) < field.min_items:
            return None, "TOO_FEW_ITEMS", f"at least {field.min_items} item(s) required"
        return out, None, None
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


def consistency(contract: Contract, rows: list, findings: Findings, *, as_of: date, ctx: dict | None = None) -> list:
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
        _CHECKS[name](contract, kept, findings, as_of, ctx or {})
    return kept


def _no_self_loop(c, rows, findings, as_of, ctx=None):
    for r in rows:
        if r.get("source") and r["source"] == r.get("target"):
            findings.add("CHECK", "ERROR", "SELF_LOOP", f"'{r['source']}' cannot be related to itself", row=r["_row"])


def _documented_needs_link(c, rows, findings, as_of, ctx=None):
    for r in rows:
        if r.get("evidence_status") in DOCUMENTED and not r.get("evidence_url"):
            findings.add("CHECK", "ERROR", "DOCUMENTED_WITHOUT_LINK", f"status {r['evidence_status']} needs an https evidence_url; use UNVERIFIED if there is none", row=r["_row"])


def _synthetic_not_documented(c, rows, findings, as_of, ctx=None):
    for r in rows:
        if r.get("is_synthetic") is True and r.get("evidence_status") in DOCUMENTED:
            findings.add("CHECK", "ERROR", "SYNTHETIC_CLAIMS_DOCUMENTED", "a synthetic relationship cannot be labelled documented or reported", row=r["_row"])


def _holdings_total(c, rows, findings, as_of, ctx=None):
    totals: Counter = Counter()
    for r in rows:
        if r.get("counterparty") and r.get("exposure_pct") is not None:
            totals[r["counterparty"]] += r["exposure_pct"]
    for cp, total in sorted(totals.items()):
        if total > 1.0 + 1e-9:
            findings.add("CHECK", "ERROR", "HOLDINGS_EXCEED_100", f"holdings of {cp} add up to {total:.4f}, more than 100%")


def _limit_consistency(c, rows, findings, as_of, ctx=None):
    for r in rows:
        lim = r.get("limit")
        if not lim:
            continue
        if lim.get("limit_type") and lim.get("limit_value") is None:
            findings.add("CHECK", "ERROR", "LIMIT_VALUE_MISSING", f"limit type {lim['limit_type']} has no value", row=r["_row"])
        if not lim.get("limit_type") and lim.get("limit_value") is not None:
            findings.add("CHECK", "ERROR", "LIMIT_TYPE_MISSING", "a limit value without a limit type cannot be used (a bare number is never compared with an exposure)", row=r["_row"])


def _price_series(c, rows, findings, as_of, ctx=None):
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


SCENARIO_WORDS = ("scenario", "hypothetical", "what if", "simulation", "stress test", "could face", "would face")


def _discovered_event_evidence(c, rows, findings, as_of, ctx):
    """Re-verify every discovered event against the STORED source text (not against what the extractor said)."""
    from ..discovery import verify as dverify

    store = ctx.get("store")
    for r in rows:
        if store is None:
            findings.add("CHECK", "ERROR", "NO_EVIDENCE_STORE", "the evidence store is not available, so quotes cannot be re-verified", row=r["_row"])
            continue
        for problem in dverify.reverify_row(store, r):
            findings.add("CHECK", "ERROR", problem["code"], problem["message"], row=r["_row"])
        if r["event_date"] and r["published_date"] and r["event_date"] > r["published_date"]:
            findings.add("CHECK", "ERROR", "EVENT_AFTER_PUBLICATION", "event_date is after published_date", row=r["_row"])
        if r["published_date"] and r["published_date"] > as_of.isoformat():
            findings.add("CHECK", "ERROR", "PUBLISHED_IN_THE_FUTURE", f"published {r['published_date']} is after {as_of.isoformat()}", row=r["_row"])
        lead = f"{r['title']} {' '.join(r['evidence_quotes'])}".lower()
        if any(w in lead for w in SCENARIO_WORDS):
            findings.add("CHECK", "ERROR", "SCENARIO_NOT_EVENT", "the title or evidence reads as a scenario or hypothetical, not a real event", row=r["_row"])


def _load_ccr_master():
    import json as _json

    from ..core.config import DATA_DIR

    path = DATA_DIR / "ccr_counterparties.json"
    return {c["id"]: c for c in _json.loads(path.read_text("utf-8"))["counterparties"]} if path.exists() else {}


def _relationship_assertions(c, rows, findings, as_of, ctx):
    from . import relationships

    store = ctx.get("store")
    for r in rows:
        for severity, code, message in relationships.check_row(r):
            findings.add("CHECK", severity, code, message, row=r["_row"])
        if store is None:
            findings.add("CHECK", "ERROR", "NO_EVIDENCE_STORE", "the evidence store is not available, so quotes cannot be re-verified", row=r["_row"])
        else:
            for p in relationships.reverify_row(store, r):
                findings.add("CHECK", "ERROR", p["code"], p["message"], row=r["_row"])
        if r["is_synthetic"]:
            findings.add("CHECK", "ERROR", "SYNTHETIC_RELATIONSHIP", "a synthetic relationship cannot be ingested as documented evidence", row=r["_row"])
        if r["relationship_as_of"] > as_of.isoformat() or r["relationship_as_of"] > r["source_published_date"]:
            findings.add("CHECK", "ERROR", "RELATIONSHIP_DATE_AFTER_SOURCE", "the relationship date is after the source's publication date or after today", row=r["_row"])
        if r["relation"] == "AFFILIATED_WITH" and r["source"] > r["target"]:
            findings.add("CHECK", "ERROR", "SYMMETRIC_NOT_ORDERED", "an undirected affiliation is stored with its two companies in alphabetical order", row=r["_row"])


def _reference_links(c, rows, findings, as_of, ctx):
    master = _load_ccr_master()
    for r in rows:
        if r["link_kind"] == "INFERRED_DEPENDENCY" and not (r.get("basis") or "").strip():
            findings.add("CHECK", "ERROR", "INFERRED_WITHOUT_BASIS", "an inferred dependency must state how it was inferred; it is never a trade reference", row=r["_row"])
        if r["as_of_date"] > as_of.isoformat():
            findings.add("CHECK", "ERROR", "FUTURE_DATE", f"{r['as_of_date']} is after {as_of.isoformat()}", row=r["_row"])
        rec = master.get(r["counterparty_id"])
        if rec and r["link_kind"] == "TRADE_REFERENCE_ENTITY" and rec.get("reference_entity_id") and rec["reference_entity_id"] != r["reference_entity_id"] and rec.get("product") == r["product"]:
            findings.add("CHECK", "WARN", "DIFFERS_FROM_CCR_MASTER", f"the CCR record lists {rec['reference_entity_id']} as the reference entity for {r['product']}; this row says {r['reference_entity_id']}", row=r["_row"])
        if rec and r["link_kind"] == "TRADE_REFERENCE_ENTITY" and rec.get("product") not in (None, r["product"]):
            findings.add("CHECK", "WARN", "PRODUCT_NOT_IN_CCR_MASTER", f"the CCR record for {r['counterparty_id']} lists product {rec.get('product')}, not {r['product']}", row=r["_row"])


def _ccr_exposure_consistency(c, rows, findings, as_of, ctx):
    from .contracts import MEASURE_LIMIT

    master = _load_ccr_master()
    seen_units: dict = {}
    owner: dict = {}
    for r in rows:
        key = r["measure"]
        unit = (r["currency"], r["unit"])
        if seen_units.setdefault(key, (unit, r["_row"]))[0] != unit:
            first = seen_units[key]
            findings.add("CHECK", "ERROR", "INCONSISTENT_UNITS", f"{key} appears as {first[0][0]} {first[0][1].lower()} (row {first[1]}) and as {unit[0]} {unit[1].lower()}; values are never converted, supply one currency and unit per measure", row=r["_row"])
        if r["as_of_date"] > as_of.isoformat():
            findings.add("CHECK", "ERROR", "FUTURE_DATE", f"as-of date {r['as_of_date']} is after {as_of.isoformat()}", row=r["_row"])
        ns = r["netting_set_id"]
        if owner.setdefault(ns, r["counterparty_id"]) != r["counterparty_id"]:
            findings.add("CHECK", "ERROR", "NETTING_SET_CONFLICT", f"netting set {ns} is attached to both {owner[ns]} and {r['counterparty_id']}", row=r["_row"])
        rec = master.get(r["counterparty_id"])
        if rec and rec.get("netting_set") and rec["netting_set"] != ns:
            others = [cid for cid, m in master.items() if m.get("netting_set") == ns and cid != r["counterparty_id"]]
            if others:
                findings.add("CHECK", "ERROR", "NETTING_SET_CONFLICT", f"netting set {ns} belongs to {others[0]} in the CCR master, not {r['counterparty_id']}", row=r["_row"])
            else:
                findings.add("CHECK", "WARN", "ORPHAN_NETTING_SET", f"netting set {ns} is not the netting set the CCR master lists for {r['counterparty_id']} ({rec['netting_set']}); an exposure on an unlisted netting set is an orphan until the master is extended", row=r["_row"])
        lt, lv, util = r.get("limit_type"), r.get("limit_value"), r.get("utilization")
        if lt and r["measure"] not in MEASURE_LIMIT or (lt and MEASURE_LIMIT.get(r["measure"]) != lt):
            findings.add("CHECK", "ERROR", "LIMIT_MEASURE_MISMATCH", f"a {lt} is never compared with {r['measure']} (limits apply only to their own measure)", row=r["_row"])
        elif lt and lv is None:
            findings.add("CHECK", "ERROR", "LIMIT_VALUE_MISSING", f"limit type {lt} has no limit value", row=r["_row"])
        elif lv is not None and not lt:
            findings.add("CHECK", "ERROR", "LIMIT_TYPE_MISSING", "a limit value without a limit type cannot be used", row=r["_row"])
        elif lt and lv is not None:
            if lv == 0:
                findings.add("CHECK", "WARN", "ZERO_LIMIT", "the limit is zero, so utilization is undefined and is left empty", row=r["_row"])
                r["utilization"] = None
            else:
                computed = round(r["value"] / lv, 10)
                if util is not None and abs(util - computed) > 1e-6:
                    findings.add("CHECK", "ERROR", "UTILIZATION_MISMATCH", f"supplied utilization {util} differs from value/limit = {computed:.6f}", row=r["_row"])
                r["utilization"] = computed
        elif util is not None:
            findings.add("CHECK", "ERROR", "UTILIZATION_WITHOUT_LIMIT", "a utilization was supplied without a limit to compute it against", row=r["_row"])
        if r["is_synthetic"] is False and not r["source_system"].strip():
            findings.add("CHECK", "ERROR", "NO_LINEAGE", "real exposures need a named source system", row=r["_row"])


_CHECKS = {"relationship_assertions": _relationship_assertions, "reference_links": _reference_links, "ccr_exposure_consistency": _ccr_exposure_consistency,
           "discovered_event_evidence": _discovered_event_evidence, "no_self_loop": _no_self_loop, "documented_needs_link": _documented_needs_link, "synthetic_not_documented": _synthetic_not_documented,
           "holdings_total": _holdings_total, "limit_consistency": _limit_consistency, "price_series": _price_series}
