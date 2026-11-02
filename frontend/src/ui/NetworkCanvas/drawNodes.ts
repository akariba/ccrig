// Node glyphs, as pure functions of (context, node, state, palette). The math (arc zones, channel shares, colours) is separate from the
// painting so it can be tested without a canvas.
//
//   Counterparty  outer arc = limit utilisation (green, amber from 85%, red when it reaches 100%, a red tick when it is over the limit)
//                 inner segmented ring = link mix by channel (share of link weight)
//                 core = rating (a dash when none is recorded), edged in the priority colour
//                 badges W wrong-way risk, ! overdue breach, ▲ near limit, ↓ negative outlook (only when the data says so)
//                 a slow amber pulse while the early-warning score is above its threshold (only when the backend supplies one)
//   Issuer        hexagon in its group colour        Risk factor   diamond
import { CHANNEL_ORDER, type Channel } from "../channels";
import type { CpInfo, GNode, Palette } from "./types";

export const UTIL_WARN = 85, UTIL_LIMIT = 100, EWS_THRESHOLD = 0.6, NODE_R = 15;
export interface ArcZone { from: number; to: number; level: "ok" | "warn" | "crit" }
export interface UtilArc { frac: number; over: boolean; zones: ArcZone[] }

/** Fractions of a full turn, clockwise from 12 o'clock. Null (no limit on file) draws nothing: an arc would claim a figure the data does not have. */
export function utilisationArc(util: number | null | undefined): UtilArc | null {
  if (util === null || util === undefined || !Number.isFinite(util) || util < 0) return null;
  const frac = Math.min(util, UTIL_LIMIT) / UTIL_LIMIT, warnAt = UTIL_WARN / UTIL_LIMIT, zones: ArcZone[] = [];
  if (frac > 0) zones.push({ from: 0, to: Math.min(frac, warnAt), level: "ok" });
  if (frac > warnAt) zones.push({ from: warnAt, to: frac, level: util >= UTIL_LIMIT ? "crit" : "warn" });
  return { frac, over: util > UTIL_LIMIT, zones };
}

export interface MixSlice { channel: Channel; share: number }
/** Share of link weight per channel, in the fixed channel order. A link with no recorded strength counts as 0.5 (neutral). Shares sum to 1; no links gives []. */
export function channelMix(links: { channel: Channel; strength: number | null }[]): MixSlice[] {
  const w = new Map<Channel, number>();
  for (const l of links) w.set(l.channel, (w.get(l.channel) ?? 0) + (l.strength ?? 0.5));
  const total = [...w.values()].reduce((a, b) => a + b, 0);
  return total <= 0 ? [] : CHANNEL_ORDER.filter((c) => w.has(c)).map((c) => ({ channel: c, share: w.get(c)! / total }));
}

export interface Badge { glyph: "W" | "!" | "▲" | "↓"; title: string }
export function badges(cp: CpInfo): Badge[] {
  const out: Badge[] = [];
  if (cp.flags.wwr) out.push({ glyph: "W", title: "Wrong-way risk" });
  if (cp.flags.overdue) out.push({ glyph: "!", title: "Overdue breach" });
  if (cp.flags.nearLimit) out.push({ glyph: "▲", title: "Near limit (85% or more)" });
  if (cp.flags.negativeOutlook === true || cp.outlook === "negative") out.push({ glyph: "↓", title: "Negative outlook" });
  return out;
}
export const pulsing = (cp: CpInfo): boolean => cp.ews !== null && cp.ews > EWS_THRESHOLD;

export function priorityColor(p: CpInfo["priority"], c: Palette): string {
  return p === "CRITICAL" ? c.crit : p === "HIGH" ? c.high : p === "MEDIUM" ? c.med : p === "LOW" ? c.low : p === "INFORMATIONAL" ? c.info : c.text3;
}
export function groupColor(group: string | null | undefined, c: Palette): string {
  if (!group) return c.text3;
  let h = 0; for (const ch of group) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return c.groups[h % c.groups.length];
}
/** Heat for the contagion overlay: distress 0-1 -> a colour that warms with distress. */
export function heatColor(d: number, c: Palette): string { return d >= 0.66 ? c.crit : d >= 0.33 ? c.high : d >= 0.12 ? c.med : c.info; }

