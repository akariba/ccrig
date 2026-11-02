// The design system on one page (Admin → /admin/ui): every shared component, in every state, with placeholder data.
// Nothing here is real data; it exists so a component can be seen, tested in the browser and reviewed in both themes.
import { useMemo, useRef, useState } from "react";
import { DataTable, type Column } from "../ui/DataTable";
import { Heatmap, PropagationFlow } from "../ui/charts";
import { CHANNELS, type Channel, type Severity } from "../ui/channels";
import { ChannelChip, EmptyState, ErrorState, FilterBar, KpiTile, ProvenanceBadge, SeverityPill, Skeleton, Tabs } from "../ui/primitives";
import { NetworkCanvas, type NetSelection, type NetworkHandle } from "../ui/NetworkCanvas";
import { NodeGuide, ChannelLegend } from "../ui/NetworkCanvas/NodeGuide";
import type { GEdge, GNode } from "../ui/NetworkCanvas/types";
import { Timeline } from "../ui/Timeline";
import { useInspector } from "../ui/InspectorDrawer";

interface Row { id: string; name: string; sev: Severity; util: number; move: number }
const SEVS: Severity[] = ["crit", "high", "med", "low", "info"];
const rows: Row[] = Array.from({ length: 320 }, (_, i) => ({ id: `r${i}`, name: `Counterparty ${String.fromCharCode(65 + (i % 26))}${Math.floor(i / 26) + 1}`, sev: SEVS[i % 5], util: (i * 37) % 120, move: ((i * 53) % 400) - 200 }));
const cols: Column<Row>[] = [
  { key: "name", header: "Counterparty", value: (r) => r.name },
  { key: "sev", header: "Severity", value: (r) => SEVS.indexOf(r.sev), render: (r) => <SeverityPill level={r.sev} /> },
  { key: "util", header: "Utilisation", unit: "%", align: "right", value: (r) => r.util, render: (r) => <span className="u-bar"><i style={{ width: `${Math.min(100, r.util)}%` }} />{r.util}</span> },
  { key: "move", header: "Key move", unit: "$mm", align: "right", value: (r) => r.move },
];
const chans = Object.keys(CHANNELS) as Channel[];
const PRI = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;
const nodes: GNode[] = Array.from({ length: 24 }, (_, i) => i < 8
  ? { id: `n${i}`, kind: "counterparty", label: `Counterparty ${String.fromCharCode(65 + i)}`, tag: `Counterparty ${String.fromCharCode(65 + i)}`, cp: { utilisation: 30 + ((i * 17) % 90), rating: i % 3 === 0 ? null : ["A", "BBB", "AA-"][i % 3], outlook: null, priority: PRI[i % 4], ews: i === 2 ? 0.8 : null, holdingsOnly: false, flags: { wwr: i % 4 === 1, overdue: i === 0, nearLimit: i % 3 === 2, negativeOutlook: null } } }
  : { id: `n${i}`, kind: i % 5 === 0 ? "factor" : "issuer", label: `Issuer ${String.fromCharCode(65 + i - 8)}`, tag: `I${i}`, group: ["Technology", "Financials", "Energy"][i % 3] });
const edges: GEdge[] = Array.from({ length: 40 }, (_, i) => ({ id: `e${i}`, source: `n${i % 8}`, target: `n${8 + ((i * 5) % 16)}`, channel: chans[i % chans.length], strength: 0.3 + ((i * 3) % 7) / 10, confidence: 0.4 + ((i * 11) % 6) / 10, directed: i % 3 === 0 }));
const labels = Array.from({ length: 6 }, (_, i) => `Issuer ${String.fromCharCode(65 + i)}`);
const cells: [number, number, number | null][] = labels.flatMap((_, y) => labels.map((__, x): [number, number, number | null] => [x, y, x === y ? 1 : x + y === 5 ? null : Math.round(((x * 7 + y * 3) % 10)) / 10]));

