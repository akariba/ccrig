import { Suspense, useCallback, type ComponentType, type LazyExoticComponent } from "react";
import { useSearchParams } from "react-router-dom";
import { Skeleton, Tabs } from "../ui/primitives";

export interface HostTab { id: string; label: string; Page: LazyExoticComponent<ComponentType> | ComponentType }
/** A workspace made of tabs. The tab is in the URL (`?tab=`), so a tab is a shareable link and survives a reload. */
export function TabHost({ title, blurb, tabs, label }: { title: string; blurb: string; tabs: HostTab[]; label: string }) {
  const [params, setParams] = useSearchParams();
  const active = tabs.find((t) => t.id === params.get("tab")) ?? tabs[0];
  // each tab starts clean: only the shell's own parameters (watchlist, as-of) travel with the switch
  const choose = useCallback((id: string) => { const next = new URLSearchParams(); for (const k of ["wl", "asof"]) { const v = params.get(k); if (v) next.set(k, v); } if (id !== tabs[0].id) next.set("tab", id); setParams(next, { replace: false }); }, [params, setParams, tabs]);
  const Page = active.Page;
  return (
    <div className="u-host">
      <div className="u-host-head">
        <h1>{title}</h1><p className="u-muted">{blurb}</p>
        <Tabs tabs={tabs.map((t) => ({ id: t.id, label: t.label }))} value={active.id} onChange={choose} label={label} />
      </div>
      <div role="tabpanel" aria-label={active.label} className="u-host-body"><Suspense fallback={<Skeleton lines={6} />}><Page /></Suspense></div>
    </div>
  );
}
