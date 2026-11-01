// Simulator mode: a deterministic generator that emits the SAME events a real run would, on a clock. Everything it produces is sample data; the UI labels it SIMULATED.
// Loss decays as 0.082·e^(−3.6k) + 0.0075 (plus small noise); RMS per domain decays from 320/210/125 bp to ~11% of that. 9 s per stage at 1× (36 s in all).
import type { Domain, IngestEvent, SourceInfo, Stage } from "./types";

export const SIM_SOURCES: SourceInfo[] = [
  { name: "exposures.parquet", totalRows: 412880, domain: "credit" }, { name: "ratings_feed.json", totalRows: 18240, domain: "credit" }, { name: "collateral.csv", totalRows: 96410, domain: "credit" },
  { name: "market_ticks", totalRows: 1284000, domain: "market" }, { name: "news_stream", totalRows: 7920, domain: "signals" },
];
export const FIELDS = ["exposure_id", "cpty_id", "notional", "mtm", "pfe_95", "epe", "rating_sp", "rating_moodys", "pd_1y", "lgd", "collat_value", "haircut", "ccy", "tenor", "price", "rate_curve", "fx_rate", "vol_surface", "news_ts", "headline", "sentiment", "source_ref"];
export const STAGE_SECONDS = 9;
const STAGES: Stage[] = ["A", "B", "C", "D"], AGENTS = ["Haiku", "Sonnet", "Opus", "All three"], RATE = [1900, 2700, 3500, 2400], SPD = [1.25, 1.6, 1.4, 1.05, 1.9], BASE = [320, 210, 125];
const LOGS: [string, string][] = [
  ["Haiku", "parsing exposures.parquet · 412,880 rows"], ["Haiku", "reading ratings_feed.json"], ["Haiku", "streaming market_ticks · 3 venues"], ["Haiku", "decoding collateral.csv · 14 columns"], ["Haiku", "capturing news_stream · 7,920 items"], ["Haiku", "5 sources staged"],
  ["Sonnet", "checking 1.82M rows against schema v7"], ["Sonnet", "dropped 4,210 duplicate trades"], ["Sonnet", "fixed 37 malformed tenor dates"], ["Sonnet", "reconciled notional vs MTM sign"], ["Sonnet", "flagged 12 orphan counterparties"], ["Sonnet", "schema match 99.1%"],
  ["Opus", "mapping 2,314 counterparties to ratings"], ["Opus", "resolved 61 legal-entity aliases"], ["Opus", "tagged 128 credit events in news"], ["Opus", "scored sentiment per obligor"], ["Opus", "linked collateral to netting sets"], ["Opus", "enrichment complete"],
  ["Haiku", "writing exposure tiles"], ["Sonnet", "cross-checking totals vs source"], ["Opus", "refreshing PFE charts"], ["All three", "dashboard published"],
];
const TICK = 0.2, TOTAL_S = STAGE_SECONDS * 4;
const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const ease = (x: number) => 1 - Math.pow(1 - clamp(x), 3);
const TOTAL_ROWS = SIM_SOURCES.reduce((a, s) => a + s.totalRows, 0);

export const lossAt = (k: number, t: number) => 0.082 * Math.exp(-3.6 * k) + 0.0075 + (k < 1 ? (Math.sin(t * 7.1) * 0.6 + Math.sin(t * 2.3)) * 0.0016 * (1 - k) : 0);
export const rmsAt = (d: number, k: number, t: number) => BASE[d] * (0.11 + 0.89 * Math.exp(-3.1 * clamp(k * 1.1 - d * 0.04))) + (k < 1 ? Math.sin(t * 3 + d) * 4 * (1 - k) : 0);

export function progressEventAt(t: number): IngestEvent {
  const stage = Math.min(3, Math.floor(t / STAGE_SECONDS)), within = clamp((t - stage * STAGE_SECONDS) / STAGE_SECONDS), k = clamp(t / TOTAL_S);
  const rowsBySource: Record<string, number> = {};
  SIM_SOURCES.forEach((s, i) => { rowsBySource[s.name] = stage > 0 ? s.totalRows : Math.min(s.totalRows, Math.round(s.totalRows * within * SPD[i])); });
  let tokens = 0;
  for (let i = 0; i <= stage; i++) tokens += RATE[i] * (i < stage ? STAGE_SECONDS : within * STAGE_SECONDS);
  const rms = [0, 1, 2].map((d) => rmsAt(d, k, t));
  return { type: "progress", stage: STAGES[stage], agent: AGENTS[stage], rowsBySource, tokens: Math.round(tokens), loss: lossAt(k, t), rmsByDomain: { credit: rms[0], market: rms[1], signals: rms[2] } as Record<Domain, number>,
    checks: { completeness: 0.61 + 0.388 * ease(k * 1.15), schemaMatch: 0.44 + 0.551 * ease((k - 0.12) * 2.4), duplicates: 4210 * ease((k - 0.25) * 4), ratingMap: ease((k - 0.5) * 4), creditEvents: 128 * ease((k - 0.55) * 4.5), freshness: 42 * (1 - ease((k - 0.75) * 4)) },
    throughput: stage === 0 ? (TOTAL_ROWS * SPD[3] / STAGE_SECONDS) * 0.55 : (TOTAL_ROWS / STAGE_SECONDS) * 0.3, latencyP95Ms: Math.round(180 + stage * 140 + Math.sin(t * 3) * 40),
    activeField: FIELDS[(Math.floor(t / 1.6) * 5 + stage * 7) % FIELDS.length], progress: within };
}

export class Simulator {
  t = 0; speed = 1; done = false;
  private n = 0; private li = 0; private si = 0;
  private emit: (e: IngestEvent) => void; private runId: string;
  constructor(emit: (e: IngestEvent) => void, runId = "sim-14") { this.emit = emit; this.runId = runId; }
  start() { this.t = 0; this.n = 0; this.li = 0; this.si = 0; this.done = false; this.emit({ type: "run_started", runId: this.runId, sources: SIM_SOURCES, simulated: true }); this.step(0); }
  /** Advance by `dtSeconds` of real time (scaled by speed), emitting every event that falls due. */
  tick(dtSeconds: number) { if (!this.done) { this.t += dtSeconds * this.speed; this.step(this.t); } }
  /** Jump to the start of a stage: the run is replayed up to that point so the history (log, curve, revisions) is filled in. */
  seek(stage: number) { this.start(); this.t = clampStage(stage) * STAGE_SECONDS; this.step(this.t); }
  private step(to: number) {
    while (!this.done && this.n * TICK <= to) { this.fire(this.n * TICK); this.n++; }
  }
  private fire(tt: number) {
    while (this.li < LOGS.length) { const at = Math.floor(this.li / 6) * STAGE_SECONDS + (this.li % 6) * 1.45; if (at > tt) break; this.emit({ type: "log", ts: at, agent: LOGS[this.li][0], message: LOGS[this.li][1] }); this.li++; }
    while (this.si < 4 && (this.si + 1) * STAGE_SECONDS <= tt + 1e-9) {
      const k = (this.si + 1) / 4, t = (this.si + 1) * STAGE_SECONDS;
      this.emit({ type: "stage_completed", stage: STAGES[this.si], residualBp: Math.round(rmsAt(0, k, t)), loss: lossAt(k, t) }); this.si++;
    }
    if (tt >= TOTAL_S - 1e-9) { this.emit({ type: "run_completed", elapsedS: TOTAL_S }); this.done = true; return; }
    this.emit(progressEventAt(tt));
  }
}
const clampStage = (i: number) => Math.max(0, Math.min(3, i));
