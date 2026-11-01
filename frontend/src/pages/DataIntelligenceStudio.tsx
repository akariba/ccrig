// Data Intelligence Studio: watch a real source move through acquisition, parsing, validation, entity resolution, evidence review and promotion.
// Layout follows the "Ingest Bench" reference (title block, status bar, optical bench, three instrument panels, specification table, event log);
// the cables follow the "Neural Cable Graph" reference. Everything shown is recorded processing - see src/studio/*.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "../studio/studio.css";
import { FlowCanvas, type Selection } from "../studio/FlowCanvas";
import { STATE_LABEL } from "../studio/states";
import { DestinationPanel, QualityInspector, ReviewPanel, SelectionDock, SourceInspector, SupportTable, Timeline } from "../studio/Panels";
import { OpError, getToken, loadRecording, readStatus, setToken, streamEvents, studioApi, type JobRow } from "../studio/api";
import { STAGE_DEFS, destinationStatus, fmtMs, jobState, reduceConnections, reduceStages, replayDelayMs, shortHash, snapshotKey } from "../studio/reduce";
import type { FlowEvent, Preview, Projection, Recording, ScenarioInfo, StageId, SupportMatrix } from "../studio/types";

type Access = { kind: "loading" } | { kind: "static" | "offline" | "disabled" | "needs-token" | "rejected" | "ready"; note?: string };
const SCENARIO = "oracle-nvidia";
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const msg = (e: unknown) => (e instanceof OpError ? `${e.code}: ${e.message}` : e instanceof Error ? e.message : String(e));

