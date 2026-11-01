"""Collapse several reports of the same underlying event into one, deterministically. The primary report is the best source; the others are kept as 'also reported by'."""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlsplit

TIER_RANK = {"PRIMARY_ISSUER": 0, "PRIMARY_REGULATOR": 1, "PRIMARY_RELATED_PARTY": 2}
_STOP = {"the", "a", "an", "and", "of", "for", "to", "in", "on", "with", "by", "at", "from", "as", "its", "new"}


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    return f"{(p.hostname or '').lower()}{p.path.rstrip('/').lower()}"


def tokens(title: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", title.lower()) if t not in _STOP and len(t) > 1}


def similar(a, b, threshold: float = 0.6) -> bool:
    if canonical_url(a.doc.url) == canonical_url(b.doc.url):
        return True
    if set(a.evidence_quotes) & set(b.evidence_quotes):
        return True
    gap = abs((date.fromisoformat(a.event_date) - date.fromisoformat(b.event_date)).days)
    ta, tb = tokens(a.title), tokens(b.title)
    return gap <= 1 and bool(ta and tb) and len(ta & tb) / len(ta | tb) >= threshold


def dedupe(candidates: list):
    """-> (primaries, rejections[{reason, url, title, published_date, stage}])."""
    parent = list(range(len(candidates)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            if similar(candidates[i], candidates[j]):
                parent[find(j)] = find(i)
    groups: dict = {}
    for i, c in enumerate(candidates):
        groups.setdefault(find(i), []).append(c)
    primaries, rejected = [], []
    for group in groups.values():
        group.sort(key=lambda c: (TIER_RANK.get(c.doc.tier, 9), -len(c.evidence_quotes), c.doc.url))
        head, rest = group[0], group[1:]
        head.also_reported_by = [c.doc.url for c in rest]
        primaries.append(head)
        for c in rest:
            rejected.append({"stage": "DEDUPE", "reason": f"another report of the same event; kept the {head.doc.tier.replace('_', ' ').lower()} source {head.doc.url}",
                             "url": c.doc.url, "title": c.title, "published_date": c.published_date})
    return sorted(primaries, key=lambda c: c.id), rejected
