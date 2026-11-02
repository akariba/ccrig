import { useEffect, useRef, useState } from "react";
import { readThemeMode, setThemeMode, type ThemeMode } from "../design/theme";
import { useHealth } from "../api/query";
import { describeBackendStatus, type BackendHealth } from "../components/healthStatus";
import { useShell } from "../app/ShellContext";
import { Icon } from "./Icon";
import { useInspector } from "./InspectorDrawer";
import { SeverityPill } from "./primitives";
import { severityOf } from "./channels";

const MODES: { id: ThemeMode; label: string; icon: string }[] = [{ id: "system", label: "System", icon: "monitor" }, { id: "light", label: "Light", icon: "sun" }, { id: "dark", label: "Dark", icon: "moon" }];

function ThemeToggle() {
  const [mode, setMode] = useState<ThemeMode>(readThemeMode);
  return (
    <div className="u-seg" role="group" aria-label="Colour theme">
      {MODES.map((m) => <button key={m.id} type="button" aria-pressed={mode === m.id} title={`${m.label} theme`} onClick={() => { setMode(m.id); setThemeMode(m.id); }}><Icon name={m.icon} size={16} /><span className="u-sr">{m.label}</span></button>)}
    </div>
  );
}

function WatchlistEditor({ onClose }: { onClose: () => void }) {
  const { watchlist, setWatchlist, queue } = useShell();
  const [draft, setDraft] = useState(new Set(watchlist)), ref = useRef<HTMLDivElement>(null);
  useEffect(() => { const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose(); }; const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); }; document.addEventListener("mousedown", h); document.addEventListener("keydown", k); return () => { document.removeEventListener("mousedown", h); document.removeEventListener("keydown", k); }; }, [onClose]);
  return (
    <div className="u-pop" ref={ref} role="dialog" aria-label="Edit watchlist">
      <p className="u-muted">The watchlist drives Today, Events & News and Stress. Default: the 10 highest-priority counterparties.</p>
      <div className="u-pop-list">
        {queue.map((r) => <label key={r.id}><input type="checkbox" checked={draft.has(r.id)} onChange={(e) => setDraft((d) => { const n = new Set(d); if (e.target.checked) n.add(r.id); else n.delete(r.id); return n; })} /> <span>{r.name}</span> <SeverityPill level={severityOf(r.priority)} /></label>)}
      </div>
      <div className="u-row"><button type="button" className="btn" onClick={() => { setWatchlist([...draft]); onClose(); }}>Apply</button><button type="button" className="btn secondary" onClick={() => { setWatchlist(null); onClose(); }}>Reset to top 10</button></div>
    </div>
  );
}

export function TopBar({ onSearch }: { onSearch: () => void }) {
  const { watchlist, asOf, setAsOf, queue, customWatchlist } = useShell();
  const insp = useInspector(), health = useHealth(), [edit, setEdit] = useState(false);
  const h: BackendHealth = health.isError ? { unreachable: true } : health.data ?? null;
  const status = describeBackendStatus(h), ai = h && !("unreachable" in h) && h.ai_enabled;
  const names = watchlist.map((id) => queue.find((r) => r.id === id)).filter((r): r is NonNullable<typeof r> => !!r);
  const mac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
  return (
    <header className="u-topbar">
      <button type="button" className="u-search-btn" onClick={onSearch} aria-label="Search names, themes and pages (shortcut: Command or Control plus K)"><Icon name="search" size={16} /><span>Search names, themes, pages…</span><kbd>{mac ? "⌘K" : "Ctrl K"}</kbd></button>
      <div className="u-watch" aria-label="Watchlist">
        <span className="u-label">Watchlist{customWatchlist ? " (custom)" : ""}</span>
        <ul className="u-chips">{names.slice(0, 2).map((r) => <li key={r.id}><button type="button" className="u-chip" onClick={() => insp.openEntity("counterparty", r.id, r.name)} title={r.name}>{r.name}</button></li>)}</ul>
        <button type="button" className="u-chip u-chip-more" aria-expanded={edit} aria-haspopup="dialog" onClick={() => setEdit((v) => !v)}>{names.length > 2 ? `+${names.length - 2} · ` : ""}{names.length} names · edit</button>
        {edit && <WatchlistEditor onClose={() => setEdit(false)} />}
      </div>
      <span className="u-spacer" />
      <label className="u-asof"><span className="u-label">As of</span><input type="date" value={asOf ?? ""} onChange={(e) => setAsOf(e.target.value || null)} aria-label="As-of date (empty means the latest data date)" title="Empty = latest data date. Pages adopt the as-of date as the data model gains history." /></label>
      <ThemeToggle />
      <div className={`u-status u-status-${status.tone}`} title={status.detail}><span className="u-dot" aria-hidden="true" />{ai ? "AI-assisted" : "Deterministic"}<span className="u-status-sub"> · {status.tone === "error" ? "backend unreachable" : status.tone === "pending" ? "connecting" : "backend OK"}</span></div>
    </header>
  );
}
