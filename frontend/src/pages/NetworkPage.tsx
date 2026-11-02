// Network: the whole relationship structure, filtered by scope and channel. Filter rail, canvas, inspector, and tables below.
import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useNetworkGraph } from "../lib/queries";
import { CHANNEL_ORDER, CHANNELS, type Channel } from "../ui/channels";
import { DataTable } from "../ui/DataTable";
import { NodeInspector } from "../ui/NodeInspector";
import { NetworkCanvas, type NetSelection } from "../ui/NetworkCanvas";
import { ChannelLegend, NodeGuide } from "../ui/NetworkCanvas/NodeGuide";
import { toGraph } from "../ui/NetworkCanvas/adapters";
import type { GNode } from "../ui/NetworkCanvas/types";
import { useShell } from "../app/ShellContext";
import { ErrorState, ProvenanceBadge, Skeleton, Tabs } from "../ui/primitives";

const KINDS: Record<string, string> = { counterparty: "Counterparty", issuer: "Issuer", factor: "Risk factor" };
export function NetworkPage() {
  const [params, setParams] = useSearchParams(), { watchlist } = useShell();
  const centerParam = params.get("id"), scope = (params.get("scope") as "watchlist" | "ego" | "all" | null) ?? (centerParam ? "ego" : "all");
  const hops = Math.max(1, Math.min(3, Number(params.get("hops") ?? 2) || 2)), includeStudio = params.get("studio") === "1", layout = params.get("layout") === "radial" ? "radial" : "force";
  const off = useMemo(() => new Set((params.get("off") ?? "").split(",").filter(Boolean) as Channel[]), [params]), nodeParam = params.get("node");
  const [tab, setTab] = useState("nodes"), [guide, setGuide] = useState(false), [highlight, setHighlight] = useState<string[]>([]);
  const setP = useCallback((patch: Record<string, string | null>) => setParams((prev) => { const n = new URLSearchParams(prev); for (const [k, v] of Object.entries(patch)) { if (v === null || v === "") n.delete(k); else n.set(k, v); } return n; }, { replace: true }), [setParams]);

  const everything = useNetworkGraph({ scope: "all", hops: 1 });                                           // for the centre picker only
  const q: Record<string, string | number | boolean> = scope === "ego" ? { scope, center: centerParam ?? "", hops, include_studio: includeStudio } : scope === "watchlist" ? { scope, ids: watchlist.join(","), hops, include_studio: includeStudio } : { scope: "all", include_studio: includeStudio };
  const net = useNetworkGraph(q, scope !== "ego" || !!centerParam);
  const graph = useMemo(() => (net.data ? toGraph(net.data.nodes, net.data.edges, net.data.clusters) : null), [net.data]);
  const visible = useMemo(() => new Set(CHANNEL_ORDER.filter((c) => !off.has(c))), [off]);
  const counts = useMemo(() => { const c: Partial<Record<Channel, number>> = {}; for (const e of graph?.edges ?? []) c[e.channel] = (c[e.channel] ?? 0) + 1; return c; }, [graph]);
  const centerId = scope === "ego" && net.data?.seeds?.[0] ? (net.data.seeds[0] as string) : undefined;
  const selected: NetSelection = nodeParam ? { type: "node", id: nodeParam } : params.get("edge") ? { type: "edge", id: params.get("edge")! } : null;
  const select = useCallback((s: NetSelection) => setP({ node: s?.type === "node" ? s.id : null, edge: s?.type === "edge" ? s.id : null }), [setP]);
  const names = (everything.data?.nodes ?? []) as { id: string; label: string; kind: string }[];
  const toggle = (c: Channel) => { const n = new Set(off); if (n.has(c)) n.delete(c); else n.add(c); setP({ off: [...n].join(",") }); };

  return (
    <div className="np" data-testid="network-page">
      <aside className="np-rail" aria-label="Filters">
        <div className="u-sec">Scope</div>
        <label className="u-field"><span className="u-label">Show</span>
          <select value={scope} onChange={(e) => setP({ scope: e.target.value, node: null, edge: null })} data-testid="scope"><option value="watchlist">My watchlist and its neighbours</option><option value="all">Everything</option><option value="ego">One name and its neighbours</option></select></label>
        {scope === "ego" && <label className="u-field"><span className="u-label">Name</span>
          <input className="input" list="np-names" value={names.find((n) => n.id === centerParam || n.id === `cp:${centerParam}` || n.id === `is:${centerParam}`)?.label ?? centerParam ?? ""} placeholder="Type a name" data-testid="center-input"
            onChange={(e) => { const hit = names.find((n) => n.label.toLowerCase() === e.target.value.toLowerCase()); if (hit) setP({ id: hit.id, node: null }); else setP({ id: e.target.value || null }); }} /><datalist id="np-names">{names.map((n) => <option key={n.id} value={n.label}>{KINDS[n.kind]}</option>)}</datalist></label>}
        {scope !== "all" && <label className="u-field"><span className="u-label">Hops</span><select value={hops} onChange={(e) => setP({ hops: e.target.value })}><option value="1">1</option><option value="2">2</option><option value="3">3</option></select></label>}
        <div className="u-sec">Layout</div>
        <div className="u-seg" role="group" aria-label="Layout">{(["force", "radial"] as const).map((l) => <button key={l} type="button" aria-pressed={layout === l} disabled={l === "radial" && scope !== "ego"} onClick={() => setP({ layout: l })}><span>{l === "force" ? "Force" : "Radial"}</span></button>)}</div>
        <div className="u-sec">Channels</div>
        <ChannelLegend visible={visible} counts={counts} onToggle={toggle} />
        <div className="u-sec">Sources</div>
        <label className="np-check" title="Relationships approved in an operator's Data Studio. They are not part of the canonical dataset and carry no criticality."><input type="checkbox" data-testid="include-studio" checked={includeStudio} onChange={(e) => setP({ studio: e.target.checked ? "1" : null })} /> Include Studio-approved relationships</label>
        <label className="np-check"><input type="checkbox" checked={guide} onChange={(e) => setGuide(e.target.checked)} /> Node guide</label>
      </aside>
      <div className="np-center">
        {includeStudio && net.data?.studio_overlay && <div className={net.data.studio_overlay.available ? "card" : "warning-box"} data-testid="studio-overlay-note" style={{ fontSize: 12, marginBottom: 8 }}>
          {net.data.studio_overlay.available ? <>Approved relationships are drawn in the ownership colour ({net.data.studio_overlay.edges_added} added). They are not in the canonical dataset, carry no criticality and change no score.{net.data.studio_overlay.release && <> · release v{net.data.studio_overlay.release.version} approved by {net.data.studio_overlay.release.approved_by}</>}</> : <>{net.data.studio_overlay.reason}</>}</div>}
        {scope === "ego" && !centerParam ? <p className="u-muted">Choose a name to see its neighbours.</p> : net.isLoading || !graph ? <Skeleton lines={10} /> : net.isError ? <ErrorState message={(net.error as Error).message} onRetry={() => net.refetch()} /> : (
          <NetworkCanvas label="Relationship network" nodes={graph.nodes} edges={graph.edges} clusters={graph.clusters} layout={layout === "radial" && centerId ? "radial" : "force"} centerId={centerId} fixedCenter={layout === "force"} visibleChannels={visible}
            selected={selected} onSelect={select} highlightIds={highlight} height={560} guide={guide ? <NodeGuide onClose={() => setGuide(false)} /> : undefined} />)}
        <p className="tp-note"><ProvenanceBadge kind="derived" /> Counterparty exposure is synthetic; supply links are curated public facts; co-movement uses real daily prices for 14 issuers only.</p>
        {graph && (
          <div className="np-tabs"><Tabs label="Network tables" value={tab} onChange={setTab} tabs={[{ id: "nodes", label: "Nodes", count: graph.nodes.length }, { id: "clusters", label: "Clusters", count: graph.clusters.length }]} />
            <div role="tabpanel">{tab === "nodes" ? <DataTable<GNode> label="Network nodes" rows={graph.nodes} rowKey={(n) => n.id} maxHeight={300} selectedKey={nodeParam} onRowClick={(n) => select({ type: "node", id: n.id })}
              columns={[{ key: "label", header: "Name", value: (n) => n.label }, { key: "kind", header: "Type", value: (n) => KINDS[n.kind] }, { key: "group", header: "Sector", value: (n) => n.group ?? null }, { key: "pri", header: "Priority", value: (n) => n.cp?.priority ?? null }, { key: "util", header: "Utilisation", unit: "%", align: "right", value: (n) => n.cp?.utilisation ?? null }]} />
              : <DataTable label="Clusters" rows={graph.clusters} rowKey={(c) => c.id} maxHeight={300} emptyTitle="No clusters in this scope" emptyHint="A cluster needs at least two counterparties that hold the same issuers." onRowClick={(c) => setHighlight(c.members)}
                columns={[{ key: "name", header: "Cluster", value: (c) => c.name }, { key: "size", header: "Members", align: "right", value: (c) => c.members.length }, { key: "members", header: "Counterparties", value: (c) => c.members.map((m) => graph.nodes.find((n) => n.id === m)?.label ?? m).join(", ") }, { key: "channel", header: "Dominant channel", value: () => CHANNELS.shared.label }]} />}
              {tab === "clusters" && highlight.length > 0 && <p className="tp-note">Highlighted on the map: {highlight.length} members. <button type="button" className="u-link" onClick={() => setHighlight([])}>Clear</button></p>}</div></div>)}
      </div>
      <aside className="np-inspector" aria-label="Inspector"><div className="u-sec">Inspector</div>
        {graph ? <NodeInspector centerId={centerId} selected={selected} nodes={graph.nodes} edges={graph.edges} onClear={() => select(null)} /> : <Skeleton lines={5} />}</aside>
    </div>
  );
}