export function DataIntelligenceStudio() {
  useEffect(() => {                                                      // a dark, full-bleed workspace; the sidebar stays
    const el = document.querySelector(".main-content");
    el?.classList.add("impact-dark");
    return () => el?.classList.remove("impact-dark");
  }, []);

  const [access, setAccess] = useState<Access>({ kind: "loading" });
  const [tokenInput, setTokenInput] = useState(getToken());
  const [scenario, setScenario] = useState<ScenarioInfo | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [support, setSupport] = useState<SupportMatrix | null>(null);
  const [recording, setRecording] = useState<Recording | null>(null);
  const [recClaim, setRecClaim] = useState<"cooccurrence" | "asserted">("asserted");

  const [source, setSource] = useState<"none" | "operator" | "recording">("none");
  const [projection, setProjection] = useState<Projection | null>(null);
  const [events, setEvents] = useState<FlowEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [liveRun, setLiveRun] = useState(false);
  const [selected, setSelected] = useState<Selection>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const lastFlow = useRef<Record<string, number>>({});
  const eventsRef = useRef<FlowEvent[]>([]);
  eventsRef.current = events;

  const stamp = useCallback((list: FlowEvent[], from: number, to: number) => {
    const now = performance.now();
    for (const e of list.slice(from, to)) if (e.stage_id) lastFlow.current[e.stage_id] = now;
  }, []);

  // ---------------------------------------------------------------- access
  const probe = useCallback(async () => {
    const st = await readStatus();
    if (st.kind === "static") return setAccess({ kind: "static", note: "This is the public static site: it has no server, so nothing can be ingested, approved or stored here." });
    if (st.kind === "offline") return setAccess({ kind: "offline", note: "The backend is not reachable." });
    if (st.kind === "disabled") return setAccess({ kind: "disabled", note: "This server is running without the operator Studio (start it with CCRIG_ENABLE_STUDIO=1 and CCRIG_STUDIO_TOKEN)." });
    if (!getToken()) return setAccess({ kind: "needs-token" });
    try {
      const sc = await studioApi.scenarios();
      setScenario(sc.scenarios[0] ?? null); setJobs(sc.jobs);
      setAccess({ kind: "ready" });
    } catch (e) {
      setAccess(e instanceof OpError && e.status === 401 ? { kind: "rejected", note: "That operator token was not accepted." } : { kind: "offline", note: msg(e) });
    }
  }, []);
  useEffect(() => { void probe(); }, [probe]);

  useEffect(() => {
    if (access.kind !== "ready") return;
    studioApi.preview(SCENARIO).then(setPreview).catch(() => setPreview(null));
    studioApi.support().then(setSupport).catch(() => setSupport(null));
  }, [access.kind]);

  const showRecording = useCallback((rec: Recording, claim: "cooccurrence" | "asserted", atEnd = true) => {
    const list = claim === "asserted" ? rec.asserted.after_rollback.events : rec.cooccurrence.after_ingest.events;
    setSource("recording"); setRecClaim(claim); setLiveRun(false); setNotice(null); setError(null); setSelected(null);
    setEvents(list); setCursor(atEnd ? list.length : 0); setPlaying(!atEnd); lastFlow.current = {};
    setProjection(null);
  }, []);

  useEffect(() => {                                                        // without an operator Studio the page shows the saved recording, clearly labelled
    if (access.kind === "loading" || access.kind === "ready" || recording) return;
    loadRecording().then((rec) => { if (rec) { setRecording(rec); setSupport(rec.support); setPreview(rec.preview); setScenario(rec.scenario_info); showRecording(rec, "asserted"); } });
  }, [access.kind, recording, showRecording]);

  // ---------------------------------------------------------------- what is on screen
  const proj: Projection | null = useMemo(() => {
    if (source === "recording" && recording) return recClaim === "asserted" ? recording.asserted[snapshotKey(events, cursor)] : recording.cooccurrence.after_ingest;
    return projection;
  }, [source, recording, recClaim, events, cursor, projection]);
  const stages = useMemo(() => reduceStages(events, cursor), [events, cursor]);
  const conns = useMemo(() => reduceConnections(stages), [stages]);
  const state = jobState(stages);
  const atEnd = cursor >= events.length;
  const status = destinationStatus(events, cursor);
  const canAct = source === "operator" && access.kind === "ready" && atEnd && !playing && !liveRun;
  const last = events[cursor - 1];
  const lastStaged = events.slice(0, cursor).reverse().find((e) => e.stage_id);

  // ---------------------------------------------------------------- playback of recorded events
  useEffect(() => {
    if (!playing) return;
    if (cursor >= events.length) { setPlaying(false); return; }
    const t = setTimeout(() => {
      let n = cursor + 1;
      while (n < events.length && events[n].seq === events[n - 1].seq) n++;      // events from one ledger row play together
      stamp(events, cursor, n); setCursor(n);
    }, cursor === 0 ? 250 : replayDelayMs(events[cursor - 1], events[cursor], speed));
    return () => clearTimeout(t);
  }, [playing, cursor, events, speed, stamp]);

  const replay = () => { lastFlow.current = {}; setCursor(0); setPlaying(true); setLiveRun(false); setSelected(null); };

  // ---------------------------------------------------------------- operator actions
  const applyProjection = useCallback((p: Projection) => {
    const before = eventsRef.current.length;
    setProjection(p); setEvents(p.events); setCursor(p.events.length); stamp(p.events, before, p.events.length);
  }, [stamp]);

  async function refreshJobs() { try { const sc = await studioApi.scenarios(); setJobs(sc.jobs); return sc; } catch { return null; } }

  async function startRun(claim: string) {
    if (busy) return;
    setBusy(true); setError(null); setNotice(null); setSource("operator"); setProjection(null); setEvents([]); setCursor(0); setPlaying(false); setSelected(null); setLiveRun(true); lastFlow.current = {};
    const abort = new AbortController();
    try {
      const sc = await studioApi.scenarios();
      let jobId: string | null = null;
      streamEvents(sc.last_seq, (e) => {                                   // events arrive as the backend records them
        if (!jobId && e.job_id) jobId = e.job_id;
        if (e.job_id !== jobId) return;
        const next = [...eventsRef.current, e];
        eventsRef.current = next; setEvents(next); stamp(next, next.length - 1, next.length); setCursor(next.length);
      }, abort.signal).catch(() => { /* the final fetch below reconciles anything the stream missed */ });
      const run = await studioApi.run(SCENARIO, claim, "studio-page");
      await sleep(300);
      abort.abort();
      applyProjection(await studioApi.job(run.job.job_id));
      if (run.duplicate) setNotice("Identical content from the same source was already ingested, so no new job was created. The resubmission was recorded in this job's history.");
      await refreshJobs();
    } catch (e) {
      abort.abort(); setError(msg(e)); setLiveRun(false);
    } finally { setBusy(false); setTimeout(() => setLiveRun(false), 4000); }
  }

  async function openJob(id: string) {
    if (!id) return;
    setBusy(true); setError(null); setNotice(null);
    try { setSource("operator"); setLiveRun(false); setPlaying(false); lastFlow.current = {}; const p = await studioApi.job(id); setProjection(p); setEvents(p.events); setCursor(p.events.length); setSelected(null); }
    catch (e) { setError(msg(e)); } finally { setBusy(false); }
  }

  async function decide(kind: "approve" | "reject", name: string, reason: string, ack = false) {
    if (!proj) return;
    setBusy(true); setError(null);
    try {
      if (kind === "approve") await studioApi.approve(proj.job.job_id, { reviewer: name, reason, acknowledge_assertions: ack });
      else await studioApi.reject(proj.job.job_id, { reviewer: name, reason });
      applyProjection(await studioApi.job(proj.job.job_id)); await refreshJobs();
    } catch (e) { setError(msg(e)); } finally { setBusy(false); }
  }
  async function rollback(name: string, reason: string) {
    if (!proj) return;
    setBusy(true); setError(null);
    try { await studioApi.rollback("relationship_evidence", { reviewer: name, reason }); applyProjection(await studioApi.job(proj.job.job_id)); }
    catch (e) { setError(msg(e)); } finally { setBusy(false); }
  }

  async function connect() {
    setToken(tokenInput.trim()); setAccess({ kind: "loading" }); await probe();
  }

  // ---------------------------------------------------------------- derived text
  const rows = stages.find((s) => s.id === "PARSE")?.records?.processed ?? null;
  const ev = stages.find((s) => s.id === "EVIDENCE");
  const quotes = proj?.assessments.flatMap((a) => a.quotes) ?? [];
  const badge = source === "recording" ? "RECORDED REPLAY" : source === "operator" ? (liveRun ? "LIVE" : playing ? "RECORDED REPLAY" : "STORED JOB") : "IDLE";
  const liveText = !last ? (access.kind === "ready" ? "Idle. Choose a claim about the stored excerpt to start a real job." : "Showing a saved recording. Nothing is running.")
    : state === "AWAITING_REVIEW" ? "Paused at the approval gate: waiting for a named reviewer." : state === "BLOCKED" ? "Held at the gate: the proposal cannot be approved. See the findings."
    : `${last.stage_id ?? "JOB"} · ${last.type.toLowerCase().replace(/_/g, " ")}${last.message ? " · " + last.message : ""}`;
  const decided = proj?.review.decisions ?? [];
  const decisionsShown = decided.filter((d) => (d.decision === "APPROVE" ? events.slice(0, cursor).some((e) => e.type === "REVIEW_APPROVED") : events.slice(0, cursor).some((e) => e.type === "REVIEW_REJECTED"))).length;
  const proof = source === "recording" && recording && recClaim === "asserted" ? { before: recording.graph_proof.before_approval, live: recording.graph_proof.after_approval, after: recording.graph_proof.after_rollback } : null;
  const destProj = source === "recording" && recording && recClaim === "asserted" ? { ...recording.asserted[snapshotKey(events, cursor)], destination: { ...recording.asserted.after_approval.destination, status } } as Projection : proj;
  const replayNote = source === "recording" ? `Recorded replay: approval and rollback were performed by the recording script as '${"recording-reviewer"}'. This site cannot approve anything.` : playing ? "Replaying a recorded job." : null;

  return (
    <div className="ds-page" data-testid="studio-page" data-source={source} data-state={state} data-access={access.kind} data-playing={playing}>
      <div className="ds-sheet">
        <header className="ds-tb">
          <div className="ds-tb-name">
            <h1>Data Intelligence <i>Studio</i></h1>
            <p className="ds-sub">{proj ? `${proj.job.job_id} · ${proj.job.source_id} → ${proj.job.target}` : "relationship evidence · stored sources → reviewed overlay"}</p>
          </div>
          <div className="ds-kpis">
            <div className="ds-kpi"><div className="ds-lab">Rows</div><b data-testid="kpi-rows">{rows ?? "—"}</b><small>{ev?.records ? `${ev.records.accepted} accepted · ${ev.records.rejected} rejected` : "parsed from the submitted file"}</small></div>
            <div className="ds-kpi"><div className="ds-lab">Stage</div><b data-testid="kpi-stage">{lastStaged?.stage_id ? STAGE_DEFS.find((d) => d.id === lastStaged.stage_id)?.label : "—"}</b><small>{lastStaged?.state ? STATE_LABEL[lastStaged.state] ?? lastStaged.state : "no job"}</small></div>
            <div className="ds-kpi"><div className="ds-lab">Evidence</div><b data-testid="kpi-evidence">{quotes.length && ev && ev.state !== "QUEUED" ? `${quotes.filter((q) => q.found_in_stored_source).length}/${quotes.length}` : "—"}</b><small>quotes found in the stored document</small></div>
            <div className="ds-kpi"><div className="ds-lab">Job</div><b data-testid="kpi-job">{state === "IDLE" ? "—" : (STATE_LABEL[state] ?? state.replace(/_/g, " ").toLowerCase())}</b><small>{decisionsShown > 0 ? `decided by ${decided[decisionsShown - 1].reviewer}` : "no decision yet"}</small></div>
          </div>
        </header>

        <div className="ds-bar">
          <div className="ds-live" data-testid="live-line"><span className={"ds-dot" + (busy || playing || liveRun ? " on" : "")} /><span className={"ds-mode " + badge.toLowerCase().replace(/ /g, "-")} data-testid="mode-badge">{badge}</span><span className="ds-live-t">{liveText}</span></div>
          <div className="ds-ctl">
            {events.length > 0 && <button type="button" className="ds-btn" data-testid="replay-btn" onClick={replay}>{playing ? "Restart replay" : "Recorded replay"}</button>}
            {playing && <button type="button" className="ds-btn" data-testid="pause-btn" onClick={() => setPlaying(false)}>Pause</button>}
            {!playing && cursor > 0 && cursor < events.length && <button type="button" className="ds-btn" data-testid="resume-btn" onClick={() => setPlaying(true)}>Resume</button>}
            <div className="ds-seg" role="group" aria-label="Replay speed">{[1, 2, 4].map((s) => <button key={s} type="button" aria-pressed={speed === s} onClick={() => setSpeed(s)}>{s}×</button>)}</div>
          </div>
        </div>

        {access.kind !== "ready" && access.kind !== "loading" && (
          <div className="ds-access" data-testid="access-note">
            <b>{access.kind === "needs-token" || access.kind === "rejected" ? "Operator access" : "Read-only"}</b>
            <span>{access.note ?? "Enter the operator token to run jobs on this machine."}</span>
            {(access.kind === "needs-token" || access.kind === "rejected") && (
              <span className="ds-row"><input data-testid="token-input" type="password" autoComplete="off" value={tokenInput} onChange={(e) => setTokenInput(e.target.value)} placeholder="operator token (kept for this tab only)" />
                <button type="button" className="ds-btn" data-testid="token-connect" onClick={connect}>Connect</button></span>
            )}
            {(access.kind === "static" || access.kind === "disabled" || access.kind === "offline") && <span>A saved recording of a real run is shown instead and is labelled as such.</span>}
          </div>
        )}

        <section className="ds-source" data-testid="source-picker">
          <div className="ds-source-l">
            <div className="ds-source-h"><span className="ds-lab">Source</span><b>{scenario?.title ?? "NVIDIA → Oracle (supplier relationship)"}</b>{preview && <code title={preview.sha256}>excerpt {shortHash(preview.sha256)}</code>}</div>
            {preview && <p className="ds-quote">“{preview.quote}”</p>}
            <details className="ds-about"><summary>About this source</summary><p className="ds-muted">{scenario?.description ?? "A stored excerpt of a public release is submitted with a claim about it."}</p></details>
          </div>
          <div className="ds-claims">
            {(scenario?.claims ?? [{ id: "cooccurrence", label: "Claim A", meaning: "" }, { id: "asserted", label: "Claim B", meaning: "" }]).map((c) => (
              <div key={c.id} className="ds-claim">
                <b>{c.label}</b><span className="ds-muted">{c.meaning}</span>
                {access.kind === "ready"
                  ? <button type="button" className="ds-btn primary" data-testid={`run-claim-${c.id}`} disabled={busy} onClick={() => startRun(c.id)}>{busy ? "Running…" : "Run this claim"}</button>
                  : <button type="button" className="ds-btn" data-testid={`rec-claim-${c.id}`} disabled={!recording} aria-pressed={source === "recording" && recClaim === c.id} onClick={() => recording && showRecording(recording, c.id as "cooccurrence" | "asserted")}>Show the recorded run</button>}
              </div>))}
          </div>
          <div className="ds-source-f">
            {access.kind === "ready" && jobs.length > 0 && (
              <label className="ds-jobs">Earlier jobs<select data-testid="job-select" value={proj?.job.job_id ?? ""} onChange={(e) => void openJob(e.target.value)}><option value="">choose…</option>{jobs.map((j) => <option key={j.job_id} value={j.job_id}>{j.job_id} · {j.source_id} · {j.status.toLowerCase().replace(/_/g, " ")}</option>)}</select></label>
            )}
            {notice && <div className="ds-callout" data-testid="notice">{notice}</div>}
            {error && !proj?.review.can_approve && <div className="ds-find error" data-testid="run-error"><span>{error}</span></div>}
          </div>
        </section>

        <section className="ds-bench" aria-label="Processing flow: source, parse, profile, validate, resolve, evidence, review, promote">
          <FlowCanvas stages={stages} conns={conns} lastFlow={lastFlow} selected={selected} onSelect={setSelected} />
          <div className="ds-legend" aria-hidden="true">
            <span className="q">queued</span><span className="r">running</span><span className="c">completed</span><span className="w">warnings</span><span className="a">awaiting review</span><span className="f">failed / blocked / rejected</span><span className="b">rolled back</span>
            <em>{source === "recording" ? "Recorded replay: particles replay recorded events." : "Particles appear only for a moment after a recorded event."}</em>
          </div>
        </section>

        <SelectionDock selected={selected} stages={stages} proj={proj} events={events} cursor={cursor} />

        <section className="ds-row3">
          <div><div className="ds-panel-h"><span className="ds-lab">Source Inspector</span></div><SourceInspector proj={proj} preview={preview} stages={stages} /></div>
          <div><div className="ds-panel-h"><span className="ds-lab">Quality &amp; Resolution Inspector</span></div><QualityInspector proj={proj} stages={stages} /></div>
          <div><div className="ds-panel-h"><span className="ds-lab">Execution Timeline</span></div><Timeline events={events} cursor={cursor} ledger={proj?.ledger} onStage={(id) => setSelected({ kind: "node", id: id as StageId })} /></div>
        </section>

        <section className="ds-row2">
          <div><div className="ds-panel-h"><span className="ds-lab">Review &amp; approval</span></div>
            <ReviewPanel proj={proj} stages={stages} canAct={canAct} replayNote={replayNote} busy={busy} error={error} decisionsShown={decisionsShown}
              onApprove={(n, r, a) => void decide("approve", n, r, a)} onReject={(n, r) => void decide("reject", n, r)} /></div>
          <div><div className="ds-panel-h"><span className="ds-lab">Promotion &amp; overlay</span></div>
            <DestinationPanel proj={destProj} status={status} live={source === "operator" && access.kind === "ready"} proof={status !== "NOT_PROMOTED" || cursor >= events.length ? proof : null} canAct={canAct} busy={busy} error={error} onRollback={(n, r) => void rollback(n, r)} /></div>
        </section>

        <section className="ds-foot">
          <div className="ds-spec">
            <div className="task"><div className="ds-lab">Task</div><div className="v">Move a documented relationship from a stored source to a reviewed overlay</div></div>
            <div><div className="ds-lab">Job</div><div className="v">{proj?.job.job_id ?? "—"}</div></div>
            <div><div className="ds-lab">Elapsed (measured)</div><div className="v" data-testid="spec-elapsed">{proj ? fmtMs(proj.job.elapsed_ms) : "—"}</div></div>
            <div><div className="ds-lab">Throughput</div><div className="v unavailable" title={proj?.metrics.unavailable.find((m) => m.metric === "throughput")?.reason} data-testid="spec-throughput">unavailable</div></div>
            <div><div className="ds-lab">Latency p95</div><div className="v unavailable" title={proj?.metrics.unavailable.find((m) => m.metric === "latency_percentiles")?.reason}>unavailable</div></div>
            <div><div className="ds-lab">Model usage</div><div className="v" title={proj?.metrics.unavailable.find((m) => m.metric === "model_usage")?.reason}>none · deterministic</div></div>
            <div><div className="ds-lab">Event ledger</div><div className="v">{proj ? `${proj.ledger.events} events · ${proj.ledger.ok ? "verified" : "BROKEN"}` : "—"}</div></div>
            <div><div className="ds-lab">Recorded</div><div className="v">{source === "recording" && recording ? recording.recorded_at.slice(0, 10) : "this session"}</div></div>
          </div>
          {source === "recording" && recording && <p className="ds-muted ds-recnote" data-testid="recording-note">{recording.note}</p>}
          <div className="ds-panel-h"><span className="ds-lab">What the Studio supports today</span></div>
          <SupportTable support={support} />
          <p className="ds-muted ds-recnote">Confidential enterprise data is never sent to public hosting or external AI services from this page. The Studio uses no language model; parsing, validation, entity resolution and evidence checks are deterministic.</p>
        </section>
      </div>
    </div>
  );
}
