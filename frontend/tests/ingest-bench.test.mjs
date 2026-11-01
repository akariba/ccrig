import assert from "node:assert/strict";
import { test } from "node:test";
import { loadTs } from "./ts-loader.mjs";

const sim = await loadTs("src/ingest-bench/simulator.ts"), red = await loadTs("src/ingest-bench/reducer.ts");
function run(seconds, speed = 1, step = 0.1) {
  let s = red.initialState(); const evs = []; const sm = new sim.Simulator((e) => { evs.push(e); s = red.reduce(s, e); }); sm.speed = speed; sm.start();
  for (let t = 0; t < seconds; t += step) sm.tick(step);
  return { s, evs, sm };
}

test("the simulated run takes 36 seconds at 1x, in four 9-second stages, and says it is simulated", () => {
  const half = run(17.9).s;
  assert.equal(half.status, "running"); assert.equal(half.simulated, true); assert.equal(half.stage, "B");
  const all = run(36.5);
  assert.equal(all.s.status, "done"); assert.equal(all.s.elapsedS, 36); assert.equal(all.evs.filter((e) => e.type === "run_completed").length, 1);
  assert.deepEqual(all.evs.filter((e) => e.type === "stage_completed").map((e) => e.stage), ["A", "B", "C", "D"]);
  assert.equal(all.evs[0].type, "run_started"); assert.equal(all.evs[0].simulated, true);
});

test("speed multiplies the simulator clock: 4x finishes in about 9 seconds", () => {
  assert.equal(run(9.2, 4).s.status, "done"); assert.notEqual(run(8.0, 4).s.status, "done");
});

test("loss follows 0.082·e^(−3.6k)+0.0075 and the RMS per domain falls to about 11% of 320/210/125 bp", () => {
  const near = (a, b, e) => assert.ok(Math.abs(a - b) <= e, `${a} !~ ${b}`);
  near(sim.lossAt(0, 0), 0.0895, 0.005); near(sim.lossAt(1, 36), 0.0075 + 0.082 * Math.exp(-3.6), 1e-9);
  near(sim.rmsAt(0, 0, 0), 320 * 0.11 + 320 * 0.89, 1); near(sim.rmsAt(0, 1, 36), 320 * (0.11 + 0.89 * Math.exp(-3.1 * 1)), 1);
  const { s } = run(36.5); near(s.rms.credit, 320 * 0.11 * 1.35, 25); assert.ok(s.rms.market < 80 && s.rms.signals < 45);
  const first = run(0.3).s, last = s; assert.ok(last.loss < first.loss / 3);
});

test("the focus improves monotonically in the data: progress, rows, tokens and the loss curve's x never go backwards", () => {
  const { evs } = run(36.5); let k = -1, rows = -1, tok = -1;
  for (const e of evs.filter((x) => x.type === "progress")) {
    const kk = (["A", "B", "C", "D"].indexOf(e.stage) + e.progress) / 4, r = Object.values(e.rowsBySource).reduce((a, b) => a + b, 0);
    assert.ok(kk >= k - 1e-9 && r >= rows && e.tokens >= tok); k = kk; rows = r; tok = e.tokens;
  }
  const { s } = run(36.5); assert.ok(s.history.length > 50); for (let i = 1; i < s.history.length; i++) assert.ok(s.history[i][0] >= s.history[i - 1][0]);
});

test("revision rows move queued -> active -> done, with residual and loss filled in as each stage completes", () => {
  const mid = run(13).s;
  assert.deepEqual(mid.revisions.map((r) => r.status), ["done", "active", "queued", "queued"]);
  assert.ok(mid.revisions[0].residualBp > 100 && mid.revisions[0].loss > 0.02 && mid.revisions[1].residualBp == null);
  assert.deepEqual(run(36.5).s.revisions.map((r) => r.status), ["done", "done", "done", "done"]);
});

test("jumping to a stage replays the run up to it, filling in history; the run then continues from there", () => {
  const evs = []; let s = red.initialState(); const sm = new sim.Simulator((e) => { evs.push(e); s = red.reduce(s, e); }); sm.start(); sm.tick(3);
  sm.seek(2);
  assert.equal(s.stage, "C"); assert.deepEqual(s.revisions.map((r) => r.status), ["done", "done", "active", "queued"]);
  assert.ok(s.logs.length === 7 && s.history.length > 40 && s.revisions[1].residualBp != null);
  sm.tick(10); assert.equal(s.stage, "D"); sm.tick(10); assert.equal(s.status, "done");
});

test("the log keeps the 7 newest lines, newest first", () => {
  const { s } = run(20); assert.equal(s.logs.length, 7); for (let i = 1; i < 7; i++) assert.ok(s.logs[i - 1].ts >= s.logs[i].ts);
});

test("check gauges: raw values are shown as streamed, rings are normalised, and a missing value is a dash, never a number", () => {
  assert.deepEqual(red.checkRows(red.initialState()).map((r) => r.text), ["—", "—", "—", "—", "—", "—"]);
  const rows = red.checkRows(run(36.5).s);
  assert.deepEqual(rows.map((r) => r.name), ["Completeness", "SchemaMatch", "Duplicates", "RatingMap", "CreditEvents", "Freshness"]);
  assert.match(rows[0].text, /^99\.\d%$/); assert.equal(rows[2].text, "−4,210"); assert.equal(rows[4].text, "128 tagged"); assert.equal(rows[5].text, "0 min lag");
  assert.ok(rows.every((r) => r.v >= 0 && r.v <= 1) && rows[5].v > 0.999);
});

test("an error event marks the failed stage and the run; the display keeps its last good numbers", () => {
  let s = red.initialState();
  for (const e of run(12).evs) s = red.reduce(s, e);
  const before = s.loss; s = red.reduce(s, { type: "error", stage: "B", message: "schema registry unreachable" });
  assert.equal(s.status, "error"); assert.equal(s.error.message, "schema registry unreachable"); assert.equal(s.revisions[1].status, "error"); assert.equal(s.loss, before);
});

test("a live run carries its own targets, and progress without a within-stage fraction still advances overall progress monotonically", () => {
  let s = red.reduce(red.initialState(), { type: "run_started", runId: "r9", sources: [{ name: "a", totalRows: 10, domain: "credit" }], targets: { duplicates: 100 } });
  assert.equal(s.simulated, false); assert.equal(s.targets.duplicates, 100); assert.equal(s.targets.creditEvents, 128);
  const p = { type: "progress", stage: "B", agent: "Sonnet", rowsBySource: { a: 5 }, tokens: 10, loss: 0.05, rmsByDomain: { credit: 1, market: 1, signals: 1 }, checks: { completeness: 1, schemaMatch: 1, duplicates: 50, ratingMap: 1, creditEvents: 1, freshness: 0 }, throughput: 1, latencyP95Ms: 1 };
  s = red.reduce(s, p); const k1 = s.k; s = red.reduce(s, { ...p, stage: "A" }); assert.ok(s.k >= k1);
  assert.equal(red.checkRows(s)[2].v, 0.5); assert.equal(red.recordsDone(s), 5); assert.equal(red.totalRows(s), 10);
});
