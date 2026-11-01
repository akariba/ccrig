import json
from datetime import date, timedelta
from pathlib import Path

from app.discovery import net, providers
from app.discovery.entity import build_query
from app.discovery.service import host_policy_ok

FIX = Path(__file__).resolve().parent / "fixtures" / "discovery"
AS_OF = date(2026, 11, 1)
MANIFEST = json.loads((FIX / "manifest.json").read_text())


def transport(entity_id="NVDA", as_of=AS_OF, window=180, *, feed=True, fr_key=None, extra=None, strict=True):
    """Replays recorded responses for exactly the URLs the providers will request. Unknown URLs fail like a closed network."""
    responses = {}
    pv = {p.id: p for p in providers.load_providers()}
    if feed:
        responses[pv["nvidia_newsroom_feed"].cfg["url"]] = (200, "text/xml", (FIX / MANIFEST["feed"]).read_bytes())
        for url, f in MANIFEST["pages"].items():
            responses[url] = (200, "text/html", (FIX / f).read_bytes())
    q = build_query(entity_id)
    fr = pv["federal_register"]
    key = fr_key or f"{entity_id.lower()}_{as_of.isoformat()}"
    for term in q.terms[:3]:
        name = MANIFEST["federal_register"].get(f"{key}|{term}")
        if name:
            responses[fr.search_url(term, as_of - timedelta(days=window), as_of)] = (200, "application/json", (FIX / name).read_bytes())
    responses.update(extra or {})
    return net.FixtureTransport(responses, host_policy_ok if strict else None)


def blocked(code="NETWORK_DISABLED"):
    class Closed:
        requested = []

        def get(self, url, accept="*/*"):
            self.requested.append(url)
            raise net.FetchRefused(code, "network discovery is not enabled (set CCRIG_DISCOVERY_NETWORK=1 on an operator machine)")
    return Closed()
