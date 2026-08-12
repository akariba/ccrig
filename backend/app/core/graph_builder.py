"""Assembles the canonical Connected Risk Graph from existing source data.

This is the ONLY place that turns raw JSON into typed GraphNode/GraphEdge
objects. Pages and the risk-cluster generator query the result through
GraphQueryService (graph_query.py) - they never re-derive graph semantics
themselves. Built once per process (STORE is loaded once at import time
already), not per-request.

Source -> node/edge mapping (see Phase 2B report for the full table):
  entities.json      -> ENTITY nodes, SECTOR/COUNTRY nodes + edges
  fact_edges.json     -> STRUCTURAL edges (REAL_PUBLIC_DATA)
  ccr_counterparties.json -> COUNTERPARTY/PRODUCT/EXPOSURE_POSITION/
                          COLLATERAL/NETTING_SET/LIMIT/CONTROL_EXCEPTION/
                          OWNER nodes + EXPOSURE/CONTROL edges + the
                          per-record risk_factor_path -> TRANSMISSION edges
                          (all SYNTHETIC_BUSINESS_SCENARIO_DATA)
  ccr_events.json     -> EVENT nodes + canonical TRANSMISSION edges
                          (CURATED_REFERENCE_DATA - a scenario chain, not
                          a measured statistic)

Market correlation (STATISTICAL domain) is NOT precomputed into a stored
edge list here - with real price data available for ~dozens of issuers,
materializing every pair upfront is wasted work the existing candidate
generation already avoids. GraphQueryService.get_statistical_relationships
computes it on demand via core.market, exactly like the existing
relationship engine does, and wraps the result as GraphEdge objects at the
query boundary.
"""
from .data import STORE
from .graph_model import (
    GraphNode, GraphEdge,
    entity_node_id, counterparty_node_id, product_node_id, risk_factor_node_id,
    event_node_id, collateral_node_id, netting_set_node_id, limit_node_id,
    control_exception_node_id, owner_node_id, sector_node_id, country_node_id,
)

STRUCTURAL_RELATIONS = {
    "SUPPLIES": "SUPPLIES", "CUSTOMER_OF": "CUSTOMER_OF",
    "LICENSES_TO": "LICENSES_TO", "LICENSES_FROM": "LICENSES_FROM",
    "PARENT_OF": "PARENT_OF", "SUBSIDIARY_OF": "SUBSIDIARY_OF",
}


def risk_factor_label(code: str) -> str:
    """"JPY" -> "JPY" (keep short acronyms upper), "UST_YIELD" -> "UST Yield"."""
    return " ".join(p if (len(p) <= 4 and p.isupper()) else p.capitalize() for p in code.split("_"))


class ConnectedRiskGraph:
    def __init__(self):
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._out_adjacency: dict[str, list[int]] = {}  # node_id -> indices into self.edges
        self._in_adjacency: dict[str, list[int]] = {}

    def add_node(self, node: GraphNode):
        # Idempotent - many source records point at the same node (e.g. two
        # counterparties both using PRODUCT:REPO); first write wins, later
        # ones must be identical in identity even if metadata differs.
        if node.id not in self.nodes:
            self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge):
        idx = len(self.edges)
        self.edges.append(edge)
        self._out_adjacency.setdefault(edge.source_node_id, []).append(idx)
        self._in_adjacency.setdefault(edge.target_node_id, []).append(idx)
        if not edge.directed:
            self._out_adjacency.setdefault(edge.target_node_id, []).append(idx)
            self._in_adjacency.setdefault(edge.source_node_id, []).append(idx)

    def out_edges(self, node_id: str) -> list[GraphEdge]:
        return [self.edges[i] for i in self._out_adjacency.get(node_id, [])]

    def in_edges(self, node_id: str) -> list[GraphEdge]:
        return [self.edges[i] for i in self._in_adjacency.get(node_id, [])]


