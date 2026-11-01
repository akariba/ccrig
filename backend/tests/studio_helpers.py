import csv
import hashlib
import io
import json
from datetime import date
from pathlib import Path

from app.core.config import DATA_DIR
from app.studio import pipeline

AS_OF = date(2026, 11, 1)
SKHY = (DATA_DIR / "raw_prices" / "SKHY_price_history_2024-01-01_2026-08-06_1day_310ff2.csv").read_bytes()
EDGE_COLS = ["source", "target", "relation", "criticality", "note", "evidence_status", "evidence_url", "is_synthetic"]
URL = "https://example.org/report"


def csv_bytes(header, rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode()


def edge(source="MU", target="AMD", relation="SUPPLIES", crit="0.4", note="n", status="REPORTED_NEWS", url=URL, synth=""):
    return [source, target, relation, crit, note, status, url, synth]


def edges_csv(*rows) -> bytes:
    return csv_bytes(EDGE_COLS, rows or [edge()])


def run(store, data, *, target="fact_edges", filename="edges.csv", source_id="test-source", scope="", **kw):
    return pipeline.ingest(store, data, source_id=source_id, filename=filename, target=target, scope=scope, as_of=kw.pop("as_of", AS_OF), operator=kw.pop("operator", "tester"), **kw)


def tree_hash(root: Path) -> str:
    """One hash over every canonical data file (names and bytes): proves a test left canonical data untouched."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def codes(store, job_id, severity=None):
    return sorted({f["code"] for f in store.findings(job_id) if severity in (None, f["severity"])})
