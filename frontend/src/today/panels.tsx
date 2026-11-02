// The panels of the Today page. Each one renders what the API returned and says plainly when the data does not exist.
import { Link } from "react-router-dom";
import { EmptyState, ErrorState, ProvenanceBadge, SeverityPill, Skeleton } from "../ui/primitives";
import { severityOf } from "../ui/channels";
import { niceDate, pct, signed } from "../lib/format";
import { useModels, usePipeline, useSources } from "../lib/queries";

export const Panel = ({ id, title, aside, children, wide }: { id: string; title: string; aside?: React.ReactNode; children: React.ReactNode; wide?: boolean }) => (
  <section className={`tp${wide ? " tp-wide" : ""}`} data-testid={id} aria-labelledby={`${id}-h`}><header className="tp-head"><h2 id={`${id}-h`} className="u-sec">{title}</h2>{aside}</header>{children}</section>
);

interface Exposure { id: string; name: string; priority: string; utilisation_pct: number | null; pfe: number | null; delta_pfe: number | null; rating: string | null; outlook: string | null; wwr: boolean; overdue: boolean; limit_type: string | null }
export function TopExposures({ rows }: { rows: Exposure[] }) {
  if (rows.length === 0) return <EmptyState title="No counterparties in this watchlist" hint="Edit the watchlist in the top bar." />;
  return (
    <ol className="te-list">
      {rows.map((r) => (
        <li key={r.id}>
          <Link className="te-row" to={`/cp/${encodeURIComponent(r.id)}`} data-testid="top-exposure-row">
            <span className="te-name">{r.name}<small>{r.limit_type ? r.limit_type.replace("_", " ").toLowerCase() : "no limit on file"}</small></span>
            <span className="te-bar" role="img" aria-label={r.utilisation_pct === null ? "No limit utilisation" : `Utilisation ${r.utilisation_pct}% of limit`}>
              <i style={{ width: `${Math.min(100, r.utilisation_pct ?? 0)}%`, background: (r.utilisation_pct ?? 0) >= 100 ? "var(--crit)" : (r.utilisation_pct ?? 0) >= 85 ? "var(--high)" : "var(--low)" }} /><b className="m85" /><b className="m100" />
            </span>
            <span className="te-num" title={r.utilisation_pct === null ? "Unavailable: no limit on file" : undefined}>{r.utilisation_pct === null ? "n/a" : pct(r.utilisation_pct, 1)}</span>
            <span className="te-rating" title={r.rating ? `Rating ${r.rating}` : "No rating is recorded"}>{r.rating ?? "—"}{r.outlook === "negative" ? "↓" : ""}</span>
            <span className="te-num" title="Change in potential future exposure since the previous snapshot ($mm)">{r.delta_pfe === null ? "n/a" : signed(r.delta_pfe)}</span>
            <SeverityPill level={severityOf(r.priority)} />
          </Link>
        </li>
      ))}
    </ol>
  );
}

export function StressHeatmap({ data, onCell }: { data: { scenarios: { id: string; label: string }[]; rows: { id: string; name: string; values: number[] }[]; index_label: string }; onCell: (scenarioId: string) => void }) {
  const color = (v: number) => (v <= 0 ? "transparent" : `color-mix(in srgb, ${v >= 0.66 ? "var(--crit)" : v >= 0.33 ? "var(--high)" : "var(--accent)"} ${Math.round(18 + 62 * v)}%, transparent)`);
  return (
    <>
      <div className="hm-wrap">
        <table className="hm" aria-label="Propagation index by counterparty and scenario">
          <thead><tr><th scope="col" /><>{data.scenarios.map((s) => <th key={s.id} scope="col" title={s.label}><span>{s.label}</span></th>)}</></tr></thead>
          <tbody>{data.rows.map((r) => (
            <tr key={r.id}><th scope="row">{r.name}</th>{r.values.map((v, i) => <td key={i}><button type="button" className="hm-cell" style={{ background: color(v) }} title={`${r.name} · ${data.scenarios[i].label}: ${v.toFixed(2)}`} aria-label={`${r.name}, ${data.scenarios[i].label}: index ${v.toFixed(2)}. Open in Stress`} onClick={() => onCell(data.scenarios[i].id)}>{v > 0 ? v.toFixed(2) : "·"}</button></td>)}</tr>
          ))}</tbody>
        </table>
      </div>
      <p className="tp-note"><ProvenanceBadge kind="derived" /> {data.index_label}</p>
    </>
  );
}

