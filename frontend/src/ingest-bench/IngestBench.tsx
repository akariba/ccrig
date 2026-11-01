// Ingest Bench: a live data-ingestion console drawn as an optical-bench engineering sheet. One requestAnimationFrame loop drives every canvas; DOM text updates at <=10 Hz.
// Events come from the backend (live) or from the simulator (always labelled SIMULATED). See README.md in this folder for how an agent emits events.
import { useEffect, useMemo, useRef, useState } from "react";
import "./tokens.css";
import "./ingestBench.css";
import { BENCH_H, BENCH_W, drawBench } from "./canvas/drawBench";
import { CONV_H, CONV_W, drawConvergence } from "./canvas/drawConvergence";
import { NET_H, NET_W, drawNetwork } from "./canvas/drawNetwork";
import { RIDGE_H, RIDGE_W, drawRidges } from "./canvas/drawRidges";
import { drawWeights } from "./canvas/drawWeights";
import { useCanvas, useColors } from "./canvas/useCanvas";
import type { View } from "./canvas/view";
import { FIELDS } from "./simulator";
import { WEIGHT_DIMS, makeWeights } from "./geometry";
import { checkRows, recordsDone, totalRows, STAGES } from "./reducer";
import { AgentLog } from "./panels/AgentLog";
import { RevisionTable, type RevRow } from "./panels/RevisionTable";
import { SpecStrip, type Spec } from "./panels/SpecStrip";
import { StatusBar, type ThemePref } from "./panels/StatusBar";
import { TitleBlock, type Kpis } from "./panels/TitleBlock";
import { useIngestStream } from "./useIngestStream";
import type { BenchState } from "./types";

const BASE_RMS: [number, number, number] = [320, 210, 125];
const ELEMENT = ["front element · Haiku", "middle element · Sonnet", "rear element · Opus", "joint polish · all three"];
const WSCALE = [2.2, 1.8, 2, 2.1];
const CHECKS = ["completeness", "schemaMatch", "duplicates", "ratingMap", "creditEvents", "freshness"] as const;
const stageIndex = (s: BenchState) => (s.status === "done" ? 4 : Math.max(0, STAGES.indexOf(s.stage)));
const ACT_OUT = [0, 1, 4, 5];

interface Disp { k: number; loss: number; rms: [number, number, number]; tokens: number; records: number; throughput: number; latency: number; checks: Record<string, number>; elapsed: number }
const newDisp = (): Disp => ({ k: 0, loss: 0.09, rms: [...BASE_RMS], tokens: 0, records: 0, throughput: 0, latency: 0, checks: Object.fromEntries(CHECKS.map((c) => [c, 0])), elapsed: 0 });

