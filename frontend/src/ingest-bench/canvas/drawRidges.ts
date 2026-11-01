// Point spread: three ridgeline plots whose noise shrinks with the domain's RMS error.
import { DOMS, MONO, type View } from "./view";
import { rgba, type Colors } from "./useCanvas";

export const RIDGE_W = 360, RIDGE_H = 170;
export function drawRidges(x: CanvasRenderingContext2D, v: View, C: Colors, time: number): void {
  x.clearRect(0, 0, RIDGE_W, RIDGE_H);
  const tt = v.reduced ? 0 : time * 0.001;
  for (let d = 0; d < 3; d++) {
    const ox = 12 + d * 116, w = 104, amp = v.rms[d] / 320;
    x.font = `400 10px ${MONO}`; x.textBaseline = "alphabetic"; x.textAlign = "left";
    x.fillStyle = C.dom[d]; x.fillText(`${["0°", "14°", "20°"][d]} ${DOMS[d]}`, ox, 14);
    for (let r = 0; r < 9; r++) {
      const by = 148 - r * 9; x.beginPath(); x.moveTo(ox, by);
      for (let s = 0; s <= 52; s++) {
        const u = s / 52, gx = Math.exp(-Math.pow((u - 0.5) / (0.11 + 0.07 * amp), 2));
        const n = (Math.sin(u * 31 + r * 1.7 + tt * 2 + d) * 0.55 + Math.sin(u * 67 - r + tt * 3.1) * 0.45) * amp * 28;
        x.lineTo(ox + u * w, by - gx * (46 - r * 2.4) - Math.abs(n) * (0.35 + gx));
      }
      x.lineTo(ox + w, by); x.closePath(); x.fillStyle = C.sheet; x.fill(); x.strokeStyle = rgba(C.dom[d], 0.45 + r * 0.06); x.lineWidth = 0.8; x.stroke();
    }
    x.fillStyle = C.ink2; x.fillText(v.loss == null ? "rms —" : `rms ${v.rms[d].toFixed(1)} bp`, ox, 166);
  }
}
