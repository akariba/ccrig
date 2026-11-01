"""Build and verify the approved-source event register (developer tool, needs network).

    python scripts/event_register.py build     # fetch every source, extract evidence verbatim, write data/events/events_nvidia.json
    python scripts/event_register.py verify    # re-fetch the sources of the committed register and re-check every record

Nothing here writes a quote that is not found, character for character, in the
retrieved source. A spec that cannot be verified is reported and left out; it
is never written with a guessed date, location or quote. The running
application never calls this: it reads the committed register, which is what
makes the Pyodide (static) build work offline.

To add an event, add a spec (URL + anchors that identify the passages to cite),
run `build`, and review the diff. The register is data you can audit.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import event_register as reg  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; CCRIG-event-verification/0.1)", "Accept": "text/html,application/json"}
PRESS = "nvidia_newsroom"


def spec(id, title, url, published, category, anchors, location_key, location_anchor, *, publisher="NVIDIA Investor Relations",
         kind="html", api_url=None, location_basis=None, event_date_basis="press release date; the release says 'today announced'"):
    return dict(id=id, title=title, url=url, published=published, category=category, anchors=anchors, location_key=location_key,
                location_anchor=location_anchor, publisher=publisher, kind=kind, api_url=api_url, location_basis=location_basis,
                event_date_basis=event_date_basis)


SPECS = [
    spec("nvda-20261021-supply-chain-capacity",
         "NVIDIA and Supply Chain Partners Expand Capacity to Accelerate AI Infrastructure Buildout",
         "https://nvidianews.nvidia.com/news/nvidia-and-supply-chain-partners-expand-capacity-to-accelerate-ai-infrastructure-buildout",
         "2026-10-21", "CORPORATE_ANNOUNCEMENT",
         ["NVIDIA today announced plans with a group of supply chain partners", "Samsung Electro-Mechanics is joining NVIDIA’s substrate supply chain",
          "NVIDIA is supporting Unimicron’s KF substrate manufacturing expansion in Taiwan", "Under an agreement signed and announced earlier this year by IBIDEN",
          "will support new U.S. testing facilities", "In Singapore, expanded testing operations"],
         "berlin-de", "GTC Berlin", publisher="NVIDIA Newsroom",
         location_basis="Dateline of the press release: 'GTC Berlin'. The release places the announcement at that conference; the facilities it names are elsewhere (see regions mentioned)."),
    spec("nvda-20261014-semicon-west-ai-fabs",
         "NVIDIA and Semiconductor Leaders Advance AI Across Chip Design and Manufacturing for AI-Defined Fabs",
         "https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-and-Semiconductor-Leaders-Advance-AI-Across-Chip-Design-and-Manufacturing-for-AI-Defined-Fabs/default.aspx",
         "2026-10-14", "CORPORATE_ANNOUNCEMENT",
         ["SAN FRANCISCO, Oct. 14, 2026 (GLOBE NEWSWIRE) -- SEMICON West", "Applied Materials, Cadence, KLA, Lam Research, Siemens, Synopsys and other semiconductor leaders",
          "FANUC and Foxconn are connecting their robot models"],
         "san-francisco-us", "SAN FRANCISCO, Oct. 14, 2026"),
    spec("nvda-20261008-us-science-commitment",
         "NVIDIA Commits $1 Billion to Advance US Science Over the Next Five Years",
         "https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Commits-1-Billion-to-Advance-US-Science-Over-the-Next-Five-Years/default.aspx",
         "2026-10-08", "CORPORATE_ANNOUNCEMENT",
         ["SANTA CLARA, Calif., Oct. 08, 2026 (GLOBE NEWSWIRE) -- NVIDIA today announced commitments valued at $1 billion"],
         "santa-clara-us", "SANTA CLARA, Calif., Oct. 08, 2026"),
    spec("nvda-20260826-q2-fy2027-results",
         "NVIDIA Announces Financial Results for Second Quarter Fiscal 2027",
         "https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-Second-Quarter-Fiscal-2027/default.aspx",
         "2026-08-26", "EARNINGS_RELEASE",
         ["SANTA CLARA, Calif., Aug. 26, 2026 (GLOBE NEWSWIRE) -- NVIDIA (NASDAQ: NVDA) today reported revenue for the second quarter",
          "Vera Rubin platform is ramping into full production", "multiyear technology partnership with SK hynix",
          "not assuming any Data Center compute revenue from China"],
         "santa-clara-us", "SANTA CLARA, Calif., Aug. 26, 2026"),
    spec("nvda-20260725-sk-group-partnership",
         "SK Group and NVIDIA Expand Strategic Partnership Across AI Factories and Next-Generation Memory",
         "https://news.skhynix.com/en/skhynix-nvidia-partnership-2026/",
         "2026-07-25", "PARTNERSHIP_ANNOUNCEMENT",
         ["Seoul, July 25, 2026 – SK Group and NVIDIA today announced plans for a $500 billion plus comprehensive partnership",
          "SK hynix is also entering into a long-term AI memory partnership with NVIDIA",
          "this agreement allows NVIDIA to secure a stable supply of next-generation AI memory",
          "plans for SK Telecom to build a 2 gigawatt-scale AI Cloud in Korea"],
         "seoul-kr", "Seoul, July 25, 2026", publisher="SK hynix Newsroom"),
    spec("nvda-20260601-gtc-taipei-rtx-spark",
         "NVIDIA and Microsoft Reinvent Windows PCs for the Age of Personal AI",
         "https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-and-Microsoft-Reinvent-Windows-PCs-for-the-Age-of-Personal-AI/default.aspx",
         "2026-06-01", "PRODUCT_ANNOUNCEMENT",
         ["TAIPEI, Taiwan, June 01, 2026 (GLOBE NEWSWIRE) -- NVIDIA GTC Taipei",
          "NVIDIA and Microsoft collaborate to deliver a native Windows experience for personal agents"],
         "taipei-tw", "TAIPEI, Taiwan, June 01, 2026"),
    spec("nvda-20260115-bis-h200-china-license-policy",
         "Revision to License Review Policy for Advanced Computing Commodities",
         "https://www.federalregister.gov/documents/2026/01/15/2026-00789/revision-to-license-review-policy-for-advanced-computing-commodities",
         "2026-01-15", "REGULATORY_ACTION",
         ["The Bureau of Industry and Security (BIS) is revising its license review policy for exports of certain semiconductors to China and Macau",
          "The semiconductors covered by this rule are the Nvidia H200 and its equivalents"],
         "country-us", "Bureau of Industry and Security", publisher="Federal Register (Commerce Department, Bureau of Industry and Security)",
         kind="federal_register_api", api_url="https://www.federalregister.gov/api/v1/documents/2026-00789.json",
         location_basis="Issued by a United States federal agency (Commerce Department, Bureau of Industry and Security, per the Federal Register's agency "
                        "metadata). The document states no city, so the location is country-level.",
         event_date_basis="Federal Register publication date; the rule's own effective date is not asserted here"),
    spec("nvda-20260105-ces-rubin-platform",
         "NVIDIA Kicks Off the Next Generation of AI With Rubin — Six New Chips, One Incredible AI Supercomputer",
         "https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Kicks-Off-the-Next-Generation-of-AI-With-Rubin--Six-New-Chips-One-Incredible-AI-Supercomputer/default.aspx",
         "2026-01-05", "PRODUCT_ANNOUNCEMENT",
         ["LAS VEGAS, Jan. 05, 2026 (GLOBE NEWSWIRE) -- CES -- NVIDIA today kickstarted the next generation of AI",
          "Microsoft’s next-generation Fairwater AI superfactories", "Among the world’s leading AI labs, cloud service providers, computer makers and startups expected to adopt Rubin"],
         "las-vegas-us", "LAS VEGAS, Jan. 05, 2026"),
]


# ------------------------------------------------------------------ retrieval
def fetch(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace")


def retrieve(s: dict) -> dict:
    """{'status', 'text', 'page_date_iso'} for one spec's source."""
    if s["kind"] == "federal_register_api":
        status, body = fetch(s["api_url"])
        doc = json.loads(body)
        text = reg.normalize_text(f"{doc.get('title', '')}. {doc.get('abstract', '')}")
        return {"status": status, "text": text, "page_date_iso": doc.get("publication_date")}
    status, body = fetch(s["url"])
    text = reg.html_to_text(body)
    shown = any(form in text for form in reg.long_date_forms(s["published"]))
    m = re.search(r"(?:Jan|Feb|Mar|Apr|May|June?|July?|Aug|Sept?|Oct|Nov|Dec)[a-z]* \d{1,2}, 20\d\d", text)
    return {"status": status, "text": text, "page_date_iso": s["published"] if shown else (m.group(0) if m else None)}


