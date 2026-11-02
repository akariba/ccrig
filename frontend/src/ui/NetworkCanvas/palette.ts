import type { Channel } from "../channels";
import { readChartTokens } from "../chartTokens";
import type { Palette } from "./types";

/** The drawing colours, read from the design tokens (so the canvas follows the theme). */
export function readPalette(): Palette {
  const t = readChartTokens();
  return { bg: t.surface2 && getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() || "#06111A", surface: t.surface, text: t.text, text2: t.text2, text3: t.text3, accent: t.accent, border: getComputedStyle(document.documentElement).getPropertyValue("--border-strong").trim() || t.border,
    crit: t.crit, high: t.high, med: t.med, low: t.low, info: t.accent, channel: t.channel as Record<Channel, string>, groups: t.series };
}
