"""The approved-source event register: loading, policy and validation.

Principles (see also docs/EVENT_IMPACT_MAP.md):

* A record is a REAL, retrieved publication. It carries the source, its
  publication date, the event date and where it came from, a location with its
  precision, and verbatim evidence passages. Nothing is generated.
* A record is admitted only if every source is on an approved domain
  (data/events/approved_sources.json) and the record was verified BY
  RETRIEVAL: the source was fetched, its date confirmed and every evidence
  passage found verbatim in it (scripts/event_register.py verify).
* This module is pure and offline, so it works unchanged in FastAPI and in the
  in-browser (Pyodide) build. Retrieval happens only in the developer script.
"""
import html
import json
import re
from datetime import date
from functools import lru_cache
from urllib.parse import urlparse

from .config import DATA_DIR

EVENTS_DIR = DATA_DIR / "events"
REGISTER_FILE = EVENTS_DIR / "events_nvidia.json"
VERIFIED = "VERIFIED_BY_RETRIEVAL"
MIN_QUOTE_CHARS = 25
FORBIDDEN_FLAGS = ("hypothetical", "scenario", "synthetic", "simulated", "is_synthetic")


# ------------------------------------------------------------------ text helpers
def normalize_text(text: str) -> str:
    """Whitespace-collapsed, entity-decoded text: the form evidence is stored and matched in."""
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def html_to_text(raw_html: str) -> str:
    raw_html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.S | re.I)
    return normalize_text(re.sub(r"<[^>]+>", " ", raw_html))


def split_sentences(text: str) -> list:
    return re.split(r"(?<=[.!?])\s+(?=[A-Z“\"▪])", text)


def sentence_containing(text: str, anchor: str):
    """The first sentence of `text` that contains `anchor`, verbatim; None if absent."""
    for sentence in split_sentences(text):
        if anchor in sentence:
            return sentence.strip()
    return None


def long_date_forms(iso: str) -> list:
    """The ways a page may print an ISO date: 'October 8, 2026' and zero-padded 'October 08, 2026'."""
    d = date.fromisoformat(iso)
    return [d.strftime("%B ") + str(d.day) + d.strftime(", %Y"), d.strftime("%B %d, %Y")]


# ------------------------------------------------------------------ data loading
@lru_cache(maxsize=1)
def approved_sources() -> dict:
    return json.loads((EVENTS_DIR / "approved_sources.json").read_text())


@lru_cache(maxsize=1)
def gazetteer() -> dict:
    return json.loads((EVENTS_DIR / "gazetteer.json").read_text())["places"]


@lru_cache(maxsize=1)
def load_register() -> dict:
    return json.loads(REGISTER_FILE.read_text())


def domain_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def source_policy(url: str):
    """The approved-source entry whose domain (or subdomain) matches `url`; None if not approved."""
    if urlparse(url).scheme != "https":
        return None
    host = domain_of(url)
    for entry in approved_sources()["sources"]:
        if any(host == d or host.endswith("." + d) for d in entry["domains"]):
            return entry
    return None


# ------------------------------------------------------------------ validation
def _iso(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def validate_event(event: dict) -> list:
    """Problems that make a record inadmissible (empty list = admissible). Offline checks only;
    that the passages really are in the source is what `verification` records."""
    problems = []
    for field in ("id", "title", "category", "published_date", "event_date", "event_date_basis",
                  "location", "sources", "evidence", "verification"):
        if not event.get(field):
            problems.append(f"missing field '{field}'")
    if problems:
        return problems
    if event.get("kind") != "REAL_EVENT":
        problems.append("kind must be 'REAL_EVENT'")
    for flag in FORBIDDEN_FLAGS:
        if event.get(flag):
            problems.append(f"flag '{flag}' marks this as not a real event")
    published, occurred = _iso(event["published_date"]), _iso(event["event_date"])
    if not published or not occurred:
        problems.append("published_date and event_date must be ISO dates")
    elif occurred > published:
        problems.append("event_date is after published_date")

    ids = set()
    for src in event["sources"]:
        policy = source_policy(src.get("url", ""))
        if not policy:
            problems.append(f"source '{src.get('url')}' is not on an approved https domain")
        elif src.get("tier") != policy["tier"]:
            problems.append(f"source tier '{src.get('tier')}' does not match approved tier '{policy['tier']}'")
        if not _iso(src.get("published_date")):
            problems.append(f"source '{src.get('id')}' has no ISO published_date")
        ids.add(src.get("id"))
    for ev in event["evidence"]:
        if ev.get("source_id") not in ids:
            problems.append(f"evidence refers to unknown source '{ev.get('source_id')}'")
        if len(ev.get("quote", "")) < MIN_QUOTE_CHARS:
            problems.append("evidence quote is too short to be a verifiable passage")

    loc = event["location"]
    place = gazetteer().get(loc.get("gazetteer_key"))
    if not place:
        problems.append(f"location '{loc.get('gazetteer_key')}' is not in the gazetteer")
    if not loc.get("basis"):
        problems.append("location has no stated basis")

    v = event["verification"]
    total = len(event["evidence"])
    if v.get("status") != VERIFIED:
        problems.append(f"verification status is '{v.get('status')}', not {VERIFIED}")
    if v.get("quotes_total") != total or v.get("quotes_found") != total:
        problems.append("not every evidence passage was found verbatim in its source")
    if v.get("date_confirmed") is not True:
        problems.append("publication date was not confirmed in the source")
    return problems


def validate_register(register: dict | None = None) -> dict:
    """{event_id: [problems]} for every record that is inadmissible (empty dict = all admissible)."""
    register = register or load_register()
    out, seen = {}, set()
    for ev in register["events"]:
        problems = validate_event(ev)
        if ev.get("id") in seen:
            problems.append("duplicate id")
        seen.add(ev.get("id"))
        if problems:
            out[ev.get("id")] = problems
    return out
