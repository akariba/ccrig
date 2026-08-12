"""Phase 3: Counterparty Risk Clusters - derived views over the canonical
Connected Risk Graph (graph_query.py), never a manually curated dashboard
section. A cluster answers "what common economic risk theme concentrates
this counterparty's existing exposure?", built by traversing outward from
each of the counterparty's actual EXPOSURE_POSITION nodes:

  position -> product / reference entity / risk-factor transmission chain
      reference entity -> structural neighbors (supply chain, ownership)
      reference entity -> statistical neighbors (market correlation, signed)

No cluster is invented where the graph has no evidence for it - a
counterparty with one exposure record and no structural/statistical
neighbors gets one small, honestly labeled cluster, not a fabricated
"Semiconductor / AI" just because that phrase is expected somewhere.
"""
from dataclasses import dataclass, field
from typing import Any

from .graph_model import GraphNode, GraphEdge, counterparty_node_id
from .graph_query import get_query_service


@dataclass
class RiskCluster:
    id: str
    counterparty_id: str
    label: str
    summary: str
    risk_factors: list[str] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    structural_relationships: list[dict] = field(default_factory=list)
    statistical_relationships: list[dict] = field(default_factory=list)
    transmission_path: list[str] = field(default_factory=list)
    collateral_links: list[str] = field(default_factory=list)
    relevant_events: list[dict] = field(default_factory=list)
    relevant_controls: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)


def _bare_id(node_id: str) -> str:
    return node_id.split(":", 1)[1]


def _transmission_chain(qs, start: GraphNode) -> list[GraphNode]:
    chain = [start]
    seen = {start.id}
    cur = start
    while True:
        nxt = [n for n, e, rev in qs.get_neighbors(cur.id, domains={"TRANSMISSION"}, edge_types={"TRANSMITS_TO"})
               if not rev and n.id not in seen]
        if not nxt:
            break
        cur = nxt[0]
        chain.append(cur)
        seen.add(cur.id)
    return chain


def _relevant_events(qs, first_risk_factor: GraphNode | None) -> list[dict]:
    if not first_risk_factor:
        return []
    events = []
    for e in qs.graph.in_edges(first_risk_factor.id):
        if e.type != "IMPACTS":
            continue
        ev = qs.get_node(e.source_node_id)
        if ev:
            events.append({"id": _bare_id(ev.id), "label": ev.label})
    return events


def _derive_label(risk_factor_chain: list[GraphNode], reference_entity: GraphNode | None) -> str:
    if risk_factor_chain:
        return " / ".join(n.label for n in risk_factor_chain[:2])
    if reference_entity:
        sector = reference_entity.metadata.get("sector")
        return sector if sector else reference_entity.label
    return "Mixed market-risk cluster"


def build_risk_clusters(counterparty_id: str, max_clusters: int = 5) -> list[RiskCluster]:
    qs = get_query_service()
    cp_id = counterparty_node_id(counterparty_id)
    if cp_id not in qs.graph.nodes:
        return []

    exposure_neighbors = qs.get_neighbors(cp_id, domains={"EXPOSURE"})
    positions = [n for n, e, rev in exposure_neighbors if n.type == "EXPOSURE_POSITION" and e.type == "HAS_EXPOSURE"]
    collateral = [n.label for n, e, rev in exposure_neighbors if n.type == "COLLATERAL"]
    controls = [{"type": n.type, "label": n.label, "metadata": n.metadata}
                for n, e, rev in qs.get_control_context(cp_id)]

    clusters: list[RiskCluster] = []
    for pos in positions:
        pos_neighbors = qs.get_neighbors(pos.id, domains={"EXPOSURE", "TRANSMISSION"})
        product = next((n for n, e, rev in pos_neighbors if n.type == "PRODUCT"), None)
        reference_entity = next((n for n, e, rev in pos_neighbors if n.type == "ENTITY"), None)
        first_risk_factor = next((n for n, e, rev in pos_neighbors
                                   if n.type == "RISK_FACTOR" and e.type == "EXPOSED_TO_RISK_FACTOR"), None)
        rf_chain = _transmission_chain(qs, first_risk_factor) if first_risk_factor else []

        structural, statistical, related_entities = [], [], []
        if reference_entity:
            bare = _bare_id(reference_entity.id)
            for n, e, rev in qs.get_structural_relationships(bare):
                if n.type != "ENTITY":
                    continue
                structural.append({"entity": n.label, "type": e.type, "reverse": rev,
                                    "evidence_url": (e.evidence or {}).get("evidence_url")})
                related_entities.append(n)
            for s in qs.get_statistical_relationships(bare)[:5]:
                other = qs.get_node(s["target_node_id"])
                statistical.append({"entity": other.label if other else s["target_node_id"],
                                     "signed_correlation": round(s["signed_value"], 3), "method": s["evidence"]["method"]})
                if other:
                    related_entities.append(other)

        entities = ([reference_entity] if reference_entity else []) + related_entities
        evidence = []
        if structural:
            evidence.append(f"{reference_entity.label} has a documented structural relationship with "
                             f"{', '.join(s['entity'] for s in structural[:3])}.")
        if statistical:
            top = statistical[0]
            evidence.append(f"{reference_entity.label} and {top['entity']} show "
                             f"{'positive' if top['signed_correlation'] >= 0 else 'inverse'} market correlation "
                             f"({top['signed_correlation']:+.2f}).")
        if rf_chain:
            evidence.append(f"Exposure transmits through {' → '.join(n.label for n in rf_chain)}.")
        if product:
            evidence.append(f"Reached via {product.label} exposure.")

        cluster = RiskCluster(
            id=f"CLUSTER:{counterparty_id}:{pos.id}",
            counterparty_id=counterparty_id,
            label=_derive_label(rf_chain, reference_entity),
            summary=f"{len(entities)} related entit{'y' if len(entities) == 1 else 'ies'}, "
                    f"{1 if product else 0} product channel, {len(collateral)} collateral linkage(s)",
            risk_factors=[n.label for n in rf_chain],
            entities=[{"id": _bare_id(n.id), "label": n.label} for n in {e.id: e for e in entities}.values()],
            products=[product.label] if product else [],
            structural_relationships=structural,
            statistical_relationships=statistical,
            transmission_path=[n.label for n in rf_chain],
            collateral_links=collateral,
            relevant_events=_relevant_events(qs, first_risk_factor),
            relevant_controls=controls,
            evidence=evidence,
            provenance=sorted({"SYNTHETIC_BUSINESS_SCENARIO_DATA"}
                               | ({"REAL_PUBLIC_DATA"} if structural else set())
                               | ({"DERIVED_DATA"} if statistical else set())),
        )
        clusters.append(cluster)

    return clusters[:max_clusters]