def _build() -> ConnectedRiskGraph:
    g = ConnectedRiskGraph()

    # --- ENTITY nodes + SECTOR/COUNTRY structural edges (REAL_PUBLIC_DATA
    # for the subset with real market/GLEIF coverage, CURATED_REFERENCE_DATA
    # for the fictional entities used as CCR scenario counterparties) ---
    for e in STORE.entities_raw:
        provenance = "REAL_PUBLIC_DATA" if e.get("has_market_data") else "CURATED_REFERENCE_DATA"
        g.add_node(GraphNode(id=entity_node_id(e["id"]), type="ENTITY", label=e["name"],
                              short_label=e["id"], provenance=provenance,
                              metadata={"sector": e.get("sector"), "country": e.get("country")}))
        if e.get("sector"):
            sid = sector_node_id(e["sector"])
            g.add_node(GraphNode(id=sid, type="SECTOR", label=e["sector"], provenance="CURATED_REFERENCE_DATA"))
            g.add_edge(GraphEdge(id=f"{e['id']}:BELONGS_TO_SECTOR", domain="STRUCTURAL", type="BELONGS_TO_SECTOR",
                                  source_node_id=entity_node_id(e["id"]), target_node_id=sid, directed=True,
                                  provenance="CURATED_REFERENCE_DATA"))
        if e.get("country"):
            cid = country_node_id(e["country"])
            g.add_node(GraphNode(id=cid, type="COUNTRY", label=e["country"], provenance="CURATED_REFERENCE_DATA"))
            g.add_edge(GraphEdge(id=f"{e['id']}:OPERATES_IN", domain="STRUCTURAL", type="OPERATES_IN",
                                  source_node_id=entity_node_id(e["id"]), target_node_id=cid, directed=True,
                                  provenance="CURATED_REFERENCE_DATA"))

    # --- STRUCTURAL fact edges (supply chain, ownership) ---
    for fe in STORE.fact_edges:
        rel = fe["relation"]
        if rel not in STRUCTURAL_RELATIONS:
            continue
        src, tgt = entity_node_id(fe["source"]), entity_node_id(fe["target"])
        if src not in g.nodes or tgt not in g.nodes:
            continue
        g.add_edge(GraphEdge(
            id=f"FACT:{fe['source']}:{rel}:{fe['target']}", domain="STRUCTURAL", type=rel,
            source_node_id=src, target_node_id=tgt, directed=True,
            provenance="REAL_PUBLIC_DATA" if fe.get("evidence_status") == "WELL_DOCUMENTED_PUBLIC" else "CURATED_REFERENCE_DATA",
            evidence={"evidence_status": fe.get("evidence_status"), "evidence_url": fe.get("evidence_url"),
                      "note": fe.get("note")},
            strength=fe.get("criticality"),
        ))

    # --- EVENT nodes + canonical TRANSMISSION chains ---
    for ev in STORE.ccr_events:
        eid = event_node_id(ev["id"])
        g.add_node(GraphNode(id=eid, type="EVENT", label=ev["label"], provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA",
                              metadata={"description": ev.get("description")}))
        path = ev.get("risk_factor_path") or []
        for i, rf in enumerate(path):
            rid = risk_factor_node_id(rf)
            g.add_node(GraphNode(id=rid, type="RISK_FACTOR", label=risk_factor_label(rf),
                                  provenance="CURATED_REFERENCE_DATA"))
            if i == 0:
                g.add_edge(GraphEdge(id=f"{eid}:IMPACTS:{rid}", domain="TRANSMISSION", type="IMPACTS",
                                      source_node_id=eid, target_node_id=rid, directed=True,
                                      provenance="CURATED_REFERENCE_DATA"))
            else:
                prev = risk_factor_node_id(path[i - 1])
                g.add_edge(GraphEdge(id=f"{prev}:TRANSMITS_TO:{rid}", domain="TRANSMISSION", type="TRANSMITS_TO",
                                      source_node_id=prev, target_node_id=rid, directed=True,
                                      provenance="CURATED_REFERENCE_DATA"))

    # --- COUNTERPARTY / EXPOSURE / CONTROL from the synthetic CCR dataset ---
    for r in STORE.ccr_counterparties:
        cp_id = counterparty_node_id(r["id"])
        g.add_node(GraphNode(id=cp_id, type="COUNTERPARTY", label=r["name"], provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA",
                              metadata={"legal_entity": r.get("legal_entity"), "counterparty_type": r.get("counterparty_type"),
                                        "rating": r.get("rating"), "watchlist": r.get("watchlist")}))

        # aggregate EXPOSURE_POSITION - the source data is one aggregate
        # record per counterparty, not individual trades, so we model it
        # honestly as a position rather than fabricating a TRADE node.
        pos_id = f"EXPOSURE_POSITION:{r['id']}"
        g.add_node(GraphNode(id=pos_id, type="EXPOSURE_POSITION", label=f"{r['name']} — {r.get('product', 'exposure')}",
                              provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA", metadata={"exposure": r.get("exposure")}))
        g.add_edge(GraphEdge(id=f"{cp_id}:HAS_EXPOSURE:{pos_id}", domain="EXPOSURE", type="HAS_EXPOSURE",
                              source_node_id=cp_id, target_node_id=pos_id, directed=True,
                              provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA"))

        if r.get("product"):
            pid = product_node_id(r["product"])
            g.add_node(GraphNode(id=pid, type="PRODUCT", label=r["product"], provenance="CURATED_REFERENCE_DATA"))
            g.add_edge(GraphEdge(id=f"{pos_id}:USES_PRODUCT:{pid}", domain="EXPOSURE", type="USES_PRODUCT",
                                  source_node_id=pos_id, target_node_id=pid, directed=True,
                                  provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA"))

        if r.get("reference_entity_id") and entity_node_id(r["reference_entity_id"]) in g.nodes:
            g.add_edge(GraphEdge(id=f"{pos_id}:REFERENCES:{r['reference_entity_id']}", domain="EXPOSURE", type="REFERENCES",
                                  source_node_id=pos_id, target_node_id=entity_node_id(r["reference_entity_id"]), directed=True,
                                  provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA"))

        if r.get("netting_set"):
            nid = netting_set_node_id(r["netting_set"])
            g.add_node(GraphNode(id=nid, type="NETTING_SET", label=r["netting_set"], provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA"))
            g.add_edge(GraphEdge(id=f"{pos_id}:NETTED_IN:{nid}", domain="EXPOSURE", type="NETTED_IN",
                                  source_node_id=pos_id, target_node_id=nid, directed=True,
                                  provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA"))

        collateral = r.get("collateral")
        if collateral and collateral.get("type"):
            colid = collateral_node_id(collateral["type"])
            g.add_node(GraphNode(id=colid, type="COLLATERAL", label=collateral["type"], provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA",
                                  metadata={"csa": collateral.get("csa"), "haircut": collateral.get("haircut")}))
            g.add_edge(GraphEdge(id=f"{cp_id}:COLLATERALISED_BY:{colid}", domain="EXPOSURE", type="COLLATERALISED_BY",
                                  source_node_id=cp_id, target_node_id=colid, directed=True,
                                  provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA"))

        # per-record risk_factor_path -> TRANSMISSION edges (reuses the same
        # RISK_FACTOR nodes the event chains populate, so a counterparty's
        # exposure and the event that's driving it connect through shared
        # nodes rather than two disconnected chains)
        rf_path = r.get("risk_factor_path") or []
        for i, rf in enumerate(rf_path):
            rid = risk_factor_node_id(rf)
            g.add_node(GraphNode(id=rid, type="RISK_FACTOR", label=risk_factor_label(rf),
                                  provenance="CURATED_REFERENCE_DATA"))
            if i == 0:
                g.add_edge(GraphEdge(id=f"{pos_id}:EXPOSED_TO:{rid}", domain="EXPOSURE", type="EXPOSED_TO_RISK_FACTOR",
                                      source_node_id=pos_id, target_node_id=rid, directed=True,
                                      provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA"))
            else:
                prev = risk_factor_node_id(rf_path[i - 1])
                g.add_edge(GraphEdge(id=f"{prev}:TRANSMITS_TO:{rid}", domain="TRANSMISSION", type="TRANSMITS_TO",
                                      source_node_id=prev, target_node_id=rid, directed=True,
                                      provenance="CURATED_REFERENCE_DATA"))

        # CONTROL: limit + exception
        limit = r.get("limit")
        if limit and limit.get("limit_id"):
            lid = limit_node_id(r["id"], limit["limit_id"])
            g.add_node(GraphNode(id=lid, type="LIMIT", label=f"{limit.get('limit_type', 'LIMIT')} — {r['name']}",
                                  provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA",
                                  metadata={"limit_type": limit.get("limit_type"), "limit_value": limit.get("limit_value")}))
            g.add_edge(GraphEdge(id=f"{cp_id}:SUBJECT_TO:{lid}", domain="CONTROL", type="SUBJECT_TO",
                                  source_node_id=cp_id, target_node_id=lid, directed=True,
                                  provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA"))

            breach = r.get("breach")
            if breach:
                exid = control_exception_node_id(r["id"], limit["limit_id"])
                g.add_node(GraphNode(id=exid, type="CONTROL_EXCEPTION", label=f"Exception — {r['name']}",
                                      provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA",
                                      metadata={"age_days": breach.get("age_days"), "sla_days": breach.get("sla_days"),
                                                "excess": breach.get("excess"), "root_cause": breach.get("root_cause")}))
                g.add_edge(GraphEdge(id=f"{cp_id}:HAS_EXCEPTION:{exid}", domain="CONTROL", type="HAS_EXCEPTION",
                                      source_node_id=cp_id, target_node_id=exid, directed=True,
                                      provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA"))
                g.add_edge(GraphEdge(id=f"{exid}:RELATES_TO:{lid}", domain="CONTROL", type="RELATES_TO",
                                      source_node_id=exid, target_node_id=lid, directed=True,
                                      provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA"))
                if r.get("coverage_owner"):
                    oid = owner_node_id(r["coverage_owner"])
                    g.add_node(GraphNode(id=oid, type="OWNER", label=r["coverage_owner"], provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA"))
                    g.add_edge(GraphEdge(id=f"{exid}:OWNED_BY:{oid}", domain="CONTROL", type="OWNED_BY",
                                          source_node_id=exid, target_node_id=oid, directed=True,
                                          provenance="SYNTHETIC_BUSINESS_SCENARIO_DATA"))

    return g


_GRAPH: ConnectedRiskGraph | None = None


def get_graph() -> ConnectedRiskGraph:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build()
    return _GRAPH
