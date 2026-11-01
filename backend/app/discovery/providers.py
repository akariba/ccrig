"""Approved source providers: an issuer newsroom RSS feed and the official Federal Register API. Each returns document references, then retrieved documents.

A provider can only retrieve from the approved source it names; documents on any other host are reported as excluded, never fetched.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree

from ..core import event_register as reg
from ..core.config import DATA_DIR
from . import net
from .entity import EntityQuery


class ProviderConfigError(ValueError):
    pass


@dataclass
class DocumentRef:
    provider_id: str
    url: str
    title: str
    published_date: str | None
    summary: str = ""
    record: dict | None = None                  # API records are their own source document
    date_basis: str = ""


@dataclass
class RetrievedDocument:
    provider_id: str
    approved_source_id: str
    tier: str
    publisher: str
    url: str
    final_url: str
    title: str
    published_date: str
    date_basis: str
    raw: bytes
    content_type: str
    text: str
    text_method: str                             # html_text | api_json
    retrieved_at: str
    http_status: int
    extras: dict = field(default_factory=dict)


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def to_text(raw: bytes, method: str) -> str:
    """The ONE deterministic way raw source bytes become the text that evidence is quoted from (also used to re-verify stored evidence)."""
    if method == "html_text":
        return reg.html_to_text(raw.decode("utf-8", "replace"))
    if method == "api_json":
        rec = json.loads(raw.decode("utf-8"))
        return reg.normalize_text(f"{rec.get('title', '')}. {rec.get('abstract', '') or ''}")
    raise ValueError(method)


def host_ok(host: str) -> bool:
    return reg.source_policy(f"https://{host}/") is not None


def load_config() -> list:
    cfg = json.loads((DATA_DIR / "discovery" / "providers.json").read_text())
    approved = {s["id"]: s for s in reg.approved_sources()["sources"]}
    for p in cfg["providers"]:
        src = approved.get(p["approved_source_id"])
        if not src:
            raise ProviderConfigError(f"provider {p['id']}: approved source '{p['approved_source_id']}' does not exist")
        policy = reg.source_policy(p["url"])
        if not policy or policy["id"] != src["id"]:
            raise ProviderConfigError(f"provider {p['id']}: its URL is not on the approved source's domains")
    return cfg["providers"]


def _iso_date(text: str):
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return None


def parse_feed(body: bytes) -> list:
    """RSS 2.0 items -> [{title, link, published_date, description, pub_raw}]. Feeds that declare a DTD or entities are refused (entity-expansion attacks)."""
    head = body[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in body.lower():
        raise net.FetchRefused("UNSAFE_XML", "the feed declares a DTD or entities, which are not accepted")
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise net.FetchRefused("MALFORMED_FEED", str(exc)[:120]) from None
    out = []
    for item in root.iter("item"):
        g = lambda tag: (item.findtext(tag) or "").strip()  # noqa: E731
        out.append({"title": g("title"), "link": g("link"), "published_date": _iso_date(g("pubDate")), "pub_raw": g("pubDate"),
                    "description": re.sub(r"\s+", " ", g("description"))})
    return out


class Provider:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.id, self.label, self.kind = cfg["id"], cfg["label"], cfg["kind"]
        self.source = next(s for s in reg.approved_sources()["sources"] if s["id"] == cfg["approved_source_id"])

    def applies(self, entity_id: str) -> bool:
        e = self.cfg.get("entities", [])
        return e == "*" or entity_id in e

    def search(self, query: EntityQuery, transport, *, window_start: date, as_of: date):
        """-> (refs, excluded, notes). `excluded` are items seen but not usable, each with the reason."""
        raise NotImplementedError

    def retrieve(self, ref: DocumentRef, transport) -> RetrievedDocument:
        raise NotImplementedError


class FeedProvider(Provider):
    def search(self, query, transport, *, window_start, as_of):
        res = transport.get(self.cfg["url"], accept="application/rss+xml, application/xml, text/xml")
        if res.status != 200:
            raise net.FetchRefused("HTTP_ERROR", f"{self.label}: HTTP {res.status}")
        items = parse_feed(res.body)
        refs, excluded = [], []
        for it in items[: self.cfg.get("max_items", 50)]:
            stub = {"url": it["link"], "title": it["title"], "published_date": it["published_date"], "provider_id": self.id}
            if not it["published_date"]:
                excluded.append({**stub, "reason": "the feed item has no usable publication date"})
            elif not reg.source_policy(it["link"]):
                excluded.append({**stub, "reason": f"source host '{urlsplit(it['link']).hostname}' is not on the approved source list; not retrieved"})
            elif it["published_date"] < window_start.isoformat() or it["published_date"] > as_of.isoformat():
                excluded.append({**stub, "reason": f"published outside the window {window_start.isoformat()} to {as_of.isoformat()}"})
            else:
                refs.append(DocumentRef(self.id, it["link"], it["title"], it["published_date"], it["description"], date_basis=f"feed pubDate '{it['pub_raw']}'"))
        return refs, excluded, [f"{self.label}: {len(items)} item(s) in the feed"]

    def retrieve(self, ref, transport):
        res = transport.get(ref.url, accept="text/html")
        if res.status != 200:
            raise net.FetchRefused("HTTP_ERROR", f"HTTP {res.status} for {ref.url}")
        policy = reg.source_policy(res.final_url)
        if not policy or policy["id"] != self.source["id"]:
            raise net.FetchRefused("HOST_NOT_APPROVED", "the document redirected outside the approved source")
        return RetrievedDocument(self.id, self.source["id"], self.source["tier"], self.cfg.get("publisher") or self.label.split(" (")[0], ref.url, res.final_url, ref.title,
                                 ref.published_date, ref.date_basis, res.body, res.content_type, to_text(res.body, "html_text"), "html_text", res.fetched_at, res.status)


class FederalRegisterProvider(Provider):
    FIELDS = ("title", "abstract", "document_number", "html_url", "publication_date", "type", "agencies")

    def search_url(self, term: str, window_start: date, as_of: date) -> str:
        qs = (f"?conditions%5Bterm%5D={quote(chr(34) + term + chr(34))}&conditions%5Bpublication_date%5D%5Bgte%5D={window_start.isoformat()}"
              f"&conditions%5Bpublication_date%5D%5Blte%5D={as_of.isoformat()}&order=newest&per_page={self.cfg.get('max_items', 25)}"
              + "".join(f"&fields%5B%5D={f}" for f in self.FIELDS))
        return self.cfg["url"] + qs

    def search(self, query, transport, *, window_start, as_of):
        refs, excluded, notes, seen = [], [], [], set()
        for term in query.terms[:3]:
            res = transport.get(self.search_url(term, window_start, as_of), accept="application/json")
            if res.status != 200:
                raise net.FetchRefused("HTTP_ERROR", f"{self.label}: HTTP {res.status}")
            doc = json.loads(res.body.decode("utf-8"))
            notes.append(f"{self.label}: {doc.get('count', 0)} document(s) match '{term}' in the window")
            for rec in doc.get("results", []):
                if rec["document_number"] in seen:
                    continue
                seen.add(rec["document_number"])
                stub = {"url": rec.get("html_url"), "title": rec.get("title"), "published_date": rec.get("publication_date"), "provider_id": self.id}
                if not reg.source_policy(rec.get("html_url") or ""):
                    excluded.append({**stub, "reason": "the record's URL is not on the approved source list"})
                    continue
                refs.append(DocumentRef(self.id, rec["html_url"], rec["title"], rec["publication_date"], rec.get("abstract") or "",
                                        record={k: rec.get(k) for k in self.FIELDS}, date_basis="Federal Register API field publication_date"))
        return refs, excluded, notes

    def retrieve(self, ref, transport):
        raw = canonical_bytes(ref.record)
        agencies = ", ".join(a.get("name") or a.get("raw_name", "") for a in ref.record.get("agencies") or []) or "agency not stated"
        return RetrievedDocument(self.id, self.source["id"], self.source["tier"], f"Federal Register ({agencies})", ref.url, ref.url, ref.title, ref.published_date, ref.date_basis,
                                 raw, "application/json", to_text(raw, "api_json"), "api_json", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), 200,
                                 extras={"document_type": ref.record.get("type"), "agencies": agencies, "location": self.cfg.get("location")})


KINDS = {"rss": FeedProvider, "federal_register": FederalRegisterProvider}


def load_providers() -> list:
    return [KINDS[c["kind"]](c) for c in load_config()]
