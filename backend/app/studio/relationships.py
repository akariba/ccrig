"""When does a quoted passage support a typed, directed relationship?  Co-occurrence is not enough.

A relationship between SOURCE and TARGET is supported by a quote only if (1) the quote is found verbatim in the stored source document, (2) the quote names BOTH
companies (resolved by the platform's deterministic entity rules), and (3) the words between the two names carry a cue for the relation, in an order consistent with the
stated direction. When there is no such cue the proposer may still assert the relationship, but only with a written rationale; that is recorded as PROPOSER_ASSERTED,
flagged, and a reviewer must acknowledge it. A cue that points the other way is an error, never silently flipped.
"""
from __future__ import annotations

import re

from ..core import event_entities, event_register as reg

# (regex, orientation): 'S_T' = the cue appears when SOURCE is named first ("A supplies B"); 'T_S' = when TARGET is named first ("B buys from A").
CUES = {
    "SUPPLIES": [(r"\b(supplies|supplied|will supply|to supply|supplier to|provides?|providing|delivers?|ships?|builds? for|manufactur\w+ for|fabricat\w+ for)\b", "S_T"),
                 (r"\b(buys?|bought|purchas\w+|sources?|procures?|relies on|depends on|is supplied by|secure\w*(?: a)?(?: stable)? supply)\b", "T_S")],
    "LICENSES_TO": [(r"\b(licen[sc]es?|licen[sc]ed|licen[sc]ing)\b", "S_T"), (r"\b(licen[sc]ed from|under (?:a )?licen[sc]e from|licen[sc]ee of)\b", "T_S")],
    "PARENT_OF": [(r"\b(owns|acquired|acquires|controls|is the parent of|parent of)\b", "S_T"), (r"\b(subsidiary of|owned by|acquired by|a unit of|a division of)\b", "T_S")],
    "SUBSIDIARY_OF": [(r"\b(subsidiary of|owned by|acquired by|a unit of|a division of)\b", "S_T"), (r"\b(owns|acquired|acquires|controls|parent of)\b", "T_S")],
    "FINANCES": [(r"\b(lends?|lent|finances?|financed|loans? to|credit facility (?:for|to)|funds?|funded)\b", "S_T"), (r"\b(borrow\w*|financed by|loan from|funded by)\b", "T_S")],
    "GUARANTEES": [(r"\b(guarantee[sd]?|guaranteeing|guarantor of)\b", "S_T"), (r"\b(guaranteed by)\b", "T_S")],
    "AFFILIATED_WITH": [(r"\b(affiliate[sd]?|affiliation|subsidiary|joint venture|sister company|member of the [\w ]+ group)\b", "ANY")],
}
MIN_RATIONALE = 20


def mentions(text: str, entity_id: str) -> list:
    return [m for m in event_entities.resolve_text(text) if m["entity_id"] == entity_id]


def analyse(relation: str, source: str, target: str, quote: str) -> dict:
    """What one quote says about the pair: both named? which first? which cue sits between them? -> {both, order, cue, orientation, direction_ok}."""
    ms, mt = mentions(quote, source), mentions(quote, target)
    if not ms or not mt:
        return {"both": False, "order": None, "cue": None, "orientation": None, "direction_ok": None}
    first_s = ms[0]["start"] <= mt[0]["start"]
    lo, hi = (ms[0], mt[0]) if first_s else (mt[0], ms[0])
    between = quote[lo["end"]:hi["start"]]
    found = None
    for pattern, orientation in CUES.get(relation, []):
        m = re.search(pattern, between, re.I)
        if m:
            found = (m.group(0), orientation)
            break
    if not found:
        # the cue may also precede both names ("Under a license from A, B ...") or follow them; look in the whole sentence for 'ANY' relations only
        for pattern, orientation in CUES.get(relation, []):
            if orientation == "ANY" and re.search(pattern, quote, re.I):
                m = re.search(pattern, quote, re.I)
                found = (m.group(0), "ANY")
                break
    if not found:
        return {"both": True, "order": "SOURCE_FIRST" if first_s else "TARGET_FIRST", "cue": None, "orientation": None, "direction_ok": None}
    cue, orientation = found
    ok = True if orientation == "ANY" else (orientation == "S_T") == first_s
    return {"both": True, "order": "SOURCE_FIRST" if first_s else "TARGET_FIRST", "cue": cue, "orientation": orientation, "direction_ok": ok}