export default function DesignGallery() {
  const net = useRef<NetworkHandle>(null), [tab, setTab] = useState("one"), [sel, setSel] = useState<NetSelection>(null), [open, setOpen] = useState<string | null>(null), insp = useInspector();
  const flow = useMemo(() => ({ nodes: [{ name: "Headline" }, { name: "Issuer A" }, { name: "Issuer B" }, { name: "Counterparty A" }, { name: "Counterparty B" }], links: [{ source: "Headline", target: "Issuer A", value: 0.8 }, { source: "Headline", target: "Issuer B", value: 0.4 }, { source: "Issuer A", target: "Counterparty A", value: 0.6 }, { source: "Issuer B", target: "Counterparty A", value: 0.2 }, { source: "Issuer B", target: "Counterparty B", value: 0.3 }] }), []);
  return (
    <div className="u-host"><div className="u-host-head"><h1>Design system</h1><p className="u-muted">Every shared component with placeholder data. Not product data.</p></div>
      <div className="u-host-body u-stack">
        <section className="card"><h2>KPI tiles</h2><div className="u-kpis">
          <KpiTile label="Critical items" value={3} delta={1} spark={[1, 2, 2, 3, 2, 3]} provenance="synthetic" /><KpiTile label="Limits at or above 85%" value={5} delta={-2} spark={[7, 6, 6, 5, 5, 5]} /><KpiTile label="Largest cluster" value="$412" unit="mm" note="3 names" provenance="derived" /><KpiTile label="Clickable tile" value="Unavailable" onClick={() => insp.openCustom({ title: "Inspector drawer", subtitle: "Opened from a tile", facts: [["Example", "42"], ["Missing value", null]], href: "/admin/ui" })} />
        </div></section>
        <section className="card"><h2>Pills, chips, badges</h2>
          <div className="u-row">{SEVS.map((s) => <SeverityPill key={s} level={s} />)}</div><div className="u-row">{chans.map((c) => <ChannelChip key={c} channel={c} />)}</div>
          <div className="u-row"><ProvenanceBadge kind="real" /><ProvenanceBadge kind="synthetic" /><ProvenanceBadge kind="derived" /><ProvenanceBadge kind="ai" /></div></section>
        <section className="card"><h2>Tabs and filters</h2><Tabs label="Example tabs" value={tab} onChange={setTab} tabs={[{ id: "one", label: "One" }, { id: "two", label: "Two", count: 4 }, { id: "three", label: "Three" }]} />
          <FilterBar active={open !== null} onClear={() => setOpen(null)}><select aria-label="Example filter" value={open ?? ""} onChange={(e) => setOpen(e.target.value || null)}><option value="">Any severity</option>{SEVS.map((s) => <option key={s}>{s}</option>)}</select></FilterBar></section>
        <section className="card"><h2>Data table (320 rows, virtualised, sort, filter, columns, CSV)</h2><DataTable label="Example counterparties" rows={rows.filter((r) => !open || r.sev === open)} rowKey={(r) => r.id} columns={cols} maxHeight={300} onRowClick={(r) => insp.openCustom({ title: r.name, facts: [["Utilisation", `${r.util}%`]], href: "/admin/ui" })} defaultSort={{ key: "util", dir: "desc" }} /></section>
        <section className="card"><h2>Network canvas</h2><ChannelLegend visible={new Set(chans)} onToggle={() => undefined} /><div className="u-row"><button type="button" className="btn secondary" onClick={() => net.current?.highlight(["n0", "n9", "n12"])}>Highlight three nodes</button><button type="button" className="btn secondary" onClick={() => net.current?.highlight([])}>Clear highlight</button></div><NetworkCanvas ref={net} label="Example network" nodes={nodes} edges={edges} selected={sel} onSelect={setSel} height={380} guide={<NodeGuide />} />{sel && <p className="u-muted">Selected {sel.type}: {sel.id}</p>}</section>
        <section className="card"><h2>Heatmap and propagation flow</h2><div className="u-two"><Heatmap label="Example heatmap" xLabels={labels} yLabels={labels} cells={cells} height={320} /><PropagationFlow label="Example propagation flow" nodes={flow.nodes} links={flow.links} height={320} /></div></section>
        <section className="card"><h2>Timeline</h2><Timeline label="Example timeline" lanes={["Direct", "Via linked names"]} items={[{ id: "a", at: "2026-07-01", lane: "Direct", label: "Example item", severity: "high" }, { id: "b", at: "2026-07-09", lane: "Via linked names", label: "Another item", severity: "med" }, { id: "c", at: "2026-07-20", lane: "Direct", label: "Third item", severity: "crit" }]} /></section>
        <section className="card"><h2>States</h2><div className="u-two"><div><h3>Loading</h3><Skeleton /></div><div><h3>Empty</h3><EmptyState title="No items for this watchlist" hint="Change the watchlist or the date." /></div></div><h3>Error</h3><ErrorState message="The request failed (example)." onRetry={() => undefined} /></section>
      </div></div>
  );
}
