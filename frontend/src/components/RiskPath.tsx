import { edgeLabel } from "../graph/edgeLabels";
import type { GraphPath, GraphNodeRef } from "../graph/types";

// A small, linear, typed-chain visual - the same rendering used everywhere
// a path through the connected graph is shown (structural fact paths,
// event transmission chains, economic exposure paths, the Investigation
// Context). Never a network diagram - one readable line. Edge labels come
// from the canonical edge registry (graph/edgeLabels.ts), direction-aware:
// a reversed traversal shows the inverse human label, never the forward
// label re-asserted backward. A hop with no typed edge gets a bare arrow,
// never a fabricated relation.
export function RiskPath({ path }: { path: GraphPath }) {
  if (path.nodes.length === 0) return null;
  return (
    <div className="hstack" style={{ flexWrap: "wrap", gap: 0, rowGap: 6 }}>
      {path.nodes.map((n, i) => (
        <span key={`${n.type}:${n.id}:${i}`} className="hstack" style={{ gap: 0 }}>
          <span style={{
            fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: 5,
            border: "1px solid var(--border)", background: "var(--surface-alt)", color: "var(--text)", whiteSpace: "nowrap",
          }}>
            {n.label}
          </span>
          {i < path.nodes.length - 1 && (
            <span style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "0 8px", lineHeight: 1.1 }}>
              {path.edges[i]?.edgeType && (
                <span className="mono" style={{ fontSize: 9, color: "var(--primary)", textTransform: "uppercase", letterSpacing: "0.03em" }}>
                  {edgeLabel(path.edges[i].edgeType, path.edges[i].traversedReverse)}
                </span>
              )}
              <span style={{ color: "var(--text-faint)", fontSize: 13 }}>{path.edges[i]?.traversedReverse ? "←" : "→"}</span>
            </span>
          )}
        </span>
      ))}
    </div>
  );
}

export function pathFromHops(hops: { from: string; to: string; relation: string; direction?: "FORWARD" | "REVERSE" }[]): GraphPath {
  if (!hops || hops.length === 0) return { nodes: [], edges: [] };
  const nodeIds = [hops[0].from, ...hops.map((h) => h.to)];
  const nodes: GraphNodeRef[] = nodeIds.map((id) => ({ id, type: "ENTITY", label: id }));
  // hop.direction "REVERSE" means the traversal (from -> to, i.e. the order
  // the analyst is reading left-to-right) runs opposite the stored fact
  // edge - the fact is really `to --relation--> from`. Surfaced as
  // traversedReverse so the registry shows the inverse label ("supplied
  // by") instead of re-asserting the forward label backward. This is the
  // Phase 1 self-caught bug's actual fix: the API always returned
  // `direction` correctly, the frontend just never read it.
  const edges = hops.map((h) => ({ edgeType: h.relation, traversedReverse: h.direction === "REVERSE" }));
  return { nodes, edges };
}

export function pathFromChain(labels: string[]): GraphPath {
  return {
    nodes: labels.map((label, i) => ({ id: String(i), type: "RISK_FACTOR" as const, label })),
    edges: labels.slice(1).map(() => ({ edgeType: null, traversedReverse: false })),
  };
}

export function pathFromInvestigation(steps: { nodeId: string; nodeType: GraphNodeRef["type"]; label: string; edgeType?: string | null; traversedReverse?: boolean }[]): GraphPath {
  return {
    nodes: steps.map((s) => ({ id: s.nodeId, type: s.nodeType, label: s.label })),
    edges: steps.slice(1).map((s) => ({ edgeType: s.edgeType ?? null, traversedReverse: s.traversedReverse ?? false })),
  };
}
