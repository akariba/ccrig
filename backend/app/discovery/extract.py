"""Candidate extraction from one retrieved document (deterministic baseline; an AI extractor may only add suggestions that pass the guard in agent.py)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from ..core import event_entities, event_register as reg
from . import verify
from .providers import RetrievedDocument

MAX_QUOTE_CHARS = 900
SCENARIO = ("scenario", "hypothetical", "what if", "simulation", "stress test", "could face", "would face", "imagine ")
BACKGROUND_TITLE = ("overview", "about us", "history of", "what is ", "faq", "frequently asked")
FORWARD = ("plans", "planned", "expected", "expects", "targeting", "aims", "will ", "to build", "ramping")
CATEGORY_RULES = (  # (category, title/lead patterns) - first match wins; disclosed in the output as category_method
    ("EARNINGS_RELEASE", r"financial results|reports? (?:first|second|third|fourth)|conference call|quarter"),
    ("PARTNERSHIP_ANNOUNCEMENT", r"partnership|collaborat|\band [A-Z][\w&.\- ]+ (?:expand|team|join|partner)|joins|alliance"),
    ("PRODUCT_ANNOUNCEMENT", r"launch|introduc|unveil|announces? (?:new|the)|platform|\bRTX\b|GeForce|laptops|chips?\b|systems"),
    ("REGULATORY_ACTION", r"^$"),
)
DATELINE_WIRE = re.compile(r"([A-Z][A-Z .'’\-]{2,30}?)(?:, ([A-Z][A-Za-z.]{1,15}(?: [A-Z][A-Za-z.]+)?))?, (?:%s)[a-z]*\.? \d{1,2}, 20\d\d \((?:GLOBE NEWSWIRE|BUSINESS WIRE|PRNewswire)\)" % "|".join(m[:3] for m in verify.MONTHS))
DATELINE_EVENT = re.compile(r"\b(?:GTC|CES|Computex|SIGGRAPH|SEMICON West|GTC Paris|GTC Taipei)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)?)\s?[—–]")
DATELINE_PLAIN = re.compile(r"(?:^|\s)([A-Z][a-z]+(?: [A-Z][a-z]+)?), (?:%s)[a-z]*\.? \d{1,2}, 20\d\d\s?[–—-]" % "|".join(m[:3] for m in verify.MONTHS))


@dataclass
class Candidate:
    id: str
    entity_id: str
    title: str
    category: str
    category_method: str
    published_date: str
    event_date: str
    event_date_basis: str
    location: dict
    evidence_quotes: list
    verification: dict
    doc: RetrievedDocument
    flags: list = field(default_factory=list)
    entity_in_title: bool = False
    also_reported_by: list = field(default_factory=list)
    relationship_candidates: list = field(default_factory=list)


@dataclass
class Rejection:
    stage: str
    reason: str
    url: str
    title: str
    published_date: str | None = None

    def as_dict(self) -> dict:
        return {"stage": self.stage, "reason": self.reason, "url": self.url, "title": self.title, "published_date": self.published_date}


def slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")[:48].strip("-")


def event_id(entity_id: str, published: str, title: str, url: str) -> str:
    return f"{entity_id.lower()}-{published.replace('-', '')}-{slug(title)}-{hashlib.sha256(url.encode()).hexdigest()[:6]}"


def body_of(doc: RetrievedDocument) -> str:
    """The article itself: for web pages, the text after the last occurrence of the title (skips site navigation); API documents are their own body."""
    if doc.text_method == "api_json":
        return doc.text
    i = doc.text.rfind(doc.title) if doc.title else -1
    return doc.text[i:] if i >= 0 else doc.text


def find_dateline(body: str, gazetteer: dict):
    """-> (gazetteer_key | None, basis_text | None, reason). Only a place the source itself prints in a dateline counts; never an assumed headquarters."""
    for rx, group in ((DATELINE_WIRE, 1), (DATELINE_EVENT, 1), (DATELINE_PLAIN, 1)):
        m = rx.search(body[:2500])
        if not m:
            continue
        city = m.group(group).strip().title() if rx is DATELINE_WIRE else m.group(group).strip()
        for key, place in gazetteer.items():
            if place["kind"] == "city" and place["label"].split(",")[0].lower() == city.lower():
                return key, m.group(0).strip(" —–-"), None
        return None, None, f"the dateline names '{city}', which is not in the gazetteer"
    return None, None, "the source prints no dateline place"


def categorize(title: str, lead: str, doc: RetrievedDocument) -> tuple:
    if doc.provider_id == "federal_register":
        return "REGULATORY_ACTION", "official Federal Register document: regulatory by source"
    for cat, rx in CATEGORY_RULES:
        if rx != r"^$" and re.search(rx, f"{title} {lead[:300]}", re.I):
            return cat, "keyword rules v1 (title and lead sentence)"
    return "CORPORATE_ANNOUNCEMENT", "default: no keyword rule matched"


def pick_quotes(body: str, query, limit: int = 3) -> list:
    sentences = [s.strip() for s in reg.split_sentences(body[:6000]) if reg.MIN_QUOTE_CHARS <= len(s.strip()) <= MAX_QUOTE_CHARS]
    names = [t.lower() for t in query.terms]
    chosen, seen = [], set()
    for s in sentences:                                           # 1) the lead sentence(s) that name the company
        if any(n in s.lower() for n in names) and s not in seen:
            chosen.append(s)
            seen.add(s)
            break
    for s in sentences:                                           # 2) sentences that name other canonical entities (these carry the relationships)
        if len(chosen) >= limit:
            break
        ids = {m["entity_id"] for m in event_entities.resolve_text(s)}
        if s not in seen and len(ids) >= 2:
            chosen.append(s)
            seen.add(s)
    return chosen


def extract(doc: RetrievedDocument, query, gazetteer: dict):
    """-> (Candidate | None, Rejection | None)."""
    stub = dict(url=doc.url, title=doc.title, published_date=doc.published_date)
    body = body_of(doc)
    if any(w in f"{doc.title} {body[:400]}".lower() for w in SCENARIO):
        return None, Rejection("CLASSIFY", "reads as a scenario or hypothetical, not a real event", **stub)
    if any(w in doc.title.lower() for w in BACKGROUND_TITLE):
        return None, Rejection("CLASSIFY", "reads as general background about an ongoing dependency, not a dated event", **stub)
    mentioned = {m["entity_id"] for m in event_entities.resolve_text(f"{doc.title}. {body[:6000]}")}
    if query.entity_id not in mentioned:
        return None, Rejection("RELEVANCE", f"{query.name} is not named in the retrieved text", **stub)
    published, date_note = doc.published_date, None
    if doc.text_method == "html_text" and not verify.date_in_text(published, body[:2500]):
        page = verify.DATE_RE.search(body[:2500])
        page_iso = verify.parse_printed_date(page.group(0)) if page else None
        if page_iso and abs((date.fromisoformat(page_iso) - date.fromisoformat(published)).days) <= 1:
            date_note = f"the page prints {page.group(0)}; the feed listed {published} (a one-day difference, typically time zones). The printed date is used."
            published = page_iso                               # the document itself is the primary source for its own date
        else:
            why = (f"the publication date is not confirmed: the source metadata says {published}, the page shows {page.group(0)}" if page
                   else f"the publication date {published} is not printed near the start of the page")
            return None, Rejection("VERIFY", why, **stub)
    key, basis_text, why_not = (None, None, None)
    if doc.text_method == "api_json" and doc.extras.get("location"):
        loc_cfg = doc.extras["location"]
        key, basis_text, why_not = loc_cfg["gazetteer_key"], None, None
        location = {"gazetteer_key": key, "basis": loc_cfg["basis"]}
    else:
        key, basis_text, why_not = find_dateline(body, gazetteer)
        location = ({"gazetteer_key": key, "basis": f"Dateline of the source: '{basis_text}'.", "basis_text": basis_text} if key
                    else {"gazetteer_key": None, "basis": "No place is evidenced by the source.", "unmapped_reason": why_not})
    quotes = pick_quotes(body, query)
    if not quotes:
        return None, Rejection("EXTRACT", "no sentence naming the company could be quoted verbatim", **stub)
    cat, method = categorize(doc.title, body, doc)
    today = re.search(r"\btoday (?:announced|announces|reported|reports)\b", body[:1500], re.I)
    basis = ("press release date; the release says 'today announced'" if today and doc.text_method == "html_text"
             else "Federal Register publication date; any effective date inside the document is not asserted here" if doc.text_method == "api_json"
             else "publication date; the source states no separate event date")
    v = verify.verify_candidate(text=doc.text, method=doc.text_method, published_date=published, title=doc.title, quotes=quotes, basis_text=basis_text,
                                record=__import__("json").loads(doc.raw) if doc.text_method == "api_json" else None)
    if v["problems"]:
        return None, Rejection("VERIFY", "unverifiable: " + "; ".join(v["problems"]), **stub)
    v["verification"]["checked_at"] = doc.retrieved_at
    flags = ["FORWARD_LOOKING"] if any(w in " ".join(quotes) for w in FORWARD) else []
    if date_note:
        basis += f". Publication date: {date_note}"
    cand = Candidate(event_id(query.entity_id, published, doc.title, doc.url), query.entity_id, doc.title, cat, method, published, published, basis, location,
                     quotes, v["verification"], doc, flags, entity_in_title=query.entity_id in {m["entity_id"] for m in event_entities.resolve_text(doc.title)})
    return cand, None
