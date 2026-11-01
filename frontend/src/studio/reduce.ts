// Pure rules that turn a list of recorded flow events into what the page shows. No React, no imports of values: the same list of events, cut at any point,
// always gives the same stage states, so a replay is exactly the recorded history up to that point. Mirrors backend/app/studio/flow.py (project()).
import type { FlowEvent, Records, StageId } from "./types";

export const STAGE_DEFS: { id: StageId; label: string; hint: string }[] = [
  { id: "SOURCE", label: "Source", hint: "receive and store the file" },
  { id: "PARSE", label: "Parse", hint: "read rows and columns" },
  { id: "PROFILE", label: "Profile", hint: "types, completeness, duplicates" },
  { id: "VALIDATE", label: "Validate", hint: "contract: types, required fields" },
  { id: "RESOLVE", label: "Resolve", hint: "match identifiers, exact first" },
  { id: "EVIDENCE", label: "Evidence", hint: "quotes, direction, staged comparison" },
  { id: "REVIEW", label: "Review", hint: "a named person decides" },
  { id: "PROMOTE", label: "Promote", hint: "versioned release and overlay" },
];
export const STAGE_ORDER = STAGE_DEFS.map((s) => s.id);

export interface StageView {
  id: StageId; label: string; state: string; records: Records | null; durationMs: number | null; startedTs: string | null; lastTs: string | null; message: string | null;
  validation: { errors: number; warnings: number; codes: Record<string, number> } | null; resolution: FlowEvent["resolution"]; error: FlowEvent["error"];
  destination: FlowEvent["destination"]; eventIds: string[];
}

export const emptyStage = (id: StageId, label: string): StageView => ({ id, label, state: "QUEUED", records: null, durationMs: null, startedTs: null, lastTs: null, message: null, validation: null, resolution: null, error: null, destination: null, eventIds: [] });

/** Stage views after applying the first `upto` events (all of them when omitted). */
export function reduceStages(events: FlowEvent[], upto: number = events.length): StageView[] {
  const views: Record<string, StageView> = Object.fromEntries(STAGE_DEFS.map((s) => [s.id, emptyStage(s.id, s.label)]));
  for (const e of events.slice(0, upto)) {
    if (!e.stage_id) continue;
    const v = views[e.stage_id];
    v.eventIds.push(e.id);
    if (e.state && !(e.type === "VALIDATION_RESULT" && v.state === "FAILED")) v.state = e.state;     // a stage that failed outright stays failed
    if (e.type === "STAGE_STARTED" && !v.startedTs) v.startedTs = e.ts;
    v.lastTs = e.ts;
    if (e.elapsed_ms != null && ["STAGE_COMPLETED", "STAGE_FAILED", "STEP_COMPLETED"].includes(e.type)) v.durationMs = (v.durationMs ?? 0) + e.elapsed_ms;
    if (e.records) v.records = e.records;
    if (e.validation) v.validation = e.validation;
    if (e.resolution) v.resolution = e.resolution;
    if (e.error) v.error = e.error;
    if (e.destination) v.destination = e.destination;
    if (e.message && ["STAGE_SKIPPED", "REVIEW_BLOCKED", "REVIEW_AWAITING"].includes(e.type)) v.message = e.message;
  }
  return STAGE_ORDER.map((id) => views[id]);
}

export interface ConnView { from: StageId; to: StageId; state: "FLOWED" | "HELD" | "AWAITING" | "IDLE" }

export function reduceConnections(stages: StageView[]): ConnView[] {
  const done = ["COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED_CHECKS", "APPROVED", "ROLLED_BACK"];
  const out: ConnView[] = [];
  for (let i = 0; i < stages.length - 1; i++) {
    const a = stages[i], b = stages[i + 1];
    let state: ConnView["state"];
    if (b.id === "REVIEW") state = b.state === "AWAITING_REVIEW" ? "AWAITING" : b.state === "BLOCKED" ? "HELD" : ["APPROVED", "REJECTED"].includes(b.state) ? "FLOWED" : "IDLE";
    else if (a.id === "REVIEW") state = ["COMPLETED", "ROLLED_BACK"].includes(b.state) ? "FLOWED" : b.state === "SKIPPED" && ["BLOCKED", "REJECTED"].includes(a.state) ? "HELD" : "IDLE";
    else state = done.includes(a.state) && !["QUEUED", "SKIPPED"].includes(b.state) ? "FLOWED" : done.includes(a.state) && b.state === "SKIPPED" ? "HELD" : "IDLE";
    out.push({ from: a.id, to: b.id, state });
  }
  return out;
}

/** The job's overall state from its stage views. */
export function jobState(stages: StageView[]): string {
  const by = Object.fromEntries(stages.map((s) => [s.id, s.state])) as Record<StageId, string>;
  if (by.PROMOTE === "ROLLED_BACK") return "ROLLED_BACK";
  if (by.REVIEW === "APPROVED") return "APPROVED";
  if (by.REVIEW === "REJECTED") return "REJECTED";
  if (by.REVIEW === "BLOCKED") return "BLOCKED";
  if (by.REVIEW === "AWAITING_REVIEW") return "AWAITING_REVIEW";
  if (stages.some((s) => s.state === "FAILED")) return "FAILED";
  if (stages.some((s) => s.state === "RUNNING")) return "RUNNING";
  return stages.every((s) => s.state === "QUEUED") ? "IDLE" : "RUNNING";
}

/** Where the data stands: not promoted, live in the overlay, or rolled back. */
export function destinationStatus(events: FlowEvent[], upto: number = events.length): "NOT_PROMOTED" | "LIVE_IN_OVERLAY" | "ROLLED_BACK" {
  let status: "NOT_PROMOTED" | "LIVE_IN_OVERLAY" | "ROLLED_BACK" = "NOT_PROMOTED";
  for (const e of events.slice(0, upto)) {
    if (e.type === "PROMOTED") status = "LIVE_IN_OVERLAY";
    else if (e.type === "ROLLED_BACK") status = "ROLLED_BACK";
    else if (e.type === "RESTORED") status = "LIVE_IN_OVERLAY";
  }
  return status;
}

/** Pacing of a replay. Recorded timestamps are shown unchanged; only the pause between steps is compressed for viewing (a human wait of minutes is not played back). */
export function replayDelayMs(prev: FlowEvent | undefined, next: FlowEvent, speed: number): number {
  if (!prev || prev.seq === next.seq) return 0;
  const gap = Date.parse(next.ts) - Date.parse(prev.ts);
  return (gap > 1000 ? 900 : 420) / Math.max(0.25, speed);
}

export const fmtMs = (ms: number | null | undefined): string => (ms == null ? "unavailable" : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(2)} s`);
export const shortHash = (h: string | null | undefined): string => (h ? `${h.slice(0, 8)}…${h.slice(-4)}` : "—");
export const clock = (ts: string): string => ts.slice(11, 23);

/** Index of the first event of a given type, or -1. */
export const firstIndex = (events: FlowEvent[], type: string): number => events.findIndex((e) => e.type === type);

/** Which saved snapshot of a recorded job to show at a given point of the replay: the state of the job's data changes only at approval and rollback. */
export function snapshotKey(events: FlowEvent[], upto: number): "after_ingest" | "after_approval" | "after_rollback" {
  const rolled = firstIndex(events, "ROLLED_BACK"), approved = firstIndex(events, "REVIEW_APPROVED");
  if (rolled >= 0 && upto > rolled) return "after_rollback";
  if (approved >= 0 && upto > approved) return "after_approval";
  return "after_ingest";
}
