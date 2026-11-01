import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { loadTs } from "./ts-loader.mjs";

const r = await loadTs("src/studio/reduce.ts");
const rec = JSON.parse(readFileSync(new URL("../public/studio-recordings/oracle-nvidia.json", import.meta.url), "utf8"));
const views = Object.values({ cooccurrence: rec.cooccurrence.after_ingest, ingest: rec.asserted.after_ingest, approved: rec.asserted.after_approval, rolled: rec.asserted.after_rollback });

test("the client reduction of the recorded events equals the backend's stage states, for every recorded snapshot", () => {
  for (const p of views) {
    const mine = Object.fromEntries(r.reduceStages(p.events).map((s) => [s.id, s.state]));
    const theirs = Object.fromEntries(p.stages.map((s) => [s.id, s.state]));
    assert.deepEqual(mine, theirs, p.job.job_id + " " + p.state);
    assert.equal(r.jobState(r.reduceStages(p.events)), p.state);
    assert.deepEqual(r.reduceConnections(r.reduceStages(p.events)).map((c) => c.state), p.connections.map((c) => c.state));
  }
});

test("a replay cut at any point shows only what had been recorded by then", () => {
  const ev = rec.asserted.after_rollback.events;
  let seenAwaiting = false, seenApproved = false;
  for (let i = 0; i <= ev.length; i++) {
    const s = Object.fromEntries(r.reduceStages(ev, i).map((x) => [x.id, x.state]));
    if (s.REVIEW === "AWAITING_REVIEW") seenAwaiting = true;
    if (s.REVIEW === "APPROVED") { seenApproved = true; assert.ok(seenAwaiting, "approval is preceded by the wait for a reviewer"); assert.notEqual(s.PROMOTE, "SKIPPED"); }
    if (s.PROMOTE === "ROLLED_BACK") assert.ok(seenApproved);
    if (i < r.firstIndex(ev, "REVIEW_APPROVED")) assert.equal(r.destinationStatus(ev, i), "NOT_PROMOTED");
  }
  assert.equal(r.destinationStatus(ev), "ROLLED_BACK");
  assert.equal(r.destinationStatus(ev, r.firstIndex(ev, "PROMOTED") + 1), "LIVE_IN_OVERLAY");
  assert.equal(r.snapshotKey(ev, 3), "after_ingest");
  assert.equal(r.snapshotKey(ev, ev.length), "after_rollback");
  assert.equal(r.snapshotKey(ev, r.firstIndex(ev, "PROMOTED") + 1), "after_approval");
});

test("replay pacing compresses waits but keeps order; events of one ledger row play together", () => {
  const a = { seq: 1, ts: "2026-11-01T10:00:00.000Z" }, b = { seq: 1, ts: "2026-11-01T10:00:00.000Z" }, c = { seq: 2, ts: "2026-11-01T10:00:00.050Z" }, d = { seq: 3, ts: "2026-11-01T10:09:00.000Z" };
  assert.equal(r.replayDelayMs(a, b, 1), 0);
  assert.equal(r.replayDelayMs(a, c, 1), 420);
  assert.equal(r.replayDelayMs(c, d, 1), 900);
  assert.equal(r.replayDelayMs(a, c, 2), 210);
  assert.equal(r.fmtMs(null), "unavailable");
  assert.equal(r.fmtMs(12), "12 ms");
  assert.equal(r.fmtMs(1500), "1.50 s");
});

test("the recording is labelled as a recording and carries every stage's real timing, never an invented metric", () => {
  assert.equal(rec.label, "Recorded replay");
  assert.match(rec.note, /recording/i);
  for (const p of views) {
    assert.deepEqual(p.metrics.unavailable.map((u) => u.metric).sort(), ["latency_percentiles", "model_usage", "quality_score", "throughput"]);
    assert.ok(!("throughput" in p.metrics.measured));
  }
  assert.equal(rec.graph_proof.before_approval.edge_present, false);
  assert.equal(rec.graph_proof.after_approval.edge_present, true);
  assert.equal(rec.graph_proof.after_approval.edge.weight, null);
  assert.equal(rec.graph_proof.after_rollback.edge_present, false);
});
