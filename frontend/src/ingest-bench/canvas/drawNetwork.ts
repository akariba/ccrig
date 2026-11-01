// The network trace: input fields -> three model columns -> six check gauges, with gold routes that re-route every ~1.6 s while running.
import { ACT_OUT, COL, EDGES, HEAD, LIT } from "../geometry";
import { FIELDS } from "../simulator";
import { MONO, type View } from "./view";
import { rgba, type Colors } from "./useCanvas";

export const NET_W = 1000, NET_H = 400;
const hsh = (n: number) => { n = Math.sin(n * 12.9898) * 43758.5453; return n - Math.floor(n); };
function text(x: CanvasRenderingContext2D, s: string, px: number, py: number, o: { w?: number; s?: number; c: string; a?: CanvasTextAlign }) {
  x.font = `${o.w ?? 400} ${o.s ?? 11}px ${MONO}`; x.fillStyle = o.c; x.textAlign = o.a ?? "left"; x.textBaseline = "alphabetic"; x.fillText(s, px, py);
}
const bz = (x: CanvasRenderingContext2D, ax: number, ay: number, bx: number, by: number) => x.bezierCurveTo((ax + bx) / 2, ay, (ax + bx) / 2, by, bx, by);
const bzPt = (ax: number, ay: number, bx: number, by: number, t: number) => { const mx = (ax + bx) / 2, u = 1 - t; return [u * u * u * ax + 3 * u * u * t * mx + 3 * u * t * t * mx + t * t * t * bx, u * u * u * ay + 3 * u * u * t * ay + 3 * u * t * t * by + t * t * t * by]; };

