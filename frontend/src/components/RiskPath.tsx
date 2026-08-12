// A small, linear, typed-chain visual - the same rendering used everywhere
// a path through the connected graph is shown (structural fact paths,
// event transmission chains, economic exposure paths). Never a network
// diagram - one readable line, edge labels only when the edge has a real
// type (a fact relation); a bare arrow otherwise (a chain without a typed
// relation should not pretend to have one).
export function RiskPath({ nodes, edgeLabels }: { nodes: string[]; edgeLabels?: (string | null)[] }) {
  if (nodes.length === 0) return null;
  return (
    <div className="hstack" style={{ flexWrap: "wrap", gap: 0, rowGap: 6 }}>
      {nodes.map((n, i) => (
        <span key={i} className="hstack" style={{ gap: 0 }}>
          <span style={{
            fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: 5,
            border: "1px solid var(--border)", background: "var(--surface-alt)", color: "var(--text)", whiteSpace: "nowrap",
          }}>
            {n}
          </span>
          {i < nodes.length - 1 && (
            <span style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "0 8px", lineHeight: 1.1 }}>
              {edgeLabels?.[i] && (
                <span className="mono" style={{ fontSize: 9, color: "var(--primary)", textTransform: "uppercase", letterSpacing: "0.03em" }}>
                  {edgeLabels[i]}
                </span>
              )}
              <span style={{ color: "var(--text-faint)", fontSize: 13 }}>→</span>
            </span>
          )}
        </span>
      ))}
    </div>
  );
}

export function pathFromHops(hops: { from: string; to: string; relation: string }[]): { nodes: string[]; edgeLabels: string[] } {
  if (!hops || hops.length === 0) return { nodes: [], edgeLabels: [] };
  return { nodes: [hops[0].from, ...hops.map((h) => h.to)], edgeLabels: hops.map((h) => h.relation) };
}

export function pathFromChain(labels: string[]): { nodes: string[]; edgeLabels: (string | null)[] } {
  return { nodes: labels, edgeLabels: labels.slice(0, -1).map(() => null) };
}

// Renders the analyst's InvestigationContext (see context/InvestigationContext.tsx)
// as a typed RiskPath - each step already carries the edge type that led to
// it (relationFromPrevious), so "TSMC > NVIDIA > Counterparty" in the
// breadcrumb and "TSMC --SUPPLIES--> NVIDIA --TRS--> Counterparty" here are
// two views of the exact same underlying investigation object, not two
// separately-maintained representations.
export function pathFromInvestigation(steps: { label: string; relationFromPrevious: string | null }[]): { nodes: string[]; edgeLabels: (string | null)[] } {
  return { nodes: steps.map((s) => s.label), edgeLabels: steps.slice(1).map((s) => s.relationFromPrevious) };
}
