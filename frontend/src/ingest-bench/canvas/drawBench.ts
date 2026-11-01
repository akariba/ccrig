// The focus bench: raw data, a Siemens-star target, three lens elements, ray bundles converging on the dashboard plane, and focus spots that sharpen with the RMS error.
import { CY, IMX, LX, RAYS, RY, SCRIBBLES, SPOT } from "../geometry";
import { fmt } from "../format";
import { DISPLAY, DOMS, MONO, type View } from "./view";
import { rgba, type Colors } from "./useCanvas";

export const BENCH_W = 1000, BENCH_H = 430;

function text(x: CanvasRenderingContext2D, s: string, px: number, py: number, o: { w?: number; s?: number; f?: string; c: string; a?: CanvasTextAlign }) {
  x.font = `${o.w ?? 400} ${o.s ?? 11}px ${o.f ?? MONO}`; x.fillStyle = o.c; x.textAlign = o.a ?? "left"; x.textBaseline = "alphabetic"; x.fillText(s, px, py);
}

export function drawBench(x: CanvasRenderingContext2D, v: View, C: Colors, time: number): void {
  x.clearRect(0, 0, BENCH_W, BENCH_H);
  const rm = v.reduced, k = v.k, live = v.running && !rm;
  x.lineWidth = 0.6; x.strokeStyle = rgba(C.ink3, 0.18);
  for (let i = 0; i < 9; i++) { const y = 318 + i * 12; x.beginPath(); x.moveTo(140 + i * 8, y + 40 - i * 2); x.lineTo(960, y - 8 - i * 2); x.stroke(); }          // perspective floor
  x.strokeStyle = C.ink2; x.lineWidth = 1; x.beginPath(); x.moveTo(250, 412); x.lineTo(900, 382); x.stroke();                                              // bench axis
  for (let i = 0; i <= 7; i++) { const px = 250 + i * 92.8, py = 412 - i * 4.3; x.beginPath(); x.moveTo(px, py); x.lineTo(px, py + 6); x.stroke(); text(x, String(i * 10 - 10), px, py + 18, { s: 10, a: "center", c: C.ink3 }); }
  text(x, "L1", LX[0] - 10, 402, { s: 10, c: C.ink2 }); text(x, "L2", LX[1] - 4, 399, { s: 10, c: C.ink2 }); text(x, "L3", LX[2] + 2, 396, { s: 10, c: C.ink2 });
  text(x, v.simulated ? `BFL 43.99 · EFL ${(55.34 - k * 4.4).toFixed(2)}` : `STAGE ${v.stage > 3 ? "D" : "ABCD"[v.stage]} · OVERALL ${Math.round(k * 100)}%`, 600, 404, { s: 10, c: C.ink3 });
  x.lineWidth = 0.55; x.strokeStyle = rgba(C.ink3, 0.4);
  for (const s of SCRIBBLES) { x.beginPath(); x.moveTo(s[0], s[1]); x.lineTo(s[2], s[3]); x.stroke(); }                                                    // raw, unstructured data

  // Siemens-star target with bezel and index mark
  const cx = 96, cy = 92, r = 58;
  x.save(); x.translate(cx, cy); x.rotate(k * Math.PI * 0.6 + (rm ? 0 : time * 0.00008));
  for (let i = 0; i < 48; i += 2) { const a0 = (i / 48) * Math.PI * 2, a1 = ((i + 1) / 48) * Math.PI * 2; x.beginPath(); x.moveTo(0, 0); x.arc(0, 0, r, a0, a1); x.closePath(); x.fillStyle = rgba(C.blue, 0.35 + 0.4 * k); x.fill(); }
  for (let i = 1; i < 48; i += 2) { const a0 = (i / 48) * Math.PI * 2, a1 = ((i + 0.5) / 48) * Math.PI * 2; x.beginPath(); x.moveTo(0, 0); x.arc(0, 0, r, a0, a1); x.closePath(); x.fillStyle = rgba(C.blue, 0.12); x.fill(); }
  x.restore();
  x.strokeStyle = C.ink; x.lineWidth = 1; x.beginPath(); x.arc(cx, cy, r + 6, 0, Math.PI * 2); x.stroke();
  x.strokeStyle = C.ink3; x.lineWidth = 0.6;
  for (let i = 0; i < 72; i++) { const a = (i / 72) * Math.PI * 2, l = i % 6 ? 3 : 6; x.beginPath(); x.moveTo(cx + Math.cos(a) * (r + 6), cy + Math.sin(a) * (r + 6)); x.lineTo(cx + Math.cos(a) * (r + 6 + l), cy + Math.sin(a) * (r + 6 + l)); x.stroke(); }
  x.fillStyle = C.gold; x.fillRect(cx - 6, cy - r - 12, 12, 3);
  text(x, "DETAIL A", 182, 46, { s: 10, w: 500, c: C.ink }); text(x, "on-axis source mix", 182, 59, { s: 10, c: C.ink3 });
  text(x, v.simulated ? `${4 + Math.round(k * 8)} feeds/s` : `${v.openSources} source${v.openSources === 1 ? "" : "s"} open`, 182, 84, { s: 20, f: DISPLAY, c: C.blue });
  text(x, "limit, dashed ring", 182, 99, { s: 10, c: C.ink3 });
  text(x, v.simulated ? `${Math.round((1 - k) * 1.4 * 10) / 10}% in 10 ms` : v.latencyP95Ms != null ? `p95 ${fmt(v.latencyP95Ms)} ms` : "p95 not reported", 182, 113, { s: 10, c: C.gold });
  text(x, "RAW SOURCES →", 448, 44, { s: 10, w: 500, c: C.ink });
  DOMS.forEach((n, d) => { const lx = 560 + d * 96; x.strokeStyle = C.dom[d]; x.lineWidth = 2; x.beginPath(); x.moveTo(lx, 40); x.lineTo(lx + 22, 40); x.stroke(); text(x, n, lx + 28, 44, { s: 10, c: C.dom[d] }); });

  // ray bundles: raw data -> L1 -> L3 -> image plane; the spread at the plane is the domain's RMS
  const spread = v.rms.map((m) => (m / 320) * 92);
  const pts = (r: (typeof RAYS)[number]) => {
    const y1 = CY + r.u * RY * 1.45, y3 = CY + r.u * RY * 0.95 - (CY - SPOT[r.d]) * 0.18, yt = SPOT[r.d] + r.u * spread[r.d];
    return [[r.sx, r.sy], [LX[0], y1], [LX[2] + 8, y3], [IMX, yt]];
  };
  for (const r of RAYS) { const p = pts(r); x.strokeStyle = rgba(C.dom[r.d], 0.32); x.lineWidth = 0.7; x.beginPath(); x.moveTo(p[0][0], p[0][1]); for (let i = 1; i < 4; i++) x.lineTo(p[i][0], p[i][1]); x.stroke(); }
  if (live) {
    x.setLineDash([3, 16]); x.lineDashOffset = -time * 0.06;
    for (const r of RAYS) { if (r.j % 3) continue; const p = pts(r); x.strokeStyle = rgba(C.dom[r.d], 0.95); x.lineWidth = 1.6; x.beginPath(); x.moveTo(p[0][0], p[0][1]); for (let i = 1; i < 4; i++) x.lineTo(p[i][0], p[i][1]); x.stroke(); }
    x.setLineDash([]);
  }
  for (let d = 0; d < 3; d++) for (let s = 0; s < 3; s++) {                                                                                                  // aperture ellipses along each bundle
    const ex = 480 + s * 110 + d * 12, yy = SPOT[d] + (CY - SPOT[d]) * (1 - (ex - 376) / 474) * 0.82;
    x.strokeStyle = rgba(C.dom[d], 0.35); x.lineWidth = 0.7; x.beginPath(); x.ellipse(ex, yy, 5, 10 + spread[d] * 0.2, 0, 0, Math.PI * 2); x.stroke();
  }

  // lens elements
  const act = v.stage < 3 ? v.stage : 3;
  LX.forEach((lx, i) => {
    const on = act === i || act === 3;
    if (on) { x.fillStyle = rgba(C.gold, 0.12); x.beginPath(); x.ellipse(lx, CY, 24, RY + 4, 0, 0, Math.PI * 2); x.fill(); }
    for (let e = 0; e < 5; e++) { x.strokeStyle = on ? (e === 2 ? C.gold : rgba(C.ink, 0.75)) : rgba(C.ink, 0.5); x.lineWidth = e === 2 ? (on ? 1.8 : 1.1) : 0.7; x.beginPath(); x.ellipse(lx - 10 + e * 5, CY, 14 + e * 1.6, RY - Math.abs(e - 2) * 6, 0, 0, Math.PI * 2); x.stroke(); }
    const bx = [352, 446, 536][i], by = [180, 148, 180][i];
    x.strokeStyle = C.ink3; x.lineWidth = 0.7; x.beginPath(); x.moveTo(bx, by + 12); x.lineTo(lx + 6, CY - RY + 18); x.stroke();
    x.beginPath(); x.arc(bx, by, 11, 0, Math.PI * 2); x.fillStyle = on ? C.ink : C.sheet; x.fill(); x.strokeStyle = C.ink; x.lineWidth = 1; x.stroke();
    if (on && live) { x.strokeStyle = C.gold; x.lineWidth = 1.4; x.beginPath(); x.arc(bx, by, 15, time * 0.004, time * 0.004 + Math.PI * 1.2); x.stroke(); }
    text(x, String(i + 1), bx, by + 4, { s: 11, w: 500, a: "center", c: on ? C.sheet : C.ink });
    text(x, ["HAIKU 5.5", "SONNET 5.5", "OPUS 5.5"][i], bx, by - 20, { s: 10, w: 500, a: "center", c: on ? C.ink : C.ink2 });
  });

  // image plane: tilted slab, field-curvature curve, focus spots
  x.fillStyle = rgba(C.sheet, 0.82); x.strokeStyle = C.ink; x.lineWidth = 1;
  x.beginPath(); x.moveTo(828, 80); x.lineTo(878, 62); x.lineTo(878, 368); x.lineTo(828, 390); x.closePath(); x.fill(); x.stroke();
  x.beginPath(); x.moveTo(878, 62); x.lineTo(892, 66); x.lineTo(892, 364); x.lineTo(878, 368); x.stroke();
  x.strokeStyle = rgba(C.ink3, 0.35); x.lineWidth = 0.5;
  for (let i = 1; i < 10; i++) { const y = 80 + i * 31; x.beginPath(); x.moveTo(828, y); x.lineTo(878, y - 18); x.stroke(); }
  text(x, "DASHBOARD PLANE", 892, 54, { s: 10, w: 500, a: "right", c: C.ink });
  x.strokeStyle = rgba(C.rose, 0.6); x.setLineDash([2, 4]); x.lineWidth = 1; x.beginPath(); x.moveTo(852, SPOT[2]); x.quadraticCurveTo(866, (SPOT[2] + SPOT[0]) / 2, 852, SPOT[0]); x.stroke(); x.setLineDash([]);
  for (let d = 0; d < 3; d++) {
    const sx = 852, sy = SPOT[d], rr = 8 + spread[d] * 0.42;
    const g = x.createRadialGradient(sx, sy, 0, sx, sy, rr * 2.2); g.addColorStop(0, rgba(C.dom[d], 0.75)); g.addColorStop(1, rgba(C.dom[d], 0));
    x.fillStyle = g; x.beginPath(); x.ellipse(sx, sy, rr * 1.3, rr * 2.2, 0, 0, Math.PI * 2); x.fill();
    x.strokeStyle = C.dom[d]; x.lineWidth = 1; x.beginPath(); x.ellipse(sx, sy, 4, 9, 0, 0, Math.PI * 2); x.stroke();
    x.beginPath(); x.moveTo(sx, sy - 18); x.lineTo(sx, sy + 18); x.moveTo(sx - 8, sy); x.lineTo(sx + 8, sy); x.stroke();
    x.strokeStyle = C.ink3; x.lineWidth = 0.6; x.beginPath(); x.moveTo(sx + 16, sy - 6); x.lineTo(905, sy - 14); x.stroke();
    text(x, DOMS[d], 910, sy - 12, { s: 12, w: 500, c: C.dom[d] });
    text(x, v.loss == null ? "rms —" : `rms ${v.rms[d].toFixed(1)} bp`, 910, sy + 3, { s: 10, c: C.ink3 });
    if (v.simulated) text(x, `Δz ${d === 1 ? "+" : "−"}${Math.round(v.rms[d] * 9.4).toLocaleString("en-US")} rows`, 910, sy + 16, { s: 10, c: C.ink3 });
  }
}