export function drawNetwork(x: CanvasRenderingContext2D, v: View, C: Colors, time: number): void {
  x.clearRect(0, 0, NET_W, NET_H);
  const stage = v.stage, act = stage < 3 ? stage + 1 : -1, live = v.running && !v.reduced;
  HEAD.forEach((h, i) => { const hx = i === 0 ? 40 : i === 4 ? 800 : COL[i].x - 78; const on = act === i || (stage === 3 && i > 0 && i < 4); text(x, h[0], hx, 18, { s: 10, w: 500, c: on ? C.ink : C.ink2 }); text(x, h[1], hx, 31, { s: 10, c: C.ink3 }); });
  for (let i = 1; i < 4; i++) {
    const on = act === i || stage === 3; if (!on) continue;
    x.fillStyle = rgba(C.gold, stage === 3 ? 0.04 : 0.07); x.fillRect(COL[i].x - 90, 6, 180, 388);
    x.strokeStyle = stage === 3 ? rgba(C.ink, 0.35) : C.ink; x.lineWidth = 1.2; x.strokeRect(COL[i].x - 90, 6, 180, 388);
    x.fillStyle = C.gold; x.fillRect(COL[i].x - 78, 36, 40, 2);
  }
  x.lineWidth = 0.6;
  for (const e of EDGES) { const a = COL[e.l], b = COL[e.l + 1]; x.strokeStyle = rgba(C.dom[e.c], e.o); x.beginPath(); x.moveTo(a.x + 11, a.ys[e.a]); bz(x, a.x + 11, a.ys[e.a], b.x - 11, b.ys[e.b]); x.stroke(); }
  const cyc = Math.floor(time / 1600), ain = v.fieldIndex ?? (cyc * 5 + stage * 7) % 22, outA = ACT_OUT[Math.min(3, stage)];
  const chains: number[][] = [];
  for (let c = 0; c < 6; c++) { const s = cyc * 13 + c * 7; chains.push([(ain + (c < 3 ? 0 : Math.floor(hsh(s) * 22))) % 22, Math.floor(hsh(s + 1) * 48), Math.floor(hsh(s + 2) * 26), Math.floor(hsh(s + 3) * 32), c < 4 ? outA : Math.floor(hsh(s + 4) * 6)]); }
  chains.forEach((ch, ci) => {
    x.strokeStyle = rgba(C.gold, ci < 4 ? 0.85 : 0.45); x.lineWidth = ci < 4 ? 1.5 : 1; x.beginPath(); x.moveTo(COL[0].x + 11, COL[0].ys[ch[0]]);
    for (let l = 0; l < 4; l++) { const a = COL[l], b = COL[l + 1]; if (l > 0) x.lineTo(a.x + 11, a.ys[ch[l]]); bz(x, a.x + 11, a.ys[ch[l]], b.x - 11, b.ys[ch[l + 1]]); }
    x.stroke();
    if (live) {
      const ph = (time * 0.00045 + ci * 0.17) % 1, seg = Math.floor(ph * 4), tt = ph * 4 - seg, a = COL[seg], b = COL[seg + 1];
      const p = bzPt(a.x + 11, a.ys[ch[seg]], b.x - 11, b.ys[ch[seg + 1]], tt);
      x.fillStyle = C.gold; x.beginPath(); x.arc(p[0], p[1], 2.6, 0, Math.PI * 2); x.fill();
    }
  });
  for (let l = 1; l < 4; l++) {
    const c = COL[l];
    c.ys.forEach((y, i) => {
      const lit = chains.some((ch) => ch[l] === i), w = l === 2 ? 22 : 18, tint = LIT[l][i] > 0.82;
      x.strokeStyle = lit ? C.gold : tint ? rgba(C.dom[i % 3], 0.9) : rgba(C.ink, 0.55); x.lineWidth = lit || tint ? 2.2 : 1; x.beginPath(); x.moveTo(c.x - w / 2, y); x.lineTo(c.x + w / 2, y); x.stroke();
    });
    text(x, `h${l}·0`, c.x, c.y0 - 8, { s: 10, a: "center", c: C.ink3 });
  }
  const c0 = COL[0];
  FIELDS.forEach((f, i) => {
    const y = c0.ys[i], on = i === ain;
    text(x, f, c0.x - 36, y + 3.5, { s: 10, a: "right", w: on ? 500 : 400, c: on ? C.ink : C.ink2 });
    x.strokeStyle = rgba(C.ink3, 0.6); x.lineWidth = 0.7; x.beginPath();
    for (let s = 0; s <= 16; s++) { const sx = c0.x - 30 + s, sy = y + Math.sin(s * 0.8 + i) * 2.6; if (s) x.lineTo(sx, sy); else x.moveTo(sx, sy); }
    x.stroke();
    x.fillStyle = on ? C.ink : rgba(C.ink3, 0.45); x.fillRect(c0.x - 4, y - 3.5, 7, 7);
    if (on) { x.strokeStyle = C.ink; x.lineWidth = 1; x.strokeRect(c0.x - 7, y - 6.5, 13, 13); }
  });
  const c4 = COL[4];
  v.checks.forEach((o, i) => {
    const y = c4.ys[i], val = o.v, on = i === outA && stage < 4;
    x.strokeStyle = rgba(C.ink, 0.25); x.lineWidth = 2.4; x.beginPath(); x.arc(c4.x, y, 11, 0, Math.PI * 2); x.stroke();
    x.strokeStyle = on ? C.gold : val > 0.97 ? C.teal : C.rose; x.beginPath(); x.arc(c4.x, y, 11, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.max(0, Math.min(1, val))); x.stroke();
    text(x, val.toFixed(2), c4.x, y + 3.5, { s: 9, a: "center", c: C.ink });
    if (on) { x.fillStyle = C.gold; x.fillRect(c4.x + 20, y - 17, o.name.length * 6.8 + 10, 15); text(x, o.name, c4.x + 25, y - 6, { s: 10, w: 500, c: C.sheet }); }
    else text(x, o.name, c4.x + 25, y - 6, { s: 10, c: C.ink });
    text(x, o.text, c4.x + 25, y + 9, { s: 10, c: C.ink3 });
    x.strokeStyle = rgba(C.ink3, 0.5); x.lineWidth = 0.6; x.beginPath(); x.moveTo(c4.x + 25, y + 17); x.lineTo(c4.x + 125, y + 17); x.stroke();
    x.fillStyle = C.ink; x.fillRect(c4.x + 25 + Math.max(0, Math.min(1, val)) * 96, y + 14, 3, 6); x.fillStyle = C.ink3; x.fillRect(c4.x + 25 + 96, y + 12, 1, 10);
  });
  text(x, "■ prediction   | target", c4.x + 25, 392, { s: 10, c: C.ink3 });
}
