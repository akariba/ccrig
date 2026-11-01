// The processing network. Eight large modules joined by luminous multi-strand Bezier cables.
//  - Module light = recorded state (amber running / awaiting, teal completed, rose refused, dashed grey skipped); its edge colour = kind of processing.
//  - A cable is lit where data passed, dim where nothing did, dashed rose where the next module refused it, held and pulsing amber at the approval gate.
//  - Pulses travel along a cable only for a moment after a recorded event for the module it feeds, or while that module is recorded as running.
//  - The language-model module sits on its own layer above the deterministic lane and is drawn as skipped unless a model call was recorded.
// Nothing moves because of a timer alone. With "reduce motion" the same states are drawn without movement.
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { fmtMs } from "./reduce";
import { LANE, neighbours, type EdgeVM, type NodeId, type NodeVM, type Selection } from "./graph";
import { KIND_COLOR, KIND_LABEL, STATE_COLOR, STATE_LABEL } from "./states";

const LW = 1120, LH = 620;                                    // logical drawing size; the whole stage scales to the space available
const NW = 120, NH = 190, STEP = 162, X0 = 14, LLM = { x: 553, y: 38, w: 176, h: 186 };
const WINDOW_MS = 2400;

interface Rect { x: number; y: number; w: number; h: number }
function makeRects(): Record<NodeId, Rect> {
  const out = {} as Record<NodeId, Rect>;
  LANE.forEach((id, i) => { out[id] = { x: X0 + i * STEP, y: 436 + (i % 2 ? 26 : -26) - NH / 2, w: NW, h: NH }; });
  out.LLM = LLM;
  return out;
}
const RECTS = makeRects();
const GLYPH: Record<string, string> = { QUEUED: "·", RUNNING: "◌", COMPLETED: "✓", COMPLETED_WITH_WARNINGS: "!", FAILED: "✕", FAILED_CHECKS: "✕", AWAITING_REVIEW: "❚❚", BLOCKED: "✕", APPROVED: "✓", REJECTED: "✕", ROLLED_BACK: "↺", SKIPPED: "–" };
const colorOf = (s: string) => STATE_COLOR[s] ?? STATE_COLOR.QUEUED;

function hsl(hex: string, dh: number, l = 0): string {
  const n = parseInt(hex.slice(1), 16), r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0; const L = (mx + mn) / 2, S = d === 0 ? 0 : d / (1 - Math.abs(2 * L - 1));
  if (d) h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return `${(h * 60 + dh + 360) % 360},${Math.round(S * 100)}%,${Math.round(Math.min(88, Math.max(30, L * 100 + l)))}%`;
}
const bez = (p: number[][], t: number) => {
  const u = 1 - t;
  return [u * u * u * p[0][0] + 3 * u * u * t * p[1][0] + 3 * u * t * t * p[2][0] + t * t * t * p[3][0], u * u * u * p[0][1] + 3 * u * u * t * p[1][1] + 3 * u * t * t * p[2][1] + t * t * t * p[3][1]];
};
const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const ease = (t: number) => t * t * (3 - 2 * t);
const STRANDS = 5;

/** The control points of one strand of one cable, in logical coordinates. */
function strand(e: EdgeVM, R: Record<NodeId, Rect>, k: number): number[][] {
  const a = R[e.from], b = R[e.to];
  if (e.id === "RESOLVE-LLM") {                                  // up from the top of Resolve into the base of the model module
    const x0 = a.x + 24 + k * 19.5, y0 = a.y, x1 = b.x + 18 + k * 15, y1 = b.y + b.h;
    return [[x0, y0], [x0, y0 - 70], [x1, y1 + 70], [x1, y1]];
  }
  if (e.id === "LLM-VERIFY") {                                    // down from the model module into the top of Verify
    const x0 = a.x + a.w - 18 - k * 15, y0 = a.y + a.h, x1 = b.x + 24 + k * 19.5, y1 = b.y;
    return [[x0, y0], [x0, y0 + 70], [x1, y1 - 70], [x1, y1]];
  }
  const x0 = a.x + a.w, y0 = a.y + a.h / 2 + (k - 2) * 28, x1 = b.x, y1 = b.y + b.h / 2 + (((k * 2 + 1) % STRANDS) - 2) * 28, dx = x1 - x0;
  return [[x0, y0], [x0 + dx * 0.58, y0], [x1 - dx * 0.58, y1], [x1, y1]];
}

interface Props {
  nodes: NodeVM[]; edges: EdgeVM[]; lastFlow: React.RefObject<Record<string, number>>; selected: Selection; onSelect: (s: Selection) => void;
  onOpen: (what: "review" | "output") => void; idleHint: string | null; maxHeight: number;
}

