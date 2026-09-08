"""Phase 3/4: Counterparty Risk Clusters - derived views over the canonical
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

Phase 4 addition: members are tiered (DIRECT / FIRST_ORDER / CONTEXTUAL)
rather than dumped as one flat list - a broad equity exposure can nominate
a dozen+ statistically/structurally adjacent names, and presenting all of
them as equally relevant buries the two or three that actually matter.
Expansion is bounded by explicit config (CLUSTER_* in config.py), never
an unbounded graph walk.
"""
from dataclasses import dataclass, field

from .config import (
    CLUSTER_MAX_FIRST_ORDER_STRUCTURAL, CLUSTER_MAX_FIRST_ORDER_STATISTICAL,
    CLUSTER_MAX_CONTEXTUAL_MEMBERS, CLUSTER_SECTOR_LABEL_MIN_SHARE,
)
from .graph_model import GraphNode, counterparty_node_id
from .graph_query import get_query_service


@dataclass
class RiskCluster:
    id: str
    counterparty_id: str
    label: str
    summary: str
    # Business-narrative fields (Phase 4 correction: the analyst-facing
    # output of a cluster is a STORY, not a graph-algorithm result). Each
    # is synthesized only from evidence already gathered below - never
    # fabricated, never a separate opaque score.
    story: list[str] = field(default_factory=list)
    why_it_matters: str = ""
    recommended_action: str = ""
    direct_members: list[dict] = field(default_factory=list)
    first_order_members: list[dict] = field(default_factory=list)
    contextual_members: list[dict] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
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


def _derive_label(rf_chain: list[GraphNode], reference_entity: GraphNode | None,
                   first_order_entities: list[GraphNode]) -> str:
    # Prefer a sector label ONLY when a real majority of the first-order
    # neighborhood actually shares it with the reference entity - otherwise
    # a label like "Semiconductors" would overstate consensus that isn't
    # there (e.g. one supplier out of five unrelated correlated names).
    if reference_entity and reference_entity.metadata.get("sector") and first_order_entities:
        sector = reference_entity.metadata["sector"]
        share = sum(1 for n in first_order_entities if n.metadata.get("sector") == sector) / len(first_order_entities)
        if share >= CLUSTER_SECTOR_LABEL_MIN_SHARE:
            return sector
    if rf_chain:
        return " / ".join(n.label for n in rf_chain[:2])
    if reference_entity:
        return reference_entity.label
    return "Mixed market-risk cluster"


def _build_story(counterparty_name: str, product, reference_entity, top_first_order,
                  rf_chain: list[GraphNode]) -> list[str]:
    """The business narrative chain, e.g.:
    ["Taiwan / foundry risk", "TSMC", "NVIDIA", "TRS exposure", "Kestrel Family Office"]
    Built only from evidence already established below (transmission chain,
    structural neighbor, reference entity, product, counterparty) - never
    an invented economic narrative."""
    steps = []
    if rf_chain:
        steps.append(f"{rf_chain[0].label} risk")
    if top_first_order and reference_entity and top_first_order.id != reference_entity.id:
        steps.append(top_first_order.label)
    if reference_entity:
        steps.append(reference_entity.label)
    if product:
        steps.append(f"{product.label} exposure")
    steps.append(counterparty_name)
    return steps


def _why_it_matters(counterparty_name: str, reference_entity, product,
                     top_structural: dict | None, top_statistical: dict | None) -> str:
    if reference_entity is None:
        return f"{counterparty_name} has an exposure position with no linked reference entity on file."
    base = f"{counterparty_name} has {product.label if product else 'an'} exposure referencing {reference_entity.label}."
    if top_structural:
        relation = top_structural["type"].replace("_", " ").lower()
        return (f"{base} {reference_entity.label} has a structural {relation} relationship with "
                f"{top_structural['entity']} - risk affecting {top_structural['entity']} can reach this exposure "
                f"even though the position only directly references {reference_entity.label}.")
    if top_statistical:
        direction = "moves with" if top_statistical["signed_correlation"] >= 0 else "moves inversely to"
        return (f"{base} {reference_entity.label} historically {direction} {top_statistical['entity']} "
                f"({top_statistical['signed_correlation']:+.2f} correlation) - a shock to one may be reflected in the other.")
    return f"{base} No first-order structural or statistical neighbors were found on the current graph."


def _recommended_action(controls: list[dict], relevant_events: list[dict]) -> str:
    # Deterministic, evidence-based - never a generated/ML suggestion.
    if any(c["type"] == "CONTROL_EXCEPTION" for c in controls):
        return "Review limit/headroom — an active control exception sits behind this exposure."
    if relevant_events:
        return "Investigate — a live event scenario is transmitting into this exposure."
    return "Monitor — no active control exception or event on file for this exposure."