export interface GlyphState { selected: boolean; hover: boolean; dim: boolean; time: number; reduced: boolean; heat?: { d: number; hop: number }; shock?: boolean; highlight?: boolean; mix: MixSlice[] }
const TAU = Math.PI * 2, TOP = -Math.PI / 2;
const arc = (x: CanvasRenderingContext2D, cx: number, cy: number, r: number, from: number, to: number) => { x.beginPath(); x.arc(cx, cy, r, TOP + from * TAU, TOP + to * TAU); x.stroke(); };
const alpha = (x: CanvasRenderingContext2D, a: number) => { x.globalAlpha = a; };

export function drawCounterparty(x: CanvasRenderingContext2D, n: GNode, p: { x: number; y: number }, s: GlyphState, c: Palette, r = NODE_R): void {
  const cp = n.cp; if (!cp) return;
  x.save(); alpha(x, s.dim ? 0.16 : 1);
  const pri = priorityColor(cp.priority, c), ring = r + 5;
  if (s.heat) { x.fillStyle = heatColor(s.heat.d, c); x.globalAlpha *= 0.12 + 0.34 * s.heat.d; x.beginPath(); x.arc(p.x, p.y, r + 14 + 10 * s.heat.d, 0, TAU); x.fill(); x.globalAlpha = s.dim ? 0.16 : 1; }
  if (s.selected || cp.priority === "CRITICAL" || s.shock || s.highlight) { x.shadowColor = s.selected || s.highlight ? c.accent : c.crit; x.shadowBlur = s.selected ? 18 : 12; }     // glow: critical items, the selection, simulations
  x.fillStyle = c.surface; x.beginPath(); x.arc(p.x, p.y, r + 1, 0, TAU); x.fill(); x.shadowBlur = 0;
  x.lineCap = "butt"; x.lineWidth = 3.4; x.strokeStyle = c.border; arc(x, p.x, p.y, ring, 0, 1);                               // track
  const u = utilisationArc(cp.utilisation);
  if (u) { for (const z of u.zones) { x.strokeStyle = z.level === "ok" ? c.low : z.level === "warn" ? c.high : c.crit; arc(x, p.x, p.y, ring, z.from, z.to); }
    if (u.over) { const a = TOP; x.strokeStyle = c.crit; x.lineWidth = 2.2; x.beginPath(); x.moveTo(p.x + Math.cos(a) * (ring - 4), p.y + Math.sin(a) * (ring - 4)); x.lineTo(p.x + Math.cos(a) * (ring + 6), p.y + Math.sin(a) * (ring + 6)); x.stroke(); } }
  const inner = r * 0.78; x.lineWidth = 3;
  if (s.mix.length === 0) { x.strokeStyle = c.border; arc(x, p.x, p.y, inner, 0, 1); }
  else { const gap = s.mix.length > 1 ? 0.012 : 0; let at = 0; for (const m of s.mix) { x.strokeStyle = c.channel[m.channel]; arc(x, p.x, p.y, inner, at + gap, Math.max(at + gap + 0.004, at + m.share - gap)); at += m.share; } }
  x.fillStyle = c.bg; x.strokeStyle = pri; x.lineWidth = 2; x.beginPath(); x.arc(p.x, p.y, r * 0.5, 0, TAU); x.fill(); x.stroke();
  x.fillStyle = c.text; x.font = `600 ${Math.round(r * 0.48)}px "JetBrains Mono", monospace`; x.textAlign = "center"; x.textBaseline = "middle"; x.fillText(cp.rating ?? "—", p.x, p.y + 0.5);
  badges(cp).forEach((b, i) => {
    const a = [-0.78, -2.36, 0.78, 2.36][i] ?? 0, bx = p.x + Math.cos(a) * (r + 10), by = p.y + Math.sin(a) * (r + 10);
    x.fillStyle = b.glyph === "!" ? c.crit : c.high; x.beginPath(); x.arc(bx, by, 5.2, 0, TAU); x.fill();
    x.fillStyle = c.bg; x.font = `700 7px "JetBrains Mono", monospace`; x.fillText(b.glyph, bx, by + 0.4);
  });
  if (pulsing(cp) && !s.reduced) { const ph = (s.time / 2400) % 1; x.strokeStyle = c.high; x.globalAlpha *= 0.55 * (1 - ph); x.lineWidth = 1.6; x.beginPath(); x.arc(p.x, p.y, ring + 4 + ph * 12, 0, TAU); x.stroke(); }
  else if (pulsing(cp)) { x.strokeStyle = c.high; x.globalAlpha *= 0.5; x.lineWidth = 1.4; x.beginPath(); x.arc(p.x, p.y, ring + 8, 0, TAU); x.stroke(); }
  if (s.shock && !s.reduced) { const ph = (s.time / 1600) % 1; x.strokeStyle = c.crit; x.globalAlpha = (s.dim ? 0.16 : 1) * (1 - ph); x.lineWidth = 2; x.beginPath(); x.arc(p.x, p.y, ring + 6 + ph * 38, 0, TAU); x.stroke(); }     // the ripple at the shock
  if (s.selected || s.hover) { x.globalAlpha = 1; x.strokeStyle = c.accent; x.lineWidth = 1.4; x.beginPath(); x.arc(p.x, p.y, ring + 8, 0, TAU); x.stroke(); }
  x.restore();
}

