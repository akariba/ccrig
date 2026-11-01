// Shell-level state: the watchlist and the as-of date. Both are mirrored into the URL (`wl`, `asof`) when they differ from
// the defaults so a shared link carries them, and kept in localStorage so they survive a visit without the parameter.
// Defaults: watchlist = the 10 highest-priority CCR counterparties; as-of = the latest data date ("latest", not a date).
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { usePriorityQueue } from "../api/query";

const WL_KEY = "ccrig.watchlist", ASOF_KEY = "ccrig.asof";
const DEFAULT_WATCHLIST_SIZE = 10;

function load(key: string): string | null { try { return localStorage.getItem(key); } catch { return null; } }
function save(key: string, value: string | null) { try { if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value); } catch { /* per-viewer convenience only */ } }
const ID = /^[A-Za-z0-9_.-]{1,64}$/;
const parseIds = (raw: string | null): string[] | null => { if (!raw) return null; const ids = raw.split(",").map((s) => s.trim()).filter((s) => ID.test(s)); return ids.length ? ids : null; };
const parseAsOf = (raw: string | null): string | null => (raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) && !Number.isNaN(Date.parse(raw)) ? raw : null);

export interface QueueRow { id: string; name: string; priority: string; counterparty_type?: string }
interface Shell {
  watchlist: string[]; customWatchlist: boolean; setWatchlist: (ids: string[] | null) => void;
  asOf: string | null; setAsOf: (d: string | null) => void;
  queue: QueueRow[]; queueLoading: boolean;
}
const Ctx = createContext<Shell | null>(null);

export function ShellProvider({ children }: { children: React.ReactNode }) {
  const loc = useLocation(), nav = useNavigate();
  const q = usePriorityQueue();
  const queue: QueueRow[] = useMemo(() => (q.data?.results ?? []).map((r: QueueRow) => ({ id: r.id, name: r.name, priority: r.priority, counterparty_type: r.counterparty_type })), [q.data]);
  const [custom, setCustom] = useState<string[] | null>(() => parseIds(new URLSearchParams(window.location.search).get("wl")) ?? parseIds(load(WL_KEY)));
  const [asOf, setAsOfState] = useState<string | null>(() => parseAsOf(new URLSearchParams(window.location.search).get("asof")) ?? parseAsOf(load(ASOF_KEY)));
  const watchlist = useMemo(() => custom ?? queue.slice(0, DEFAULT_WATCHLIST_SIZE).map((r) => r.id), [custom, queue]);

  const setWatchlist = useCallback((ids: string[] | null) => { setCustom(ids && ids.length ? ids : null); save(WL_KEY, ids && ids.length ? ids.join(",") : null); }, []);
  const setAsOf = useCallback((d: string | null) => { setAsOfState(d); save(ASOF_KEY, d); }, []);

  // Mirror into the URL: add the parameters when they are customised, remove them when they are back at the default. Replace, never push.
  const wlParam = custom?.join(",") ?? null, lastSearch = useRef(loc.search);
  useEffect(() => {
    const params = new URLSearchParams(loc.search);
    const want = (k: string, v: string | null) => { if (v === null) { if (params.has(k)) { params.delete(k); return true; } return false; } if (params.get(k) !== v) { params.set(k, v); return true; } return false; };
    const changed = [want("wl", wlParam), want("asof", asOf)].some(Boolean);
    if (changed && lastSearch.current !== `?${params}`) { lastSearch.current = `?${params}`; nav({ pathname: loc.pathname, search: params.toString() ? `?${params}` : "" , hash: loc.hash }, { replace: true }); }
  }, [loc.pathname, loc.search, loc.hash, wlParam, asOf, nav]);
  useEffect(() => { lastSearch.current = loc.search; }, [loc.search]);

  const value = useMemo<Shell>(() => ({ watchlist, customWatchlist: custom !== null, setWatchlist, asOf, setAsOf, queue, queueLoading: q.isLoading }), [watchlist, custom, setWatchlist, asOf, setAsOf, queue, q.isLoading]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useShell(): Shell {
  const v = useContext(Ctx);
  if (!v) throw new Error("useShell must be used inside ShellProvider");
  return v;
}
