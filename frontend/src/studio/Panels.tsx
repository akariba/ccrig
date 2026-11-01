// The supporting panels. Each shows only what the recorded events have reached: a panel never reveals a result before the stage that produced it.
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { STAGE_DEFS, clock, fmtMs, shortHash, type StageView } from "./reduce";
import type { Selection } from "./FlowCanvas";
import { STATE_COLOR, STATE_LABEL } from "./states";
import type { Assessment, FlowEvent, GraphProof, MentionItem, Preview, Projection, QuoteAssessment, SupportMatrix } from "./types";

const reached = (stages: StageView[], id: string) => stages.find((s) => s.id === id)?.state !== "QUEUED";
const flat = (v: unknown): string => (v == null ? "—" : typeof v === "object" ? JSON.stringify(v).slice(0, 160) : String(v));

export function Badge({ state, children }: { state: string; children?: ReactNode }) {
  const c = STATE_COLOR[state] ?? "#8aa0b2";
  return <span className="ds-badge" style={{ color: c, borderColor: c }}>{children ?? STATE_LABEL[state] ?? state}</span>;
}
export function KV({ rows }: { rows: [string, unknown][] }) {
  return <dl className="ds-kv">{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd title={flat(v)}>{flat(v)}</dd></div>)}</dl>;
}
function Marked({ m }: { m: MentionItem }) {
  const a = m.context_offset, b = a + (m.end - m.start);
  return <>{m.context.slice(0, a)}<mark>{m.context.slice(a, b)}</mark>{m.context.slice(b)}</>;
}

