// The display graph: eight modules and the cables between them, derived ONLY from the stage views of recorded events.
//   SOURCE -> PARSE -> VALIDATE -> RESOLVE -> LLM -> VERIFY -> REVIEW -> OUTPUT
// The language-model module is an optional branch off the deterministic lane. Cables show the dependencies that were actually recorded: when no model call was
// recorded the branch is drawn as skipped and the evidence stage is fed directly by the resolve stage.
import type { StageId } from "./types";
import type { StageView } from "./reduce";

export type NodeId = "SOURCE" | "PARSE" | "VALIDATE" | "RESOLVE" | "LLM" | "VERIFY" | "REVIEW" | "OUTPUT";
export type Kind = "ingest" | "deterministic" | "llm" | "verify" | "gate" | "output";
export interface NodeDef { id: NodeId; label: string; kind: Kind; from: StageId[]; blurb: string }
export const NODE_DEFS: NodeDef[] = [
  { id: "SOURCE", label: "Source", kind: "ingest", from: ["SOURCE"], blurb: "receive the file and store it by hash" },
  { id: "PARSE", label: "Parse", kind: "ingest", from: ["PARSE", "PROFILE"], blurb: "read rows and columns, profile the table" },
  { id: "VALIDATE", label: "Validate", kind: "deterministic", from: ["VALIDATE"], blurb: "check types and required fields against the contract" },
  { id: "RESOLVE", label: "Resolve", kind: "deterministic", from: ["RESOLVE"], blurb: "match identifiers to canonical entities, exact first, never fuzzy" },
  { id: "LLM", label: "Language model", kind: "llm", from: ["LLM"], blurb: "a model call, shown only when one was recorded" },
  { id: "VERIFY", label: "Verify", kind: "verify", from: ["EVIDENCE"], blurb: "quotes found in the stored source, direction and wording checked" },
  { id: "REVIEW", label: "Review", kind: "gate", from: ["REVIEW"], blurb: "a named person decides" },
  { id: "OUTPUT", label: "Output", kind: "output", from: ["PROMOTE"], blurb: "versioned release and overlay" },
];
export const NODE_OF_STAGE: Record<StageId, NodeId> = { SOURCE: "SOURCE", PARSE: "PARSE", PROFILE: "PARSE", VALIDATE: "VALIDATE", RESOLVE: "RESOLVE", LLM: "LLM", EVIDENCE: "VERIFY", REVIEW: "REVIEW", PROMOTE: "OUTPUT" };
export const LANE: NodeId[] = ["SOURCE", "PARSE", "VALIDATE", "RESOLVE", "VERIFY", "REVIEW", "OUTPUT"];

export interface NodeVM { id: NodeId; label: string; kind: Kind; state: string; hero: string; sub: string; durationMs: number | null; pips: [string, string][] | null; stages: StageView[] }
export type EdgeState = "FLOWED" | "HELD" | "AWAITING" | "IDLE" | "SKIPPED";
export interface EdgeVM { id: string; from: NodeId; to: NodeId; state: EdgeState; branch: boolean }
export interface Context { reviewer?: string | null; decided?: string | null }

