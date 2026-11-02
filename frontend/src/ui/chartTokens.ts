// Charts cannot use var(--x): they read the tokens from the document and are re-themed when the theme changes.
import { useSyncExternalStore } from "react";
import { cssVar, onThemeChange } from "../design/theme";

export interface ChartTokens {
  text: string; text2: string; text3: string; border: string; surface: string; surface2: string; accent: string;
  series: string[]; crit: string; high: string; med: string; low: string; font: string; mono: string;
  channel: Record<string, string>;
}
export function readChartTokens(): ChartTokens {
  const v = (n: string, f = "") => cssVar(n, f);
  return {
    text: v("--text", "#232019"), text2: v("--text-2", "#5f5c54"), text3: v("--text-3", "#6f6c63"), border: v("--border", "#e0ddd3"), surface: v("--surface", "#fff"), surface2: v("--surface-2", "#f0efe9"), accent: v("--accent", "#2c5b6b"),
    series: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => v(`--chart-${i}`)), crit: v("--crit"), high: v("--high"), med: v("--med"), low: v("--low"),
    font: v("--font-body", "Inter, sans-serif"), mono: v("--font-mono", "monospace"),
    channel: Object.fromEntries(["ownership", "exposure", "supply", "shared", "comovement", "hidden"].map((c) => [c, v(`--ch-${c}`)])),
  };
}

let version = 0;
const subscribe = (fn: () => void) => onThemeChange(() => { version++; fn(); });
/** Changes whenever the theme does, so a chart (or canvas) can rebuild itself with the new colours. */
export const useThemeVersion = () => useSyncExternalStore(subscribe, () => version, () => 0);
