// Weights: four pixel heatmaps. The active model's matrix shimmers (random cells update) and is outlined in gold by the caller. Decoration: cell values encode nothing.
import type { Weights } from "../geometry";
import { rgba, type Colors } from "./useCanvas";

export function drawWeights(x: CanvasRenderingContext2D, m: Weights[number], C: Colors, shimmer: boolean): void {
  x.fillStyle = C.sheet; x.fillRect(0, 0, m.w, m.h);
  m.v.forEach((p, j) => { if (shimmer && Math.random() < 0.04) p[0] = Math.random(); x.fillStyle = rgba(C.dom[p[1]], 0.12 + p[0] * 0.78); x.fillRect(j % m.w, Math.floor(j / m.w), 1, 1); });
}
