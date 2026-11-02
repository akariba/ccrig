// Boxed mono tags at a constant screen size. Greedy, priority-ordered placement: a tag takes the first of four positions around its node
// that overlaps no earlier tag and no node glyph; a tag that fits nowhere is dropped (it appears on hover or zoom, never on top of another).
import type { Pt, Rect } from "./types";

export interface LabelItem { id: string; text: string; at: Pt; radius: number; priority: number; w: number; h: number }
export const overlaps = (a: Rect, b: Rect, gap = 2): boolean => a.x < b.x + b.w + gap && a.x + a.w + gap > b.x && a.y < b.y + b.h + gap && a.y + a.h + gap > b.y;
export const inside = (r: Rect, bounds: Rect): boolean => r.x >= bounds.x && r.y >= bounds.y && r.x + r.w <= bounds.x + bounds.w && r.y + r.h <= bounds.y + bounds.h;

/** Approximate width of a mono tag: constant advance per character plus padding (the renderer uses the same function, so tests and drawing agree). */
export const tagWidth = (text: string, fontPx = 11, pad = 6): number => Math.ceil(text.length * fontPx * 0.6 + pad * 2);

export function placeLabels(items: LabelItem[], bounds: Rect, glyphs: { at: Pt; radius: number }[] = []): Map<string, Rect> {
  const placed = new Map<string, Rect>(), taken: Rect[] = glyphs.map((g) => ({ x: g.at.x - g.radius, y: g.at.y - g.radius, w: g.radius * 2, h: g.radius * 2 }));
  for (const it of [...items].sort((a, b) => b.priority - a.priority || a.id.localeCompare(b.id))) {
    const gap = 4, { x, y } = it.at, r = it.radius;
    const options: Rect[] = [
      { x: x - it.w / 2, y: y + r + gap, w: it.w, h: it.h },          // below
      { x: x - it.w / 2, y: y - r - gap - it.h, w: it.w, h: it.h },   // above
      { x: x + r + gap, y: y - it.h / 2, w: it.w, h: it.h },          // right
      { x: x - r - gap - it.w, y: y - it.h / 2, w: it.w, h: it.h },   // left
    ];
    const own = taken.findIndex((t) => Math.abs(t.x + t.w / 2 - x) < 0.5 && Math.abs(t.y + t.h / 2 - y) < 0.5);
    const pick = options.find((o) => inside(o, bounds) && !taken.some((t, i) => i !== own && overlaps(o, t)));
    if (pick) { placed.set(it.id, pick); taken.push(pick); }
  }
  return placed;
}
