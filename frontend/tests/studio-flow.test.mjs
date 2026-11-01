import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { loadTs } from "./ts-loader.mjs";

const r = await loadTs("src/studio/reduce.ts");
const g = await loadTs("src/studio/graph.ts");
const rec = JSON.parse(readFileSync(new URL("../public/studio-recordings/oracle-nvidia.json", import.meta.url), "utf8"));
const views = { cooccurrence: rec.cooccurrence.after_ingest, ingest: rec.asserted.after_ingest, approved: rec.asserted.after_approval, rolled: rec.asserted.after_rollback };
const nodes = (events, upto) => g.buildNodes(r.reduceStages(events, upto));
const by = (ns) => Object.fromEntries(ns.map((n) => [n.id, n]));
const edgeStates = (events, upto) => Object.fromEntries(g.buildEdges(nodes(events, upto)).map((e) => [e.id, e.state]));

test("the client reduction of the recorded events equals the backend's stage states, for every recorded snapshot", () => {
  for (const p of Object.values(views)) {
    const mine = Object.fromEntries(r.reduceStages(p.events).map((s) => [s.id, s.state]));
    assert.deepEqual(mine, Object.fromEntries(p.stages.map((s) => [s.id, s.state])), p.job.job_id + " " + p.state);
    assert.equal(r.jobState(r.reduceStages(p.events)), p.state);
  }
});

test("a replay cut at any point shows only what had been recorded by then", () => {
  const ev = views.rolled.events;
  let seenAwaiting = false, seenApproved = false;
  for (let i = 0; i <= ev.length; i++) {
    const s = Object.fromEntries(r.reduceStages(ev, i).map((x) => [x.id, x.state]));
    if (s.REVIEW === "AWAITING_REVIEW") seenAwaiting = true;
    if (s.REVIEW === "APPROVED") { seenApproved = true; assert.ok(seenAwaiting); assert.notEqual(s.PROMOTE, "SKIPPED"); }
    if (s.PROMOTE === "ROLLED_BACK") assert.ok(seenApproved);
    if (i < r.firstIndex(ev, "REVIEW_APPROVED")) assert.equal(r.destinationStatus(ev, i), "NOT_PROMOTED");
  }
  assert.equal(r.destinationStatus(ev), "ROLLED_BACK");
  assert.equal(r.snapshotKey(ev, 3), "after_ingest");
  assert.equal(r.snapshotKey(ev, ev.length), "after_rollback");
});

test("the network has eight modules in the required order, and the model module is an optional branch", () => {
  assert.deepEqual(g.NODE_DEFS.map((n) => n.id), ["SOURCE", "PARSE", "VALIDATE", "RESOLVE", "LLM", "VERIFY", "REVIEW", "OUTPUT"]);
  assert.deepEqual(g.LANE, ["SOURCE", "PARSE", "VALIDATE", "RESOLVE", "VERIFY", "REVIEW", "OUTPUT"]);
  const ids = g.buildEdges(nodes([])).map((e) => e.id).sort();
  assert.deepEqual(ids, ["LLM-VERIFY", "PARSE-VALIDATE", "RESOLVE-LLM", "RESOLVE-VERIFY", "REVIEW-OUTPUT", "SOURCE-PARSE", "VALIDATE-RESOLVE", "VERIFY-REVIEW"]);
  assert.ok(Object.values(edgeStates([])).every((s) => s === "IDLE"), "before any event nothing is lit");
});

test("no model call recorded: the module is skipped (never running) and the evidence stage is fed directly by the resolve stage", () => {
  const ev = views.ingest.events;
  for (let i = 0; i <= ev.length; i++) assert.ok(!["RUNNING", "COMPLETED"].includes(by(nodes(ev, i)).LLM.state), "the model never appears to run");
  const n = by(nodes(ev));
  assert.equal(n.LLM.state, "SKIPPED"); assert.equal(n.LLM.hero, "not invoked"); assert.match(n.LLM.sub, /no model call was recorded/);
  const e = edgeStates(ev);
  assert.equal(e["RESOLVE-LLM"], "SKIPPED"); assert.equal(e["LLM-VERIFY"], "SKIPPED"); assert.equal(e["RESOLVE-VERIFY"], "FLOWED");
});

