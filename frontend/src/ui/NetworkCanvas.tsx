import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { CHANNELS, type Channel } from "./channels";
import { readChartTokens, useThemeVersion } from "./chartTokens";
import { DataTable } from "./DataTable";

cytoscape.use(fcose);

export interface NetNode { id: string; label: string; kind: "counterparty" | "issuer" | "sector" | "country"; size?: number; importance?: number; color?: string }
export interface NetEdge { id: string; source: string; target: string; channel: Channel; strength?: number; confidence?: number; directed?: boolean }
export type NetSelection = { type: "node"; id: string } | { type: "edge"; id: string } | null;
interface Props { nodes: NetNode[]; edges: NetEdge[]; selected?: NetSelection; onSelect?: (s: NetSelection) => void; onExpand?: (id: string) => void; labelTop?: number; height?: number; label: string }

/** Cytoscape + fcose, with the channel colours from the tokens, names as labels (only the most important until zoomed in), hover highlight, and a list view for narrow screens and screen readers. */
export function NetworkCanvas({ nodes, edges, selected, onSelect, onExpand, labelTop = 14, height = 520, label }: Props) {
  const host = useRef<HTMLDivElement>(null), cyRef = useRef<cytoscape.Core | null>(null), theme = useThemeVersion();
  const [list, setList] = useState(false);
  const cb = useRef({ onSelect, onExpand }); cb.current = { onSelect, onExpand };
  const topIds = useMemo(() => new Set([...nodes].sort((a, b) => (b.importance ?? b.size ?? 0) - (a.importance ?? a.size ?? 0)).slice(0, labelTop).map((n) => n.id)), [nodes, labelTop]);

  useEffect(() => {
    if (list || !host.current) return;
    const t = readChartTokens();
    const cy = cytoscape({
      container: host.current, minZoom: 0.2, maxZoom: 4, wheelSensitivity: 0.3,
      elements: [
        ...nodes.map((n) => ({ data: { id: n.id, label: n.label, kind: n.kind, size: 16 + Math.min(1, n.size ?? 0.3) * 26, top: topIds.has(n.id), color: n.color ?? "" } })),
        ...edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, channel: e.channel, strength: e.strength ?? 0.5, confidence: e.confidence ?? 1, directed: !!e.directed } })),
      ],
      style: [
        { selector: "node", style: { "background-color": (n: cytoscape.NodeSingular) => n.data("color") || (n.data("kind") === "counterparty" ? t.accent : t.text3), width: "data(size)", height: "data(size)", label: (n: cytoscape.NodeSingular) => (n.data("top") ? n.data("label") : ""), color: t.text, "font-size": 12, "font-family": t.font, "text-valign": "bottom", "text-margin-y": 4, "text-wrap": "ellipsis", "text-max-width": "120px", "text-background-color": t.surface, "text-background-opacity": 0.8, "text-background-padding": "2px", "border-width": 2, "border-color": t.surface, shape: (n: cytoscape.NodeSingular) => (n.data("kind") === "counterparty" ? "ellipse" : n.data("kind") === "issuer" ? "round-rectangle" : "diamond") } },
        { selector: "node.labelled", style: { label: "data(label)" } },
        { selector: "edge", style: { width: (e: cytoscape.EdgeSingular) => 1 + 3 * e.data("strength"), opacity: (e: cytoscape.EdgeSingular) => 0.25 + 0.65 * e.data("confidence"), "line-color": (e: cytoscape.EdgeSingular) => t.channel[e.data("channel")] ?? t.text3, "target-arrow-color": (e: cytoscape.EdgeSingular) => t.channel[e.data("channel")] ?? t.text3, "target-arrow-shape": (e: cytoscape.EdgeSingular) => (e.data("directed") ? "triangle" : "none"), "curve-style": "bezier", "line-style": (e: cytoscape.EdgeSingular) => { const d = CHANNELS[e.data("channel") as Channel]?.dash; return !d ? "solid" : d.startsWith("1 ") || d.startsWith("2 ") ? "dotted" : "dashed"; } } },
        { selector: ".faded", style: { opacity: 0.12 } },
        { selector: ":selected", style: { "border-color": t.text, "border-width": 3, "overlay-opacity": 0 } },
      ],
      layout: { name: "fcose", animate: false, quality: "default", randomize: true, nodeRepulsion: 6500, idealEdgeLength: 90 } as cytoscape.LayoutOptions,
    });
    cyRef.current = cy;
    cy.on("tap", "node", (e) => cb.current.onSelect?.({ type: "node", id: e.target.id() }));
    cy.on("tap", "edge", (e) => cb.current.onSelect?.({ type: "edge", id: e.target.id() }));
    cy.on("tap", (e) => { if (e.target === cy) cb.current.onSelect?.(null); });
    cy.on("dbltap", "node", (e) => cb.current.onExpand?.(e.target.id()));
    cy.on("mouseover", "node", (e) => { const n = e.target, around = n.closedNeighborhood(); cy.elements().not(around).addClass("faded"); n.addClass("labelled"); n.neighborhood("node").addClass("labelled"); });
    cy.on("mouseout", "node", () => { cy.elements().removeClass("faded"); cy.nodes().removeClass("labelled"); });
    cy.on("zoom", () => cy.nodes().toggleClass("labelled", cy.zoom() > 1.4));
    return () => { cy.destroy(); cyRef.current = null; };
  }, [nodes, edges, list, theme, topIds]);

  useEffect(() => {
    const cy = cyRef.current; if (!cy) return;
    cy.elements().unselect();
    if (selected) cy.getElementById(selected.id).select();
  }, [selected, nodes, edges, list, theme]);

  const nameOf = (id: string) => nodes.find((n) => n.id === id)?.label ?? id;
  return (
    <div className="u-net">
      <div className="u-net-bar">
        <span className="u-muted">{nodes.length} nodes · {edges.length} links</span><span className="u-spacer" />
        {!list && <><button type="button" className="btn secondary" aria-label="Zoom in" onClick={() => cyRef.current?.zoom({ level: (cyRef.current.zoom() || 1) * 1.3, renderedPosition: { x: (host.current?.clientWidth ?? 0) / 2, y: height / 2 } })}>＋</button>
          <button type="button" className="btn secondary" aria-label="Zoom out" onClick={() => cyRef.current?.zoom({ level: (cyRef.current.zoom() || 1) / 1.3, renderedPosition: { x: (host.current?.clientWidth ?? 0) / 2, y: height / 2 } })}>−</button>
          <button type="button" className="btn secondary" onClick={() => cyRef.current?.fit(undefined, 30)}>Fit</button></>}
        <button type="button" className="btn secondary" aria-pressed={list} onClick={() => setList((v) => !v)}>{list ? "View graph" : "List view"}</button>
      </div>
      {list ? (
        <div key="list" className="u-net-list">
          <DataTable label={`${label}: nodes`} rows={nodes} rowKey={(n) => n.id} maxHeight={260} columns={[{ key: "label", header: "Name", value: (n) => n.label }, { key: "kind", header: "Type", value: (n) => n.kind }, { key: "imp", header: "Importance", value: (n) => n.importance ?? null, align: "right" }]} onRowClick={(n) => onSelect?.({ type: "node", id: n.id })} />
          <DataTable label={`${label}: links`} rows={edges} rowKey={(e) => e.id} maxHeight={260} columns={[{ key: "a", header: "From", value: (e) => nameOf(e.source) }, { key: "b", header: "To", value: (e) => nameOf(e.target) }, { key: "c", header: "Channel", value: (e) => CHANNELS[e.channel].label }, { key: "s", header: "Strength", value: (e) => e.strength ?? null, align: "right" }, { key: "k", header: "Confidence", value: (e) => e.confidence ?? null, align: "right" }]} onRowClick={(e) => onSelect?.({ type: "edge", id: e.id })} />
        </div>
      ) : <div key="canvas" ref={host} className="u-net-canvas" style={{ height }} role="application" aria-label={`${label}. Use the list view for a text alternative.`} />}
    </div>
  );
}
