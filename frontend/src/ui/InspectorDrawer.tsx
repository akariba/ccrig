import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useFocusTrap } from "./useFocusTrap";
import { Skeleton, ErrorState, SeverityPill } from "./primitives";
import { severityOf } from "./channels";

export interface InspectorContent { title: string; subtitle?: string; href?: string; badges?: ReactNode; facts?: [string, ReactNode][]; body?: ReactNode }
type Target = { kind: "counterparty" | "issuer"; id: string; name: string } | { kind: "custom"; content: InspectorContent };
interface Api { openEntity: (kind: "counterparty" | "issuer", id: string, name: string) => void; openCustom: (c: InspectorContent) => void; close: () => void }
const Ctx = createContext<Api | null>(null);

// eslint-disable-next-line react-refresh/only-export-components
export function useInspector(): Api { const v = useContext(Ctx); if (!v) throw new Error("useInspector must be used inside InspectorProvider"); return v; }

/** The shared summary drawer: clicking an entity, edge, event or alert anywhere opens it, and "Open full page" is the only thing that navigates. */
export function InspectorProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<Target | null>(null);
  const close = useCallback(() => setTarget(null), []);
  const value = useMemo<Api>(() => ({ openEntity: (kind, id, name) => setTarget({ kind, id, name }), openCustom: (content) => setTarget({ kind: "custom", content }), close }), [close]);
  return <Ctx.Provider value={value}>{children}{target && <Drawer target={target} onClose={close} />}</Ctx.Provider>;
}

function Drawer({ target, onClose }: { target: Target; onClose: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useFocusTrap(ref, true, onClose);
  return (
    <aside className="u-drawer" role="dialog" aria-modal="true" aria-label="Details" ref={ref} tabIndex={-1}>
      <button type="button" className="u-drawer-close" aria-label="Close details" data-autofocus onClick={onClose}>×</button>
      {target.kind === "custom" ? <Body content={target.content} /> : <EntityBrief kind={target.kind} id={target.id} name={target.name} />}
    </aside>
  );
}

function Body({ content }: { content: InspectorContent }) {
  return (
    <div className="u-drawer-body">
      <h2>{content.title}</h2>{content.subtitle && <p className="u-muted">{content.subtitle}</p>}{content.badges && <div className="u-row">{content.badges}</div>}
      {content.facts && <dl className="u-facts">{content.facts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v ?? "Unavailable"}</dd></div>)}</dl>}
      {content.body}
      {content.href && <Link className="btn" to={content.href}>Open full page</Link>}
    </div>
  );
}

/** A short summary from the endpoints that already exist; the full page keeps the detail. */
function EntityBrief({ kind, id, name }: { kind: "counterparty" | "issuer"; id: string; name: string }) {
  const q = useQuery({
    queryKey: ["brief", kind, id],
    queryFn: async () => {
      if (kind === "issuer") { const d = await api.entity360(id); return { title: d.header.name, subtitle: [d.header.sector, d.header.country].filter(Boolean).join(" · "), facts: [["Related names", String(d.relationship_summary.top_related.length)], ["Counterparties exposed", String(d.counterparties_exposed.length + (d.counterparty_materiality?.results?.length ?? 0))]] as [string, ReactNode][], href: `/issuer/${encodeURIComponent(id)}` }; }
      const r = await api.priorityDetail(id).catch(() => null);
      if (r) return { title: r.name, subtitle: r.legal_entity, badges: <SeverityPill level={severityOf(r.priority)} />, facts: [["Driver", r.driver], ["Product", r.product], ["Utilisation", r.utilisation_pct != null ? `${r.utilisation_pct}%` : null], ["Suggested action", r.decision?.decision]] as [string, ReactNode][], href: `/cp/${encodeURIComponent(id)}` };
      const p = await api.counterparty360(id);
      return { title: p.header.name, subtitle: p.header.industry, facts: [["Holdings", String(p.direct_holdings.length)], ["Profile", "Portfolio holdings only (partial profile)"]] as [string, ReactNode][], href: `/cp/${encodeURIComponent(id)}` };
    },
  });
  if (q.isLoading) return <div className="u-drawer-body"><h2>{name}</h2><Skeleton lines={5} /></div>;
  if (q.isError) return <div className="u-drawer-body"><h2>{name}</h2><ErrorState message={String((q.error as Error).message)} onRetry={() => q.refetch()} /></div>;
  return <Body content={q.data!} />;
}
