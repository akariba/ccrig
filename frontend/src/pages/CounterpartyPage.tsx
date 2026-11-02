// Counterparty: everything about one name. Header and KPIs from /api/cp/{id}; the relationship map is the shared NetworkCanvas (radial ego, two hops);
// the inspector and the "all relationships" table are two views of the same selection, which lives in the URL (?node=).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useShell } from "../app/ShellContext";
import { GlobalEventImpactMap } from "./GlobalEventImpactMap";
import { useCounterpartyPage, useNetworkGraph, useStressRun } from "../lib/queries";
import { money, pct } from "../lib/format";
import { CHANNEL_ORDER, CHANNELS, severityOf, type Channel } from "../ui/channels";
import { DataTable } from "../ui/DataTable";
import { EChart } from "../ui/EChart";
import { NodeInspector } from "../ui/NodeInspector";
import { NetworkCanvas, type NetSelection, type NetworkHandle } from "../ui/NetworkCanvas";
import { ChannelLegend, NodeGuide } from "../ui/NetworkCanvas/NodeGuide";
import { toGraph } from "../ui/NetworkCanvas/adapters";
import type { HeatMap } from "../ui/NetworkCanvas/types";
import type { ChartTokens } from "../ui/chartTokens";
import { RiskPath, pathFromChain } from "../components/RiskPath";
import { EmptyState, ErrorState, KpiTile, ProvenanceBadge, SeverityPill, Skeleton } from "../ui/primitives";

interface LinkRow { node_id: string; edge_id: string; name: string; kind: string; channel: string; direction: string | null; strength: number | null; confidence: number | null }
const Sec = ({ title, children, aside, id }: { title: string; children: React.ReactNode; aside?: React.ReactNode; id?: string }) => <section className="tp" data-testid={id}><header className="tp-head"><h2 className="u-sec">{title}</h2>{aside}</header>{children}</section>;