def build_risk_clusters(counterparty_id: str, max_clusters: int = 5) -> list[RiskCluster]:
    qs = get_query_service()
    cp_id = counterparty_node_id(counterparty_id)
    if cp_id not in qs.graph.nodes:
        return []

    counterparty_name = qs.get_node(cp_id).label
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

        all_structural, all_statistical = [], []
        if reference_entity:
            bare = _bare_id(reference_entity.id)
            # Ranked by strength (fact criticality) - NOT insertion order -
            # so e.g. TSMC (0.95, the actual primary foundry dependency)
            # outranks a weaker/incidental supply edge.
            struct_neighbors = sorted(
                (t for t in qs.get_structural_relationships(bare) if t[0].type == "ENTITY"),
                key=lambda t: -(t[1].strength or 0),
            )
            for n, e, rev in struct_neighbors:
                all_structural.append({"node": n, "entity": n.label, "type": e.type, "reverse": rev,
                                        "strength": e.strength, "evidence_url": (e.evidence or {}).get("evidence_url")})
            for s in qs.get_statistical_relationships(bare):  # already sorted by |correlation| desc
                other = qs.get_node(s["target_node_id"])
                if other:
                    all_statistical.append({"node": other, "entity": other.label,
                                             "signed_correlation": round(s["signed_value"], 3), "method": s["evidence"]["method"]})

        # --- bounded tiering: DIRECT -> FIRST_ORDER (capped) -> CONTEXTUAL (capped) ---
        # Dedup keyed by node.id in a plain dict (insertion-order preserving)
        # rather than a set of nodes - GraphNode isn't hashable (it carries a
        # dict `metadata` field) and, separately, Python's string-hash
        # randomization would otherwise make ordering non-deterministic
        # across process runs even if it were.
        def _dedup(items: list[dict]) -> list[GraphNode]:
            seen: dict[str, GraphNode] = {}
            for e in items:
                seen.setdefault(e["node"].id, e["node"])
            return list(seen.values())

        direct_nodes = [reference_entity] if reference_entity else []
        first_order_structural = all_structural[:CLUSTER_MAX_FIRST_ORDER_STRUCTURAL]
        first_order_statistical = all_statistical[:CLUSTER_MAX_FIRST_ORDER_STATISTICAL]
        first_order_nodes = _dedup(first_order_structural + first_order_statistical)
        first_order_ids = {n.id for n in first_order_nodes}

        contextual_structural = all_structural[CLUSTER_MAX_FIRST_ORDER_STRUCTURAL:]
        contextual_statistical = all_statistical[CLUSTER_MAX_FIRST_ORDER_STATISTICAL:]
        contextual_nodes = [n for n in _dedup(contextual_structural + contextual_statistical)
                             if n.id not in first_order_ids][:CLUSTER_MAX_CONTEXTUAL_MEMBERS]

        evidence = []
        if first_order_structural:
            evidence.append(f"{reference_entity.label} has a documented structural relationship with "
                             f"{', '.join(e['entity'] for e in first_order_structural)}.")
        if first_order_statistical:
            top = first_order_statistical[0]
            evidence.append(f"{reference_entity.label} and {top['entity']} show "
                             f"{'positive' if top['signed_correlation'] >= 0 else 'inverse'} market correlation "
                             f"({top['signed_correlation']:+.2f}).")
        if rf_chain:
            evidence.append(f"Exposure transmits through {' → '.join(n.label for n in rf_chain)}.")
        if product:
            evidence.append(f"Reached via {product.label} exposure.")

        top_structural = first_order_structural[0] if first_order_structural else None
        top_statistical = first_order_statistical[0] if first_order_statistical else None
        top_first_order_node = first_order_nodes[0] if first_order_nodes else None
        cluster_events = _relevant_events(qs, first_risk_factor)

        cluster = RiskCluster(
            id=f"CLUSTER:{counterparty_id}:{pos.id}",
            counterparty_id=counterparty_id,
            label=_derive_label(rf_chain, reference_entity, first_order_nodes),
            summary=f"{len(direct_nodes)} direct, {len(first_order_nodes)} first-order, {len(contextual_nodes)} contextual — "
                    f"{1 if product else 0} product channel, {len(collateral)} collateral linkage(s)",
            story=_build_story(counterparty_name, product, reference_entity, top_first_order_node, rf_chain),
            why_it_matters=_why_it_matters(counterparty_name, reference_entity, product, top_structural, top_statistical),
            recommended_action=_recommended_action(controls, cluster_events),
            direct_members=[{"id": _bare_id(n.id), "label": n.label} for n in direct_nodes],
            first_order_members=[{"id": _bare_id(n.id), "label": n.label} for n in first_order_nodes],
            contextual_members=[{"id": _bare_id(n.id), "label": n.label} for n in contextual_nodes],
            risk_factors=[n.label for n in rf_chain],
            products=[product.label] if product else [],
            structural_relationships=[{k: v for k, v in e.items() if k != "node"} for e in all_structural],
            statistical_relationships=[{k: v for k, v in e.items() if k != "node"} for e in all_statistical],
            transmission_path=[n.label for n in rf_chain],
            collateral_links=collateral,
            relevant_events=cluster_events,
            relevant_controls=controls,
            evidence=evidence,
            provenance=sorted({"SYNTHETIC_BUSINESS_SCENARIO_DATA"}
                               | ({"REAL_PUBLIC_DATA"} if all_structural else set())
                               | ({"DERIVED_DATA"} if all_statistical else set())),
        )
        clusters.append(cluster)

    return clusters[:max_clusters]
