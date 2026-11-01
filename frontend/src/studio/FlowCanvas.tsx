// The processing canvas: eight stage cards joined by luminous Bezier cables. Cables and particles are drawn from recorded state only:
//  - a cable is bright when data passed through it, dim when nothing did, dashed rose when the next stage refused it, pulsing amber at the approval gate;
//  - particles travel along a cable only for a moment after a recorded event for the stage it feeds, or while that stage is recorded as running.
// Nothing moves because of a timer alone. With "reduce motion" the same states are drawn without movement.
import { useEffect, useRef, useState } from "react";
import { STAGE_DEFS, fmtMs, type ConnView, type StageView } from "./reduce";
import { STATE_COLOR, STATE_LABEL } from "./states";
import type { StageId } from "./types";

export const W = 1000, H = 232, NW = 92, NTOP = 16, NH = 198;
const X = (i: number) => 12 + i * ((W - 24 - NW) / 7);
const STRANDS = 5, WINDOW_MS = 1700;

const GLYPH: Record<string, string> = { QUEUED: "·", RUNNING: "◌", COMPLETED: "✓", COMPLETED_WITH_WARNINGS: "!", FAILED: "✕", FAILED_CHECKS: "✕", AWAITING_REVIEW: "❚❚", BLOCKED: "✕", APPROVED: "✓", REJECTED: "✕", ROLLED_BACK: "↺", SKIPPED: "–" };
const colorOf = (s: string) => STATE_COLOR[s] ?? STATE_COLOR.QUEUED;

export type Selection = { kind: "node"; id: StageId } | { kind: "conn"; from: StageId; to: StageId } | null;

function rgba(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
const bezPt = (p0: number[], p1: number[], p2: number[], p3: number[], t: number) => {
  const u = 1 - t;
  return [u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0], u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]];
};
const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));

interface Props {
  stages: StageView[]; conns: ConnView[]; lastFlow: React.RefObject<Record<string, number>>; selected: Selection; onSelect: (s: Selection) => void; busyLabel?: string;
}

