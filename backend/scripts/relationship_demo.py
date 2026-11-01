"""End-to-end demonstration: a documented issuer relationship, from source page to the graph, with provenance, review history and rollback.

    python scripts/relationship_demo.py          (from backend/)

Source: a stored excerpt of the real NVIDIA/Oracle release of 27 Oct 2026 (the test fixture recorded from nvidianews.nvidia.com; nothing is fetched).
Every step runs the operator CLI in its own process. Canonical data is read, never written; that is verified by hashing at the end.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
FIX = BACKEND / "tests" / "fixtures" / "discovery"
MANIFEST = json.loads((FIX / "manifest.json").read_text())
URL = next(u for u in MANIFEST["pages"] if "oracle" in u)
TITLE = "NVIDIA and Oracle Expand NVIDIA Vera Rubin to Multi-Gigawatt Scale and Bring NVIDIA Vera CPU to Oracle Cloud Infrastructure"
QUOTE = ("NVIDIA and Oracle today announced plans to expand Oracle Cloud Infrastructure (OCI) Superclusters with NVIDIA Vera Rubin NVL72 systems to multi-gigawatt scale, "
         "supporting growing customer demand for AI training, inference and agentic applications.")


def tree_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((BACKEND / "data").rglob("*")):
        if p.is_file():
            h.update(str(p).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def cli(ws, *args, expect=0):
    r = subprocess.run([sys.executable, "-m", "app.studio", "--dir", str(ws), *map(str, args)], cwd=BACKEND, capture_output=True, text=True)
    assert r.returncode == expect, (args, r.returncode, r.stdout, r.stderr)
    return json.loads(r.stdout if expect == 0 else r.stderr)


def show(title, obj):
    print(f"\n== {title}\n" + (obj if isinstance(obj, str) else json.dumps(obj, indent=1, sort_keys=True)))


def row(src, **over):
    base = {"id": f"rel-nvda-supplies-orcl-{src['source_sha256'][:6]}", "source": "NVDA", "target": "ORCL", "relation": "SUPPLIES", "relationship_as_of": "2026-10-27", "evidence_quotes": [QUOTE],
            "source_url": src["source_url"], "source_publisher": src["source_publisher"], "source_tier": src["source_tier"], "approved_source_id": src["approved_source_id"], "source_title": src["source_title"],
            "source_published_date": src["source_published_date"], "retrieved_at": src["retrieved_at"], "source_sha256": src["source_sha256"], "text_method": "html_text",
            "assertion": {}, "verification": {**src["verification"], "quotes_total": 1, "quotes_found": 1}, "is_synthetic": False}
    base.update(over)
    return base


def main() -> int:
    before = tree_hash()
    tmp = Path(tempfile.mkdtemp(prefix="relationship-demo-"))
    ws = tmp / "workspace"
    page = FIX / next(f for u, f in MANIFEST["pages"].items() if "oracle" in u)

    src = cli(ws, "source-add", page, "--url", URL, "--published-date", "2026-10-27", "--title", TITLE)
    show("1. the source page is stored as hash-addressed evidence (approved domain; title and date found in the page)",
         {k: src[k] for k in ("source_url", "source_tier", "source_published_date", "source_sha256")})

    def write(name, rows):
        p = tmp / name
        p.write_text(json.dumps({"rows": rows}))
        return p

    naive = cli(ws, "ingest", write("naive.json", [row(src)]), "--source-id", "rel-naive", "--target", "relationship_evidence")
    rep = cli(ws, "report", naive["job_id"])
    show("2. the same quote, claimed as an explicit statement, is blocked: both companies are named but nothing states a supply relationship",
         {"status": naive["status"], "blocking": naive["blocking"], "verdict": rep["verdict"], "categories": {k: {"errors": v["errors"], "example": v["examples"][0]["message"][:150]} for k, v in rep["categories"].items()}})

    asserted = row(src, assertion={"basis": "PROPOSER_ASSERTED", "cue": None, "direction_basis": "NVIDIA is the supplier; Oracle deploys NVIDIA systems",
                                   "rationale": "The release describes OCI Superclusters built with NVIDIA Vera Rubin NVL72 systems: Oracle deploys NVIDIA's systems, which makes NVIDIA its supplier."})
    job = cli(ws, "ingest", write("asserted.json", [asserted]), "--source-id", "rel-asserted", "--target", "relationship_evidence")
    stg = cli(ws, "staging", job["job_id"])
    show("3. asserted by the proposer with a written rationale: staged with a warning and a preview of its effect on the graph",
         {"status": job["status"], "findings": job["findings"]["by_code"], "graph_effect": stg["graph_effect"], "assertions_to_confirm": stg["assertions_to_confirm"]})
    show("   approval is refused until the reviewer confirms the assertion",
         cli(ws, "approve", job["job_id"], "--reviewer", "alice", "--reason", "looks right", expect=2))
    show("4. approved by a named reviewer", cli(ws, "approve", job["job_id"], "--reviewer", "alice", "--reason", "The release describes OCI deploying NVIDIA systems; confirmed against the quoted sentence.", "--ack-assertions"))

    rels = cli(ws, "relationships")
    eff = rels["adoption_effect"]
    show("5. what the approval changes in the supported graph, and what it does not",
         {"new_edges": eff["new_edges"], "connectivity": {k: eff["connectivity"][k] for k in ("canonical", "with_approved", "newly_connected_issuers")},
          "scoring_changed_by_approval": eff["analytical_coverage"]["scoring_changed_by_approval"]})
    show("6. genuinely linked counterparties, and the gaps stated explicitly",
         {"portfolio_counterparties_holding_NVDA": sorted({x["counterparty"] for x in eff["linked_counterparties"]["portfolio_holdings"]}),
          "ccr_reference_entities": eff["linked_counterparties"]["ccr_reference_entities"], "gaps": eff["gaps"]})

    os.environ.update(CCRIG_ENABLE_STUDIO="1", CCRIG_STUDIO_TOKEN="demo", CCRIG_STUDIO_DIR=str(ws))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers import graph

    app = FastAPI()
    app.include_router(graph.router)
    c = TestClient(app)
    plain = c.get("/api/graph/ego/ORCL?layers=fact&hops=1").json()
    shown = c.get("/api/graph/ego/ORCL?layers=fact&hops=1&include_studio=true").json()
    edge = next(e for e in shown["edges"] if e["relation"] == "SUPPLIES")
    show("7. the relationship in CCRIG's graph (Graph Explorer, include approved relationships), with provenance",
         {"default_view_shows_it": any(e["relation"] == "SUPPLIES" for e in plain["edges"]), "overlay": {k: shown["studio_overlay"][k] for k in ("available", "edges_added")},
          "edge": {"from": edge["source"], "relation": edge["relation"], "to": edge["target"], "weight": edge["weight"], "evidence_status": edge["evidence"]["evidence_status"]},
          "provenance": {k: edge["evidence"]["studio_evidence"][0][k] for k in ("source_url", "source_published_date", "relationship_as_of", "source_sha256")} | {"assertion": edge["evidence"]["studio_evidence"][0]["assertion"]["basis"]},
          "approved_by": shown["studio_overlay"]["release"]["approved_by"]})

    show("8. review history", [{"decision": d["decision"], "reviewer": d["reviewer"], "reason": d["reason"][:90]} for d in cli(ws, "show", job["job_id"])["decisions"]])
    show("9. rollback restores the canonical view", cli(ws, "rollback", "relationship_evidence", "--reviewer", "bob", "--reason", "demonstrating rollback"))
    after = c.get("/api/graph/ego/ORCL?layers=fact&hops=1&include_studio=true").json()
    show("   after rollback the approved edge is gone, the history is not",
         {"supplies_edge_present": any(e["relation"] == "SUPPLIES" for e in after["edges"]), "ledger": cli(ws, "verify-ledger")})

    check = subprocess.run([sys.executable, "-m", "validation.run", "--check"], cwd=BACKEND, capture_output=True, text=True)
    show("10. analytical regression check (scores, ranks, priorities, determinism baselines)", check.stdout.strip().splitlines()[-1])
    assert tree_hash() == before, "canonical data changed"
    print("\ncanonical data under backend/data: unchanged (every file hashed before and after)")
    print(f"workspace left at {ws}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
