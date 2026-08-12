// Canonical graph-path model (Phase 2). RiskPath (typed visual rendering)
// and the Investigation breadcrumb (simplified rendering) are two VIEWS
// over the same GraphPath - neither maintains its own separate notion of
// what the path is, which is what keeps them from disagreeing.
export type NodeType = "ENTITY" | "COUNTERPARTY" | "EVENT" | "RISK_FACTOR" | "PRODUCT" | "THEME" | "COUNTRY";

export interface GraphNodeRef {
  id: string;
  type: NodeType;
  label: string;
}

export interface GraphPathEdge {
  /** Canonical edge type, e.g. "SUPPLIES", "TRS" - never a display string. */
  edgeType: string | null;
  /** True when the analyst traversed this hop against the edge's stored
   * semantic direction (see graph/edgeLabels.ts). The underlying fact is
   * never rewritten - only its presentation inverts. */
  traversedReverse: boolean;
  evidenceRef?: unknown;
}

export interface GraphPath {
  nodes: GraphNodeRef[];
  /** edges[i] connects nodes[i] -> nodes[i+1] in traversal order; length = nodes.length - 1. */
  edges: GraphPathEdge[];
}
