// Deterministic layouts. Same graph, same seed, same positions: tests can pin them and a shared link looks the same everywhere.
import type { GEdge, GNode, Pt } from "./types";

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

export interface ForceOptions { width: number; height: number; iterations?: number; seed?: number; fixed?: Record<string, Pt>; clusters?: string[][] }

/** Fruchterman-Reingold with a grid cutoff for repulsion (near-linear, so thousands of nodes stay interactive) and a gentle pull of cluster members toward their centroid. */
export function forceLayout(nodes: GNode[], edges: GEdge[], o: ForceOptions): Record<string, Pt> {
  const n = nodes.length, pos: Record<string, Pt> = {};
  if (n === 0) return pos;
  const rnd = mulberry32(o.seed ?? 7), iters = o.iterations ?? (n > 800 ? 80 : n > 300 ? 160 : 260);
  const area = o.width * o.height, ideal = Math.min(Math.sqrt(area / n) * (n > 60 ? 0.95 : 0.6), 110), cell = ideal * 2.4;
  const ids = nodes.map((x) => x.id).sort();
  ids.forEach((id, i) => { const a = (i / n) * Math.PI * 2, r = Math.min(o.width, o.height) * (0.15 + 0.3 * rnd()); pos[id] = { x: o.width / 2 + Math.cos(a) * r, y: o.height / 2 + Math.sin(a) * r }; });
  for (const [id, p] of Object.entries(o.fixed ?? {})) if (pos[id]) pos[id] = { ...p };
  const index = new Map(ids.map((id, i) => [id, i]));
  const links = edges.filter((e) => index.has(e.source) && index.has(e.target) && e.source !== e.target);
  const memberCluster = new Map<string, number>();
  (o.clusters ?? []).forEach((c, ci) => c.forEach((m) => memberCluster.set(m, ci)));
  let temp = Math.min(o.width, o.height) / 8;
  for (let it = 0; it < iters; it++) {
    const dx = new Float64Array(n), dy = new Float64Array(n), grid = new Map<string, number[]>();
    ids.forEach((id, i) => { const p = pos[id], key = `${Math.floor(p.x / cell)},${Math.floor(p.y / cell)}`; (grid.get(key) ?? grid.set(key, []).get(key)!).push(i); });
    ids.forEach((id, i) => {
      const p = pos[id], gx = Math.floor(p.x / cell), gy = Math.floor(p.y / cell);
      for (let ox = -1; ox <= 1; ox++) for (let oy = -1; oy <= 1; oy++) for (const j of grid.get(`${gx + ox},${gy + oy}`) ?? []) {
        if (j <= i) continue;
        const q = pos[ids[j]]; let ex = p.x - q.x, ey = p.y - q.y, d2 = ex * ex + ey * ey;
        if (d2 < 0.01) { ex = rnd() - 0.5; ey = rnd() - 0.5; d2 = 0.5; }
        const d = Math.sqrt(d2), f = (ideal * ideal) / d / d;
        dx[i] += ex * f; dy[i] += ey * f; dx[j] -= ex * f; dy[j] -= ey * f;
      }
    });
    for (const e of links) {
      const i = index.get(e.source)!, j = index.get(e.target)!, a = pos[e.source], b = pos[e.target];
      const ex = a.x - b.x, ey = a.y - b.y, d = Math.max(0.1, Math.hypot(ex, ey)), w = 0.6 + (e.strength ?? 0.5), f = (d * d) / ideal * 0.02 * w / d;
      dx[i] -= ex * f; dy[i] -= ey * f; dx[j] += ex * f; dy[j] += ey * f;
    }
    if (memberCluster.size) {
      const sum = new Map<number, { x: number; y: number; n: number }>();
      for (const [id, c] of memberCluster) if (pos[id]) { const s = sum.get(c) ?? { x: 0, y: 0, n: 0 }; s.x += pos[id].x; s.y += pos[id].y; s.n++; sum.set(c, s); }
      for (const [id, c] of memberCluster) { const s = sum.get(c); if (s && pos[id]) { const i = index.get(id)!; dx[i] += (s.x / s.n - pos[id].x) * 0.05; dy[i] += (s.y / s.n - pos[id].y) * 0.05; } }
    }
    ids.forEach((id, i) => {
      if (o.fixed?.[id]) return;
      const p = pos[id]; dx[i] += (o.width / 2 - p.x) * 0.03; dy[i] += (o.height / 2 - p.y) * 0.03;
      const len = Math.hypot(dx[i], dy[i]) || 1, step = Math.min(len, temp);
      p.x += (dx[i] / len) * step; p.y += (dy[i] / len) * step;
      p.x = Math.max(24, Math.min(o.width - 24, p.x)); p.y = Math.max(24, Math.min(o.height - 24, p.y));
    });
    temp *= 0.985;
  }
  return pos;
}

export interface RadialResult { pos: Record<string, Pt>; hops: Record<string, number> }

/** Ego layout: the centre in the middle, ring 1 = direct links, ring 2 = second hop (anything further shares ring 3). Ring members are ordered by their parent's angle, so links stay short. */
export function radialEgo(nodes: GNode[], edges: GEdge[], centerId: string, o: { width: number; height: number }): RadialResult {
  const ids = new Set(nodes.map((x) => x.id)), adj = new Map<string, string[]>();
  for (const e of edges) { if (!ids.has(e.source) || !ids.has(e.target) || e.source === e.target) continue; (adj.get(e.source) ?? adj.set(e.source, []).get(e.source)!).push(e.target); (adj.get(e.target) ?? adj.set(e.target, []).get(e.target)!).push(e.source); }
  const hops: Record<string, number> = {}, parent: Record<string, string> = {};
  const root = ids.has(centerId) ? centerId : [...ids].sort()[0];
  if (!root) return { pos: {}, hops: {} };
  hops[root] = 0; let frontier = [root];
  while (frontier.length) {
    const next: string[] = [];
    for (const u of frontier) for (const v of [...(adj.get(u) ?? [])].sort()) if (!(v in hops)) { hops[v] = hops[u] + 1; parent[v] = u; next.push(v); }
    frontier = next;
  }
  for (const id of ids) if (!(id in hops)) hops[id] = 3;                 // unreachable nodes sit on the outer ring
  const cx = o.width / 2, cy = o.height / 2, R = Math.min(o.width, o.height) / 2 - 36, radii = [0, R * 0.42, R * 0.78, R * 1.0];
  const pos: Record<string, Pt> = { [root]: { x: cx, y: cy } }, angle: Record<string, number> = { [root]: 0 };
  for (let ring = 1; ring <= 3; ring++) {
    const members = [...ids].filter((id) => hops[id] === ring).sort((a, b) => (angle[parent[a]] ?? 0) - (angle[parent[b]] ?? 0) || a.localeCompare(b));
    members.forEach((id, i) => {
      const a = -Math.PI / 2 + (i / Math.max(1, members.length)) * Math.PI * 2 + (ring % 2 ? 0 : Math.PI / Math.max(2, members.length));
      angle[id] = a; pos[id] = { x: cx + Math.cos(a) * radii[ring], y: cy + Math.sin(a) * radii[ring] };
    });
  }
  return { pos, hops };
}
