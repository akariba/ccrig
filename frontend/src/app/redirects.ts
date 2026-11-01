// Old routes -> their new home, with the old parameters carried across. Pure (no router import) so every mapping is tested.
// The legacy pages still read the same parameter names, so most of them travel unchanged; only the id of a counterparty or an
// issuer moves from the query string into the path.
export interface Redirect { pathname: string; search: string }

const TAB_ROUTES: Record<string, { to: string; tab?: string }> = {
  "/inbox": { to: "/", tab: "inbox" },
  "/exposure-movers": { to: "/", tab: "movers" },
  "/breaches": { to: "/", tab: "controls" },
  "/graph": { to: "/network", tab: "graph" },
  "/distance-map": { to: "/network", tab: "distance" },
  "/event-studio": { to: "/events", tab: "analyse" },
  "/event-impact-map": { to: "/events", tab: "map" },
  "/theme-radar": { to: "/events", tab: "themes" },
  "/model-lab": { to: "/models", tab: "weights" },
  "/backtest-lab": { to: "/models", tab: "backtest" },
};
const ADMIN_ROUTES: Record<string, string> = { "/provenance": "/admin/sources", "/data-studio": "/admin/studio", "/ingest-bench": "/admin/ingest" };

export function isOldRoute(pathname: string): boolean {
  const p = trim(pathname);
  return p in TAB_ROUTES || p in ADMIN_ROUTES || p === "/counterparty" || p === "/entity";
}

const trim = (p: string) => (p.length > 1 ? p.replace(/\/+$/, "") : p);

export function redirectFor(pathname: string, search: string): Redirect | null {
  const p = trim(pathname), params = new URLSearchParams(search);
  if (p === "/counterparty" || p === "/entity") {
    const id = params.get("id"), base = p === "/counterparty" ? "/cp" : "/issuer";
    params.delete("id");
    return { pathname: id ? `${base}/${encodeURIComponent(id)}` : base, search: params.toString() ? `?${params}` : "" };
  }
  if (p in ADMIN_ROUTES) return { pathname: ADMIN_ROUTES[p], search: search && search !== "?" ? search : "" };
  const t = TAB_ROUTES[p];
  if (t) { if (t.tab && !params.has("tab")) params.set("tab", t.tab); return { pathname: t.to, search: params.toString() ? `?${params}` : "" }; }
  return null;
}
