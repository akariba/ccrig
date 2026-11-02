import type { Pt } from "./types";

export interface HitNode { id: string; at: Pt; radius: number }
/** The nearest node whose glyph (plus `pad` px of forgiveness) contains the point; nearer wins, so overlapping glyphs behave. */
export function hitNode(nodes: HitNode[], p: Pt, pad = 3): string | null {
  let best: string | null = null, bestD = Infinity;
  for (const n of nodes) { const d = Math.hypot(p.x - n.at.x, p.y - n.at.y); if (d <= n.radius + pad && d < bestD) { best = n.id; bestD = d; } }
  return best;
}

export const quadPoint = (a: Pt, c: Pt, b: Pt, t: number): Pt => { const u = 1 - t; return { x: u * u * a.x + 2 * u * t * c.x + t * t * b.x, y: u * u * a.y + 2 * u * t * c.y + t * t * b.y }; };

export interface HitEdge { id: string; a: Pt; c: Pt; b: Pt; width: number }
/** The edge whose curve passes within `tol` px of the point (the curve is sampled; fine for the few hundred edges on screen). */
export function hitEdge(edges: HitEdge[], p: Pt, tol = 5, samples = 18): string | null {
  let best: string | null = null, bestD = Infinity;
  for (const e of edges) for (let i = 0; i <= samples; i++) { const q = quadPoint(e.a, e.c, e.b, i / samples), d = Math.hypot(p.x - q.x, p.y - q.y); if (d <= tol + e.width / 2 && d < bestD) { best = e.id; bestD = d; } }
  return best;
}
