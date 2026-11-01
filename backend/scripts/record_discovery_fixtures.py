"""Record small, real fixtures for the event-discovery tests (developer tool; needs network).

    CCRIG_DISCOVERY_NETWORK=1 python scripts/record_discovery_fixtures.py

Saves: the NVIDIA newsroom feed (item titles, links, dates and summaries only), a short excerpt of each approved release page it links to
(the first ~1,600 characters of the article body), and the Federal Register API responses for a few company searches. The tests replay these;
nothing in the test suite touches the network.
"""
import json
import re
import sys
from datetime import date, timedelta
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import event_register as reg  # noqa: E402
from app.discovery import extract, net, providers  # noqa: E402
from app.discovery.entity import build_query  # noqa: E402
from app.discovery.service import host_policy_ok  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "discovery"
AS_OF = date(2026, 11, 1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t = net.HttpTransport(host_policy_ok)
    prov = {p.id: p for p in providers.load_providers()}
    feed = t.get(prov["nvidia_newsroom_feed"].cfg["url"])
    items = providers.parse_feed(feed.body)
    approved = [i for i in items if reg.source_policy(i["link"])][:4]
    others = [i for i in items if not reg.source_policy(i["link"])][:3]
    xml = ['<?xml version="1.0" encoding="utf-8"?>', '<rss version="2.0"><channel><title>News Releases - NVIDIA Newsroom (test fixture: titles, links, dates)</title>']
    for it in approved + others:
        xml.append(f"<item><title>{escape(it['title'])}</title><link>{escape(it['link'])}</link><pubDate>{it['pub_raw']}</pubDate><description>{escape(it['description'][:300])}</description></item>")
    xml.append("</channel></rss>")
    (OUT / "feed_nvidia.xml").write_text("\n".join(xml), "utf-8")
    pages = {}
    for it in approved:
        res = t.get(it["link"])
        text = reg.html_to_text(res.body.decode("utf-8", "replace"))
        i = text.rfind(it["title"])
        body = text[i + len(it["title"]):][:1600].rsplit(" ", 1)[0] if i >= 0 else ""
        slug = extract.slug(it["title"])[:40]
        html = (f"<html><head><title>{escape(it['title'])} | NVIDIA Newsroom</title></head><body><nav>NVIDIA Newsroom Artificial Intelligence Computing Leadership from NVIDIA</nav>"
                f"<h1>{escape(it['title'])}</h1><div>{escape(body)}</div><footer>(test fixture: excerpt of the real release page)</footer></body></html>")
        (OUT / f"page_{slug}.html").write_text(html, "utf-8")
        pages[it["link"]] = f"page_{slug}.html"
    fr = prov["federal_register"]
    scenarios = {"nvda_2026-11-01": ("NVDA", AS_OF), "nvda_2026-02-01": ("NVDA", date(2026, 2, 1)), "amd_2026-11-01": ("AMD", AS_OF), "jpm_2026-11-01": ("JPM", AS_OF)}
    frs = {}
    for name, (eid, as_of) in scenarios.items():
        q = build_query(eid)
        for term in q.terms[:3]:
            url = fr.search_url(term, as_of - timedelta(days=180), as_of)
            res = t.get(url, accept="application/json")
            doc = json.loads(res.body)
            doc["results"] = doc["results"][:12]
            fname = f"fr_{name}_{extract.slug(term)}.json"
            (OUT / fname).write_text(json.dumps(doc, sort_keys=True, indent=1), "utf-8")
            frs[f"{name}|{term}"] = fname
    (OUT / "manifest.json").write_text(json.dumps({"feed": "feed_nvidia.xml", "pages": pages, "federal_register": frs, "recorded_at": str(AS_OF)}, indent=1, sort_keys=True), "utf-8")
    print("recorded", len(list(OUT.glob("*"))), "files")


if __name__ == "__main__":
    main()
