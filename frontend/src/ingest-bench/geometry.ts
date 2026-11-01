// Static drawing geometry, generated once from fixed seeds so every render is identical. (Decoration only: none of it encodes data.)
let seed = 7;
const rnd = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
const withSeed = <T,>(s: number, fn: () => T): T => { seed = s; return fn(); };

export const SCRIBBLES: number[][] = withSeed(11, () => Array.from({ length: 260 }, () => { const x = 10 + rnd() * 190, y = 150 + rnd() * 250, a = rnd() * Math.PI, l = 12 + rnd() * 40; return [x, y, x + Math.cos(a) * l, y + Math.sin(a) * l]; }));
export interface Ray { d: number; j: number; u: number; sy: number; sx: number }
export const RAYS: Ray[] = withSeed(11, () => { for (let i = 0; i < 260 * 4; i++) rnd(); const out: Ray[] = []; for (let d = 0; d < 3; d++) for (let j = 0; j < 15; j++) out.push({ d, j, u: j / 14 - 0.5, sy: 190 + rnd() * 190, sx: 60 + rnd() * 140 }); return out; });
export const LX = [268, 322, 376], CY = 250, RY = 118, IMX = 850, SPOT = [330, 232, 132];

export interface Col { x: number; n: number; y0: number; y1: number; ys: number[] }
export const COL: Col[] = [{ x: 160, n: 22, y0: 48, y1: 376 }, { x: 360, n: 48, y0: 48, y1: 380 }, { x: 560, n: 26, y0: 150, y1: 282 }, { x: 740, n: 32, y0: 86, y1: 350 }, { x: 842, n: 6, y0: 84, y1: 344 }]
  .map((c) => ({ ...c, ys: Array.from({ length: c.n }, (_, i) => c.y0 + ((c.y1 - c.y0) * i) / (c.n - 1)) }));
export interface Edge { l: number; a: number; b: number; c: number; o: number }
export const EDGES: Edge[] = withSeed(29, () => { const out: Edge[] = []; for (let l = 0; l < 4; l++) for (let e = 0; e < (l === 3 ? 90 : 210); e++) out.push({ l, a: Math.floor(rnd() * COL[l].n), b: Math.floor(rnd() * COL[l + 1].n), c: Math.floor(rnd() * 3), o: 0.06 + rnd() * 0.14 }); return out; });
export const LIT: number[][] = withSeed(29, () => { for (let i = 0; i < 4 * 210 * 4; i++) rnd(); return COL.map((c) => c.ys.map(() => rnd())); });
export const HEAD: [string, string][] = [["INPUT · 22", "task, context, sources"], ["HIDDEN 1 · HAIKU (48)", "48 · ReLU · extract"], ["HIDDEN 2 · SONNET (26)", "26 · ReLU · validate"], ["HIDDEN 3 · OPUS (32)", "32 · ReLU · enrich"], ["OUTPUT · 6", "linear · checks"]];
export const WEIGHT_DIMS: [number, number, string][] = [[22, 64, "22→48"], [48, 40, "48→26"], [26, 54, "26→32"], [32, 12, "32→6"]];
export const ACT_OUT = [0, 1, 4, 5];

/** Weight matrices: per cell an intensity and a domain index. Shimmering mutates the intensities (decoration). */
export function makeWeights() {
  return withSeed(53, () => WEIGHT_DIMS.map(([w, h]) => ({ w, h, v: Array.from({ length: w * h }, () => [rnd(), Math.floor(rnd() * 3)] as [number, number]) })));
}
export type Weights = ReturnType<typeof makeWeights>;
