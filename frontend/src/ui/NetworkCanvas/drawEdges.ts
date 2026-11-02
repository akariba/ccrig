// Edges: curved, channel-coloured, width by strength, opacity by confidence. Particles travel only along directed channels and only in the stored
// direction; derived channels shimmer as dashes. Parallel links between the same pair fan out; self-loops never exist.
import { CHANNELS, type Channel } from "../channels";
import { quadPoint } from "./hitTest";
import type { GEdge, Palette, Pt } from "./types";

export const MOVING: ReadonlySet<Channel> = new Set<Channel>(["ownership", "exposure", "supply"]);
export const DERIVED: ReadonlySet<Channel> = new Set<Channel>(["shared", "comovement", "hidden"]);

/** One edge per (unordered pair, channel, relation): the strongest wins; self-loops are dropped. */
export function mergeParallel(edges: GEdge[]): GEdge[] {
  const best = new Map<string, GEdge>();
  for (const e of edges) {
    if (e.source === e.target) continue;
    const [a, b] = e.directed ? [e.source, e.target] : [e.source, e.target].sort(), key = `${a}|${b}|${e.channel}|${e.relation ?? ""}`, old = best.get(key);
    if (!old || (e.strength ?? 0) > (old.strength ?? 0)) best.set(key, e);
  }
  return [...best.values()].sort((a, b) => a.id.localeCompare(b.id));
}

/** Position of an edge among the edges that join the same two nodes: 0..count-1, so that they can be drawn with different curvature. */
export function parallelIndex(edges: GEdge[]): Map<string, { index: number; count: number }> {
  const groups = new Map<string, GEdge[]>();
  for (const e of edges) { const k = [e.source, e.target].sort().join("|"); (groups.get(k) ?? groups.set(k, []).get(k)!).push(e); }
  const out = new Map<string, { index: number; count: number }>();
  for (const g of groups.values()) g.forEach((e, i) => out.set(e.id, { index: i, count: g.length }));
  return out;
}

/** Quadratic control point: a gentle bow (so edges never overlap their nodes' straight line), more for parallel edges. */
export function controlPoint(a: Pt, b: Pt, index = 0, count = 1): Pt {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
  const off = (0.12 + (index - (count - 1) / 2) * 0.16) * len, sign = a.x + a.y <= b.x + b.y ? 1 : -1;
  return { x: mx - (dy / len) * off * sign, y: my + (dx / len) * off * sign };
}

export const edgeWidth = (e: Pick<GEdge, "strength">): number => 0.8 + 3.2 * Math.max(0, Math.min(1, e.strength ?? 0.4));
export const edgeOpacity = (e: Pick<GEdge, "confidence">): number => 0.25 + 0.65 * Math.max(0, Math.min(1, e.confidence ?? 0.7));
export const showsArrow = (e: GEdge): boolean => e.directed && (e.strength ?? 0) >= 0.5;

export function particleAt(e: GEdge, a: Pt, c: Pt, b: Pt, timeMs: number, i: number): Pt | null {
  if (!e.directed || !MOVING.has(e.channel)) return null;
  let h = 0; for (const ch of e.id) h = (h * 33 + ch.charCodeAt(0)) >>> 0;
  const t = (((timeMs / 1000) * 0.22 + (h % 997) / 997 + i * 0.5) % 1 + 1) % 1;
  return quadPoint(a, c, b, t);
}

export interface EdgeDraw { e: GEdge; a: Pt; c: Pt; b: Pt; dim: boolean; time: number; reduced: boolean; selected: boolean; k: number }
export function drawEdge(x: CanvasRenderingContext2D, d: EdgeDraw, p: Palette): void {
  const color = p.channel[d.e.channel], dash = CHANNELS[d.e.channel].dash;
  x.save(); x.globalAlpha = d.dim ? 0.07 : edgeOpacity(d.e) * (d.selected ? 1 : 0.85); x.strokeStyle = color; x.lineWidth = edgeWidth(d.e) + (d.selected ? 1.2 : 0); x.lineCap = "round";
  if (DERIVED.has(d.e.channel)) { x.setLineDash([6, 5]); x.lineDashOffset = d.reduced ? 0 : -(d.time / 90) % 11; } else if (dash && d.e.channel === "exposure") x.setLineDash([1, 5]); else x.setLineDash([]);
  x.beginPath(); x.moveTo(d.a.x, d.a.y); x.quadraticCurveTo(d.c.x, d.c.y, d.b.x, d.b.y); x.stroke(); x.setLineDash([]);
  if (showsArrow(d.e) && !d.dim) { const m = quadPoint(d.a, d.c, d.b, 0.64), n = quadPoint(d.a, d.c, d.b, 0.68), ang = Math.atan2(n.y - m.y, n.x - m.x); x.fillStyle = color; x.globalAlpha = 0.9; x.beginPath(); x.moveTo(m.x + Math.cos(ang) * 6, m.y + Math.sin(ang) * 6); x.lineTo(m.x + Math.cos(ang + 2.5) * 5, m.y + Math.sin(ang + 2.5) * 5); x.lineTo(m.x + Math.cos(ang - 2.5) * 5, m.y + Math.sin(ang - 2.5) * 5); x.closePath(); x.fill(); }
  if (!d.reduced && !d.dim) for (let i = 0; i < 2; i++) { const q = particleAt(d.e, d.a, d.c, d.b, d.time, i); if (q) { x.globalAlpha = 0.95; x.fillStyle = color; x.beginPath(); x.arc(q.x, q.y, 1.9, 0, Math.PI * 2); x.fill(); } }
  x.restore();
}