export function FlowCanvas({ nodes, edges, lastFlow, selected, onSelect, onOpen, idleHint, maxHeight }: Props) {
  const outer = useRef<HTMLDivElement>(null), cv = useRef<HTMLCanvasElement>(null), raf = useRef(0);
  const [box, setBox] = useState({ w: 1200 });
  const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const scale = Math.max(0.5, Math.min(box.w / LW, maxHeight / LH));
  const R = RECTS;
  const selNode = selected?.kind === "node" ? selected.id : null, selEdge = selected?.kind === "edge" ? selected.id : null;
  const near = selNode ? neighbours(selNode, edges) : null;

  useLayoutEffect(() => {
    const el = outer.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setBox({ w: el.clientWidth }));
    ro.observe(el); setBox({ w: el.clientWidth });
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const canvas = cv.current;
    if (!canvas) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(LW * scale * dpr); canvas.height = Math.round(LH * scale * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const st = Object.fromEntries(nodes.map((n) => [n.id, n.state])) as Record<NodeId, string>;
    const activeWindow = (now: number, e: EdgeVM) => now - ((lastFlow.current ?? {})[e.to] ?? -1e9);
    const animating = (now: number) => !reduce && (nodes.some((n) => n.state === "RUNNING") || edges.some((e) => e.state === "AWAITING" || (e.state !== "IDLE" && e.state !== "SKIPPED" && activeWindow(now, e) < WINDOW_MS)));

    const draw = (now: number) => {
      ctx.setTransform(dpr * scale, 0, 0, dpr * scale, 0, 0);
      ctx.clearRect(0, 0, LW, LH);
      ctx.globalCompositeOperation = "lighter";
      ctx.lineCap = "round";
      edges.forEach((e) => {
        const focus = selEdge === e.id ? 1.9 : selNode ? (e.from === selNode || e.to === selNode ? 1.7 : 0.35) : 1;
        const upC = colorOf(st[e.from]), dnC = colorOf(st[e.to]);
        const age = activeWindow(now, e), running = st[e.to] === "RUNNING" && e.state === "FLOWED";
        for (let k = 0; k < STRANDS; k++) {
          const P = strand(e, R, k), centre = k === 2, shift = (k - 2) * 15 + (reduce ? 0 : Math.sin(now / 2600 + k) * 4);
          let a = 0.08, c0 = "#566472", c1 = "#566472", dash: number[] = [], end = 1, w = 1;
          if (e.state === "FLOWED") { a = centre ? 0.95 : 0.6; c0 = upC; c1 = dnC; w = centre ? 1.7 : 1.1; }
          else if (e.state === "AWAITING") { a = (centre ? 0.95 : 0.55) * (reduce ? 1 : 0.7 + 0.3 * Math.sin(now / 420)); c0 = upC; c1 = STATE_COLOR.AWAITING_REVIEW; w = centre ? 1.7 : 1.1; }
          else if (e.state === "HELD") { a = centre ? 0.85 : 0.5; c0 = upC; c1 = STATE_COLOR.BLOCKED; dash = [6, 6]; end = 0.8; w = 1.1; }
          else if (e.state === "SKIPPED") { a = centre ? 0.34 : 0.14; c0 = c1 = KIND_COLOR.llm; dash = [3, 7]; w = 0.9; }
          else { a = centre ? 0.2 : 0.1; }
          a = Math.min(1, a * focus);
          const g = ctx.createLinearGradient(P[0][0], P[0][1], P[3][0], P[3][1]);
          g.addColorStop(0, `hsla(${hsl(c0, shift)},${a})`); g.addColorStop(1, `hsla(${hsl(c1, shift, 8)},${a})`);
          ctx.beginPath(); ctx.moveTo(P[0][0], P[0][1]);
          for (let t = 0.03; t <= end + 1e-6; t += 0.03) { const p = bez(P, Math.min(t, end)); ctx.lineTo(p[0], p[1]); }
          ctx.setLineDash(dash); ctx.strokeStyle = g;
          if (e.state !== "IDLE" && e.state !== "SKIPPED") { ctx.lineWidth = w * 6; ctx.globalAlpha = 0.09 * focus; ctx.stroke(); ctx.globalAlpha = 1; }          // soft glow under the strand
          ctx.lineWidth = w * (selEdge === e.id ? 1.6 : 1); ctx.stroke(); ctx.setLineDash([]);
          if (e.state === "HELD" && centre) {
            const p = bez(P, 0.8); ctx.strokeStyle = `rgba(224,122,144,.95)`; ctx.lineWidth = 2; ctx.beginPath();
            ctx.moveTo(p[0] - 5, p[1] - 5); ctx.lineTo(p[0] + 5, p[1] + 5); ctx.moveTo(p[0] + 5, p[1] - 5); ctx.lineTo(p[0] - 5, p[1] + 5); ctx.stroke();
          }
          if ((e.state === "FLOWED" || e.state === "AWAITING") && centre) {                   // arrowhead: the direction the data moved
            const p = bez(P, 1), q = bez(P, 0.95), ang = Math.atan2(p[1] - q[1], p[0] - q[0]);
            ctx.fillStyle = `hsla(${hsl(c1, 0, 10)},${Math.min(1, a)})`; ctx.beginPath(); ctx.moveTo(p[0] + Math.cos(ang) * 1, p[1] + Math.sin(ang) * 1);
            ctx.lineTo(p[0] - 8 * Math.cos(ang - 0.42), p[1] - 8 * Math.sin(ang - 0.42)); ctx.lineTo(p[0] - 8 * Math.cos(ang + 0.42), p[1] - 8 * Math.sin(ang + 0.42)); ctx.fill();
          }
          // recorded pulses: a comet with a tail, eased, strand by strand
          if (!reduce && (e.state === "FLOWED" || e.state === "AWAITING" || e.state === "HELD")) {
            let t = -1;
            if (running) t = ((now / 1250) + k * 0.19) % 1;
            else if (age >= 0 && age < WINDOW_MS) t = ease(clamp((age - k * 130) / 1500));
            else if (e.state === "AWAITING") t = 0.9 + 0.05 * Math.sin(now / 330 + k * 1.3);
            if (t > 0.005 && t < 0.999) {
              const tt = Math.min(t, end), head = bez(P, tt), fade = e.state === "AWAITING" ? 1 : 1 - Math.pow(tt, 4);
              for (let s = 0; s < 6; s++) { const p = bez(P, Math.max(0, tt - s * 0.022)); ctx.fillStyle = `hsla(${hsl(c1, shift, 22)},${0.5 * fade * (1 - s / 6) * Math.min(1.4, focus)})`; ctx.beginPath(); ctx.arc(p[0], p[1], (centre ? 3.4 : 2.4) * (1 - s * 0.1), 0, 7); ctx.fill(); }
              const gr = ctx.createRadialGradient(head[0], head[1], 0, head[0], head[1], 11); gr.addColorStop(0, `hsla(${hsl(c1, shift, 30)},${0.8 * fade})`); gr.addColorStop(1, `hsla(${hsl(c1, shift, 30)},0)`);
              ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(head[0], head[1], 11, 0, 7); ctx.fill();
            }
          }
        }
      });
      ctx.globalCompositeOperation = "source-over";
    };
    cancelAnimationFrame(raf.current);
    const frame = (now: number) => { draw(now); raf.current = animating(now) ? requestAnimationFrame(frame) : 0; };
    frame(performance.now());
    return () => cancelAnimationFrame(raf.current);
  }, [nodes, edges, selNode, selEdge, scale, lastFlow, reduce, R]);

  const groups: { label: string; kind: string; ids: NodeId[] }[] = [
    { label: KIND_LABEL.ingest, kind: "ingest", ids: ["SOURCE", "PARSE"] }, { label: KIND_LABEL.deterministic, kind: "deterministic", ids: ["VALIDATE", "RESOLVE"] },
    { label: KIND_LABEL.verify, kind: "verify", ids: ["VERIFY"] }, { label: KIND_LABEL.gate, kind: "gate", ids: ["REVIEW"] }, { label: KIND_LABEL.output, kind: "output", ids: ["OUTPUT"] },
  ];
  const key = (fn: () => void) => (ev: KeyboardEvent) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); fn(); } };

  return (
    <div className="ds-stage-outer" ref={outer} data-testid="flow-canvas" data-scale={scale.toFixed(3)} style={{ height: LH * scale }}>
     <div style={{ position: "relative", width: LW * scale, height: LH * scale, flex: "none" }}>
      <div className="ds-stage" style={{ width: LW, height: LH, transform: `scale(${scale})` }}>
        <div className="ds-llm-layer" style={{ left: LLM.x - 22, top: LLM.y - 30, width: LLM.w + 44, height: LLM.h + 46 }}>
          <span>LLM EXECUTION LAYER</span><em>optional · only if a model call was recorded</em>
        </div>
        <canvas ref={cv} className="ds-cables" style={{ width: LW, height: LH }} aria-hidden="true" />
        {nodes.map((n) => {
          const r = R[n.id], c = colorOf(n.state), kc = KIND_COLOR[n.kind], on = selNode === n.id, dim = !!near && !near.has(n.id) && !on;
          const idx = NODE_INDEX[n.id];
          return (
            <div key={n.id} role="button" tabIndex={0} className={`ds-node kind-${n.kind}${on ? " sel" : ""}${dim ? " dim" : ""}${n.id === "LLM" ? " core" : ""}`} data-testid={`flow-node-${n.id}`} data-state={n.state}
              aria-pressed={on} aria-label={`${n.label}: ${STATE_LABEL[n.state] ?? n.state}. ${n.hero}`} onClick={() => onSelect({ kind: "node", id: n.id })} onKeyDown={key(() => onSelect({ kind: "node", id: n.id }))}
              style={{ left: r.x, top: r.y, width: r.w, height: r.h, ["--c" as string]: c, ["--k" as string]: kc } as CSSProperties}>
              <div className="ds-node-h"><span className="ds-idx">{idx}</span><b>{n.label}</b></div>
              <div className="ds-node-state"><em className={n.state === "RUNNING" ? "spin" : ""}>{GLYPH[n.state] ?? "·"}</em>{n.id === "LLM" && n.state === "SKIPPED" ? "skipped" : STATE_LABEL[n.state] ?? n.state}</div>
              <div className="ds-node-hero" title={n.hero}>{n.hero}</div>
              <div className="ds-node-sub" title={n.sub}>{n.sub}</div>
              {n.pips && <div className="ds-pips">{n.pips.map(([l, s]) => <span key={l} style={{ color: colorOf(s) }}>{GLYPH[s] ?? "·"} {l}</span>)}</div>}
              <div className="ds-node-foot">{n.durationMs != null ? fmtMs(n.durationMs) : ""}</div>
              {n.id === "REVIEW" && n.state === "AWAITING_REVIEW" && <button type="button" className="ds-cta" data-testid="open-review" onClick={(ev) => { ev.stopPropagation(); onOpen("review"); }}>Decide ▸</button>}
              {n.id === "OUTPUT" && (n.state === "COMPLETED" || n.state === "ROLLED_BACK") && <button type="button" className="ds-cta" data-testid="open-output" onClick={(ev) => { ev.stopPropagation(); onOpen("output"); }}>Inspect ▸</button>}
            </div>
          );
        })}
        {edges.map((e) => {
          const a = R[e.from], b = R[e.to], sel = selEdge === e.id;
          const left = Math.min(a.x + a.w, b.x) - (e.branch ? 0 : 0), top = e.branch ? Math.min(a.y, b.y) : Math.min(a.y, b.y) + 40;
          const box2 = e.branch ? { left: Math.min(a.x, b.x) + 30, top: Math.min(a.y + a.h, b.y + b.h) - 4, width: 120, height: 70 } : { left, top, width: Math.max(24, Math.abs(b.x - (a.x + a.w))), height: Math.abs(b.y - a.y) + 110 };
          const fixed = e.id === "RESOLVE-LLM" ? { left: a.x + 28, top: LLM.y + LLM.h + 8, width: 110, height: a.y - (LLM.y + LLM.h) - 14 } : e.id === "LLM-VERIFY" ? { left: R.VERIFY.x + 10, top: LLM.y + LLM.h + 8, width: 110, height: R.VERIFY.y - (LLM.y + LLM.h) - 14 } : box2;
          return <button key={e.id} type="button" className={"ds-edge" + (sel ? " sel" : "")} data-testid={`flow-conn-${e.id}`} data-state={e.state} aria-pressed={sel} aria-label={`Connection ${e.from} to ${e.to}: ${e.state.toLowerCase()}`}
            style={{ ...fixed }} onClick={() => onSelect({ kind: "edge", id: e.id })} />;
        })}
        {groups.map((g) => {
          const x0 = R[g.ids[0]].x, x1 = R[g.ids[g.ids.length - 1]].x + NW;
          return <div key={g.label} className="ds-group" style={{ left: x0, width: x1 - x0, ["--k" as string]: KIND_COLOR[g.kind] } as CSSProperties}><i /><span>{g.label}</span></div>;
        })}
        {idleHint && <div className="ds-idle-hint" data-testid="idle-hint">{idleHint}</div>}
      </div>
     </div>
    </div>
  );
}
const NODE_INDEX: Record<NodeId, string> = { SOURCE: "01", PARSE: "02", VALIDATE: "03", RESOLVE: "04", LLM: "05", VERIFY: "06", REVIEW: "07", OUTPUT: "08" };
