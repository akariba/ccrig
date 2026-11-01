"""The approved-relationship overlay: Studio-approved relationship evidence, read-only, layered over the canonical fact graph on request.

The canonical dataset is never edited. With the Studio enabled on an operator machine or private server, a request that asks for it (include_studio) sees the
approved edges in addition to the canonical ones, each carrying its provenance; everything else, including every score, keeps reading the canonical graph.
On the public and static deployments there is no workspace, so the overlay is simply unavailable and says so.
"""
from __future__ import annotations

DATASET = "relationship_evidence"


def group_edges(rows: list) -> list:
    """Evidence rows -> one record per (source, relation, target) with all its evidence, oldest statement first."""
    by_edge: dict = {}
    for r in rows:
        by_edge.setdefault((r["source"], r["relation"], r["target"]), []).append(r)
    out = []
    for (s, rel, t), evid in sorted(by_edge.items()):
        evid = sorted(evid, key=lambda r: (r["relationship_as_of"], r["source_sha256"]))
        out.append({"source": s, "target": t, "relation": rel,
                    "first_documented": evid[0]["relationship_as_of"], "latest_documented": evid[-1]["relationship_as_of"],
                    "evidence": [{"source_url": r["source_url"], "source_publisher": r["source_publisher"], "source_tier": r["source_tier"], "source_published_date": r["source_published_date"],
                                  "relationship_as_of": r["relationship_as_of"], "quotes": r["evidence_quotes"], "assertion": r["assertion"], "source_sha256": r["source_sha256"],
                                  "verification": r["verification"]} for r in evid]})
    return out


def canonical_keys() -> set:
    from ..core.graph_store import FACT_GRAPH

    return {(a, d["relation"], b) for a, b, d in FACT_GRAPH.edges(data=True)}


def load(store):
    """-> (edges, release) for the current approved relationship evidence, or ([], None)."""
    current = store.current(DATASET, "")
    if not current:
        return [], None
    rows = store.read_release(current["release_id"])["rows"]
    canon = canonical_keys()
    edges = group_edges(rows)
    for e in edges:
        e["in_canonical"] = (e["source"], e["relation"], e["target"]) in canon
        e["status"] = "STUDIO_APPROVED"
    return edges, {k: current[k] for k in ("release_id", "version", "approved_by", "created_at", "content_hash", "rows", "job_id")}


def approved(include: bool) -> dict:
    """What a request that asked for the overlay gets: {requested, available, reason, edges, release}. Never raises; says why when unavailable."""
    base = {"requested": include, "available": False, "reason": None, "edges": [], "release": None}
    if not include:
        return base
    from . import config

    if not config.studio_enabled():
        return {**base, "reason": "Approved relationships exist only in an operator's Data Studio workspace. This deployment (the public or static build) shows the canonical dataset only."}
    try:
        root = config.studio_dir()
    except config.UnsafeWorkspace as exc:
        return {**base, "reason": str(exc)}
    if not (root / "studio.db").exists():
        return {**base, "reason": "The Data Studio has no workspace yet, so there are no approved relationships."}
    from .store import StudioStore

    edges, release = load(StudioStore(root))
    if release is None:
        return {**base, "available": True, "reason": "No relationship evidence has been approved yet."}
    return {**base, "available": True, "edges": edges, "release": release}


def merged_graph(edges: list):
    """The canonical fact graph plus the approved edges, as a NEW graph (the canonical one is untouched). Approved edges carry no criticality: none is assumed."""
    from ..core.graph_store import FACT_GRAPH

    g = FACT_GRAPH.copy()
    for e in edges:
        if g.has_edge(e["source"], e["target"], key=e["relation"]):
            continue                                                 # already canonical: the evidence is provenance only
        first = e["evidence"][0]
        g.add_edge(e["source"], e["target"], key=e["relation"], layer="FACT", source=e["source"], target=e["target"], relation=e["relation"], criticality=None,
                   note=f"Approved in the Data Studio from {first['source_publisher']} ({first['source_published_date']}).", evidence_status="STUDIO_APPROVED",
                   evidence_url=first["source_url"], studio=True)
    return g
