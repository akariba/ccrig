"""Baseline for the Global Event Impact Map responses (separate from analytics_snapshot.json, which
this feature does not touch). Pins exactly what the map is told: events, order, locations, evidence,
typed paths and limitations. A change here is a change to what users see.

    python -m validation.impact_snapshot --write     # re-record (intended changes only)
    python -m validation.impact_snapshot --check
"""
import argparse
import json
import sys

from . import snapshot

IMPACT_FILE = snapshot.BASELINE_DIR / "impact_map_snapshot.json"
REQUESTS = [
    ("search:NVIDIA", "/api/impact-map/search?q=NVIDIA"),
    ("search:no-match", "/api/impact-map/search?q=zzzzqq"),
    ("events:NVDA", "/api/impact-map/NVDA/events"),
    ("events:NVDA:30d", "/api/impact-map/NVDA/events?recency_days=30"),
    ("events:NVDA:wide", "/api/impact-map/NVDA/events?recency_days=730"),
    ("events:NVDA:as-of-2026-06-30", "/api/impact-map/NVDA/events?as_of=2026-06-30"),
    ("events:TSM", "/api/impact-map/TSM/events"),
    ("register", "/api/impact-map/register"),
]


def capture(request) -> dict:
    out = {}
    for name, path in REQUESTS:
        status, body = request("GET", path, None)
        out[name] = {"status": status, "body": body}
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m validation.impact_snapshot")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    actual = snapshot.normalise(capture(snapshot.fastapi_request()))
    if args.write:
        IMPACT_FILE.write_text(json.dumps(actual, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
        print(f"wrote {IMPACT_FILE}")
        return 0
    diffs = snapshot.diff(json.loads(IMPACT_FILE.read_text()), actual)
    for p, e, a in diffs:
        print(f"DRIFT {p}: expected {e!r}, got {a!r}")
    print("OK: no drift" if not diffs else "FAILED")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