test("modules and cables follow the recorded gate: blocked is held with a refused cable; awaiting pauses at the gate; approval and rollback follow", () => {
  const blocked = edgeStates(views.cooccurrence.events), nb = by(nodes(views.cooccurrence.events));
  assert.equal(nb.VERIFY.state, "FAILED_CHECKS"); assert.equal(nb.VERIFY.hero, "rejected"); assert.equal(nb.REVIEW.state, "BLOCKED"); assert.equal(nb.OUTPUT.state, "SKIPPED");
  assert.equal(blocked["VERIFY-REVIEW"], "HELD"); assert.equal(blocked["REVIEW-OUTPUT"], "HELD");
  const wait = edgeStates(views.ingest.events), nw = by(nodes(views.ingest.events));
  assert.equal(wait["VERIFY-REVIEW"], "AWAITING"); assert.equal(nw.REVIEW.hero, "awaiting"); assert.equal(nw.VERIFY.hero, "asserted");
  const done = by(g.buildNodes(r.reduceStages(views.approved.events), { decided: "recording-reviewer" }));
  assert.equal(done.REVIEW.sub, "by recording-reviewer"); assert.equal(done.OUTPUT.state, "COMPLETED"); assert.match(done.OUTPUT.hero, /^v\d+$/);
  const back = by(nodes(views.rolled.events));
  assert.equal(back.OUTPUT.state, "ROLLED_BACK"); assert.equal(back.OUTPUT.hero, "rolled back");
});

// SYNTHETIC events, built by this test only: what the page shows IF the ledger records a model call. The real pipeline records none.
const syn = (type, state, extra = {}) => ({ id: type + state, seq: 1, ts: "2026-11-01T10:00:00.000Z", stage_id: "LLM", type, state, records: null, resolution: null, validation: null, destination: null, error: null, message: "", elapsed_ms: null, ...extra });
test("a recorded model call is shown exactly as recorded, unrecorded fields stay unrecorded, and a failure is a failure", () => {
  const running = by(nodes([syn("STAGE_STARTED", "RUNNING", { llm: { provider: "p", model: "m", calls: null, latency_ms: null, input_tokens: null, output_tokens: null } })])).LLM;
  assert.equal(running.state, "RUNNING"); assert.equal(running.hero, "m");
  const done = by(nodes([syn("STAGE_COMPLETED", "COMPLETED", { llm: { provider: "p", model: "m", calls: 1, latency_ms: 812, input_tokens: 1500, output_tokens: null } })])).LLM;
  assert.equal(done.sub, "p · 812 ms · 1500/? tok");                                   // output tokens were not recorded: a question mark, never an estimate
  const none = by(nodes([syn("STAGE_COMPLETED", "COMPLETED", { llm: null })])).LLM;
  assert.equal(none.sub, "provider details not recorded");
  const failed = by(nodes([syn("STAGE_FAILED", "FAILED", { error: { type: "ConnectError", message: "unreachable" } })])).LLM;
  assert.equal(failed.hero, "failed"); assert.equal(failed.sub, "ConnectError");
  const evs = [syn("STAGE_COMPLETED", "COMPLETED", { llm: { provider: "p", model: "m", calls: 1, latency_ms: 5, input_tokens: 1, output_tokens: 1 } })];
  const e = Object.fromEntries(g.buildEdges(by2(evs)).map((x) => [x.id, x.state]));
  assert.equal(e["RESOLVE-VERIFY"], "IDLE");                                          // the evidence stage is no longer fed directly
});
function by2(evs) { return g.buildNodes(r.reduceStages(evs)); }

test("replay pacing compresses waits but keeps order; events of one ledger row play together", () => {
  const a = { seq: 1, ts: "2026-11-01T10:00:00.000Z" }, b = { seq: 1, ts: "2026-11-01T10:00:00.000Z" }, c = { seq: 2, ts: "2026-11-01T10:00:00.050Z" }, d = { seq: 3, ts: "2026-11-01T10:09:00.000Z" };
  assert.equal(r.replayDelayMs(a, b, 1), 0); assert.equal(r.replayDelayMs(a, c, 1), 420); assert.equal(r.replayDelayMs(c, d, 1), 900); assert.equal(r.replayDelayMs(a, c, 2), 210);
  assert.equal(r.fmtMs(null), "unavailable"); assert.equal(r.fmtMs(12), "12 ms"); assert.equal(r.fmtMs(1500), "1.50 s");
});

test("the recording is labelled as a recording and carries real timing, never an invented metric", () => {
  assert.equal(rec.label, "Recorded replay"); assert.match(rec.note, /recording/i);
  for (const p of Object.values(views)) {
    assert.deepEqual(p.metrics.unavailable.map((u) => u.metric).sort(), ["latency_percentiles", "model_usage", "quality_score", "throughput"]);
    assert.ok(!("throughput" in p.metrics.measured));
    assert.ok(!p.events.some((e) => e.stage_id === "LLM" && ["RUNNING", "COMPLETED"].includes(e.state)), "the recording contains no model activity");
  }
  assert.equal(rec.graph_proof.before_approval.edge_present, false); assert.equal(rec.graph_proof.after_approval.edge_present, true);
  assert.equal(rec.graph_proof.after_approval.edge.weight, null); assert.equal(rec.graph_proof.after_rollback.edge_present, false);
});
