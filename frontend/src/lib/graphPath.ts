// Path finding over the links that are on screen (breadth-first, so the shortest route; ties by id so the answer never depends on input order).
export interface PathEdge { id: string; source: string; target: string }
/** The ordered node ids from `from` to `to`, and the edge between each pair; null when they are not connected. */
export function pathBetween(edges: PathEdge[], from: string, to: string): { nodes: string[]; edges: string[] } | null {
  if (from === to) return { nodes: [from], edges: [] };
  const adj = new Map<string, { to: string; edge: string }[]>();
  for (const e of [...edges].sort((a, b) => a.id.localeCompare(b.id))) { if (e.source === e.target) continue; (adj.get(e.source) ?? adj.set(e.source, []).get(e.source)!).push({ to: e.target, edge: e.id }); (adj.get(e.target) ?? adj.set(e.target, []).get(e.target)!).push({ to: e.source, edge: e.id }); }
  const prev = new Map<string, { from: string; edge: string }>(), q = [from], seen = new Set([from]);
  while (q.length) {
    const u = q.shift()!;
    for (const n of (adj.get(u) ?? []).sort((a, b) => a.to.localeCompare(b.to))) if (!seen.has(n.to)) { seen.add(n.to); prev.set(n.to, { from: u, edge: n.edge }); if (n.to === to) { q.length = 0; break; } q.push(n.to); }
  }
  if (!prev.has(to)) return null;
  const nodes = [to], es: string[] = []; let cur = to;
  while (cur !== from) { const p = prev.get(cur)!; es.unshift(p.edge); nodes.unshift(p.from); cur = p.from; }
  return { nodes, edges: es };
}

const KEY = "ccrig.link-reviews";
export type Review = { status: "confirmed"; at: string };
/** Link reviews are a per-viewer convenience kept in this browser only (no shared review store exists yet). */
export function loadReviews(): Record<string, Review> { try { const v = JSON.parse(localStorage.getItem(KEY) ?? "{}"); return v && typeof v === "object" ? v : {}; } catch { return {}; } }
export function saveReview(edgeId: string, on: boolean): Record<string, Review> {
  const all = loadReviews(); if (on) all[edgeId] = { status: "confirmed", at: new Date().toISOString() }; else delete all[edgeId];
  try { localStorage.setItem(KEY, JSON.stringify(all)); } catch { /* the choice then lasts for this page only */ }
  return all;
}