export function FlowCanvas({ stages, conns, lastFlow, selected, onSelect }: Props) {
  const box = useRef<HTMLDivElement>(null), cv = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(1000);
  const raf = useRef(0);
  const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setWidth(Math.max(320, el.clientWidth)));
    ro.observe(el); setWidth(Math.max(320, el.clientWidth));
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const canvas = cv.current;
    if (!canvas) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1), s = width / W;
    canvas.width = Math.round(width * dpr); canvas.height = Math.round(H * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const byId = Object.fromEntries(stages.map((st) => [st.id, st])) as Record<StageId, StageView>;

    const animating = (now: number) => !reduce && (stages.some((st) => st.state === "RUNNING") || conns.some((c) => c.state === "AWAITING") || Object.values(lastFlow.current ?? {}).some((t) => now - t < WINDOW_MS));

    const draw = (now: number) => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, H);
      ctx.globalCompositeOperation = "lighter";
      conns.forEach((c, i) => {
        const up = byId[c.from], dn = byId[c.to];
        const x0 = (X(i) + NW) * s, x1 = X(i + 1) * s, dx = x1 - x0;
        const sel = selected?.kind === "conn" && selected.from === c.from && selected.to === c.to;
        const age = now - ((lastFlow.current ?? {})[c.to] ?? -1e9);
        const running = dn.state === "RUNNING" || up.state === "RUNNING";
        for (let k = 0; k < STRANDS; k++) {
          const y0 = NTOP + 46 + k * 26, y1 = NTOP + 46 + ((k * 2 + 1) % STRANDS) * 26, wob = reduce ? 0 : Math.sin(now / 900 + k * 1.7 + i) * 3;
          const P = [[x0, y0], [x0 + dx * 0.5, y0 + wob], [x1 - dx * 0.5, y1 - wob], [x1, y1]];
          const centre = k === 2;
          let a = 0.1, from = colorOf("QUEUED"), to = colorOf("QUEUED"), dash: number[] = [];
          if (c.state === "FLOWED") { a = centre ? 0.8 : 0.5; from = colorOf(up.state); to = colorOf(dn.state); }
          else if (c.state === "AWAITING") { a = (centre ? 0.85 : 0.45) * (reduce ? 1 : 0.65 + 0.35 * Math.sin(now / 380)); from = colorOf(up.state); to = STATE_COLOR.AWAITING_REVIEW; }
          else if (c.state === "HELD") { a = centre ? 0.8 : 0.45; from = colorOf(up.state); to = STATE_COLOR.BLOCKED; dash = [5, 5]; }
          const end = c.state === "HELD" ? 0.82 : 1;
          const g = ctx.createLinearGradient(x0, 0, x1, 0);
          g.addColorStop(0, rgba(from, a)); g.addColorStop(1, rgba(to, a));
          ctx.beginPath(); ctx.moveTo(P[0][0], P[0][1]);
          const q = (t: number) => bezPt(P[0], P[1], P[2], P[3], t);
          for (let t = 0.04; t <= end + 1e-6; t += 0.04) { const p = q(Math.min(t, end)); ctx.lineTo(p[0], p[1]); }
          ctx.setLineDash(dash); ctx.strokeStyle = g; ctx.lineWidth = (sel ? 2.4 : centre ? 1.5 : 0.9); ctx.stroke(); ctx.setLineDash([]);
          if (sel) { ctx.lineWidth = 6; ctx.globalAlpha = 0.12; ctx.stroke(); ctx.globalAlpha = 1; }
          if (c.state === "HELD" && centre) {                                         // the refusal mark where the cable stops
            const p = q(0.82); ctx.strokeStyle = rgba(STATE_COLOR.BLOCKED, 0.95); ctx.lineWidth = 1.8; ctx.beginPath();
            ctx.moveTo(p[0] - 4, p[1] - 4); ctx.lineTo(p[0] + 4, p[1] + 4); ctx.moveTo(p[0] + 4, p[1] - 4); ctx.lineTo(p[0] - 4, p[1] + 4); ctx.stroke();
          }
          if (c.state === "FLOWED" || c.state === "AWAITING") {                       // arrowhead: the direction data moved
            const p = q(1), r = q(0.96); const ang = Math.atan2(p[1] - r[1], p[0] - r[0]);
            ctx.fillStyle = rgba(to, a); ctx.beginPath(); ctx.moveTo(p[0], p[1]);
            ctx.lineTo(p[0] - 5 * Math.cos(ang - 0.45), p[1] - 5 * Math.sin(ang - 0.45)); ctx.lineTo(p[0] - 5 * Math.cos(ang + 0.45), p[1] - 5 * Math.sin(ang + 0.45)); ctx.fill();
          }
          // particles - only while an event backs them
          if (!reduce && c.state !== "IDLE") {
            let t = -1;
            if (running) t = ((now / 900) + k * 0.21) % 1;
            else if (age >= 0 && age < WINDOW_MS) t = clamp((age - k * 110) / 1100);
            else if (c.state === "AWAITING") t = 0.88 + 0.06 * Math.sin(now / 300 + k);
            if (t > 0 && t < 1) {
              const p = q(Math.min(t, end)), fade = c.state === "AWAITING" ? 0.9 : 1 - t * t * t;
              ctx.fillStyle = rgba(running ? STATE_COLOR.RUNNING : to, 0.95 * fade); ctx.beginPath(); ctx.arc(p[0], p[1], centre ? 2.6 : 1.8, 0, 7); ctx.fill();
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
  }, [stages, conns, selected, width, lastFlow, reduce]);

  const selNode = selected?.kind === "node" ? selected.id : null;
  return (
    <div className="ds-stage-scroll">
      <div className="ds-stage" ref={box} style={{ height: H }} data-testid="flow-canvas">
        <canvas ref={cv} className="ds-cables" style={{ width: "100%", height: H }} aria-hidden="true" />
        {STAGE_DEFS.map((def, i) => {
          const st = stages[i];
          const rec = st.records, tot = rec?.processed ?? 0, acc = rec?.accepted ?? 0, rej = rec?.rejected ?? 0;
          const v = st.validation;
          return (
            <button key={def.id} type="button" className={"ds-node" + (selNode === def.id ? " sel" : "")} data-testid={`flow-node-${def.id}`} data-state={st.state}
              aria-pressed={selNode === def.id} aria-label={`${def.label}: ${STATE_LABEL[st.state] ?? st.state}`}
              style={{ left: `${(X(i) / W) * 100}%`, width: `${(NW / W) * 100}%`, top: NTOP, height: NH, ["--c" as string]: colorOf(st.state) }}
              onClick={() => onSelect({ kind: "node", id: def.id })}>
              <span className="ds-node-h"><i>{i + 1}</i><b>{def.label.toUpperCase()}</b><em className={st.state === "RUNNING" ? "spin" : ""}>{GLYPH[st.state] ?? "·"}</em></span>
              <span className="ds-node-s">{STATE_LABEL[st.state] ?? st.state}</span>
              <span className="ds-node-r"><u>{rec?.unit ?? "records"}</u><b>{rec ? (rec.processed ?? "—") : "—"}</b></span>
              <span className="ds-node-r"><u>accepted</u><b>{rec ? (rec.accepted ?? "—") : "—"}</b></span>
              <span className="ds-node-r"><u>rejected</u><b className={rec && (rec.rejected ?? 0) > 0 ? "bad" : ""}>{rec ? (rec.rejected ?? "—") : "—"}</b></span>
              <span className="ds-node-r"><u>errors</u><b className={v && v.errors ? "bad" : ""}>{v ? v.errors : st.state === "QUEUED" ? "—" : 0}</b></span>
              <span className="ds-node-r"><u>duration</u><b>{st.durationMs != null ? fmtMs(st.durationMs) : "—"}</b></span>
              <i className="ds-node-bar" aria-hidden="true"><u style={{ width: tot ? `${(acc / tot) * 100}%` : 0 }} /><s style={{ width: tot ? `${(rej / tot) * 100}%` : 0 }} /></i>
            </button>
          );
        })}
        {conns.map((c, i) => {
          const sel = selected?.kind === "conn" && selected.from === c.from && selected.to === c.to;
          return (
            <button key={c.from} type="button" className={"ds-conn" + (sel ? " sel" : "")} data-testid={`flow-conn-${c.from}-${c.to}`} data-state={c.state} aria-pressed={sel}
              aria-label={`Connection ${c.from} to ${c.to}: ${c.state.toLowerCase()}`}
              style={{ left: `${((X(i) + NW) / W) * 100}%`, width: `${((X(i + 1) - X(i) - NW) / W) * 100}%`, top: NTOP + 20, height: 150 }}
              onClick={() => onSelect({ kind: "conn", from: c.from, to: c.to })} />
          );
        })}
      </div>
    </div>
  );
}