const DONE = ["COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED_CHECKS", "APPROVED", "ROLLED_BACK"];
const bytes = (n: number | null | undefined) => (n == null ? "—" : n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} kB`);
const plural = (n: number | null | undefined, w: string) => (n == null ? "—" : `${n} ${w}${n === 1 ? "" : "s"}`);
const ms = (n: number | null | undefined) => (n == null ? "" : n < 1000 ? `${n} ms` : `${(n / 1000).toFixed(2)} s`);

/** One module's state from its recorded stage(s). Parse covers two recorded steps (parse, profile): it shows the later one once the earlier completed. */
function stateOf(def: NodeDef, by: Record<string, StageView>): string {
  const [a, b] = def.from.map((id) => by[id]);
  if (!b) return a.state;
  if (a.state === "QUEUED" || a.state === "RUNNING" || a.state === "FAILED" || a.state === "SKIPPED") return a.state;
  return b.state === "QUEUED" ? "COMPLETED" : b.state;
}

export function buildNodes(stages: StageView[], ctx: Context = {}): NodeVM[] {
  const by = Object.fromEntries(stages.map((s) => [s.id, s])) as Record<StageId, StageView>;
  return NODE_DEFS.map((def) => {
    const own = def.from.map((id) => by[id]), st = stateOf(def, by), main = own[own.length - 1], first = own[0];
    const dur = own.reduce<number | null>((t, s) => (s.durationMs == null ? t : (t ?? 0) + s.durationMs), null);
    const vErr = main.validation?.errors ?? 0;
    let hero = "—", sub = def.blurb, pips: NodeVM["pips"] = null;
    const reached = st !== "QUEUED";
    switch (def.id) {
      case "SOURCE": if (reached && first.records) { hero = bytes(first.records.processed); sub = st === "FAILED" ? (first.error?.message ?? "refused") : "stored by content hash"; } break;
      case "PARSE": if (reached) {
        hero = plural(by.PARSE.records?.processed, "row"); sub = by.PARSE.records?.columns != null ? `${by.PARSE.records.columns} columns` : sub;
        pips = [["parse", by.PARSE.state], ["profile", by.PROFILE.state]];
      } break;
      case "VALIDATE": if (reached && first.records) { hero = `${first.records.accepted ?? "—"}/${first.records.processed ?? "—"} rows`; sub = vErr ? plural(vErr, "error") : "typed against the contract"; } break;
      case "RESOLVE": if (reached && first.records) { hero = `${first.records.accepted ?? "—"}/${first.records.processed ?? "—"} ids`; const r = first.resolution; sub = r ? `${r.resolved} exact · ${r.mapped} mapped · ${r.ambiguous + r.unresolved} refused` : sub; } break;
      case "LLM":
        if (st === "SKIPPED") { hero = "not invoked"; sub = "no model call was recorded"; }
        else if (reached) {
          const l = first.llm;
          hero = st === "FAILED" ? "failed" : l?.model ?? (st === "RUNNING" ? "running" : "completed");
          sub = st === "FAILED" ? first.error?.type ?? "call failed" : [l?.provider, l?.latency_ms != null ? ms(l.latency_ms) : null, l?.input_tokens != null || l?.output_tokens != null ? `${l?.input_tokens ?? "?"}/${l?.output_tokens ?? "?"} tok` : null].filter(Boolean).join(" · ") || "provider details not recorded";
        } break;
      case "VERIFY": if (reached && first.records) {
        hero = vErr ? "rejected" : st === "COMPLETED_WITH_WARNINGS" ? "asserted" : first.records.accepted ? "supported" : "—";
        sub = vErr ? Object.keys(main.validation?.codes ?? {})[0]?.replace(/_/g, " ").toLowerCase() ?? plural(vErr, "error") : st === "COMPLETED_WITH_WARNINGS" ? "no explicit wording; needs a reviewer" : `${first.records.accepted}/${first.records.processed} rows accepted`;
      } break;
      case "REVIEW":
        hero = st === "AWAITING_REVIEW" ? "awaiting" : st === "BLOCKED" ? "blocked" : st === "APPROVED" ? "approved" : st === "REJECTED" ? "rejected" : st === "ROLLED_BACK" ? "rolled back" : "—";
        sub = st === "AWAITING_REVIEW" ? "a named reviewer must decide" : st === "BLOCKED" ? "cannot be approved" : (st === "APPROVED" || st === "REJECTED") && ctx.decided ? `by ${ctx.decided}` : def.blurb; break;
      case "OUTPUT": {
        const d = first.destination;
        hero = st === "ROLLED_BACK" ? "rolled back" : st === "COMPLETED" && d ? `v${d.version}` : st === "SKIPPED" ? "not promoted" : "—";
        sub = st === "COMPLETED" && d ? `${d.dataset} · studio overlay` : st === "ROLLED_BACK" ? "overlay effect reversed" : st === "SKIPPED" ? "nothing was released" : def.blurb; break;
      }
    }
    if (!reached) sub = def.blurb;
    return { id: def.id, label: def.label, kind: def.kind, state: st, hero, sub, durationMs: dur, pips, stages: own };
  });
}

export function buildEdges(nodes: NodeVM[]): EdgeVM[] {
  const st = Object.fromEntries(nodes.map((n) => [n.id, n.state])) as Record<NodeId, string>;
  const ran = ["RUNNING", "COMPLETED", "FAILED"].includes(st.LLM);              // a model call was recorded
  const lane = (a: NodeId, b: NodeId): EdgeState => {
    const sa = st[a], sb = st[b];
    if (b === "REVIEW") return sb === "AWAITING_REVIEW" ? "AWAITING" : sb === "BLOCKED" ? "HELD" : ["APPROVED", "REJECTED"].includes(sb) ? "FLOWED" : "IDLE";
    if (a === "REVIEW") return ["COMPLETED", "ROLLED_BACK"].includes(sb) ? "FLOWED" : sb === "SKIPPED" && ["BLOCKED", "REJECTED"].includes(sa) ? "HELD" : "IDLE";
    if (!DONE.includes(sa)) return "IDLE";
    return sb === "QUEUED" ? "IDLE" : sb === "SKIPPED" ? "HELD" : "FLOWED";
  };
  const edges: EdgeVM[] = [];
  for (let i = 0; i < LANE.length - 1; i++) {
    const a = LANE[i], b = LANE[i + 1];
    let state = lane(a, b);
    if (a === "RESOLVE" && b === "VERIFY" && ran) state = "IDLE";                  // the evidence stage was fed by the model's output instead
    edges.push({ id: `${a}-${b}`, from: a, to: b, state, branch: false });
  }
  const toLlm: EdgeState = st.LLM === "SKIPPED" ? "SKIPPED" : ran ? "FLOWED" : "IDLE";
  const fromLlm: EdgeState = st.LLM === "SKIPPED" ? "SKIPPED" : st.LLM === "COMPLETED" ? (st.VERIFY === "QUEUED" ? "IDLE" : "FLOWED") : st.LLM === "FAILED" ? "HELD" : "IDLE";
  edges.push({ id: "RESOLVE-LLM", from: "RESOLVE", to: "LLM", state: toLlm, branch: true }, { id: "LLM-VERIFY", from: "LLM", to: "VERIFY", state: fromLlm, branch: true });
  return edges;
}

/** Whether a given edge carries a recorded pulse right now: an event for the stage it feeds must have been applied (the caller supplies timestamps). */
export const feeds = (e: EdgeVM): NodeId => e.to;
export type Selection = { kind: "node"; id: NodeId } | { kind: "edge"; id: string } | null;
export const neighbours = (id: NodeId, edges: EdgeVM[]): Set<NodeId> => new Set(edges.filter((e) => e.from === id || e.to === id).flatMap((e) => [e.from, e.to]));
