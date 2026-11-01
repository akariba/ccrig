// Canvas plumbing: DPR-aware sizing in fixed logical coordinates, and theme colours read from the CSS variables at runtime (re-read when the theme changes).
import { useEffect, useRef, useState } from "react";

export interface Colors { paper: string; sheet: string; ink: string; ink2: string; ink3: string; rule: string; hair: string; hl: string; blue: string; teal: string; rose: string; gold: string; dom: [string, string, string] }
const NAMES = ["paper", "sheet", "ink", "ink-2", "ink-3", "rule", "hair", "hl", "blue", "teal", "rose", "gold"] as const;

export function readColors(el: Element): Colors {
  const cs = getComputedStyle(el), g = (n: string) => cs.getPropertyValue("--" + n).trim() || "#888888";
  const v = Object.fromEntries(NAMES.map((n) => [n, g(n)])) as Record<(typeof NAMES)[number], string>;
  return { paper: v.paper, sheet: v.sheet, ink: v.ink, ink2: v["ink-2"], ink3: v["ink-3"], rule: v.rule, hair: v.hair, hl: v.hl, blue: v.blue, teal: v.teal, rose: v.rose, gold: v.gold, dom: [v.blue, v.teal, v.rose] };
}
export function rgba(hex: string, a: number): string {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** Colours of the sheet, refreshed when the OS scheme or the data-theme attribute changes. `version` changes whenever they do. */
export function useColors(root: React.RefObject<HTMLElement | null>): { colors: Colors | null; version: number } {
  const [state, setState] = useState<{ colors: Colors | null; version: number }>({ colors: null, version: 0 });
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const refresh = () => setState((s) => ({ colors: readColors(el), version: s.version + 1 }));
    refresh();
    const mq = matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", refresh);
    const mo = new MutationObserver(refresh);
    mo.observe(el, { attributes: true, attributeFilter: ["data-theme"] });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { mq.removeEventListener("change", refresh); mo.disconnect(); };
  }, [root]);
  return state;
}

/** A canvas drawn in logical units (lw x lh) and scaled to the element's width. Returns the ref and a function that gives the prepared 2D context. */
export function useCanvas(lw: number, lh: number) {
  const ref = useRef<HTMLCanvasElement>(null);
  const size = useRef({ w: 0 });
  const prepare = (): CanvasRenderingContext2D | null => {
    const c = ref.current;
    if (!c) return null;
    const dpr = Math.min(2, window.devicePixelRatio || 1), w = c.clientWidth || lw;
    if (size.current.w !== w || c.width !== Math.round(w * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round((w * lh) / lw * dpr); size.current.w = w; }
    const ctx = c.getContext("2d");
    ctx?.setTransform(c.width / lw, 0, 0, c.height / lh, 0, 0);
    return ctx;
  };
  return { ref, prepare };
}
