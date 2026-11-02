// Stress & Shocks (first version): pick a preset or a counterparty default, run the deterministic propagation, read who is reached. A propagation index, never a loss figure.
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useShell } from "../app/ShellContext";
import { useNetworkGraph, useScenarios, useStressRun } from "../lib/queries";
import { DataTable } from "../ui/DataTable";
import { NetworkCanvas } from "../ui/NetworkCanvas";
import { toGraph } from "../ui/NetworkCanvas/adapters";
import type { HeatMap } from "../ui/NetworkCanvas/types";
import { EmptyState, ErrorState, KpiTile, ProvenanceBadge, Skeleton } from "../ui/primitives";

interface Row { id: string; label: string; kind: string; distress: number; hop: number; path: string[]; utilisation_before?: number; utilisation_after?: number }
export function StressPage() {
  const [params, setParams] = useSearchParams(), { queue } = useShell(), sc = useScenarios(), run = useStressRun();
  const wanted = params.get("scenario") ?? "", net = useNetworkGraph({ scope: "all" });
  const graph = useMemo(() => (net.data ? toGraph(net.data.nodes, net.data.edges, net.data.clusters) : null), [net.data]);
  const [hops, setHops] = useState(3);
  const options = useMemo(() => [...(sc.data?.scenarios ?? []).map((s: { id: string; label: string; shock: string[] }) => ({ id: s.id, label: s.label, shock: s.shock })), ...queue.map((r) => ({ id: `DEFAULT:${r.id}`, label: `${r.name} defaults`, shock: [`cp:${r.id}`] }))], [sc.data, queue]);
  const chosen = options.find((o) => o.id === wanted);
  useEffect(() => { if (chosen) run.mutate({ shock: chosen.shock, label: chosen.label, max_hops: hops }); }, [chosen?.id, hops]);   // eslint-disable-line react-hooks/exhaustive-deps
  const heat: HeatMap | null = useMemo(() => (run.data ? Object.fromEntries(run.data.nodes.map((n: Row) => [n.id, { d: n.distress, hop: n.hop }])) : null), [run.data]);
  const d = run.data;
  return (
    <div className="u-host" data-testid="stress-page">
      <div className="u-host-head"><h1>Stress & Shocks</h1><p className="u-muted">If X breaks, who gets hit and which limits fail? A deterministic propagation over the relationship network.</p></div>
      <div className="u-host-body u-stack">
        <div className="card u-row">
          <label className="u-field"><span className="u-label">Scenario</span>
            <select value={wanted} data-testid="scenario-select" onChange={(e) => setParams(e.target.value ? { scenario: e.target.value } : {})}><option value="">Choose a scenario…</option>{options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}</select></label>
          <label className="u-field"><span className="u-label">Max hops</span><select value={hops} onChange={(e) => setHops(Number(e.target.value))}>{[1, 2, 3, 4].map((h) => <option key={h}>{h}</option>)}</select></label>
          <span className="tp-note"><ProvenanceBadge kind="derived" /> Propagation index, not a loss estimate. No currency figure is produced.</span>
        </div>
        {!chosen ? <EmptyState title="Choose a scenario" hint="Pick a preset or a counterparty default. The Today page's stress heatmap opens here with its scenario selected." action={<Link className="btn secondary" to="/">Back to Today</Link>} />
          : run.isPending ? <Skeleton lines={8} /> : run.isError ? <ErrorState message={(run.error as Error).message} onRetry={() => run.mutate({ shock: chosen.shock, label: chosen.label, max_hops: hops })} /> : d && (
          <>
            <div className="kpis kpis-6">
              <KpiTile label="Names reached" value={d.names_reached} /><KpiTile label="Hops reached" value={d.hops_reached} /><KpiTile label="Counterparties reached" value={d.counterparties_reached} />
              <KpiTile label="Crossing 85% of limit" value={d.crossing_85.length} /><KpiTile label="Crossing 100% of limit" value={d.crossing_100.length} /><KpiTile label="Max index" value={d.nodes.filter((n: Row) => n.hop > 0)[0]?.distress.toFixed(2) ?? "0.00"} />
            </div>
            {d.names_reached === 0 && <p className="warning-box">No recorded relationship leaves the shocked node, so nothing propagates in this data.</p>}
            <section className="tp"><header className="tp-head"><h2 className="u-sec">Network heat</h2></header>{graph && <NetworkCanvas label="Contagion overlay" nodes={graph.nodes} edges={graph.edges} clusters={graph.clusters} layout="force" heat={heat} shock={d.shocked} height={460} />}</section>
            <section className="tp"><header className="tp-head"><h2 className="u-sec">Who is reached</h2></header>
              <DataTable<Row> label="Names reached" rows={d.nodes} rowKey={(r) => r.id} maxHeight={420} defaultSort={{ key: "distress", dir: "desc" }}
                columns={[{ key: "label", header: "Name", value: (r) => r.label }, { key: "kind", header: "Type", value: (r) => r.kind }, { key: "hop", header: "Hop", align: "right", value: (r) => r.hop }, { key: "distress", header: "Index", align: "right", value: (r) => r.distress },
                  { key: "path", header: "Path", value: (r) => r.path.join(" → ") }, { key: "before", header: "Utilisation before", unit: "%", align: "right", value: (r) => r.utilisation_before ?? null }, { key: "after", header: "Utilisation after", unit: "%", align: "right", value: (r) => r.utilisation_after ?? null }]} />
              <p className="tp-note">Utilisation after = utilisation × (1 + index × {d.method.utilisation_sensitivity}); the multiplier is {d.method.sensitivity_is}.</p></section>
          </>)}
      </div>
    </div>
  );
}
