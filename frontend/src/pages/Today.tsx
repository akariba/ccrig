// Today: the command center. The hero is the live relationship network of the watchlist; everything below it is a panel over the same payload.
import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useShell } from "../app/ShellContext";
import { GlobalEventImpactMap } from "./GlobalEventImpactMap";
import { Concentration, DataHealth, MarketEvents, Panel, RatingsFlags, StressHeatmap, TopExposures } from "../today/panels";
import { useNetworkGraph, useStressRun, useToday } from "../lib/queries";
import { niceDate, todayISO } from "../lib/format";
import { CHANNEL_ORDER, type Channel } from "../ui/channels";
import { EmptyState, ErrorState, KpiTile, ProvenanceBadge, Skeleton } from "../ui/primitives";
import { NetworkCanvas, type NetSelection, type NetworkHandle } from "../ui/NetworkCanvas";
import { ChannelLegend, NodeGuide } from "../ui/NetworkCanvas/NodeGuide";
import { toGraph } from "../ui/NetworkCanvas/adapters";
import type { HeatMap } from "../ui/NetworkCanvas/types";

export function Today() {
  const { watchlist, asOf } = useShell(), nav = useNavigate(), asOfDate = asOf ?? todayISO();
  const q = useToday(asOfDate, watchlist);
  const net = useNetworkGraph({ scope: "watchlist", ids: watchlist.join(","), hops: 2 }, watchlist.length > 0);
  const graph = useMemo(() => (net.data ? toGraph(net.data.nodes, net.data.edges, net.data.clusters) : null), [net.data]);
  const [visible, setVisible] = useState<ReadonlySet<Channel>>(new Set(CHANNEL_ORDER)), [guide, setGuide] = useState(false), [sel, setSel] = useState<NetSelection>(null);
  const sim = useStressRun(), handle = useRef<NetworkHandle>(null);
  const heat: HeatMap | null = useMemo(() => (sim.data ? Object.fromEntries(sim.data.nodes.map((n: { id: string; distress: number; hop: number }) => [n.id, { d: n.distress, hop: n.hop }])) : null), [sim.data]);
  const counts = useMemo(() => { const c: Partial<Record<Channel, number>> = {}; for (const e of graph?.edges ?? []) c[e.channel] = (c[e.channel] ?? 0) + 1; return c; }, [graph]);
  const d = q.data;
  const target = d?.simulate as { id: string; name: string; priority: string } | null | undefined;
  const nameOf = (id: string) => graph?.nodes.find((n) => n.id === id)?.label ?? id;

  if (q.isError) return <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />;
  return (
    <div className="today" data-testid="today-page">
      <section className="hero" aria-labelledby="hero-h">
        <div className="hero-text">
          <p className="u-sec" data-testid="hero-date">{niceDate(asOfDate)}{asOf ? "" : " · latest"}</p>
          <p className="hero-scope u-muted">{d ? d.scope.line : "Loading the watchlist…"}</p>
          <h2 id="hero-h" className="hero-head">{d ? d.headline : <Skeleton lines={2} height={22} />}</h2>
          {d && <p className="hero-sum">{d.summary} <span className="hero-tag"><ProvenanceBadge kind="derived" label="Template summary" /></span></p>}
          <div className="hero-actions">
            <button type="button" className="btn" data-testid="simulate" disabled={!target || sim.isPending} onClick={() => target && sim.mutate({ shock: [`cp:${target.id}`], label: `${target.name} defaults` })}>{target ? `Simulate ${target.name} default` : "Simulate a default"}</button>
            {d?.top_critical && <Link className="btn secondary" to={`/cp/${encodeURIComponent(d.top_critical.id)}`}>Open {d.top_critical.name}</Link>}
            <button type="button" className="btn secondary" aria-pressed={guide} onClick={() => setGuide((v) => !v)}>Node guide</button>
            <a className="btn secondary" href="#world-map">World map ↓</a>
          </div>
          {sim.isError && <ErrorState message={(sim.error as Error).message} onRetry={() => target && sim.mutate({ shock: [`cp:${target.id}`] })} />}
          {sim.data && (
            <div className="sim-card" data-testid="sim-result" role="status">
              <div className="u-sec">Simulation · {sim.data.label}</div>
              <dl>
                <dt>Names reached</dt><dd data-testid="sim-names">{sim.data.names_reached}</dd><dt>Hops</dt><dd data-testid="sim-hops">{sim.data.hops_reached}</dd>
                <dt>Counterparties reached</dt><dd>{sim.data.counterparties_reached}</dd>
                <dt>Crossing 100% of limit</dt><dd data-testid="sim-cross">{sim.data.crossing_100.length ? sim.data.crossing_100.map(nameOf).join(", ") : "none"}</dd>
                <dt>Crossing 85%</dt><dd>{sim.data.crossing_85.length ? sim.data.crossing_85.map(nameOf).join(", ") : "none"}</dd>
              </dl>
              {sim.data.names_reached === 0 && <p className="tp-note">No recorded relationship leaves this counterparty, so nothing propagates in this data.</p>}
              <p className="tp-note"><ProvenanceBadge kind="derived" /> {sim.data.index_label}</p>
              <button type="button" className="u-link" onClick={() => sim.reset()}>Clear simulation</button>
            </div>
          )}
        </div>
        <div className="hero-graph">
          <ChannelLegend visible={visible} counts={counts} onToggle={(c) => setVisible((s) => { const n = new Set(s); if (n.has(c)) n.delete(c); else n.add(c); return n; })} />
          {net.isLoading || !graph ? <Skeleton lines={8} /> : net.isError ? <ErrorState message={(net.error as Error).message} onRetry={() => net.refetch()} /> :
            <NetworkCanvas ref={handle} label="Relationship network of the watchlist" nodes={graph.nodes} edges={graph.edges} clusters={graph.clusters} layout="force" visibleChannels={visible} heat={heat} shock={sim.data?.shocked ?? []}
              selected={sel} onSelect={(s) => { setSel(s); if (s?.type === "node" && s.id.startsWith("cp:")) nav(`/cp/${encodeURIComponent(s.id.slice(3))}`); }} height={460} guide={guide ? <NodeGuide onClose={() => setGuide(false)} /> : undefined} />}
          <p className="tp-note">Click a counterparty to open it. Hover to focus its neighbours. Ctrl/⌘ + scroll zooms; drag pans.</p>
        </div>
      </section>
      <div className="kpis" data-testid="kpis">
        {d ? d.kpis.map((k: { id: string; label: string; value: number | null; note: string | null; severity?: "crit" | "high" | "med" }) => <KpiTile key={k.id} label={k.label} value={k.value === null ? "Unavailable" : k.value} note={k.value === null ? k.note : "No history to chart"} provenance="synthetic" />) : Array.from({ length: 6 }, (_, i) => <Skeleton key={i} lines={2} />)}
      </div>
      <Panel id="world-map" title="Global event map" wide aside={d ? <span className="tp-note">{d.map_entity.name} · {d.map_entity.basis}</span> : undefined}>
        <div id="world-map">{d?.map_entity?.entity_id ? <GlobalEventImpactMap variant="compact" entityId={d.map_entity.entity_id} /> : d ? <EmptyState title="No event register entry" hint="The approved-source register covers no issuer here." /> : <Skeleton lines={6} />}</div>
      </Panel>
      <div className="tp-grid">
        <Panel id="top-exposures" title="Top exposures" aside={<span className="tp-note">limit utilisation · 85% and 100% marked</span>}>{d ? <TopExposures rows={d.top_exposures} /> : <Skeleton lines={6} />}</Panel>
        <Panel id="stress-heatmap" title="Stress heatmap" aside={<span className="tp-note">counterparty × scenario</span>}>{d ? <StressHeatmap data={d.stress_heatmap} onCell={(id) => nav(`/stress?scenario=${encodeURIComponent(id)}`)} /> : <Skeleton lines={6} />}</Panel>
        <Panel id="market-events" title="Market events">{d ? <MarketEvents rows={d.market_events} /> : <Skeleton lines={6} />}</Panel>
        <Panel id="concentration" title="Concentration">{d ? <Concentration data={d.concentration} /> : <Skeleton lines={6} />}</Panel>
        <Panel id="ratings-flags" title="Ratings and flags">{d ? <RatingsFlags data={d.ratings} /> : <Skeleton lines={4} />}</Panel>
        <Panel id="data-health" title="Data and AI health" wide><DataHealth asOf={asOfDate} /></Panel>
      </div>
      <p className="tp-note today-links">Detail views: <Link to="/?tab=inbox">Inbox</Link> · <Link to="/?tab=movers">Exposure movers</Link> · <Link to="/?tab=controls">Controls</Link></p>
    </div>
  );
}
