"""GraphQueryService - the only sanctioned way to read the Connected Risk
Graph. Pages/endpoints call this rather than re-deriving graph semantics
from raw JSON themselves (see graph_builder.py's module docstring for why
that duplication is exactly what caused the Phase 1 direction bug).

Deliberately simple: indexed adjacency + BFS, no generic graph algorithm
library beyond what graph_builder already uses. Statistical (market
correlation) edges are computed on demand here, not stored in the graph -
see graph_builder.py's docstring for why.
"""
from dataclasses import dataclass

from . import market
from .config import STATISTICAL_EDGE_MIN_ABS_CORRELATION
from .data import STORE
from .graph_builder import ConnectedRiskGraph, get_graph
from .graph_model import GraphEdge, GraphNode, entity_node_id


@dataclass
class PathHop:
    edge: GraphEdge
    traversed_reverse: bool  # True when this hop was read target->source


@dataclass
class GraphPathResult:
    nodes: list[GraphNode]
    hops: list[PathHop]


class GraphQueryService:
    def __init__(self, graph: ConnectedRiskGraph):
        self.graph = graph

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.graph.nodes.get(node_id)

    def get_edges(self, node_id: str) -> list[GraphEdge]:
        return self.graph.out_edges(node_id) + [e for e in self.graph.in_edges(node_id) if e.directed]

    def get_neighbors(self, node_id: str, domains: set[str] | None = None,
                       edge_types: set[str] | None = None) -> list[tuple[GraphNode, GraphEdge, bool]]:
        """Returns (neighbor_node, edge, traversed_reverse) triples."""
        results = []
        for e in self.graph.out_edges(node_id):
            if domains and e.domain not in domains:
                continue
            if edge_types and e.type not in edge_types:
                continue
            nbr = self.graph.nodes.get(e.target_node_id)
            if nbr:
                results.append((nbr, e, False))
        for e in self.graph.in_edges(node_id):
            if domains and e.domain not in domains:
                continue
            if edge_types and e.type not in edge_types:
                continue
            if not e.directed:
                continue  # already covered via out_edges (undirected edges are indexed both ways)
            nbr = self.graph.nodes.get(e.source_node_id)
            if nbr:
                results.append((nbr, e, True))
        return results

    def get_focused_path(self, source_node_id: str, target_node_id: str,
                          allowed_domains: set[str] | None = None, max_hops: int = 3) -> GraphPathResult | None:
        """Deterministic BFS preserving semantic edge direction independent
        of traversal direction (see graph_model.py: `directed` + PathHop's
        traversed_reverse). Mirrors core/paths.py's fact_path_between, but
        generalized across ALL edge domains rather than only STRUCTURAL."""
        if source_node_id == target_node_id:
            return None
        frontier = [(source_node_id, [])]
        visited = {source_node_id}
        for _ in range(max_hops):
            next_frontier = []
            for node_id, trail in frontier:
                for nbr, edge, reverse in self.get_neighbors(node_id, domains=allowed_domains):
                    if nbr.id in visited:
                        continue
                    new_trail = trail + [PathHop(edge=edge, traversed_reverse=reverse)]
                    if nbr.id == target_node_id:
                        # Rebuild the traversal-order node sequence directly from hops -
                        # each hop's traversal target is source_node_id if reversed,
                        # else target_node_id (see graph_model.py's `directed` semantics).
                        nodes = [self.graph.nodes[source_node_id]]
                        cur = source_node_id
                        for h in new_trail:
                            cur = h.edge.target_node_id if not h.traversed_reverse else h.edge.source_node_id
                            nodes.append(self.graph.nodes[cur])
                        return GraphPathResult(nodes=nodes, hops=new_trail)
                    next_frontier.append((nbr.id, new_trail))
                    visited.add(nbr.id)
            frontier = next_frontier
            if not frontier:
                break
        return None

    def get_structural_relationships(self, entity_id: str) -> list[tuple[GraphNode, GraphEdge, bool]]:
        return self.get_neighbors(entity_node_id(entity_id), domains={"STRUCTURAL"})

    def get_statistical_relationships(self, entity_id: str, min_abs_correlation: float | None = None) -> list[dict]:
        """Computed on demand (see module docstring) - wraps core.market's
        signed correlation as GraphEdge-shaped dicts. Threshold is a
        documented POC config value (STATISTICAL_EDGE_MIN_ABS_CORRELATION),
        never silently hardcoded, and never drops the sign: a strong
        inverse relationship (rho very negative) passes the same abs()
        threshold as a strong positive one and is returned with its true
        sign intact."""
        threshold = min_abs_correlation if min_abs_correlation is not None else STATISTICAL_EDGE_MIN_ABS_CORRELATION
        out = []
        for other_id in STORE.issuer_ids:
            if other_id == entity_id:
                continue
            corr = market.signed_correlation(entity_id, other_id)
            if not corr or abs(corr["full_sample_corr"]) < threshold:
                continue
            out.append({
                "domain": "STATISTICAL", "type": "MARKET_CORRELATED_WITH", "directed": False,
                "source_node_id": entity_node_id(entity_id), "target_node_id": entity_node_id(other_id),
                "signed_value": corr["full_sample_corr"], "provenance": "DERIVED_DATA",
                "evidence": {"method": "PEARSON", "n_obs": corr["n_obs"], "source": corr["source"]},
            })
        out.sort(key=lambda e: -abs(e["signed_value"]))
        return out

    def get_exposure_paths(self, entity_id: str) -> list[GraphPathResult]:
        """All EXPOSURE-domain paths from a counterparty exposure position
        back to this entity, when the entity is used as a reference/
        underlying - i.e. "who has typed CCR exposure referencing this
        issuer", generalized from the existing counterparty_materiality
        join into canonical graph terms."""
        node_id = entity_node_id(entity_id)
        results = []
        for edge in self.graph.in_edges(node_id):
            if edge.domain != "EXPOSURE" or edge.type != "REFERENCES":
                continue
            pos_node = self.graph.nodes.get(edge.source_node_id)
            if not pos_node:
                continue
            cp_edges = [e for e in self.graph.in_edges(pos_node.id) if e.type == "HAS_EXPOSURE"]
            for cp_edge in cp_edges:
                cp_node = self.graph.nodes.get(cp_edge.source_node_id)
                if not cp_node:
                    continue
                results.append(GraphPathResult(
                    nodes=[cp_node, pos_node, self.graph.nodes[node_id]],
                    hops=[PathHop(edge=cp_edge, traversed_reverse=False), PathHop(edge=edge, traversed_reverse=False)],
                ))
        return results

    def get_counterparty_graph(self, counterparty_node_id_: str) -> dict:
        """Everything hanging off one counterparty, domain-separated -
        the basis for both the Exposure & Controls tab and risk-cluster
        generation (risk_clusters.py)."""
        return {
            "exposure": self.get_neighbors(counterparty_node_id_, domains={"EXPOSURE"}),
            "control": self.get_neighbors(counterparty_node_id_, domains={"CONTROL"}),
        }

    def get_control_context(self, counterparty_node_id_: str) -> list[tuple[GraphNode, GraphEdge, bool]]:
        return self.get_neighbors(counterparty_node_id_, domains={"CONTROL"})


def get_query_service() -> GraphQueryService:
    return GraphQueryService(get_graph())
