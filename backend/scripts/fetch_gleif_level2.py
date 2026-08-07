"""Fetch GLEIF Level-2 (relationship) data for every entity in
backend/data/gleif_sample.json and cache the result locally, so normal app
startup NEVER depends on network access (BUILD_MANDATE offline requirement).

Follows the real GLEIF API conventions (api.gleif.org/api/v1), not guessed
identifiers:

    GET /lei-records/{lei}                       -> relationships.direct-parent
                                                      / relationships.ultimate-parent
                                                      links: either "related"
                                                      (real reported parent) or
                                                      "reporting-exception"
                                                      (entity reported it has
                                                      none / declined to report)
    GET /lei-records/{lei}/direct-parent-relationship     -> relationship record
    GET /lei-records/{lei}/ultimate-parent-relationship   -> relationship record

Run:
    python backend/scripts/fetch_gleif_level2.py

Output: backend/data/gleif_level2_cache.json
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
GLEIF_API = "https://api.gleif.org/api/v1"


def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.api+json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _relationship_record(lei, kind):
    """kind: 'direct-parent-relationship' or 'ultimate-parent-relationship'."""
    try:
        rec = _get(f"{GLEIF_API}/lei-records/{lei}/{kind}")
    except Exception:
        return None
    rel = rec.get("data", {}).get("attributes", {}).get("relationship")
    if not rel:
        return None
    return {
        "parent_lei": rel["endNode"]["id"],
        "child_lei": rel["startNode"]["id"],
        "relationship_type": rel["type"],
        "status": rel.get("status"),
    }


def fetch_level2_for_entity(name, lei):
    try:
        base = _get(f"{GLEIF_API}/lei-records/{lei}")
    except Exception as exc:
        return {"lei": lei, "error": str(exc)}
    rels = base.get("data", {}).get("relationships", {})
    dp_links = rels.get("direct-parent", {}).get("links", {})
    up_links = rels.get("ultimate-parent", {}).get("links", {})

    direct_parent = _relationship_record(lei, "direct-parent-relationship") if "related" in dp_links else None
    ultimate_parent = _relationship_record(lei, "ultimate-parent-relationship") if "related" in up_links else None

    return {
        "lei": lei,
        "direct_parent": direct_parent,
        "direct_parent_reporting_exception": "reporting-exception" in dp_links and "related" not in dp_links,
        "ultimate_parent": ultimate_parent,
        "ultimate_parent_reporting_exception": "reporting-exception" in up_links and "related" not in up_links,
        "source": "GLEIF",
        "source_type": "REAL_PUBLIC_DATA",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    with open(os.path.join(DATA_DIR, "gleif_sample.json")) as f:
        gleif_sample = json.load(f)

    cache = {}
    for name, rec in gleif_sample.items():
        if not rec or "lei" not in rec:
            continue
        print(f"Fetching Level-2 relationships for {name} ({rec['lei']})...")
        cache[name] = fetch_level2_for_entity(name, rec["lei"])
        time.sleep(0.1)  # be polite to the public API

    out_path = os.path.join(DATA_DIR, "gleif_level2_cache.json")
    with open(out_path, "w") as f:
        json.dump(cache, f, indent=2)
    n_with_direct = sum(1 for v in cache.values() if v.get("direct_parent"))
    n_with_ultimate = sum(1 for v in cache.values() if v.get("ultimate_parent"))
    print(f"Wrote {out_path}: {len(cache)} entities, {n_with_direct} with a reported direct parent, "
          f"{n_with_ultimate} with a reported ultimate parent.")


if __name__ == "__main__":
    main()