export function hexPoints(cx: number, cy: number, r: number): [number, number][] { return Array.from({ length: 6 }, (_, i) => { const a = TOP + (i * TAU) / 6; return [cx + Math.cos(a) * r, cy + Math.sin(a) * r] as [number, number]; }); }

export function drawIssuer(x: CanvasRenderingContext2D, n: GNode, p: { x: number; y: number }, s: GlyphState, c: Palette, r = 9): void {
  x.save(); alpha(x, s.dim ? 0.16 : 1);
  if (s.heat) { x.fillStyle = heatColor(s.heat.d, c); x.globalAlpha *= 0.12 + 0.34 * s.heat.d; x.beginPath(); x.arc(p.x, p.y, r + 10 + 8 * s.heat.d, 0, TAU); x.fill(); x.globalAlpha = s.dim ? 0.16 : 1; }
  if (s.selected || s.highlight) { x.shadowColor = c.accent; x.shadowBlur = 16; }
  x.beginPath(); hexPoints(p.x, p.y, r).forEach(([a, b], i) => (i ? x.lineTo(a, b) : x.moveTo(a, b))); x.closePath();
  x.fillStyle = groupColor(n.group, c); x.globalAlpha *= 0.9; x.fill(); x.shadowBlur = 0; x.globalAlpha = s.dim ? 0.16 : 1; x.lineWidth = 1.6; x.strokeStyle = s.selected || s.hover ? c.accent : c.bg; x.stroke();
  x.restore();
}

export function drawFactor(x: CanvasRenderingContext2D, _n: GNode, p: { x: number; y: number }, s: GlyphState, c: Palette, r = 8): void {
  x.save(); alpha(x, s.dim ? 0.16 : 1);
  if (s.heat) { x.fillStyle = heatColor(s.heat.d, c); x.globalAlpha *= 0.12 + 0.34 * s.heat.d; x.beginPath(); x.arc(p.x, p.y, r + 12 + 8 * s.heat.d, 0, TAU); x.fill(); x.globalAlpha = s.dim ? 0.16 : 1; }
  if (s.selected || s.highlight) { x.shadowColor = c.accent; x.shadowBlur = 14; }
  x.beginPath(); x.moveTo(p.x, p.y - r); x.lineTo(p.x + r, p.y); x.lineTo(p.x, p.y + r); x.lineTo(p.x - r, p.y); x.closePath();
  x.fillStyle = c.surface; x.fill(); x.shadowBlur = 0; x.lineWidth = 1.8; x.strokeStyle = s.selected || s.hover ? c.accent : c.text2; x.stroke();
  if (s.shock && !s.reduced) { const ph = (s.time / 1600) % 1; x.strokeStyle = c.crit; x.globalAlpha = 1 - ph; x.beginPath(); x.arc(p.x, p.y, r + 4 + ph * 36, 0, TAU); x.stroke(); }
  x.restore();
}

/** The radius used for hit-testing and label placement. */
export const glyphRadius = (n: GNode): number => (n.kind === "counterparty" ? NODE_R + 8 : n.kind === "issuer" ? 10 : 9);
export function drawGlyph(x: CanvasRenderingContext2D, n: GNode, p: { x: number; y: number }, s: GlyphState, c: Palette): void {
  (n.kind === "counterparty" ? drawCounterparty : n.kind === "issuer" ? drawIssuer : drawFactor)(x, n, p, s, c);
}
