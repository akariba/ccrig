"""End-to-end demonstration of the Data Intelligence Studio on REAL data already in the repository.

    python scripts/studio_demo.py            (from backend/)

Uses a throw-away workspace and the real SK hynix price file (backend/data/raw_prices). Every step runs the operator CLI in its own process,
so the persistence shown is real. Canonical data is read, never written; the script verifies that at the end.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SRC = next((BACKEND / "data" / "raw_prices").glob("SKHY_price_history_*.csv"))


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
    print(f"\n== {title}\n" + json.dumps(obj, indent=1, sort_keys=True))


def main() -> int:
    before = tree_hash()
    tmp = Path(tempfile.mkdtemp(prefix="studio-demo-"))
    ws, files = tmp / "workspace", tmp / "files"
    files.mkdir()
    lines = SRC.read_text().splitlines()
    (files / "SKHY_batch1.csv").write_text("\n".join(lines[:11]) + "\n")           # header + first 10 closes
    (files / "SKHY_full.csv").write_text("\n".join(lines) + "\n")                    # all 20 closes
    corrupt = lines[:6] + ["2026-07-20,abc", "2026-07-21,149.0", "2026-07-21,151.5", "2026-12-31,150.0"] + lines[6:9]
    (files / "SKHY_corrupt.csv").write_text("\n".join(corrupt) + "\n")

    j1 = cli(ws, "ingest", files / "SKHY_batch1.csv", "--source-id", "skhy-prices-batch1", "--target", "prices", "--scope", "SKHY", "--operator", "demo")
    st1 = cli(ws, "staging", j1["job_id"])
    show("1. first batch (10 real closes) ingested", {"job": j1, "vs_previous": {k: st1["vs_previous_release"][k] for k in ("new", "changed", "unchanged")}, "vs_canonical": {k: st1["vs_canonical"][k] for k in ("new", "changed", "unchanged")}})
    show("   approved by a named reviewer", cli(ws, "approve", j1["job_id"], "--reviewer", "alice", "--reason", "first 10 closes match the canonical SKHY file"))

    j2 = cli(ws, "ingest", files / "SKHY_full.csv", "--source-id", "skhy-prices-batch2", "--target", "prices", "--scope", "SKHY", "--operator", "demo")
    st2 = cli(ws, "staging", j2["job_id"])
    show("2. full file as a second batch", {"job": j2, "vs_previous_release": {k: st2["vs_previous_release"][k] for k in ("version", "new", "changed", "unchanged")}, "vs_canonical": {k: st2["vs_canonical"][k] for k in ("new", "changed", "unchanged")}})
    show("   approved -> version 2", cli(ws, "approve", j2["job_id"], "--reviewer", "alice", "--reason", "10 further closes, identical to the canonical file"))

    again = cli(ws, "ingest", files / "SKHY_full.csv", "--source-id", "skhy-prices-batch2", "--target", "prices", "--scope", "SKHY")
    show("3. the same file again from the same source (idempotent)", {"duplicate": again["duplicate"], "job_id": again["job_id"], "same_as": j2["job_id"]})

    bad = cli(ws, "ingest", files / "SKHY_corrupt.csv", "--source-id", "skhy-prices-corrupt", "--target", "prices", "--scope", "SKHY")
    detail = cli(ws, "show", bad["job_id"])
    show("4. a corrupted copy is blocked", {"status": bad["status"], "blocking": bad["blocking"], "findings": [f"{f['severity']} {f['code']} (row {f.get('row')}): {f['message'][:80]}" for f in detail["findings"]]})
    refusal = cli(ws, "approve", bad["job_id"], "--reviewer", "alice", "--reason", "try anyway", expect=2)
    show("   approval is refused", refusal)

    events = cli(ws, "events", j2["job_id"])
    show("5. job lifecycle for the second batch (real counts and elapsed time)", [f"{e['stage']:8} {e['kind']:9} counts={e['counts']} elapsed_ms={e['elapsed_ms']}" for e in events if e["kind"] == "COMPLETED"])

    show("6. rollback to the previous approved state", cli(ws, "rollback", "prices", "--scope", "SKHY", "--reviewer", "alice", "--reason", "demonstrating restoration"))
    exported = cli(ws, "export", "prices", "--scope", "SKHY")
    show("   current approved state", {"version": exported["version"], "rows": len(exported["canonical_shape"]["rows"]), "approved_by": exported["approved_by"], "warning": exported["warning"]})
    show("7. a brand-new process sees the persisted state", cli(ws, "datasets"))
    show("   hash-chained ledger", cli(ws, "verify-ledger"))

    assert tree_hash() == before, "canonical data changed"
    print("\ncanonical data under backend/data: unchanged (verified by hashing every file before and after)")
    print(f"workspace left at {ws} for inspection")
    return 0


if __name__ == "__main__":
    sys.exit(main())