def check(s: dict, quotes=None) -> dict:
    """Retrieve and check one spec. Returns the verification facts; `quotes` (stored) are re-checked, else extracted from anchors."""
    got = retrieve(s)
    text = got["text"]
    problems = []
    if got["page_date_iso"] != s["published"]:
        problems.append(f"publication date not confirmed (page shows {got['page_date_iso']!r}, expected {s['published']!r})")
    if s["title"] not in text:
        problems.append("title not found verbatim in the source")
    if quotes is None:
        quotes = []
        for anchor in s["anchors"]:
            sentence = reg.sentence_containing(text, anchor)
            if sentence is None:
                problems.append(f"anchor not found: {anchor[:60]!r}")
            else:
                quotes.append(sentence)
    found = sum(1 for q in quotes if q in text)
    if found != len(quotes):
        problems.append(f"{len(quotes) - found} quote(s) not found verbatim")
    loc_ok = s["location_anchor"] in text
    if not loc_ok:
        problems.append(f"location basis {s['location_anchor']!r} not found in the source")
    return {"quotes": quotes, "problems": problems, "http_status": got["status"], "text_chars": len(text),
            "verification": {"status": reg.VERIFIED if not problems else "FAILED",
                             "method": "scripts/event_register.py (retrieved the source, matched the date, title, location basis and every quote verbatim)",
                             "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "http_status": got["status"], "date_confirmed": got["page_date_iso"] == s["published"],
                             "quotes_total": len(quotes), "quotes_found": found}}


