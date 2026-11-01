"""Cross-process determinism sweep.

Issues a broad, fixed set of read-only requests (every issuer, counterparty,
theme, priority record and Event Studio scenario) and fingerprints each
response BYTE FOR BYTE - list order included, nothing sorted or masked.
Running it in two processes with different PYTHONHASHSEED values and
comparing the fingerprints shows exactly which outputs depend on Python's
per-process string-hash randomisation (set / dict-of-set iteration order).

    python -m validation.determinism --out sweep.json
    python -m validation.determinism --compare a.json b.json

Excluded on purpose: timing-dependent output (the scalability benchmark).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

EVENT_TEXTS = [
    "A magnitude 7.2 earthquake struck near Hsinchu, Taiwan, disrupting semiconductor fabrication at several TSMC plants and raising concerns for NVIDIA, AMD and Apple chip supply.",
    "A major earthquake in Taiwan disrupts semiconductor fabrication facilities.",
    "Russia-Ukraine escalation raises energy and defense risks.",
    "Regional bank funding stress after a major bank failure.",
    "AI bubble fears hit NVIDIA, Microsoft and Alphabet as GPU demand slows.",
    "New export controls on advanced chips to China hit ASML, Applied Materials and SK Hynix.",
    "Oil prices spike after OPEC cuts; Shell, Exxon and BP rally while Maersk shipping costs rise.",
    "JPMorgan and Citigroup face credit losses as Deutsche Bank warns on funding.",
    "TSMC supply chain disruption",
]
SEARCH_QUERIES = ["IBM", "TSM", "Taiwan", "AI bubble", "TSM supply chain", "SKHY", "semiconductors",
                  "TSMC supply disruption after Taiwan earthquake", "CP_ALPHA", "bank funding stress"]


def requests(request) -> list:
    """(name, method, path, body) for the sweep; `request` fetches lists we depend on."""
    _, entities = request("GET", "/api/entities?limit=1000", None)
    issuers = [e["id"] for e in entities["results"]]
    _, cps = request("GET", "/api/counterparties", None)
    cp_ids = [c["id"] if "id" in c else c["counterparty_id"] for c in cps["results"]]
    _, themes = request("GET", "/api/themes", None)
    theme_ids = [t["theme_id"] for t in themes["results"]]
    _, queue = request("GET", "/api/priority-queue", None)
    ccr_ids = [r["id"] for r in queue["results"]]

    out = [("entities", "GET", "/api/entities", None), ("counterparties", "GET", "/api/counterparties", None),
           ("themes", "GET", "/api/themes", None), ("priority_queue", "GET", "/api/priority-queue", None),
           ("breaches", "GET", "/api/breaches", None), ("provenance", "GET", "/api/provenance", None),
           ("provenance_coverage", "GET", "/api/provenance/coverage", None),
           ("backtest_scenarios", "GET", "/api/backtest/scenarios", None),
           ("backtest_run", "GET", "/api/backtest/run", None),
           ("presets", "GET", "/api/model-lab/presets", None),
           ("anchors", "GET", "/api/model-lab/calibration/anchors", None),
           ("metric_definitions", "GET", "/api/metric-definitions", None),
           ("sample_scenarios", "GET", "/api/event/sample-scenarios", None),
           ("distance_list", "GET", "/api/distance-map/counterparties", None)]
    for e in issuers:
        out += [(f"entity:{e}", "GET", f"/api/entities/{e}", None),
                (f"graph1:{e}", "GET", f"/api/graph/ego/{e}", None),
                (f"graph2:{e}", "GET", f"/api/graph/ego/{e}?hops=2", None),
                (f"score:{e}", "POST", "/api/model-lab/score", {"entity_id": e})]
    for a, b in [("TSM", "NVDA"), ("TSM", "SSNLF"), ("JPM", "BAC"), ("XOM", "SHEL"), ("IBM", "MSFT"), ("AMD", "INTC")]:
        out += [(f"explain:{a}:{b}", "GET", f"/api/entities/{a}/explain/{b}", None),
                (f"pair:{a}:{b}", "POST", "/api/model-lab/pair", {"a": a, "b": b})]
    for c in cp_ids:
        out += [(f"cp360:{c}", "GET", f"/api/counterparties/{c}", None),
                (f"distance:{c}", "GET", f"/api/distance-map/counterparty/{c}", None),
                (f"graphcp:{c}", "GET", f"/api/graph/ego/{c}?hops=2", None)]
    for t in theme_ids:
        out.append((f"theme:{t}", "GET", f"/api/themes/{t}", None))
    for c in ccr_ids:
        out += [(f"priority:{c}", "GET", f"/api/priority-queue/{c}", None),
                (f"clusters:{c}", "GET", f"/api/priority-queue/{c}/risk-clusters", None)]
    for i, text in enumerate(EVENT_TEXTS):
        out.append((f"event:{i}", "POST", "/api/event/parse", {"text": text}))
        out.append((f"event_hops3:{i}", "POST", "/api/event/parse", {"text": text, "max_hops": 3, "top_k": 30}))
    for q in SEARCH_QUERIES:
        out.append((f"search:{q}", "GET", f"/api/search?q={q}", None))
    for preset in ("general", "supply_chain_shock", "market_funding_shock", "thematic_tech_shock"):
        out.append((f"score_preset:{preset}", "POST", "/api/model-lab/score", {"entity_id": "TSM", "preset": preset}))
    out += [("calibration_run", "POST", "/api/model-lab/calibration/run", {}),
            ("market_agreement", "POST", "/api/model-lab/calibration/market-agreement", {})]
    return out


def fingerprint(body) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def sweep(request) -> dict:
    """name -> {"status", "fingerprint", "body"} (body kept so a difference can be explained)."""
    result = {}
    for name, method, path, body in requests(request):
        status, data = request(method, path, body)
        result[name] = {"status": status, "fingerprint": fingerprint(data), "body": data}
    return result


def first_difference(a, b, path="$"):
    """Where two JSON values first differ (list order matters)."""
    if type(a) is not type(b):
        return path, a, b
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}.{k}", a.get(k, "<absent>"), b.get(k, "<absent>")
            d = first_difference(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_difference(x, y, f"{path}[{i}]")
            if d:
                return d
        if len(a) != len(b):
            return f"{path}.length", len(a), len(b)
        return None
    return None if a == b else (path, a, b)


def compare(first: dict, second: dict) -> list:
    """Names whose responses differ, with the first differing path."""
    diffs = []
    for name in sorted(set(first) | set(second)):
        a, b = first.get(name), second.get(name)
        if a is None or b is None:
            diffs.append((name, "<missing in one run>", None, None))
        elif a["status"] != b["status"] or a["fingerprint"] != b["fingerprint"]:
            where = first_difference(a["body"], b["body"]) or ("status", a["status"], b["status"])
            diffs.append((name, *where))
    return diffs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m validation.determinism")
    parser.add_argument("--out", help="write the sweep to this file")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"), help="compare two sweep files")
    args = parser.parse_args(argv)

    if args.compare:
        a, b = (json.load(open(p)) for p in args.compare)
        diffs = compare(a, b)
        for name, path, x, y in diffs:
            print(f"DIFFERS {name}: first difference at {path}: {str(x)[:70]!r} vs {str(y)[:70]!r}")
        print(f"{len(a)} requests compared; {len(diffs)} differ")
        return 1 if diffs else 0

    from . import snapshot

    result = sweep(snapshot.fastapi_request())
    if args.out:
        json.dump(result, open(args.out, "w"))
    print(f"{len(result)} requests swept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