export function CounterpartyPage() {
  const { id } = useParams(), nav = useNavigate(), [params, setParams] = useSearchParams();
  const { queue } = useShell();
  const portfolio = useQuery({ queryKey: ["counterparties"], queryFn: () => api.listCounterparties() });
  const page = useCounterpartyPage(id), net = useNetworkGraph({ scope: "ego", center: id ?? "", hops: 2 }, !!id && page.isSuccess);
  const [layout, setLayout] = useState<"radial" | "force">("radial"), [off, setOff] = useState<Set<Channel>>(new Set());
  const sim = useStressRun(), handle = useRef<NetworkHandle>(null);
  const graph = useMemo(() => (net.data ? toGraph(net.data.nodes, net.data.edges, net.data.clusters) : null), [net.data]);
  const visible = useMemo(() => new Set(CHANNEL_ORDER.filter((c) => !off.has(c))), [off]);
  const counts = useMemo(() => { const c: Partial<Record<Channel, number>> = {}; for (const e of graph?.edges ?? []) c[e.channel] = (c[e.channel] ?? 0) + 1; return c; }, [graph]);
  const centerId = id ? `cp:${id}` : undefined, nodeParam = params.get("node");
  const selected: NetSelection = nodeParam ? { type: "node", id: nodeParam } : null;
  const select = useCallback((s: NetSelection) => setParams((p) => { const n = new URLSearchParams(p); if (s?.type === "node") n.set("node", s.id); else n.delete("node"); return n; }, { replace: true }), [setParams]);
  const heat: HeatMap | null = useMemo(() => (sim.data ? Object.fromEntries(sim.data.nodes.map((n: { id: string; distress: number; hop: number }) => [n.id, { d: n.distress, hop: n.hop }])) : null), [sim.data]);
  useEffect(() => { if (!id && queue[0]) nav(`/cp/${encodeURIComponent(queue[0].id)}`, { replace: true }); }, [id, queue, nav]);     // /cp with no name opens the highest-priority counterparty
  const d = page.data, stories = useQuery({ queryKey: ["risk-clusters", id], queryFn: () => api.riskClusters(id!), enabled: !!id && !!d && !d.holdings_only, retry: false });

  const options = useMemo(() => { const m = new Map<string, string>(); for (const r of queue) m.set(r.id, r.name); for (const r of portfolio.data?.results ?? []) if (!m.has(r.id)) m.set(r.id, r.name); return [...m].sort((a, b) => a[1].localeCompare(b[1])); }, [queue, portfolio.data]);

  const exposure = useCallback((t: ChartTokens) => {
    const s = d?.exposure_series; if (!s) return {};
    const lim = s.limit?.value != null && s.limit.applies_to ? s.limit : null, line = (key: "pfe" | "nse" | "rc", color: string) => ({ name: key.toUpperCase(), type: "line", symbolSize: 8, data: s.points.map((p: Record<string, number | null>) => p[key]), itemStyle: { color }, lineStyle: { color, width: 2 },
      markLine: lim && lim.applies_to === key ? { symbol: "none", silent: true, label: { formatter: `Limit ${lim.value}`, color: t.crit, position: "insideEndTop" }, lineStyle: { color: t.crit, type: "dashed" }, data: [{ yAxis: lim.value }] } : undefined });
    return { animation: false, textStyle: { fontFamily: t.font, color: t.text2 }, tooltip: { trigger: "axis" }, legend: { textStyle: { color: t.text2 }, top: 0 }, grid: { left: 54, right: 76, top: 34, bottom: 28 },
      xAxis: { type: "category", data: s.points.map((p: { label: string }) => p.label), axisLabel: { color: t.text2 } }, yAxis: { type: "value", name: "$mm", axisLabel: { color: t.text2 }, splitLine: { lineStyle: { color: t.border } } },
      series: [line("pfe", t.accent), line("nse", t.series[1]), line("rc", t.series[2])], ...(s.breach ? {} : {}) };
  }, [d]);
  const stress = useCallback((t: ChartTokens) => ({ animation: false, textStyle: { fontFamily: t.font, color: t.text2 }, tooltip: {}, grid: { left: 190, right: 40, top: 8, bottom: 24 }, xAxis: { type: "value", min: 0, max: 1, axisLabel: { color: t.text2 }, splitLine: { lineStyle: { color: t.border } } },
    yAxis: { type: "category", inverse: true, data: (d?.stress.scenarios ?? []).map((s: { label: string }) => s.label), axisLabel: { color: t.text2, width: 170, overflow: "truncate" } },
    series: [{ type: "bar", data: (d?.stress.scenarios ?? []).map((s: { distress: number }) => ({ value: s.distress, itemStyle: { color: s.distress >= 0.66 ? t.crit : s.distress >= 0.33 ? t.high : t.accent } })), label: { show: true, position: "right", color: t.text2, formatter: (p: { value: number }) => p.value.toFixed(2) } }] }), [d]);

  if (!id) return <div className="u-host-body"><EmptyState title="Choose a counterparty" hint="Pick one from the selector, the search (Ctrl/⌘ K) or the Today page." action={<Link className="btn" to="/">Go to Today</Link>} /></div>;
  if (page.isError) return <ErrorState message={`${(page.error as Error).message.includes("404") ? "This counterparty is not in the data." : (page.error as Error).message}`} onRetry={() => page.refetch()} />;
  const h = d?.header, k = d?.kpis;
  return (
    <div className="cpp" data-testid="counterparty-page">
      <header className="cpp-head">
        <label className="u-field"><span className="u-label">Counterparty</span>
          <select aria-label="Choose a counterparty" value={id} onChange={(e) => nav(`/cp/${encodeURIComponent(e.target.value)}`)} data-testid="cp-select">{options.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></label>
        {d ? (
          <div className="cpp-title"><h2>{d.name}</h2>
            <div className="u-row">{h.priority && <SeverityPill level={severityOf(h.priority)} />}<span className="u-muted">{[h.counterparty_type, h.product].filter(Boolean).join(" · ") || (d.holdings_only ? "Holdings only (no CCR record)" : "")}</span>
              <span className="cpp-rating" title={h.rating ? `Rating ${h.rating}` : "No rating is recorded"} data-testid="rating">Rating {h.rating ?? "Unavailable"}{h.outlook ? ` (${h.outlook})` : ""}</span>
              {h.flags.wwr && <span className="u-chip" title="Wrong-way risk">W · wrong-way risk</span>}{h.flags.overdue && <span className="u-chip" title="Overdue breach">! · overdue breach</span>}{h.flags.near_limit && <span className="u-chip">▲ · near limit</span>}
              <span className="u-muted">Owner: {h.owner ?? "Unassigned"}</span><ProvenanceBadge kind="synthetic" /></div></div>
        ) : <Skeleton lines={2} height={20} />}
        <div className="cpp-actions">
          <button type="button" className="btn" data-testid="simulate-cp" disabled={!d || sim.isPending} onClick={() => sim.mutate({ shock: [`cp:${id}`], label: `${d?.name} defaults` })}>Simulate default</button>
          <button type="button" className="btn secondary" disabled title="The assistant is not built yet; nothing here calls a model">Ask CCRIG about this name</button>
        </div>
      </header>
      {sim.data && <div className="sim-card" role="status" data-testid="sim-result"><div className="u-sec">Simulation · {sim.data.label}</div><p style={{ margin: "4px 0" }}>Reaches {sim.data.names_reached} names in {sim.data.hops_reached} hop{sim.data.hops_reached === 1 ? "" : "s"}; counterparties crossing 100%: {sim.data.crossing_100.length ? sim.data.crossing_100.length : "none"}.{sim.data.names_reached === 0 ? " No recorded relationship leaves this counterparty." : ""}</p><p className="tp-note"><ProvenanceBadge kind="derived" /> {sim.data.index_label} <button type="button" className="u-link" onClick={() => sim.reset()}>Clear</button></p></div>}
      <div className="kpis kpis-6" data-testid="cp-kpis">
        <KpiTile label="PFE" value={k ? (k.pfe ?? "Unavailable") : "…"} unit={k?.pfe != null ? "$mm" : undefined} delta={k?.delta_pfe ?? null} deltaUnit=" $mm" goodWhen="down" note="no history to chart" provenance="synthetic" />
        <KpiTile label="Limit utilisation" value={k ? (k.utilisation_pct != null ? pct(k.utilisation_pct, 1) : "Unavailable") : "…"} note={k?.limit_type ? `${k.limit_type.replace("_", " ").toLowerCase()} · headroom ${money(k.headroom)}` : "no limit on file"} provenance="synthetic" />
        <KpiTile label="Rating" value={k ? (k.rating ?? "Unavailable") : "…"} note="none recorded in the data" />
        <KpiTile label="Early-warning score" value={k ? (k.ews ?? "Unavailable") : "…"} note="not built yet" />
        <KpiTile label="Systemic rank" value={d?.systemic_rank ? `${d.systemic_rank.rank} of ${d.systemic_rank.of}` : "…"} note="weighted PageRank on the network" provenance="derived" />
        <KpiTile label="Driver and next action" value={k ? (k.driver ?? "Unavailable") : "…"} note={d?.decision?.decision ?? "no CCR record"} />
      </div>
      <div className="cpp-main">
        <Sec id="cp-map" title="Relationship map" aside={<div className="u-row"><div className="u-seg" role="group" aria-label="Layout">{(["radial", "force"] as const).map((l) => <button key={l} type="button" aria-pressed={layout === l} onClick={() => setLayout(l)}><span>{l === "radial" ? "Radial" : "Force"}</span></button>)}</div></div>}>
          <ChannelLegend visible={visible} counts={counts} onToggle={(c) => setOff((s) => { const n = new Set(s); if (n.has(c)) n.delete(c); else n.add(c); return n; })} />
          {net.isLoading || !graph ? <Skeleton lines={8} /> : net.isError ? <ErrorState message={(net.error as Error).message} onRetry={() => net.refetch()} /> : graph.edges.length === 0 ? <EmptyState title="No recorded relationships" hint="This counterparty has no link to an issuer, a risk factor or another counterparty in the data, so there is nothing to draw and a default here cannot propagate." /> :
            <NetworkCanvas ref={handle} label={`Relationships of ${d?.name ?? id}`} nodes={graph.nodes} edges={graph.edges} clusters={graph.clusters} layout={layout} centerId={centerId} fixedCenter visibleChannels={visible} selected={selected} onSelect={select} heat={heat} shock={sim.data?.shocked ?? []} height={500} />}
        </Sec>
        <div className="u-stack"><Sec id="cp-inspector" title="Inspector">{graph ? <NodeInspector centerId={centerId} selected={selected} nodes={graph.nodes} edges={graph.edges} onClear={() => select(null)} /> : <Skeleton lines={5} />}</Sec><NodeGuide inline /></div>
      </div>
      <Sec id="cp-links" title="All relationships" aside={<span className="tp-note">synced with the map</span>}>
        {d ? <DataTable label={`Relationships of ${d.name}`} rows={d.links as LinkRow[]} rowKey={(l) => l.edge_id} selectedKey={selected ? (d.links as LinkRow[]).find((l) => l.node_id === selected.id)?.edge_id : null} maxHeight={320} emptyTitle="No recorded relationships"
          onRowClick={(l) => select({ type: "node", id: l.node_id })}
          columns={[{ key: "name", header: "Name", value: (l) => l.name }, { key: "kind", header: "Type", value: (l) => l.kind }, { key: "channel", header: "Channel", value: (l) => CHANNELS[l.channel as Channel].label }, { key: "dir", header: "Direction", value: (l) => l.direction ?? "none" },
            { key: "strength", header: "Strength", align: "right", value: (l) => l.strength }, { key: "conf", header: "Confidence", align: "right", value: (l) => l.confidence }]} /> : <Skeleton lines={4} />}
      </Sec>
      <div className="tp-grid">
        <Sec id="cp-exposure" title="Exposure vs limit">{d?.exposure_series ? <><EChart label={`Exposure and limit of ${d.name}`} build={exposure} height={260} deps={d} table={{ columns: ["Snapshot", "PFE ($mm)", "NSE ($mm)", "RC ($mm)"], rows: d.exposure_series.points.map((p: { label: string; pfe: number; nse: number; rc: number }) => [p.label, p.pfe, p.nse, p.rc]) }} />
          <p className="tp-note"><ProvenanceBadge kind="synthetic" /> {d.exposure_series.note}{d.exposure_series.limit.value != null && !d.exposure_series.limit.applies_to ? " The limit applies to a measure that is not charted." : ""}{d.exposure_series.breach ? ` Breach: ${d.exposure_series.breach.age_days} days old against a ${d.exposure_series.breach.sla_days}-day target.` : ""}</p></> : d ? <EmptyState title="No exposure record" hint="This counterparty has holdings only, with no exposure, limit or breach data." /> : <Skeleton lines={5} />}</Sec>
        <Sec id="cp-stress" title="Stress impact by scenario">{d ? <><EChart label={`Propagation index by scenario for ${d.name}`} build={stress} height={260} deps={d} table={{ columns: ["Scenario", "Index", "Hop"], rows: d.stress.scenarios.map((s: { label: string; distress: number; hop: number | null }) => [s.label, s.distress, s.hop]) }} /><p className="tp-note"><ProvenanceBadge kind="derived" /> {d.stress.index_label}</p></> : <Skeleton lines={5} />}</Sec>
      </div>
      {stories.data?.results?.length > 0 && (
        <Sec id="cp-stories" title="Risk stories" aside={<span className="tp-note">derived from exposure, relationships and transmission</span>}>
          {stories.data.results.map((c: { id: string; label: string; story: string[]; why_it_matters: string; recommended_action: string }) => (
            <div key={c.id} className="story"><h3>{c.label}</h3><RiskPath path={pathFromChain(c.story)} /><p>{c.why_it_matters}</p><p className="ai-box"><span className="ai-label">Next action</span>{c.recommended_action}</p></div>))}
        </Sec>)}
      <Sec id="cp-events" title="Events and news" aside={<span className="tp-note">for this name and its linked names</span>}>
        {!d ? <Skeleton lines={4} /> : d.events.length === 0 ? <EmptyState title="Nothing in the data reaches this counterparty" hint="Events are matched through the companies they name and the counterparties that hold them." /> : (
          <><ul className="me-list">{d.events.map((e: { id: string; title: string; date: string; link: string; via: string; badge: string | null }) => <li key={e.id}><div className="me-top"><span className="me-date">{e.date}</span><span className="me-cat">{e.link}{e.link !== "direct" ? ` (${e.via})` : ""}</span>{e.badge && <span className={`me-badge me-${e.badge.toLowerCase()}`}>{e.badge}</span>}</div><p className="me-title">{e.title}</p></li>)}</ul>
            {d.events.some((e: { badge: string | null }) => e.badge === "Verified") && d.events_entity && <GlobalEventImpactMap variant="compact" entityId={d.events_entity} eventIds={d.events.filter((e: { badge: string | null }) => e.badge === "Verified").map((e: { id: string }) => e.id)} />}</>)}
      </Sec>
    </div>
  );
}