export function IngestBench() {
  const q = new URLSearchParams(window.location.search);
  const demo = q.get("demo") === "1", runParam = q.get("run");
  const stream = useIngestStream(runParam ?? "latest", demo);
  const root = useRef<HTMLDivElement>(null);
  const { colors, version } = useColors(root);
  const [theme, setTheme] = useState<ThemePref>(() => { try { return (localStorage.getItem("ib-theme") as ThemePref) || "auto"; } catch { return "auto"; } });
  useEffect(() => { try { localStorage.setItem("ib-theme", theme); } catch { /* per-viewer convenience only */ } }, [theme]);

  const bench = useCanvas(BENCH_W, BENCH_H), net = useCanvas(NET_W, NET_H), ridge = useCanvas(RIDGE_W, RIDGE_H), conv = useCanvas(CONV_W, CONV_H);
  const wRefs = [useRef<HTMLCanvasElement>(null), useRef<HTMLCanvasElement>(null), useRef<HTMLCanvasElement>(null), useRef<HTMLCanvasElement>(null)];
  const weights = useMemo(() => makeWeights(), []);
  const latest = useRef({ stream, colors, version });
  latest.current = { stream, colors, version };
  const disp = useRef<Disp>(newDisp());
  const [ui, setUi] = useState<{ kpis: Kpis; spec: Spec; rows: RevRow[]; text: string; tone: "run" | "done" | "error" | "idle" }>(() => ({
    kpis: { records: 0, total: 0, tokens: 0, loss: null, step: 0, stageLetter: "A", stageCaption: ELEMENT[0], runLabel: "—", nSources: 0 }, spec: { sheet: 1, sources: 0, throughput: null, latencyMs: null, elapsedS: 0 }, rows: [], text: "Waiting for a run…", tone: "idle" }));

  useEffect(() => {
    const rmQuery = matchMedia("(prefers-reduced-motion: reduce)");
    let raf = 0, last = performance.now(), animT = 0, frame = 0, lastUi = 0, lastVersion = -1;
    const loop = (now: number) => {
      const { stream: st, colors: C, version: ver } = latest.current, s = st.state, dt = Math.min(0.1, (now - last) / 1000); last = now;
      const d = disp.current, f = st.paused ? 0 : 1 - Math.exp(-9 * dt), ease = (cur: number, to: number) => cur + (to - cur) * f;
      const sIdx = stageIndex(s), done = s.status === "done";
      d.k = ease(d.k, s.k); d.loss = ease(d.loss, s.loss ?? d.loss); d.tokens = ease(d.tokens, s.tokens); d.records = ease(d.records, recordsDone(s));
      d.throughput = ease(d.throughput, s.throughput ?? 0); d.latency = ease(d.latency, s.latencyP95Ms ?? 0); d.elapsed = st.getElapsed();
      const target = s.rms ?? { credit: BASE_RMS[0], market: BASE_RMS[1], signals: BASE_RMS[2] };
      d.rms = [ease(d.rms[0], target.credit), ease(d.rms[1], target.market), ease(d.rms[2], target.signals)];
      for (const c of CHECKS) d.checks[c] = ease(d.checks[c], s.checks?.[c] ?? (c === "freshness" ? s.targets.freshness : 0));
      if (!st.paused) animT += dt * 1000;
      frame++;
      const reduced = rmQuery.matches, running = s.status === "running" && !st.paused;
      const rows = checkRows({ ...s, checks: s.checks ? ({ ...s.checks, ...d.checks } as BenchState["checks"]) : null });
      const open = s.sources.filter((x) => (s.rowsBySource[x.name] ?? 0) > 0 && (s.rowsBySource[x.name] ?? 0) < x.totalRows).length;
      const v: View = { k: d.k, stage: sIdx, running, reduced, simulated: st.mode === "demo" || s.simulated, rms: d.rms, loss: s.loss == null ? null : d.loss, checks: rows, activeOut: ACT_OUT[Math.min(3, sIdx)],
        fieldIndex: s.activeField ? FIELDS.indexOf(s.activeField) : null, history: s.history, openSources: open, latencyP95Ms: s.latencyP95Ms };
      if (C) {
        const b = bench.prepare(); if (b) drawBench(b, v, C, animT);
        const n = net.prepare(); if (n) drawNetwork(n, v, C, animT);
        if (frame % 2 === 0 || ver !== lastVersion) { const r = ridge.prepare(); if (r) drawRidges(r, v, C, animT); const c = conv.prepare(); if (c) drawConvergence(c, v, C); }
        const act = sIdx < 3 ? [sIdx] : sIdx === 3 ? [0, 1, 2, 3] : [];
        wRefs.forEach((ref, i) => {
          const cv = ref.current, ctx = cv?.getContext("2d");
          if (!cv || !ctx) return;
          const live = act.includes(i) || (sIdx === 0 && i === 0);
          if (ver !== lastVersion || (frame % 3 === 0 && live && running && !reduced)) drawWeights(ctx, weights[i], C, live && running && !reduced);
          cv.style.outline = live && sIdx < 4 ? `1.5px solid ${C.gold}` : "none";
        });
        lastVersion = ver;
      }
      if (now - lastUi > 100) {                                                       // DOM text at <= 10 Hz
        lastUi = now;
        const lastLog = s.logs[0];
        const revRows: RevRow[] = s.revisions.map((r) => ({ ...r, shownResidual: r.status === "done" ? r.residualBp : r.status === "active" ? d.rms[0] : null, shownLoss: r.status === "done" ? r.loss : r.status === "active" && s.loss != null ? d.loss : null }));
        const text = s.status === "error" && s.error ? `Error at stage ${s.error.stage}: ${s.error.message}` : done ? "Load complete · dashboard is live" : s.status === "waiting" ? "Waiting for a run…" : `${st.paused ? "Paused · " : ""}${lastLog ? `${lastLog.agent} · ${lastLog.message}` : s.agent ? `${s.agent} · working` : "starting"}`;
        setUi({
          kpis: { records: d.records, total: totalRows(s), tokens: d.tokens, loss: s.loss == null ? null : d.loss, step: s.eventCount, stageLetter: done ? "Done" : s.stage, stageCaption: done ? "all elements in focus" : ELEMENT[sIdx], runLabel: s.runId ? s.runId.replace(/^[A-Za-z]+-?/, "") || s.runId : "—", nSources: s.sources.length },
          spec: { sheet: Math.min(4, sIdx + 1), sources: s.sources.length, throughput: s.throughput == null ? null : d.throughput, latencyMs: s.latencyP95Ms == null ? null : d.latency, elapsedS: d.elapsed },
          rows: revRows, text, tone: s.status === "error" ? "error" : done ? "done" : s.status === "running" ? "run" : "idle",
        });
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the loop reads everything it needs from refs
  }, []);

  const s = stream.state, simulated = stream.mode === "demo" || s.simulated;
  return (
    <div className="ib-root" ref={root} data-theme={theme === "auto" ? undefined : theme} data-testid="ib-root" data-mode={stream.mode} data-status={s.status}>
      <div className="ib-sheet">
        <div className="ib-corner" /><div className="ib-rul" aria-hidden="true">{[1, 2, 3, 4, 5, 6, 7, 8].map((n) => <span key={n}>{n}</span>)}</div><div className="ib-corner" />
        <div className="ib-rul v" aria-hidden="true">{"ABCDEF".split("").map((n) => <span key={n}>{n}</span>)}</div>
        <div className="ib-frame">
          <TitleBlock k={ui.kpis} />
          <StatusBar tone={ui.tone} text={ui.text} mode={stream.mode} simulated={s.simulated} paused={stream.paused} done={s.status === "done"} speed={stream.speed} canControl={stream.canControl} theme={theme}
            onPause={stream.pause} onResume={stream.resume} onRestart={stream.restart} onSpeed={stream.setSpeed} onTheme={setTheme} />
          <section className="ib-bench" aria-label="Focus bench: data sources pass through three model elements and converge on the dashboard plane"><div className="ib-scroll"><canvas ref={bench.ref} data-testid="ib-canvas-bench" /></div></section>
          <section className="ib-net" aria-label="Network trace: source fields routed through each model to the six output checks"><div className="ib-scroll"><canvas ref={net.ref} data-testid="ib-canvas-net" /></div></section>
          <section className="ib-row3">
            <div><div className="ib-panel-h"><span className="ib-lab">Point spread · 3 domains</span><span className="ib-lab">window 640 ms</span></div><canvas ref={ridge.ref} className="ib-ridge" data-testid="ib-canvas-ridge" /></div>
            <div><div className="ib-panel-h"><span className="ib-lab">Weights</span><span className="ib-lab">W1 · W2 · W3 · W4</span></div>
              <div className="ib-wts">{WEIGHT_DIMS.map(([w, h, cap], i) => (
                <figure key={i}><canvas ref={wRefs[i]} width={w} height={h} style={{ width: w * WSCALE[i], height: h * WSCALE[i] }} data-testid={`ib-w${i}`} /><figcaption><b>W{i + 1}</b>{cap}</figcaption></figure>))}</div></div>
            <div><div className="ib-panel-h"><span className="ib-lab">Convergence</span><span className="ib-lab">log scale</span></div><canvas ref={conv.ref} className="ib-ridge" data-testid="ib-canvas-conv" /></div>
          </section>
          <section className="ib-foot">
            <div><SpecStrip s={ui.spec} /><RevisionTable rows={ui.rows} canJump={stream.canControl} onJump={stream.seekStage} /></div>
            <AgentLog lines={s.logs} />
          </section>
        </div>
        <div className="ib-rul v" aria-hidden="true">{"ABCDEF".split("").map((n) => <span key={n}>{n}</span>)}</div>
        <div className="ib-corner" /><div className="ib-rul" aria-hidden="true">{[1, 2, 3, 4, 5, 6, 7, 8].map((n) => <span key={n}>{n}</span>)}</div><div className="ib-corner" />
      </div>
      <p className="ib-note" data-testid="ib-note">{simulated ? "Simulated run with sample data. Nothing here is a measurement of a real load. Tap a revision row to jump to that stage." : `Live run ${s.runId ?? ""}. Values are exactly as the agents reported them.`}{stream.note ? ` ${stream.note}` : ""}</p>
    </div>
  );
}
