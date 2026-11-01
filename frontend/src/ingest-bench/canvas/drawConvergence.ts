// Convergence: log-scale loss over the four stage bands, with the target line and the latest point.
import { MONO, type View } from "./view";
import { rgba, type Colors } from "./useCanvas";

export const CONV_W = 360, CONV_H = 170;
const TARGET = 0.0105;
export function drawConvergence(x: CanvasRenderingContext2D, v: View, C: Colors): void {
  x.clearRect(0, 0, CONV_W, CONV_H);
  const L = 34, R = 346, Tp = 22, B = 148, ly = (val: number) => B - ((Math.log10(Math.max(1e-4, val)) - Math.log10(0.005)) / (Math.log10(0.12) - Math.log10(0.005))) * (B - Tp);
  const txt = (s: string, px: number, py: number, c: string, a: CanvasTextAlign = "left", w = 400) => { x.font = `${w} 10px ${MONO}`; x.fillStyle = c; x.textAlign = a; x.textBaseline = "alphabetic"; x.fillText(s, px, py); };
  "ABCD".split("").forEach((rev, i) => {
    const x0 = L + ((R - L) * i) / 4, active = i === v.stage && v.stage < 4;
    if (active) { x.fillStyle = rgba(C.gold, 0.1); x.fillRect(x0, Tp, (R - L) / 4, B - Tp); }
    txt(rev, x0 + (R - L) / 8, 15, active ? C.ink : C.ink3, "center", active ? 500 : 400);
    if (i) { x.strokeStyle = rgba(C.ink3, 0.35); x.setLineDash([2, 3]); x.lineWidth = 0.7; x.beginPath(); x.moveTo(x0, Tp); x.lineTo(x0, B); x.stroke(); x.setLineDash([]); }
  });
  for (const g of [0.1, 0.03, 0.01]) { const y = ly(g); x.strokeStyle = rgba(C.ink3, 0.25); x.lineWidth = 0.5; x.beginPath(); x.moveTo(L, y); x.lineTo(R, y); x.stroke(); txt(String(g), L - 5, y + 3.5, C.ink3, "right"); }
  x.strokeStyle = C.ink; x.lineWidth = 1; x.beginPath(); x.moveTo(L, Tp); x.lineTo(L, B); x.lineTo(R, B); x.stroke();
  const ty = ly(TARGET); x.strokeStyle = C.teal; x.setLineDash([4, 3]); x.beginPath(); x.moveTo(L, ty); x.lineTo(R, ty); x.stroke(); x.setLineDash([]);
  txt("target 0.0105", R, ty - 5, C.teal, "right");
  const h = v.history;
  if (h.length > 1) {
    const X = (k: number) => L + (R - L) * k;
    x.beginPath(); h.forEach((p, i) => { const px = X(p[0]), py = ly(p[1]); if (i) x.lineTo(px, py); else x.moveTo(px, py); });
    const last = h[h.length - 1]; x.lineTo(X(last[0]), B); x.lineTo(L, B); x.closePath(); x.fillStyle = rgba(C.blue, 0.1); x.fill();
    x.beginPath(); h.forEach((p, i) => { const px = X(p[0]), py = ly(p[1]); if (i) x.lineTo(px, py); else x.moveTo(px, py); }); x.strokeStyle = C.ink; x.lineWidth = 1.3; x.stroke();
    x.fillStyle = C.sheet; x.strokeStyle = C.ink; x.beginPath(); x.arc(X(last[0]), ly(last[1]), 3.5, 0, Math.PI * 2); x.fill(); x.stroke();
  }
  txt(v.loss == null ? "eval loss —" : `eval loss ${v.loss.toFixed(4)}`, L, 166, C.ink2);
}