interface Ev { id: string; title: string; date: string; category: string | null; badge: string | null; source: string | null; reaches: { id: string; name: string; hops: number; via: string }[] }
export function MarketEvents({ rows }: { rows: Ev[] }) {
  if (rows.length === 0) return <EmptyState title="No events on or before this date" />;
  return (
    <ul className="me-list">
      {rows.map((e) => (
        <li key={e.id}>
          <div className="me-top"><span className="me-dot" title="Severity is not rated in this data" aria-label="Severity not rated" /><span className="me-date">{niceDate(e.date)}</span><span className="me-cat">{e.category?.replace(/_/g, " ").toLowerCase()}</span>
            {e.badge && <span className={`me-badge me-${e.badge.toLowerCase()}`} title={e.badge === "Verified" ? "Quoted text and date confirmed in an approved source" : e.badge === "Sample" ? "Synthetic sample item" : "Public headline, not verified by retrieval"}>{e.badge}</span>}</div>
          <p className="me-title">{e.title}</p>
          {e.reaches.length > 0 && <div className="reach-row"><span className="tp-note">Reaches</span>{e.reaches.slice(0, 4).map((r) => <Link key={r.id} className="u-chip" to={`/cp/${encodeURIComponent(r.id)}`} title={r.hops === 0 ? `exposure to ${r.via}` : `one supply step from ${r.via}`}>{r.name}</Link>)}{e.reaches.length > 4 && <span className="tp-note">+{e.reaches.length - 4}</span>}</div>}
        </li>
      ))}
    </ul>
  );
}

export function Concentration({ data }: { data: { sectors: string[]; rows: { id: string; name: string; values: number[] }[]; unit: string; universe: string } }) {
  const max = Math.max(1, ...data.rows.flatMap((r) => r.values));
  return (
    <>
      <div className="hm-wrap">
        <table className="hm" aria-label="Exposure by counterparty and sector">
          <thead><tr><th scope="col" />{data.sectors.map((s) => <th key={s} scope="col" title={s}><span>{s}</span></th>)}</tr></thead>
          <tbody>{data.rows.map((r) => <tr key={r.id}><th scope="row"><Link to={`/cp/${encodeURIComponent(r.id)}`}>{r.name}</Link></th>{r.values.map((v, i) => <td key={i}><span className="hm-cell static" style={{ background: v > 0 ? `color-mix(in srgb, var(--accent) ${Math.round(14 + 66 * (v / max))}%, transparent)` : "transparent" }} title={`${r.name} · ${data.sectors[i]}: ${v}%`}>{v > 0 ? v.toFixed(0) : "·"}</span></td>)}</tr>)}</tbody>
        </table>
      </div>
      <p className="tp-note"><ProvenanceBadge kind="synthetic" /> {data.unit}. Rows: {data.universe}.</p>
    </>
  );
}

export function RatingsFlags({ data }: { data: { available: boolean; reason: string; flags: Record<string, number | null> } }) {
  const f = data.flags;
  return (
    <>
      {!data.available && <EmptyState title="No rating ladder" hint={data.reason} />}
      <ul className="flag-list">
        {([["wwr", "Wrong-way risk"], ["overdue", "Overdue breach"], ["near_limit", "Near limit (85% or more)"], ["watchlist", "On a watchlist"], ["negative_outlook", "Negative outlook"]] as const).map(([k, label]) => <li key={k}><span>{label}</span><b>{f[k] === null ? "Unavailable" : f[k]}</b></li>)}
      </ul>
    </>
  );
}

const STATUS: Record<string, string> = { ok: "On time", stale: "Stale", unknown: "Unknown" };
export function DataHealth({ asOf }: { asOf: string }) {
  const src = useSources(asOf), mod = useModels(), pipe = usePipeline();
  return (
    <div className="dh">
      <div><h3 className="u-sec">Pipeline</h3>
        {pipe.isLoading ? <Skeleton lines={2} /> : pipe.data?.available ? <ul className="flag-list">{pipe.data.stages.map((s: { id: string; label: string; state: string }) => <li key={s.id}><span>{s.label}</span><b>{s.state}</b></li>)}</ul> : <p className="tp-note" data-testid="pipeline-unavailable">Unavailable. {pipe.data?.reason}{" "}<Link to="/admin/studio">Open the Studio</Link></p>}
      </div>
      <div><h3 className="u-sec">Source freshness</h3>
        {src.isLoading ? <Skeleton lines={4} /> : src.isError ? <ErrorState message={(src.error as Error).message} onRetry={() => src.refetch()} /> : (
          <>
            <ul className="fresh">{src.data.sources.map((s: { id: string; label: string; last_data: string | null; age_days: number | null; sla_days: number; status: string }) => (
              <li key={s.id} className={`fr-${s.status}`}><span>{s.label}</span><b>{s.last_data ? niceDate(s.last_data) : "no date"}</b><span className="fr-s">{STATUS[s.status]}{s.age_days !== null ? ` · ${s.age_days} d old, target ${s.sla_days} d` : ""}</span></li>))}</ul>
            <p className="tp-note">{src.data.stale} of {src.data.sources.length} sources are stale against their targets. {src.data.sla_note}</p>
          </>)}
      </div>
      <div><h3 className="u-sec">Models and AI</h3>
        {mod.isLoading ? <Skeleton lines={3} /> : mod.isError ? <ErrorState message={(mod.error as Error).message} onRetry={() => mod.refetch()} /> : (
          <>
            <ul className="flag-list">{mod.data.providers.map((p: { id: string; label: string; status: string; model: string | null }) => <li key={p.id}><span>{p.label}{p.model ? ` · ${p.model}` : ""}</span><b>{p.status}</b></li>)}</ul>
            <p className="tp-note" data-testid="usage-unavailable">Token use, p95 latency and error rate: Unavailable. {mod.data.usage.reason}</p>
          </>)}
      </div>
    </div>
  );
}
