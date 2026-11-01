import { useCallback, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { PAGES, ADMIN_PAGES } from "../app/pages";
import { looksLikeHeadline, search, type Entry, type EntryKind } from "../lib/searchIndex";
import { useOperatorMode, usePriorityQueue } from "../api/query";
import { useFocusTrap } from "./useFocusTrap";
import { Icon } from "./Icon";

const RECENT_KEY = "ccrig.recent-searches";
interface Recent { name: string; href: string; kind: EntryKind }
function loadRecent(): Recent[] { try { const v = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]"); return Array.isArray(v) ? v.slice(0, 6) : []; } catch { return []; } }
function saveRecent(r: Recent) { try { const next = [r, ...loadRecent().filter((x) => x.href !== r.href)].slice(0, 6); localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch { /* per-viewer convenience */ } }
const KIND_LABEL: Record<EntryKind, string> = { counterparty: "Counterparty", issuer: "Issuer", theme: "Theme", event: "Event", page: "Page" };

/** The search index: counterparties (CCR and portfolio), issuers, themes and pages. Loaded the first time the palette opens. */
// eslint-disable-next-line react-refresh/only-export-components
export function useEntries(enabled: boolean): Entry[] {
  const op = useOperatorMode();
  const queue = usePriorityQueue();
  const portfolio = useQuery({ queryKey: ["counterparties"], queryFn: () => api.listCounterparties(), enabled });
  const issuers = useQuery({ queryKey: ["issuers"], queryFn: () => api.listEntities({ limit: 1000 }), enabled });
  const themes = useQuery({ queryKey: ["themes"], queryFn: () => api.listThemes(), enabled });
  return useMemo(() => {
    const out: Entry[] = [];
    for (const p of [...PAGES, ...(op.data ? ADMIN_PAGES : [])]) out.push({ kind: "page", key: `page:${p.id}`, name: p.label, href: p.to, detail: p.blurb });
    const seen = new Set<string>();
    for (const r of queue.data?.results ?? []) { seen.add(r.id); out.push({ kind: "counterparty", key: `cp:${r.id}`, name: r.name, href: `/cp/${encodeURIComponent(r.id)}`, detail: [r.counterparty_type, r.priority?.toLowerCase()].filter(Boolean).join(" · "), aliases: [r.legal_entity, r.id].filter(Boolean) }); }
    for (const r of portfolio.data?.results ?? []) if (!seen.has(r.id)) out.push({ kind: "counterparty", key: `cp:${r.id}`, name: r.name, href: `/cp/${encodeURIComponent(r.id)}`, detail: [r.industry, r.country].filter(Boolean).join(" · "), aliases: [r.id] });
    for (const r of issuers.data?.results ?? []) out.push({ kind: "issuer", key: `is:${r.id}`, name: r.name, href: `/issuer/${encodeURIComponent(r.id)}`, detail: [r.sector, r.country].filter(Boolean).join(" · "), aliases: [r.ticker, r.id].filter(Boolean) });
    for (const t of themes.data?.results ?? []) out.push({ kind: "theme", key: `th:${t.theme_id}`, name: t.label, href: `/events?tab=themes&theme=${encodeURIComponent(t.theme_id)}`, detail: t.kind === "DISCOVERED_THEME" ? "discovered theme" : "curated theme" });
    return out;
  }, [op.data, queue.data, portfolio.data, issuers.data, themes.data]);
}

/** The index is built by the shell (not here), so typing re-renders only the list, never the data hooks. */
export function CommandPalette({ open, onClose, entries }: { open: boolean; onClose: () => void; entries: Entry[] }) {
  const nav = useNavigate(), ref = useRef<HTMLDivElement>(null), [q, setQ] = useState(""), [i, setI] = useState(0);
  const hits = useMemo(() => search(entries, q), [entries, q]);
  const headline = q.trim() && looksLikeHeadline(q, hits);
  const recent = useMemo(() => (open ? loadRecent() : []), [open]);       // read when it opens, not on every keystroke
  const rows: { key: string; name: string; detail?: string; kind: EntryKind | "analyse"; href: string }[] = useMemo(() => {
    if (!q.trim()) return recent.map((r) => ({ key: r.href, name: r.name, kind: r.kind, href: r.href, detail: "recent" }));
    const list = hits.map((h) => ({ key: h.key, name: h.name, detail: h.detail, kind: h.kind as EntryKind | "analyse", href: h.href }));
    if (headline) list.unshift({ key: "analyse", name: "Analyse as event", detail: q.trim(), kind: "analyse", href: `/events?tab=analyse&text=${encodeURIComponent(q.trim())}` });
    return list;
  }, [q, hits, headline, recent]);
  const close = useCallback(() => { setQ(""); setI(0); onClose(); }, [onClose]);
  useFocusTrap(ref, open, close);
  if (!open) return null;

  const go = (r: (typeof rows)[number]) => { if (r.kind !== "analyse") saveRecent({ name: r.name, href: r.href, kind: r.kind }); close(); nav(r.href); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setI((n) => Math.min(rows.length - 1, n + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setI((n) => Math.max(0, n - 1)); }
    else if (e.key === "Enter" && rows[i]) { e.preventDefault(); go(rows[i]); }
  };
  return (
    <div className="u-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
      <div className="u-palette" role="dialog" aria-modal="true" aria-label="Search" ref={ref} onKeyDown={onKey}>
        <div className="u-palette-in"><Icon name="search" />
          <input data-autofocus role="combobox" aria-expanded="true" aria-controls="palette-list" aria-activedescendant={rows[i] ? `pal-${i}` : undefined} aria-label="Search counterparties, issuers, themes and pages" placeholder="Search a name, a theme, a page — or paste a headline" value={q} onChange={(e) => { setQ(e.target.value); setI(0); }} />
          <kbd>esc</kbd></div>
        <ul id="palette-list" role="listbox" className="u-palette-list">
          {rows.length === 0 && <li className="u-palette-empty">{q.trim() ? "No match. Try fewer letters, or paste a longer headline to analyse it as an event." : "Type to search. Recent searches appear here."}</li>}
          {rows.map((r, n) => (
            <li key={r.key} id={`pal-${n}`} role="option" aria-selected={n === i} className={n === i ? "on" : ""} onMouseEnter={() => setI(n)} onMouseDown={(e) => { e.preventDefault(); go(r); }}>
              <span className={`u-kind u-kind-${r.kind}`}>{r.kind === "analyse" ? "Event" : KIND_LABEL[r.kind]}</span><span className="u-palette-name">{r.name}</span>{r.detail && <span className="u-palette-detail">{r.detail}</span>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