def check_row(row: dict) -> list:
    """Findings [(severity, code, message)] for one relationship row, using only the row's own quotes (their presence in the source is verified separately)."""
    out = []
    a = row["assertion"] or {}
    src, tgt, rel = row["source"], row["target"], row["relation"]
    if src == tgt:
        return [("ERROR", "SELF_RELATIONSHIP", "a company cannot be related to itself")]
    results = [analyse(rel, src, tgt, q) for q in row["evidence_quotes"]]
    both = [r for r in results if r["both"]]
    if not both:
        return [("ERROR", "CO_OCCURRENCE_ONLY", "no quoted passage names both companies, so nothing here establishes a relationship between them (naming one company in a document is not a relationship)")]
    wrong = [r for r in both if r["cue"] and r["direction_ok"] is False]
    right = [r for r in both if r["cue"] and r["direction_ok"]]
    if wrong and not right:
        return [("ERROR", "DIRECTION_CONFLICT", f"the wording ('{wrong[0]['cue']}') points the opposite way to the stated direction; the stored direction is source -> target and is never flipped silently")]
    if right:
        if a.get("basis") != "EXPLICIT_CUE":
            out.append(("WARN", "CUE_FOUND_BUT_NOT_DECLARED", f"the quote carries the cue '{right[0]['cue']}'; the assertion basis is recorded as EXPLICIT_CUE"))
        return out
    # both companies are named, but no cue for this relation sits between them
    if a.get("basis") == "EXPLICIT_CUE":
        return [("ERROR", "CUE_NOT_FOUND", "the row claims an explicit cue, but none was found between the two company names in any quote")]
    rationale = (a.get("rationale") or "").strip()
    if a.get("basis") != "PROPOSER_ASSERTED" or len(rationale) < MIN_RATIONALE:
        return [("ERROR", "UNSUPPORTED_RELATIONSHIP_ASSERTION", f"both companies are named but nothing states a {rel} relationship; to assert it anyway give basis PROPOSER_ASSERTED and a rationale of at least {MIN_RATIONALE} characters")]
    return [("WARN", "NO_EXPLICIT_CUE", "no wording in the quotes states this relationship; it is asserted by the proposer from the quoted text and a reviewer must confirm it")]


def reverify_row(store, row: dict) -> list:
    """Re-check the row's quotes, source title and publication date against the STORED document: [{code, message}]."""
    from ..discovery import providers, verify

    try:
        raw = store.read_raw(row["source_sha256"])
    except FileNotFoundError:
        return [{"code": "EVIDENCE_MISSING", "message": "the stored source document for this relationship is missing"}]
    except Exception as exc:  # noqa: BLE001
        return [{"code": "EVIDENCE_CORRUPT", "message": f"{type(exc).__name__}: {str(exc)[:120]}"}]
    method = row["text_method"]
    text = providers.to_text(raw, method)
    import json as _json

    record = _json.loads(raw.decode("utf-8")) if method == "api_json" else None
    v = verify.verify_candidate(text=text, method=method, published_date=row["source_published_date"], title=row.get("source_title") or "", quotes=row["evidence_quotes"], basis_text=None, record=record)
    return [{"code": "EVIDENCE_NOT_FOUND", "message": p} for p in v["problems"]]


def add_source(store, data: bytes, *, url: str, published_date: str, title: str, retrieved_at: str | None = None) -> dict:
    """Store an operator-supplied copy of an approved-source web page as raw evidence (no network). The URL must be on an approved https domain, and the page must
    contain the title and the publication date. Returns what a relationship row needs: sha256, tier, publisher fields, text method."""
    from ..discovery import providers, verify

    policy = reg.source_policy(url)
    if not policy:
        raise ValueError("the URL is not on an approved https source domain")
    text = providers.to_text(data, "html_text")
    problems = []
    if title not in text:
        problems.append("the title is not in the page")
    if not verify.date_in_text(published_date, text):
        problems.append(f"the publication date {published_date} is not printed in the page")
    if problems:
        raise ValueError("; ".join(problems))
    sha = store.put_raw(data)
    return {"source_sha256": sha, "source_url": url, "source_title": title, "source_published_date": published_date, "source_tier": policy["tier"], "approved_source_id": policy["id"],
            "source_publisher": policy.get("publisher") or policy["id"].replace("_", " ").title(), "text_method": "html_text", "retrieved_at": retrieved_at or store.clock()[:10],
            "verification": {"status": reg.VERIFIED, "method": "source stored; title and publication date found in the text", "checked_at": retrieved_at or store.clock()[:10],
                             "quotes_total": 0, "quotes_found": 0, "date_confirmed": True, "date_basis": "the publication date is printed in the stored page"}}
