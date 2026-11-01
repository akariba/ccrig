import { useMemo } from "react";
import { SEVERITY, type Severity } from "./channels";

export interface TimelineItem { id: string; at: string; lane: string; label: string; severity?: Severity }
/** Dated items on named lanes (for example direct news and news via linked names). An ordered list below carries the same content for screen readers. */
export function Timeline({ items, lanes, onSelect, label }: { items: TimelineItem[]; lanes: string[]; onSelect?: (id: string) => void; label: string }) {
  const model = useMemo(() => {
    const times = items.map((i) => Date.parse(i.at)).filter(Number.isFinite);
    if (times.length === 0) return null;
    const lo = Math.min(...times), hi = Math.max(...times), span = hi - lo || 1;
    return { lo, hi, x: (t: number) => 6 + ((t - lo) / span) * 88 };
  }, [items]);
  if (!model) return <p className="u-muted">No dated items.</p>;
  const laneH = 44, W = 100, H = lanes.length * laneH + 22;
  const sorted = [...items].sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  return (
    <figure className="u-timeline">
      <svg viewBox={`0 0 ${W * 10} ${H}`} role="group" aria-label={label} preserveAspectRatio="none" className="u-tl-svg" style={{ height: H }}>
        {lanes.map((l, i) => <g key={l}><line x1={0} x2={W * 10} y1={i * laneH + laneH / 2} y2={i * laneH + laneH / 2} stroke="var(--border)" /><text x={4} y={i * laneH + 12} fontSize="12" fill="var(--text-3)">{l}</text></g>)}
        {sorted.map((it) => {
          const lane = Math.max(0, lanes.indexOf(it.lane)), cx = model.x(Date.parse(it.at)) * 10, cy = lane * laneH + laneH / 2 + 4, sev = it.severity ?? "info";
          return (
            <g key={it.id} tabIndex={onSelect ? 0 : undefined} role={onSelect ? "button" : undefined} aria-label={`${it.at.slice(0, 10)}: ${it.label} (${SEVERITY[sev].label})`} className="u-tl-dot" onClick={() => onSelect?.(it.id)}
              onKeyDown={(e) => { if (onSelect && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onSelect(it.id); } }}>
              <circle cx={cx} cy={cy} r={7} fill={`var(--${sev}-bg, var(--surface))`} stroke={`var(--${sev === "info" ? "accent" : sev})`} strokeWidth={2} /><title>{`${it.at.slice(0, 10)} · ${it.label}`}</title>
            </g>
          );
        })}
        <text x={4} y={H - 4} fontSize="12" fill="var(--text-3)">{new Date(model.lo).toISOString().slice(0, 10)}</text><text x={W * 10 - 4} y={H - 4} fontSize="12" textAnchor="end" fill="var(--text-3)">{new Date(model.hi).toISOString().slice(0, 10)}</text>
      </svg>
      <ol className="u-sr">{sorted.map((it) => <li key={it.id}>{it.at.slice(0, 10)} · {it.lane} · {it.label}</li>)}</ol>
    </figure>
  );
}
