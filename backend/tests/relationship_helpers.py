import json
from datetime import date

from app.studio import pipeline, relationships
from app.studio.store import canonical_json
from tests.discovery_helpers import FIX, MANIFEST

AS_OF = date(2026, 11, 1)
ORACLE_URL = next(u for u in MANIFEST["pages"] if "oracle" in u)
ORACLE_TITLE = "NVIDIA and Oracle Expand NVIDIA Vera Rubin to Multi-Gigawatt Scale and Bring NVIDIA Vera CPU to Oracle Cloud Infrastructure"
ORACLE_QUOTE = ("NVIDIA and Oracle today announced plans to expand Oracle Cloud Infrastructure (OCI) Superclusters with NVIDIA Vera Rubin NVL72 systems to multi-gigawatt scale, "
                "supporting growing customer demand for AI training, inference and agentic applications.")
SKHY_QUOTE = ("As a follow-up measure to solidify their previous long-term technical partnership, this agreement allows NVIDIA to secure a stable supply of next-generation AI memory, "
              "while enabling SK hynix to expand the foundation for growth.")
SKHY_URL = "https://news.skhynix.com/en/skhynix-nvidia-partnership-2026/"
SKHY_TITLE = "SK Group and NVIDIA Expand Strategic Partnership Across AI Factories and Next-Generation Memory"


def oracle_source(store):
    return relationships.add_source(store, (FIX / next(f for u, f in MANIFEST["pages"].items() if "oracle" in u)).read_bytes(), url=ORACLE_URL, published_date="2026-10-27", title=ORACLE_TITLE)


def skhy_source(store):
    """A TEST FIXTURE page that contains a real sentence from the SK hynix release (the original page is not stored in the repository)."""
    html = (f"<html><head><title>{SKHY_TITLE}</title></head><body><h1>{SKHY_TITLE}</h1><p>Seoul, July 25, 2026 – SK Group and NVIDIA today announced a partnership.</p>"
            f"<p>{SKHY_QUOTE}</p></body></html>").encode()
    return relationships.add_source(store, html, url=SKHY_URL, published_date="2026-07-25", title=SKHY_TITLE)


def rel_row(src, source, target, relation, quotes, *, basis="PROPOSER_ASSERTED", rationale="The release says OCI deploys NVIDIA systems; that is a customer relationship.", cue=None, as_of=None, **over):
    row = {"id": f"rel-{source.lower()}-{relation.lower().replace('_', '-')}-{target.lower()}-{src['source_sha256'][:6]}", "source": source, "target": target, "relation": relation,
           "relationship_as_of": as_of or src["source_published_date"], "evidence_quotes": list(quotes), "source_url": src["source_url"], "source_publisher": src["source_publisher"],
           "source_tier": src["source_tier"], "approved_source_id": src["approved_source_id"], "source_title": src["source_title"], "source_published_date": src["source_published_date"],
           "retrieved_at": src["retrieved_at"], "source_sha256": src["source_sha256"], "text_method": src["text_method"],
           "assertion": {"basis": basis, "cue": cue, "direction_basis": f"{source} is stated as the {relation.lower().replace('_', ' ')} side", "rationale": rationale},
           "verification": {**src["verification"], "quotes_total": len(quotes), "quotes_found": len(quotes)}, "is_synthetic": False}
    row.update(over)
    return row


def ingest_rows(store, rows, target="relationship_evidence", *, source_id="relationship-evidence", scope="", name="rows.json", key="rows"):
    return pipeline.ingest(store, canonical_json({key: rows}).encode(), source_id=source_id, filename=name, target=target, scope=scope, operator="tester", as_of=AS_OF)["job"]
