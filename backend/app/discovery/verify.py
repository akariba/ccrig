"""Deterministic verification of discovered claims against the retrieved evidence. No AI is involved, and nothing here proves a claim TRUE:
it proves that the retrieved source contains the quoted text, the publication date, the title and the dateline the event relies on."""
from __future__ import annotations

import json
import re
from datetime import date

from ..core import event_register as reg

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
ABBR = {"January": ["Jan"], "February": ["Feb"], "March": ["Mar"], "April": ["Apr"], "May": ["May"], "June": ["June", "Jun"], "July": ["July", "Jul"], "August": ["Aug"],
        "September": ["Sept", "Sep"], "October": ["Oct"], "November": ["Nov"], "December": ["Dec"]}
DATE_RE = re.compile(r"\b(?:%s)[a-z]*\.? \d{1,2}, 20\d\d\b" % "|".join(m[:3] for m in MONTHS))


def date_forms(iso: str) -> list:
    """Every way a page commonly prints an ISO date: 'October 8, 2026', 'Oct. 08, 2026', '8 October 2026', '2026-10-08'."""
    d = date.fromisoformat(iso)
    full = MONTHS[d.month - 1]
    out = {iso, f"{d.day} {full} {d.year}"}
    for name in [full, *ABBR[full]]:
        for dot in ("", ".") if name != full else ("",):
            for day in (str(d.day), f"{d.day:02d}"):
                out.add(f"{name}{dot} {day}, {d.year}")
    return sorted(out)


def parse_printed_date(printed: str):
    """'Oct. 26, 2026' / 'October 26, 2026' -> '2026-10-26' (None if it is not a real date)."""
    m = re.match(r"([A-Za-z]+)\.? (\d{1,2}), (20\d\d)", printed)
    if not m:
        return None
    month = next((i + 1 for i, name in enumerate(MONTHS) if name.lower().startswith(m.group(1).lower()[:3])), None)
    try:
        return date(int(m.group(3)), month, int(m.group(2))).isoformat() if month else None
    except ValueError:
        return None


def date_in_text(iso: str, text: str) -> bool:
    return any(form in text for form in date_forms(iso))


def verify_candidate(*, text: str, method: str, published_date: str, title: str, quotes: list, basis_text: str | None, record: dict | None = None) -> dict:
    """The verification block stored with the event, plus the list of problems (empty when everything was found)."""
    problems = []
    found = sum(1 for q in quotes if q in text)
    if found != len(quotes):
        problems.append(f"{len(quotes) - found} quote(s) not found verbatim in the retrieved text")
    if any(len(q) < reg.MIN_QUOTE_CHARS for q in quotes):
        problems.append("a quote is too short to be a verifiable passage")
    if method == "api_json":
        confirmed = bool(record) and record.get("publication_date") == published_date
        date_basis = "Federal Register API field publication_date matches"
        if title and title not in text:
            problems.append("the title is not in the retrieved text")
    else:
        confirmed = date_in_text(published_date, text)
        date_basis = "the publication date is printed in the retrieved page"
        if title and title not in text:
            problems.append("the title is not found verbatim in the retrieved page")
    if not confirmed:
        problems.append("the publication date is not confirmed by the retrieved source")
    if basis_text and basis_text not in text:
        problems.append(f"the dateline '{basis_text}' is not found in the retrieved text")
    return {"verification": {"status": reg.VERIFIED if not problems else "FAILED", "method": "event discovery: retrieved the source and matched the publication date, title, dateline and every quote verbatim",
                             "checked_at": None, "quotes_total": len(quotes), "quotes_found": found, "date_confirmed": confirmed, "date_basis": date_basis}, "problems": problems}


def reverify_row(store, row: dict) -> list:
    """Re-check a staged row against the STORED raw bytes (so a forged or edited row cannot pass): [{code, message}]."""
    from . import providers

    try:
        raw = store.read_raw(row["source_sha256"])
    except FileNotFoundError:
        return [{"code": "EVIDENCE_MISSING", "message": "the stored source document for this event is missing"}]
    except Exception as exc:  # noqa: BLE001
        return [{"code": "EVIDENCE_CORRUPT", "message": f"{type(exc).__name__}: {str(exc)[:120]}"}]
    method = row["text_method"]
    text = providers.to_text(raw, method)
    record = json.loads(raw.decode("utf-8")) if method == "api_json" else None
    loc = row.get("location") or {}
    out = verify_candidate(text=text, method=method, published_date=row["published_date"], title=row.get("source_title") or "", quotes=row["evidence_quotes"],
                           basis_text=loc.get("basis_text"), record=record)
    return [{"code": "EVIDENCE_NOT_FOUND", "message": p} for p in out["problems"]]
