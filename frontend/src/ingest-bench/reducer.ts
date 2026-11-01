// Pure reducer: IngestEvent -> BenchState. No React, no clock. `k` is overall progress 0..1 (stage index plus the within-stage fraction when the event carries one).
import type { BenchState, IngestEvent, Revision, Stage } from "./types";

export const STAGES: Stage[] = ["A", "B", "C", "D"];
const stageIdx = (s: string) => Math.max(0, STAGES.indexOf(s as Stage));
export const DEFAULT_TARGETS = { completeness: 1, schemaMatch: 1, duplicates: 4210, ratingMap: 1, creditEvents: 128, freshness: 42 };   // normalisation of the gauge rings; a run may override them

export function revisionsFor(nSources: number): Revision[] {
  const plan: [Stage, string, string][] = [["A", `Front element · parse ${nSources} sources`, "Haiku"], ["B", "Middle element · schema, dedupe", "Sonnet"],
    ["C", "Rear element · map ratings, tag news", "Opus"], ["D", "Joint polish · publish to dashboard", "All three"]];
  return plan.map(([rev, change, by], i) => ({ rev, change, by, residualBp: null, loss: null, status: i === 0 ? "active" : "queued" }));
}

export function initialState(): BenchState {
  return { status: "waiting", runId: null, simulated: false, sources: [], targets: { ...DEFAULT_TARGETS }, rowsBySource: {}, stage: "A", agent: "", tokens: 0, loss: null, rms: null, checks: null,
    throughput: null, latencyP95Ms: null, activeField: null, k: 0, history: [], logs: [], revisions: revisionsFor(0), elapsedS: 0, error: null, eventCount: 0 };
}

export function reduce(state: BenchState, ev: IngestEvent): BenchState {
  const s = { ...state, eventCount: state.eventCount + 1 };
  switch (ev.type) {
    case "run_started":
      return { ...initialState(), status: "running", runId: ev.runId, simulated: !!ev.simulated, sources: ev.sources, targets: { ...DEFAULT_TARGETS, ...(ev.targets ?? {}) }, revisions: revisionsFor(ev.sources.length), eventCount: 1 };
    case "progress": {
      const i = stageIdx(ev.stage), k = Math.max(s.k, Math.min(1, (i + Math.max(0, Math.min(1, ev.progress ?? 0.5))) / 4));
      const revisions = s.revisions.map((r, j) => (j < i && r.status !== "done" && r.status !== "error" ? { ...r, status: "done" as const } : j === i && r.status === "queued" ? { ...r, status: "active" as const } : r));
      const history = k - (s.history.length ? s.history[s.history.length - 1][0] : -1) >= 0.002 ? [...s.history, [k, ev.loss] as [number, number]].slice(-600) : s.history;
      return { ...s, status: s.status === "waiting" ? "running" : s.status, stage: ev.stage, agent: ev.agent, rowsBySource: { ...s.rowsBySource, ...ev.rowsBySource }, tokens: ev.tokens, loss: ev.loss, rms: ev.rmsByDomain, checks: ev.checks,
        throughput: ev.throughput, latencyP95Ms: ev.latencyP95Ms, activeField: ev.activeField ?? null, k, history, revisions };
    }
    case "log":
      return { ...s, logs: [{ ts: ev.ts, agent: ev.agent, message: ev.message }, ...s.logs].slice(0, 7) };
    case "stage_completed": {
      const i = stageIdx(ev.stage);
      const revisions = s.revisions.map((r, j) => (j === i ? { ...r, status: "done" as const, residualBp: ev.residualBp, loss: ev.loss } : j === i + 1 && r.status === "queued" ? { ...r, status: "active" as const } : r));
      return { ...s, revisions, k: Math.max(s.k, (i + 1) / 4) };
    }
    case "run_completed":
      return { ...s, status: "done", k: 1, elapsedS: ev.elapsedS, revisions: s.revisions.map((r) => (r.status === "error" ? r : { ...r, status: "done" as const })) };
    case "error": {
      const i = stageIdx(ev.stage);
      return { ...s, status: "error", error: { stage: ev.stage, message: ev.message }, revisions: s.revisions.map((r, j) => (j === i ? { ...r, status: "error" as const } : r)) };
    }
  }
}

/** Gauge rows for the six checks: raw value as streamed, and a 0..1 ring fill (see DEFAULT_TARGETS). */
export function checkRows(state: BenchState): { name: string; v: number; text: string }[] {
  const c = state.checks, t = state.targets, z = (n: number) => Math.max(0, Math.min(1, n));
  const row = (name: string, raw: number | null, fill: (x: number) => number, text: (x: number) => string) => ({ name, v: raw == null ? 0 : z(fill(raw)), text: raw == null ? "—" : text(raw) });
  return [
    row("Completeness", c?.completeness ?? null, (x) => x / t.completeness, (x) => (x * 100).toFixed(1) + "%"),
    row("SchemaMatch", c?.schemaMatch ?? null, (x) => x / t.schemaMatch, (x) => (x * 100).toFixed(1) + "%"),
    row("Duplicates", c?.duplicates ?? null, (x) => x / t.duplicates, (x) => "−" + Math.round(x).toLocaleString("en-US")),
    row("RatingMap", c?.ratingMap ?? null, (x) => x / t.ratingMap, (x) => (x * 100).toFixed(0) + "%"),
    row("CreditEvents", c?.creditEvents ?? null, (x) => x / t.creditEvents, (x) => Math.round(x) + " tagged"),
    row("Freshness", c?.freshness ?? null, (x) => 1 - x / t.freshness, (x) => Math.round(x) + " min lag"),
  ];
}
export const totalRows = (s: BenchState) => s.sources.reduce((a, x) => a + x.totalRows, 0);
export const recordsDone = (s: BenchState) => s.sources.reduce((a, x) => a + Math.min(x.totalRows, s.rowsBySource[x.name] ?? 0), 0);
