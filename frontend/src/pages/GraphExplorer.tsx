import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import cytoscape from "cytoscape";
import { api } from "../api/client";

const LAYER_COLOR: Record<string, string> = {
  FACT: "#4f98a3",
  DERIVED: "#a84b2f",
  EXPOSURE: "#ffc553",
};

export function GraphExplorer() {
  const [params, setParams] = useSearchParams();
  const centerId = params.get("id") || "TSM";
  const [inputId, setInputId] = useState(centerId);
  const [hops, setHops] = useState(1);
  const [layers, setLayers] = useState<Record<string, boolean>>({ fact: true, derived: true, exposure: true });
  const [graph, setGraph] = useState<any>(null);
  const [selected, setSelected] = useState<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<any>(null);

  useEffect(() => {
    const activeLayers = Object.entries(layers).filter(([, v]) => v).map(([k]) => k).join(",");
    api.egoGraph(centerId, { hops, layers: activeLayers }).then(setGraph);
    setInputId(centerId);
  }, [centerId, hops, layers]);

  useEffect(() => {
    if (!graph || !containerRef.current) return;
    if (cyRef.current) cyRef.current.destroy();

    const elements = [
      ...graph.nodes.map((n: any) => ({ data: { id: n.id, label: n.id, ...n } })),
      ...graph.edges.map((e: any, i: number) => ({
        data: { id: `e${i}`, source: e.source, target: e.target, relation: e.relation, layer: e.layer, weight: e.weight, evidence: e.evidence },
      })),
    ];

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (ele: any) => (ele.data("id") === centerId ? "#4f98a3" : ele.data("is_synthetic") ? "#bb653b" : "#393836"),
            label: "data(label)",
            color: "#cdccca",
            "font-size": 9,
            "text-valign": "bottom",
            "text-margin-y": 4,
            width: (ele: any) => (ele.data("id") === centerId ? 34 : 22),
            height: (ele: any) => (ele.data("id") === centerId ? 34 : 22),
            "border-width": 1.5,
            "border-color": "#171614",
          },
        },
        {
          selector: "edge",
          style: {
            width: (ele: any) => 1 + (ele.data("weight") || 0.3) * 3,
            "line-color": (ele: any) => LAYER_COLOR[ele.data("layer")] || "#5a5957",
            "target-arrow-color": (ele: any) => LAYER_COLOR[ele.data("layer")] || "#5a5957",
            "target-arrow-shape": (ele: any) => (ele.data("layer") === "DERIVED" ? "none" : "triangle"),
            "line-style": (ele: any) => (ele.data("layer") === "DERIVED" ? "dashed" : ele.data("layer") === "EXPOSURE" ? "dotted" : "solid"),
            "curve-style": "bezier",
            opacity: 0.85,
          },
        },
      ],
      layout: { name: "cose", animate: false, nodeRepulsion: 8000, idealEdgeLength: 90 } as any,
    });

    cy.on("tap", "node", (evt: any) => {
      const id = evt.target.data("id");
      setParams({ id });
    });
    cy.on("tap", "edge", (evt: any) => {
      setSelected({ type: "edge", data: evt.target.data() });
    });

    cyRef.current = cy;
    return () => cy.destroy();
  }, [graph]);

  return (
    <div className="stack">
      <div className="page-header">
        <h1>Interactive Graph Explorer</h1>
        <div className="subtitle">
          Bounded ego-graph only — never renders the full universe. Fact (solid, directional), Derived (dashed,
          symmetric), Exposure (dotted, counterparty → issuer) layers are toggleable and visually distinct.
        </div>
      </div>

      <div className="card">
        <div className="hstack" style={{ flexWrap: "wrap", gap: 16 }}>
          <div className="searchbar" style={{ maxWidth: 260 }}>
            <input className="input" value={inputId} onChange={(e) => setInputId(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && setParams({ id: inputId })} placeholder="Center entity ID" />
            <button className="btn secondary" onClick={() => setParams({ id: inputId })}>Go</button>
          </div>
          <div className="hstack">
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Hops</span>
            <select value={hops} onChange={(e) => setHops(Number(e.target.value))}>
              <option value={1}>1</option>
              <option value={2}>2</option>
            </select>
          </div>
          {Object.keys(layers).map((k) => (
            <label key={k} className="hstack" style={{ fontSize: 12, color: "var(--text-muted)", cursor: "pointer" }}>
              <input type="checkbox" checked={layers[k]} onChange={(e) => setLayers({ ...layers, [k]: e.target.checked })} />
              <span style={{ color: LAYER_COLOR[k.toUpperCase()] }}>■</span> {k}
            </label>
          ))}
          {graph && <span style={{ fontSize: 11.5, color: "var(--text-faint)", marginLeft: "auto" }}>{graph.node_count} nodes · {graph.edge_count} edges</span>}
        </div>
      </div>

      <div className="row">
        <div className="card" style={{ flex: 2, height: 480, padding: 0, overflow: "hidden" }}>
          <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
        </div>
        <div className="card" style={{ flex: 1, height: 480, overflowY: "auto" }}>
          <div className="section-title">Legend</div>
          {graph && Object.entries(graph.legend).map(([k, v]: any) => (
            <div key={k} className="hstack" style={{ fontSize: 11.5, marginBottom: 6 }}>
              <span style={{ color: LAYER_COLOR[k] }}>■</span> {v}
            </div>
          ))}
          <div className="section-title" style={{ marginTop: 16 }}>Selected edge</div>
          {selected?.type === "edge" ? (
            <div style={{ fontSize: 12 }}>
              <p>{selected.data.source} → {selected.data.target}</p>
              <p><strong>{selected.data.relation}</strong> ({selected.data.layer})</p>
              {selected.data.evidence?.note && <p style={{ color: "var(--text-muted)" }}>{selected.data.evidence.note}</p>}
              {selected.data.evidence?.evidence_url && (
                <a href={selected.data.evidence.evidence_url} target="_blank" rel="noreferrer">source</a>
              )}
            </div>
          ) : (
            <div className="empty-state" style={{ padding: 8 }}>Click an edge to inspect it.</div>
          )}
        </div>
      </div>
    </div>
  );
}
