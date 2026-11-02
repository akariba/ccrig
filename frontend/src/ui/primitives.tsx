import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { CHANNELS, PROVENANCE, SEVERITY, type Channel, type Provenance, type Severity } from "./channels";

/** Severity is never colour alone: a glyph and the word travel with it. */
export function SeverityPill({ level, label }: { level: Severity; label?: string }) {
  const s = SEVERITY[level];
  return <span className={`u-sev u-sev-${level}`}><span aria-hidden="true">{s.glyph}</span> {label ?? s.label}</span>;
}

export function ChannelChip({ channel, title }: { channel: Channel; title?: string }) {
  const c = CHANNELS[channel];
  return (
    <span className="u-chan" title={title ?? c.desc} style={{ ["--c" as string]: `var(${c.cssVar})` }}>
      <svg width="22" height="8" aria-hidden="true"><line x1="1" y1="4" x2="21" y2="4" stroke="var(--c)" strokeWidth="2.4" strokeDasharray={c.dash || undefined} strokeLinecap="round" /></svg>{c.label}
    </span>
  );
}

/** Every number carries one. The badge links to the source registry. */
export function ProvenanceBadge({ kind, label }: { kind: Provenance; label?: string }) {
  const p = PROVENANCE[kind];
  return <Link className={`u-prov u-prov-${kind}`} to="/admin/sources" title={`${p.code}: see where this comes from`}>{label ?? p.label}</Link>;
}

export function Sparkline({ values, width = 84, height = 24, label }: { values: number[]; width?: number; height?: number; label?: string }) {
  const v = values.filter((x) => Number.isFinite(x));
  if (v.length < 2) return null;
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
  const pts = v.map((y, i) => `${((i / (v.length - 1)) * (width - 2) + 1).toFixed(1)},${(height - 2 - ((y - lo) / span) * (height - 4)).toFixed(1)}`).join(" ");
  return <svg width={width} height={height} role="img" aria-label={label ?? `Trend over ${v.length} points, from ${v[0]} to ${v[v.length - 1]}`} className="u-spark"><polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" /></svg>;
}

export interface KpiProps { label: string; value: ReactNode; unit?: string; delta?: number | null; deltaUnit?: string; goodWhen?: "down" | "up"; spark?: number[]; note?: ReactNode; onClick?: () => void; provenance?: Provenance }
export function KpiTile({ label, value, unit, delta, deltaUnit, goodWhen = "down", spark, note, onClick, provenance }: KpiProps) {
  const dir = delta === null || delta === undefined || delta === 0 ? "flat" : delta > 0 ? "up" : "down";
  const good = dir === "flat" ? null : (goodWhen === "down") === (dir === "down");
  const body = (
    <>
      <span className="u-kpi-label">{label}</span>
      <span className={`u-kpi-value${typeof value === "string" && !/^[-+\d.,%$ ]/.test(value) ? " text" : ""}`}>{value}{unit && <span className="u-kpi-unit"> {unit}</span>}</span>
      <span className="u-kpi-foot">
        {delta !== null && delta !== undefined && <span className={`u-delta ${good === null ? "" : good ? "good" : "bad"}`} aria-label={`${dir === "flat" ? "unchanged" : dir === "up" ? "up" : "down"} ${Math.abs(delta)}${deltaUnit ?? ""} versus the previous date`}>{dir === "up" ? "▲" : dir === "down" ? "▼" : "■"} {Math.abs(delta)}{deltaUnit}</span>}
        {spark && <Sparkline values={spark} />}
        {note && <span className="u-kpi-note">{note}</span>}
        {provenance && <ProvenanceBadge kind={provenance} />}
      </span>
    </>
  );
  return onClick ? <button type="button" className="u-kpi u-kpi-btn" onClick={onClick}>{body}</button> : <div className="u-kpi">{body}</div>;
}

export function Skeleton({ lines = 3, height = 14 }: { lines?: number; height?: number }) {
  return <div className="u-skel" role="status" aria-label="Loading">{Array.from({ length: lines }, (_, i) => <span key={i} style={{ height, width: `${100 - ((i * 17) % 40)}%` }} />)}</div>;
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return <div className="u-empty"><strong>{title}</strong>{hint && <p>{hint}</p>}{action}</div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="u-error" role="alert"><strong>Something went wrong</strong><p>{message}</p>{onRetry && <button type="button" className="btn secondary" onClick={onRetry}>Retry</button>}</div>;
}

export function FilterBar({ children, onClear, active }: { children: ReactNode; onClear?: () => void; active?: boolean }) {
  return <div className="u-filterbar" role="group" aria-label="Filters">{children}{onClear && active && <button type="button" className="u-link" onClick={onClear}>Clear filters</button>}</div>;
}

export interface TabDef { id: string; label: string; count?: number }
/** Accessible tablist: arrow keys, Home and End move between tabs; the active tab is the URL's, supplied by the caller. */
export function Tabs({ tabs, value, onChange, label }: { tabs: TabDef[]; value: string; onChange: (id: string) => void; label: string }) {
  const base = useId(), refs = useRef<(HTMLButtonElement | null)[]>([]);
  const move = (e: KeyboardEvent, i: number) => {
    const n = tabs.length; let j = i;
    if (e.key === "ArrowRight") j = (i + 1) % n; else if (e.key === "ArrowLeft") j = (i - 1 + n) % n; else if (e.key === "Home") j = 0; else if (e.key === "End") j = n - 1; else return;
    e.preventDefault(); onChange(tabs[j].id); refs.current[j]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className="u-tabs">
      {tabs.map((t, i) => (
        <button key={t.id} ref={(el) => { refs.current[i] = el; }} role="tab" type="button" id={`${base}-${t.id}`} aria-selected={t.id === value} tabIndex={t.id === value ? 0 : -1}
          className={`u-tab${t.id === value ? " on" : ""}`} onClick={() => onChange(t.id)} onKeyDown={(e) => move(e, i)}>{t.label}{t.count !== undefined && <span className="u-tab-count">{t.count}</span>}</button>
      ))}
    </div>
  );
}