// ---------------------------------------------------------------- Source Inspector
export function SourceInspector({ proj, preview, stages }: { proj: Projection | null; preview: Preview | null; stages: StageView[] }) {
  const [all, setAll] = useState(false);
  const doc = proj?.source_documents[0];
  const mentions = doc?.mentions ?? preview?.mentions ?? [], entities = doc?.entities ?? preview?.entities ?? [], total = doc?.mention_total ?? preview?.mention_total ?? 0;
  const shown = all ? mentions : mentions.slice(0, 5);
  return (
    <div data-testid="source-inspector">
      <div className="ds-lab">Submitted file</div>
      {proj && reached(stages, "SOURCE") ? (
        <KV rows={[["file", proj.job.filename], ["format", proj.job.format], ["bytes", proj.job.bytes], ["sha-256", shortHash(proj.job.sha256)], ["source id", proj.job.source_id], ["target contract", proj.job.target],
                   ["classification", proj.job.classification], ["submitted by", proj.job.operator], ["rows parsed", stages[1].records?.processed ?? "—"], ["columns", stages[1].records?.columns ?? "—"]]} />
      ) : <p className="ds-muted">Nothing submitted yet. Choose a claim above to start a real job.</p>}
      <div className="ds-lab" style={{ marginTop: 12 }}>Evidence document {doc ? "(stored by hash)" : preview ? "(stored excerpt, not yet submitted)" : ""}</div>
      {doc || preview ? (
        <>
          <KV rows={[["title", doc ? proj?.proposal[0]?.provenance.source_title ?? "—" : preview?.source_title], ["published", doc?.source_published_date ?? preview?.published_date], ["publisher", doc?.source_publisher ?? "approved source"],
                     ["tier", doc?.source_tier ?? "—"], ["url", doc?.source_url ?? preview?.source_url], ["sha-256", shortHash(doc?.source_sha256 ?? preview?.sha256)], ["bytes", doc?.bytes ?? preview?.bytes],
                     ["text characters", doc?.text_chars ?? preview?.text_chars], ["quote found verbatim", preview ? (preview.quote_found_verbatim ? "yes" : "no") : doc ? (doc.stored ? "checked at the evidence stage" : "document missing") : "—"]]} />
          <div className="ds-lab" style={{ marginTop: 10 }}>Company mentions · {total} found by deterministic name, brand and ticker rules</div>
          <div className="ds-chips">{entities.map((e) => <span key={e.entity_id} className="ds-chip" data-testid={`mention-chip-${e.entity_id}`}>{e.name}<em>{e.entity_id} ×{e.count}</em></span>)}</div>
          <ul className="ds-ctx" data-testid="mention-list">{shown.map((m, i) => <li key={i}><b>{m.entity_id}</b> <span><Marked m={m} /></span></li>)}</ul>
          {mentions.length > 5 && <button className="ds-btn ghost" type="button" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show ${mentions.length - 5} more`}</button>}
          <p className="ds-muted">A mention is not a relationship: two names in one document establish nothing until the evidence stage finds wording that states how they are related.</p>
        </>
      ) : <p className="ds-muted">No evidence document available.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- Quality & Resolution Inspector
function Quote({ q, a }: { q: QuoteAssessment; a: Assessment }) {
  const marks = [...q.spans].sort((x, y) => x.start - y.start);
  const parts: ReactNode[] = []; let at = 0;
  marks.forEach((s, i) => { if (s.start < at) return; parts.push(q.quote.slice(at, s.start)); parts.push(<mark key={i} className={s.role}>{q.quote.slice(s.start, s.end)}</mark>); at = s.end; });
  parts.push(q.quote.slice(at));
  return (
    <blockquote data-testid="assessment-quote">
      {parts}
      <footer>
        {q.both ? <>between the two names: <code>{JSON.stringify(q.between)}</code> · wording for {a.relation} found: <b>{q.cue ? `"${q.cue}"` : "none"}</b>{q.cue ? ` (${q.direction_ok ? "direction consistent" : "points the other way"})` : ""}</>
                : <>this passage does not name both companies</>}
        {" · "}{q.found_in_stored_source === true ? "found verbatim in the stored document" : q.found_in_stored_source === false ? "NOT found in the stored document" : "stored document unavailable"}
      </footer>
    </blockquote>
  );
}

export function QualityInspector({ proj, stages }: { proj: Projection | null; stages: StageView[] }) {
  if (!proj) return <div data-testid="quality-inspector"><p className="ds-muted">Quality and resolution results appear here as each stage records them.</p></div>;
  const res = stages.find((s) => s.id === "RESOLVE");
  const mappings = ((proj.stages.find((s) => s.id === "RESOLVE")?.outputs?.mappings as { value: string; entity_id: string; rule: string }[] | undefined) ?? []);
  const stageFindings = STAGE_DEFS.filter((d) => reached(stages, d.id)).map((d) => ({ d, items: proj.stages.find((s) => s.id === d.id)?.findings ?? [], v: stages.find((s) => s.id === d.id)?.validation })).filter((x) => x.v && (x.v.errors || x.v.warnings));
  return (
    <div data-testid="quality-inspector">
      <div className="ds-lab">Validation findings</div>
      {stageFindings.length ? stageFindings.map(({ d, items }) => (
        <div key={d.id} className="ds-fgroup" data-testid={`findings-${d.id}`}>
          <b>{d.label}</b>
          {items.map((f, i) => <div key={i} className={"ds-find " + f.severity.toLowerCase()}><code>{f.code}</code><span>{f.message}</span></div>)}
        </div>))
        : <p className="ds-muted">{reached(stages, "VALIDATE") ? "No findings recorded so far." : "Waiting for validation."}</p>}
      <div className="ds-lab" style={{ marginTop: 12 }}>Entity resolution · exact identifiers first, never fuzzy</div>
      {res?.resolution ? (
        <>
          <KV rows={[["distinct identifiers", res.resolution.distinct_identifiers], ["resolved", res.resolution.resolved], ["mapped (needs acknowledgement)", res.resolution.mapped], ["ambiguous", res.resolution.ambiguous], ["unresolved", res.resolution.unresolved]]} />
          {mappings.map((m, i) => <div key={i} className="ds-find warn"><code>{m.rule}</code><span>{m.value} → {m.entity_id}</span></div>)}
          <p className="ds-muted">Issuer, portfolio and CCR counterparty identifiers are resolved in their own universes and are never merged.</p>
        </>
      ) : <p className="ds-muted">Not reached.</p>}
      <div className="ds-lab" style={{ marginTop: 12 }}>Evidence assessment</div>
      {reached(stages, "EVIDENCE") && proj.assessments.length ? proj.assessments.map((a) => (
        <div key={a.row} className="ds-assess" data-testid="assessment" data-verdict={a.verdict}>
          <div className="ds-assess-h"><b>{a.source} <span className="rel">—{a.relation}→</span> {a.target}</b><span className={"ds-verdict " + a.verdict.toLowerCase()} data-testid="assessment-verdict">{a.verdict.replace(/_/g, " ").toLowerCase()}</span></div>
          {a.semantics && <div className="ds-muted">direction as stored: {a.semantics.direction}</div>}
          {a.quotes.map((q, i) => <Quote key={i} q={q} a={a} />)}
          <p className="ds-why">{a.why}</p>
          {typeof a.assertion.rationale === "string" && <p className="ds-muted">Proposer's written rationale: “{a.assertion.rationale}”</p>}
        </div>))
        : <p className="ds-muted">{reached(stages, "EVIDENCE") ? "No relationship rows to assess." : "Not reached."}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- Execution Timeline
export function Timeline({ events, cursor, onStage, ledger }: { events: FlowEvent[]; cursor: number; onStage: (id: string) => void; ledger?: { ok: boolean; events: number } }) {
  const shown = events.slice(0, cursor);
  const max = Math.max(1, ...shown.map((e) => e.elapsed_ms ?? 0));
  return (
    <div data-testid="timeline">
      <div className="ds-muted">{shown.length} of {events.length} recorded events{ledger ? ` · ledger hash chain ${ledger.ok ? "verified" : "BROKEN"}` : ""}. Timestamps are as recorded.</div>
      <ol className="ds-tl">
        {shown.map((e, i) => {
          const prev = shown[i - 1], dt = prev ? Date.parse(e.ts) - Date.parse(prev.ts) : null;
          const bad = e.state && ["FAILED", "FAILED_CHECKS", "BLOCKED", "REJECTED"].includes(e.state);
          return (
            <li key={e.id} data-testid="timeline-row" data-event-id={e.id} data-type={e.type} className={bad ? "bad" : e.type === "ROLLED_BACK" ? "rb" : ""} onClick={() => e.stage_id && onStage(e.stage_id)}>
              <time title={e.ts}>{clock(e.ts)}</time><i>{dt == null ? "" : dt < 1000 ? `+${dt}ms` : `+${(dt / 1000).toFixed(1)}s`}</i>
              <b>{e.stage_id ?? "JOB"}</b><span>{e.type.toLowerCase().replace(/_/g, " ")}</span>
              <em title={e.hash}>{summary(e)}</em>
              {e.elapsed_ms != null && <u style={{ width: `${Math.max(3, (e.elapsed_ms / max) * 100)}%` }} title={fmtMs(e.elapsed_ms)} />}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
function summary(e: FlowEvent): string {
  if (e.error) return `${e.error.type}: ${e.error.message}`;
  if (e.destination) return `${e.destination.dataset} v${e.destination.version} (${e.destination.kind.toLowerCase().replace(/_/g, " ")})`;
  if (e.validation) return `${e.validation.errors} error(s), ${e.validation.warnings} warning(s): ${Object.keys(e.validation.codes).join(", ")}`;
  if (e.records) return `${e.records.processed ?? "?"} ${e.records.unit} → ${e.records.accepted ?? "?"} accepted, ${e.records.rejected ?? "?"} rejected${e.elapsed_ms != null ? ` · ${fmtMs(e.elapsed_ms)}` : ""}`;
  if (e.elapsed_ms != null) return fmtMs(e.elapsed_ms);
  return e.message;
}

// ---------------------------------------------------------------- Selection dock (node or connection)
export function SelectionDock({ selected, stages, proj, events, cursor }: { selected: Selection; stages: StageView[]; proj: Projection | null; events: FlowEvent[]; cursor: number }) {
  if (!selected) return <div className="ds-dock" data-testid="selection-dock"><span className="ds-lab">Selection</span><p className="ds-muted">Select a stage to see what went in, what came out, its findings and its history; select a cable to see what data passed between two stages.</p></div>;
  if (selected.kind === "conn") {
    const c = proj?.connections.find((x) => x.from === selected.from && x.to === selected.to);
    const a = stages.find((s) => s.id === selected.from)!, b = stages.find((s) => s.id === selected.to)!;
    const state = a.state === "QUEUED" ? "IDLE" : b.state === "QUEUED" ? "IDLE" : c?.state ?? "—";
    return (
      <div className="ds-dock" data-testid="selection-dock" data-kind="conn">
        <span className="ds-lab">Connection</span><h3>{a.label} → {b.label}</h3>
        <KV rows={[["upstream", STATE_LABEL[a.state]], ["downstream", STATE_LABEL[b.state]], ["passed", state === "IDLE" ? "nothing yet" : c?.what ?? "—"], ["gate", state === "AWAITING" ? "paused: waiting for a named reviewer" : state === "HELD" ? "held: the next stage refused it, see its findings" : "open"]]} />
        <p className="ds-muted">A cable carries particles only for a moment after a recorded event for the stage it feeds. A dashed rose cable stops where the data was refused.</p>
      </div>
    );
  }
  const def = STAGE_DEFS.find((d) => d.id === selected.id)!, v = stages.find((s) => s.id === selected.id)!, info = proj?.stages.find((s) => s.id === selected.id);
  const own = events.slice(0, cursor).filter((e) => e.stage_id === selected.id);
  const gated = v.state !== "QUEUED";
  return (
    <div className="ds-dock" data-testid="selection-dock" data-kind="node" data-stage={selected.id}>
      <span className="ds-lab">Stage {STAGE_DEFS.findIndex((d) => d.id === selected.id) + 1} · {def.hint}</span>
      <h3>{def.label} <Badge state={v.state} /></h3>
      <div className="ds-dock-cols">
        <div><div className="ds-lab">Input</div>{gated && info?.inputs ? <KV rows={Object.entries(info.inputs)} /> : <p className="ds-muted">{gated ? "recorded as the previous stage's output" : "not reached"}</p>}</div>
        <div><div className="ds-lab">Output</div>{gated && info?.outputs ? <KV rows={Object.entries(info.outputs).filter(([, x]) => x != null)} /> : v.records ? <KV rows={[["processed", v.records.processed], ["accepted", v.records.accepted], ["rejected", v.records.rejected]]} /> : <p className="ds-muted">{gated ? "none recorded" : "not reached"}</p>}</div>
        <div>
          <div className="ds-lab">Findings</div>
          {gated && info?.findings.length ? info.findings.slice(0, 6).map((f, i) => <div key={i} className={"ds-find " + f.severity.toLowerCase()}><code>{f.code}</code><span>{f.message}</span></div>) : <p className="ds-muted">{gated ? "none" : "not reached"}</p>}
          {v.error && <div className="ds-find error"><code>{v.error.type}</code><span>{v.error.message}</span></div>}
          {v.message && <p className="ds-muted">{v.message}</p>}
        </div>
        <div><div className="ds-lab">History</div>{own.length ? <ul className="ds-hist">{own.map((e) => <li key={e.id}><time>{clock(e.ts)}</time> {e.type.toLowerCase().replace(/_/g, " ")}{e.elapsed_ms != null ? ` · ${fmtMs(e.elapsed_ms)}` : ""}</li>)}</ul> : <p className="ds-muted">no events yet</p>}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Review, destination, support
export function ReviewPanel(p: {
  proj: Projection | null; stages: StageView[]; canAct: boolean; replayNote: string | null; busy: boolean; error: string | null; decisionsShown: number;
  onApprove: (name: string, reason: string, ack: boolean) => void; onReject: (name: string, reason: string) => void;
}) {
  const [name, setName] = useState(""), [reason, setReason] = useState(""), [ack, setAck] = useState(false);
  const review = p.proj?.review, rv = p.stages.find((s) => s.id === "REVIEW")!;
  const need = review?.requires?.acknowledge_assertions;
  const ready = name.trim().length > 0 && reason.trim().length > 0 && (!need || ack);
  const decisions = review?.decisions.slice(0, p.decisionsShown) ?? [];
  return (
    <div data-testid="review-panel" data-state={rv.state}>
      <div className="ds-lab">Review gate <Badge state={rv.state} /></div>
      {!p.proj || rv.state === "QUEUED" ? <p className="ds-muted">The proposal reaches the gate after the evidence stage.</p> : null}
      {rv.state === "BLOCKED" && <div data-testid="review-blocked"><p>This proposal cannot be approved. It is held at the gate because of:</p>{review?.blocked_because?.map((b, i) => <div key={i} className="ds-find error"><code>{b.code}</code><span>{b.message}</span></div>)}</div>}
      {rv.state === "AWAITING_REVIEW" && review && (
        <div>
          <p>Waiting for a named reviewer. Approval publishes to the Studio workspace and its overlay only; it does not modify canonical data or any score.</p>
          {need && <div className="ds-callout" data-testid="review-assert-note">The relationship <b>{review.requires!.assertions_to_confirm.map((a) => `${a[0]} ${a[1]} ${a[2]}`).join(", ")}</b> is asserted by the proposer. No wording in the quoted text states it. The reviewer must confirm it explicitly.</div>}
          {p.canAct ? (
            <div className="ds-form">
              <label>Reviewer name<input data-testid="review-name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="who is deciding" /></label>
              <label>Reason<textarea data-testid="review-reason" value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} placeholder="what you checked" rows={2} /></label>
              {need && <label className="ds-check"><input data-testid="review-ack" type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I have read the quoted passage and confirm the asserted relationship is supported by it.</label>}
              <div className="ds-row">
                <button type="button" className="ds-btn primary" data-testid="review-approve" disabled={!ready || p.busy} onClick={() => p.onApprove(name.trim(), reason.trim(), ack)}>Approve</button>
                <button type="button" className="ds-btn" data-testid="review-reject" disabled={!name.trim() || !reason.trim() || p.busy} onClick={() => p.onReject(name.trim(), reason.trim())}>Reject</button>
              </div>
              {p.error && <div className="ds-find error" data-testid="review-error"><span>{p.error}</span></div>}
            </div>
          ) : <p className="ds-muted" data-testid="review-readonly">{p.replayNote ?? "Review is available to the operator only."}</p>}
        </div>
      )}
      {decisions.length > 0 && (
        <table className="ds-table" data-testid="decision-history"><thead><tr><th>Decision</th><th>Reviewer</th><th>When</th><th>Reason</th></tr></thead>
          <tbody>{decisions.map((d, i) => <tr key={i}><td>{d.decision}</td><td>{d.reviewer}</td><td>{d.at.slice(0, 19).replace("T", " ")}</td><td>{d.reason}</td></tr>)}</tbody></table>
      )}
    </div>
  );
}

export function DestinationPanel(p: {
  proj: Projection | null; status: string; live: boolean; proof: { before: GraphProof; live: GraphProof; after: GraphProof } | null; canAct: boolean; busy: boolean; error: string | null;
  onRollback: (name: string, reason: string) => void;
}) {
  const [name, setName] = useState(""), [reason, setReason] = useState("");
  const d = p.proj?.destination;
  return (
    <div data-testid="destination-panel" data-status={p.status}>
      <div className="ds-lab">Destination <Badge state={p.status === "LIVE_IN_OVERLAY" ? "APPROVED" : p.status === "ROLLED_BACK" ? "ROLLED_BACK" : "QUEUED"}>{p.status.replace(/_/g, " ").toLowerCase()}</Badge></div>
      <KV rows={[["destination", d ? `${d.dataset} · ${d.kind.toLowerCase().replace(/_/g, " ")}` : "relationship_evidence · studio overlay"], ["canonical data modified", "no"], ["scores, weights, distance map", "unchanged"]]} />
      {d && p.status === "LIVE_IN_OVERLAY" && d.edges.map((e, i) => <div key={i} className="ds-find ok" data-testid="overlay-edge"><code>{e.relation}</code><span>{e.source} → {e.target} is visible in the approved-relationship overlay</span></div>)}
      {p.live && p.status === "LIVE_IN_OVERLAY" && d && (
        <div className="ds-row" style={{ marginTop: 8 }}>{d.links.map((l) => <Link key={l.href} className="ds-btn primary" data-testid={l.testid} to={l.href}>{l.label}</Link>)}</div>
      )}
      {p.status === "LIVE_IN_OVERLAY" && d?.adoption && (
        <div data-testid="adoption">
          <div className="ds-lab" style={{ marginTop: 10 }}>What approval changed</div>
          <KV rows={[["issuers with a documented relationship", `${flat((d.adoption.connectivity.canonical as Record<string, unknown>)?.issuers_with_a_documented_relationship)} → ${flat((d.adoption.connectivity.with_approved as Record<string, unknown>)?.issuers_with_a_documented_relationship)}`],
                     ["newly connected issuers", ((d.adoption.connectivity.newly_connected_issuers as string[]) ?? []).join(", ") || "none"], ["scoring changed by approval", d.adoption.scoring_changed_by_approval ? "yes" : "no"],
                     ["portfolio holders of the endpoints", [...new Set(d.adoption.linked_counterparties.portfolio_holdings.map((h) => h.counterparty))].join(", ") || "none"],
                     ["CCR trades referencing the endpoints", Object.entries(d.adoption.linked_counterparties.ccr_reference_entities).map(([k, v]) => `${k}: ${v.length ? v.map((x) => `${x.ccr_counterparty} (${x.product})`).join(", ") : "none"}`).join("; ")]]} />
          <ul className="ds-gaps">{d.adoption.gaps.map((g, i) => <li key={i}>{g}</li>)}</ul>
        </div>
      )}
      {p.proof && (
        <div data-testid="graph-proof">
          <div className="ds-lab" style={{ marginTop: 10 }}>Graph Explorer, as recorded (ego network of ORCL, approved relationships included)</div>
          <table className="ds-table"><thead><tr><th>When</th><th>NVDA → ORCL edge</th><th>Evidence</th></tr></thead><tbody>
            {([["before approval", p.proof.before], ["after approval", p.proof.live], ["after rollback", p.proof.after]] as [string, GraphProof][]).map(([w, g]) => (
              <tr key={w}><td>{w}</td><td>{g.edge_present ? "present" : "absent"}</td><td>{g.edge ? `${g.edge.evidence_status}, weight ${g.edge.weight ?? "none"}, ${g.edge.provenance.source_publisher}, ${g.edge.provenance.source_published_date}, ${g.edge.assertion}` : "—"}</td></tr>))}
          </tbody></table>
        </div>
      )}
      {p.status === "LIVE_IN_OVERLAY" && p.canAct && (
        <div className="ds-form" style={{ marginTop: 10 }}>
          <div className="ds-lab">Roll back</div>
          <label>Reviewer name<input data-testid="rollback-name" value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label>Reason<input data-testid="rollback-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          <button type="button" className="ds-btn" data-testid="rollback-btn" disabled={!name.trim() || !reason.trim() || p.busy} onClick={() => p.onRollback(name.trim(), reason.trim())}>Roll back the approved relationship</button>
          {p.error && <div className="ds-find error"><span>{p.error}</span></div>}
          <p className="ds-muted">Rollback returns to the previous approved state. The decision history and the event ledger are kept.</p>
        </div>
      )}
      {p.status === "ROLLED_BACK" && <p className="ds-muted" data-testid="rolled-back-note">The approved relationship was rolled back: it no longer appears in the overlay. The approval, the rollback and every event stay in the history.</p>}
    </div>
  );
}

export function SupportTable({ support }: { support: SupportMatrix | null }) {
  if (!support) return null;
  return (
    <div data-testid="support-matrix">
      <table className="ds-table"><thead><tr><th>Domain</th><th>Support today</th><th>What works</th><th>What does not</th></tr></thead>
        <tbody>{support.domains.map((d) => <tr key={d.dataset} data-level={d.level}><td>{d.label}<br /><code>{d.dataset}</code></td><td><span className={"ds-level " + d.level.toLowerCase()}>{d.level.replace("_", " ").toLowerCase()}</span></td><td>{d.supported}</td><td>{d.limits}</td></tr>)}</tbody></table>
      <table className="ds-table" style={{ marginTop: 10 }}><thead><tr><th>Source type</th><th>Support</th><th>Note</th></tr></thead>
        <tbody>{support.formats.map((f) => <tr key={f.format}><td>{f.format}</td><td><span className={"ds-level " + f.level.toLowerCase()}>{f.level.toLowerCase()}</span></td><td>{f.note}</td></tr>)}</tbody></table>
    </div>
  );
}
