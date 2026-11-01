"""Record a real Oracle-NVIDIA run through the operator API and save it as a static asset for read-only "Recorded replay".

    python scripts/record_flow.py          (from backend/; writes ../frontend/public/studio-recordings/oracle-nvidia.json)

Nothing is simulated: the script starts a throwaway workspace, submits both claims through the same endpoints the Studio page uses, approves the asserted one as a named
demonstration reviewer, reads the Graph Explorer's overlay, rolls the relationship back, and saves what the API returned. The public site replays this file; it cannot run,
approve or roll back anything. The stored excerpt is public (a release published by NVIDIA); no confidential data is involved.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
OUT = BACKEND.parent / "frontend" / "public" / "studio-recordings" / "oracle-nvidia.json"
TOKEN = "recording-only"
H = {"X-Studio-Token": TOKEN}
REVIEWER = "recording-reviewer"


def main() -> int:
    ws = Path(tempfile.mkdtemp(prefix="flow-recording-")) / "workspace"
    os.environ.update(CCRIG_ENABLE_STUDIO="1", CCRIG_STUDIO_TOKEN=TOKEN, CCRIG_STUDIO_DIR=str(ws))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers import graph, studio, studio_ops

    app = FastAPI()
    for r in (studio.router, studio_ops.router, graph.router):
        app.include_router(r)
    c = TestClient(app)

    def get(path, **kw):
        r = c.get(path, headers=H, **kw)
        assert r.status_code == 200, (path, r.status_code, r.text[:300])
        return r.json()

    def post(path, body):
        r = c.post(path, headers=H, json=body)
        assert r.status_code == 200, (path, r.status_code, r.text[:300])
        return r.json()

    def ego():
        shown = c.get("/api/graph/ego/ORCL?layers=fact&hops=1&include_studio=true").json()
        edge = next((e for e in shown["edges"] if e["relation"] == "SUPPLIES" and e["source"] == "NVDA"), None)
        proof = {"edge_present": edge is not None, "overlay": {k: shown.get("studio_overlay", {}).get(k) for k in ("available", "edges_added")}}
        if edge:
            ev = edge["evidence"]["studio_evidence"][0]
            proof["edge"] = {"source": edge["source"], "relation": edge["relation"], "target": edge["target"], "weight": edge["weight"], "evidence_status": edge["evidence"]["evidence_status"],
                             "provenance": {k: ev[k] for k in ("source_url", "source_publisher", "source_published_date", "relationship_as_of", "source_sha256")}, "assertion": ev["assertion"]["basis"]}
        return proof

    scen = get("/api/studio/flow/scenarios")
    preview = get("/api/studio/flow/scenarios/oracle-nvidia")
    naive = post("/api/studio/flow/run", {"scenario": "oracle-nvidia", "claim": "cooccurrence", "operator": "recording-script"})
    naive_view = get(f"/api/studio/flow/jobs/{naive['job']['job_id']}")
    first = post("/api/studio/flow/run", {"scenario": "oracle-nvidia", "claim": "asserted", "operator": "recording-script"})
    jid = first["job"]["job_id"]
    after_ingest = get(f"/api/studio/flow/jobs/{jid}")
    again = post("/api/studio/flow/run", {"scenario": "oracle-nvidia", "claim": "asserted", "operator": "recording-script"})
    assert again["duplicate"] and again["job"]["job_id"] == jid
    proof_before = ego()
    post(f"/api/studio/jobs/{jid}/approve", {"reviewer": REVIEWER, "reason": "Recording: confirmed against the quoted sentence.", "acknowledge_assertions": True})
    after_approval = get(f"/api/studio/flow/jobs/{jid}")
    proof_live = ego()
    post("/api/studio/datasets/relationship_evidence/rollback", {"reviewer": REVIEWER, "reason": "Recording: demonstrating rollback."})
    after_rollback = get(f"/api/studio/flow/jobs/{jid}")
    proof_after = ego()
    assert not proof_before["edge_present"] and proof_live["edge_present"] and not proof_after["edge_present"]
    support = get("/api/studio/flow/support")

    rec = {"schema": "ccrig.flow-recording.v1", "label": "Recorded replay", "scenario": "oracle-nvidia", "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "recorded_by": "backend/scripts/record_flow.py",
           "note": ("A real run through the operator API in a throwaway workspace on the recording machine. Approval and rollback were performed by the script acting as the demonstration reviewer "
                    f"'{REVIEWER}'; in live use a named person decides. This file is a recording: nothing on this site ingests, approves or rolls back data."),
           "preview": preview, "scenario_info": scen["scenarios"][0], "support": support,
           "cooccurrence": {"after_ingest": naive_view},
           "asserted": {"after_ingest": after_ingest, "after_approval": after_approval, "after_rollback": after_rollback, "duplicate_submission": {"job_id": again["job"]["job_id"], "duplicate": True}},
           "graph_proof": {"before_approval": proof_before, "after_approval": proof_live, "after_rollback": proof_after,
                           "note": "Read from the Graph Explorer's endpoint (ego network of ORCL, approved relationships included) at each point of the run."}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes); job {jid}; ledger {after_rollback['ledger']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