def record(s: dict, result: dict) -> dict:
    policy = reg.source_policy(s["url"])
    basis = s["location_basis"] or f"Dateline of the source: '{s['location_anchor']}'."
    return {
        "id": s["id"], "kind": "REAL_EVENT", "title": s["title"], "category": s["category"],
        "published_date": s["published"], "event_date": s["published"], "event_date_basis": s["event_date_basis"],
        "location": {"gazetteer_key": s["location_key"], "basis": basis, "basis_text": s["location_anchor"]},
        "sources": [{"id": "s1", "publisher": s["publisher"], "url": s["url"], "title": s["title"], "published_date": s["published"],
                     "tier": policy["tier"], "approved_source_id": policy["id"], "retrieved_at": result["verification"]["checked_at"]}],
        "evidence": [{"source_id": "s1", "quote": q} for q in result["quotes"]],
        "verification": result["verification"],
    }


def build(out_path: Path) -> int:
    events, failed = [], []
    for s in SPECS:
        try:
            result = check(s)
        except Exception as exc:  # network or parse failure: report, never guess
            failed.append((s["id"], [f"{type(exc).__name__}: {exc}"]))
            continue
        if result["problems"]:
            failed.append((s["id"], result["problems"]))
        else:
            events.append(record(s, result))
            print(f"verified  {s['id']}  ({result['verification']['quotes_found']}/{result['verification']['quotes_total']} quotes)")
    for eid, problems in failed:
        print(f"REJECTED  {eid}: " + "; ".join(problems))
    events.sort(key=lambda e: (e["published_date"], e["id"]), reverse=True)
    out_path.write_text(json.dumps({
        "schema_version": 1,
        "register": {"description": "Real, retrieved publications about NVIDIA from approved primary sources, each verified by retrieval. "
                                    "Built by scripts/event_register.py; edit by re-running it, not by hand.",
                     "coverage": "NVIDIA (NVDA) pilot", "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                     "specs_total": len(SPECS), "specs_rejected": [{"id": i, "problems": p} for i, p in failed]},
        "events": events}, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {out_path} ({len(events)} verified, {len(failed)} rejected)")
    return 0 if not failed else 1


def verify(path: Path) -> int:
    register = json.loads(path.read_text())
    by_id = {s["id"]: s for s in SPECS}
    bad = 0
    for ev in register["events"]:
        s = by_id.get(ev["id"])
        if not s:
            print(f"UNKNOWN  {ev['id']}: no spec"); bad += 1; continue
        try:
            r = check(s, quotes=[e["quote"] for e in ev["evidence"]])
        except Exception as exc:
            print(f"ERROR    {ev['id']}: {type(exc).__name__}: {exc}"); bad += 1; continue
        print(f"{'OK      ' if not r['problems'] else 'DRIFTED '} {ev['id']} {'; '.join(r['problems'])}")
        bad += bool(r["problems"])
    return 1 if bad else 0


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "data" / "events" / "events_nvidia.json"
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit(build(target) if cmd == "build" else verify(target) if cmd == "verify" else print(__doc__) or 2)
