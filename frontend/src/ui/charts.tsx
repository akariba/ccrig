import { useCallback } from "react";
import { EChart } from "./EChart";
import type { Cell } from "../lib/tableModel";
import type { ChartTokens } from "./chartTokens";

export interface HeatmapProps { label: string; xLabels: string[]; yLabels: string[]; cells: [number, number, number | null][]; min?: number; max?: number; format?: (v: number) => string; height?: number; onCell?: (x: number, y: number) => void }
/** Matrix heatmap (correlation matrix, counterparty × issuer overlap). Cells with no value stay empty and are listed as "—" in the table. */
export function Heatmap({ label, xLabels, yLabels, cells, min = 0, max = 1, format = (v) => v.toFixed(2), height = 360, onCell }: HeatmapProps) {
  const build = useCallback((t: ChartTokens) => ({
    textStyle: { fontFamily: t.font, color: t.text2 }, animation: false,
    tooltip: { position: "top", formatter: (p: { value: [number, number, number | null] }) => `${yLabels[p.value[1]]} × ${xLabels[p.value[0]]}: ${p.value[2] === null ? "Unavailable" : format(p.value[2])}` },
    grid: { left: 110, right: 20, top: 10, bottom: 70, containLabel: false },
    xAxis: { type: "category", data: xLabels, axisLabel: { rotate: 45, color: t.text2, fontSize: 12 }, splitArea: { show: false } },
    yAxis: { type: "category", data: yLabels, axisLabel: { color: t.text2, fontSize: 12 }, inverse: true },
    visualMap: { min, max, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemWidth: 12, itemHeight: 120, textStyle: { color: t.text2 }, inRange: { color: [t.surface2, t.accent] } },
    series: [{ type: "heatmap", data: cells.filter((c) => c[2] !== null), itemStyle: { borderColor: t.surface, borderWidth: 1 }, emphasis: { itemStyle: { borderColor: t.text, borderWidth: 1 } } }],
  }), [xLabels, yLabels, cells, min, max, format]);
  const rows: Cell[][] = cells.map(([x, y, v]) => [yLabels[y], xLabels[x], v === null ? null : Number(v.toFixed(4))]);
  return <EChart label={label} build={build} height={height} table={{ columns: ["Row", "Column", "Value"], rows }} deps={cells} onClick={(p) => { const v = (p as { value?: number[] }).value; if (v && onCell) onCell(v[0], v[1]); }} />;
}

export interface FlowNode { name: string; depth?: number }
export interface FlowLink { source: string; target: string; value: number }
/** Sankey of how a shock or a headline fans out: headline → issuers → counterparties, link width = relevance. */
export function PropagationFlow({ label, nodes, links, height = 320 }: { label: string; nodes: FlowNode[]; links: FlowLink[]; height?: number }) {
  const build = useCallback((t: ChartTokens) => ({
    textStyle: { fontFamily: t.font, color: t.text2 }, animation: false, tooltip: { trigger: "item", triggerOn: "mousemove" },
    series: [{ type: "sankey", left: 8, right: 120, top: 8, bottom: 8, nodeGap: 10, nodeWidth: 14, data: nodes.map((n) => ({ name: n.name, depth: n.depth })), links,
      lineStyle: { color: "gradient", opacity: 0.4, curveness: 0.5 }, label: { color: t.text, fontSize: 12 }, itemStyle: { color: t.accent, borderColor: t.accent } }],
  }), [nodes, links]);
  return <EChart label={label} build={build} height={height} table={{ columns: ["From", "To", "Relevance"], rows: links.map((l) => [l.source, l.target, l.value]) }} deps={links} />;
}
