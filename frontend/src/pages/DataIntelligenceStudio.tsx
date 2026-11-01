// Data Intelligence Studio: a computational instrument. A stored source enters on the left and moves through eight modules to a reviewed output; every light, cable and pulse
// is a recorded event (live stream or labelled replay). Technical detail lives in a contextual drawer that is closed until asked for. See src/studio/*.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "../studio/studio.css";
import { FlowCanvas } from "../studio/FlowCanvas";
import { DestinationPanel, EdgeDetail, LlmDetail, QualityInspector, ReviewPanel, SelectionDock, SourceInspector, SupportTable, Timeline } from "../studio/Panels";
import { TimelineStrip } from "../studio/TimelineStrip";
import { OpError, getToken, loadRecording, readStatus, setToken, streamEvents, studioApi, type JobRow } from "../studio/api";
import { NODE_DEFS, NODE_OF_STAGE, buildEdges, buildNodes, type Selection } from "../studio/graph";
import { destinationStatus, fmtMs, jobState, reduceStages, replayDelayMs, shortHash, snapshotKey } from "../studio/reduce";
import { KIND_LABEL } from "../studio/states";
import type { FlowEvent, Preview, Projection, Recording, ScenarioInfo, SupportMatrix } from "../studio/types";

type Access = { kind: "loading" } | { kind: "static" | "offline" | "disabled" | "needs-token" | "rejected" | "ready"; note?: string };
type Tab = "stage" | "source" | "quality" | "review" | "output" | "events" | "about";
const SCENARIO = "oracle-nvidia";
const TABS: [Tab, string][] = [["stage", "Stage"], ["source", "Source"], ["quality", "Quality"], ["review", "Review"], ["output", "Output"], ["events", "Events"], ["about", "About"]];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const msg = (e: unknown) => (e instanceof OpError ? `${e.code}: ${e.message}` : e instanceof Error ? e.message : String(e));

export function DataIntelligenceStudio() {
  useEffect(() => {                                                      // a dark, full-bleed workspace; the sidebar stays
    const el = document.querySelector(".main-content");
    el?.classList.add("impact-dark", "ds-host");
    return () => el?.classList.remove("impact-dark", "ds-host");
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
  const [drawer, setDrawer] = useState<{ open: boolean; tab: Tab }>({ open: false, tab: "stage" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [vh, setVh] = useState(typeof window === "undefined" ? 900 : window.innerHeight);
  const lastFlow = useRef<Record<string, number>>({});
  const eventsRef = useRef<FlowEvent[]>([]);
  eventsRef.current = events;
  useEffect(() => { const f = () => setVh(window.innerHeight); window.addEventListener("resize", f); return () => window.removeEventListener("resize", f); }, []);

  const stamp = useCallback((list: FlowEvent[], from: number, to: number) => {       // a recorded event lights the cable that feeds its module
    const now = performance.now();
    for (const e of list.slice(from, to)) if (e.stage_id) lastFlow.current[NODE_OF_STAGE[e.stage_id]] = now;
  }, []);

  // ---------------------------------------------------------------- access
  const probe = useCallback(async () => {
    const st = await readStatus();
    if (st.kind === "static") return setAccess({ kind: "static", note: "Public static site: no server, so nothing can be ingested, approved or stored here." });
    if (st.kind === "offline") return setAccess({ kind: "offline", note: "The backend is not reachable." });
    if (st.kind === "disabled") return setAccess({ kind: "disabled", note: "This server runs without the operator Studio (CCRIG_ENABLE_STUDIO and CCRIG_STUDIO_TOKEN are not set)." });
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
    setEvents(list); setCursor(atEnd ? list.length : 0); setPlaying(!atEnd); lastFlow.current = {}; setProjection(null);
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
  const state = jobState(stages);
  const status = destinationStatus(events, cursor);
  const decided = proj?.review.decisions ?? [];
  const decisionsShown = decided.filter((d) => events.slice(0, cursor).some((e) => e.type === (d.decision === "APPROVE" ? "REVIEW_APPROVED" : "REVIEW_REJECTED"))).length;
  const reviewer = decisionsShown > 0 ? decided[decisionsShown - 1].reviewer : null;
  const nodes = useMemo(() => buildNodes(stages, { decided: reviewer }), [stages, reviewer]);
  const edges = useMemo(() => buildEdges(nodes), [nodes]);
  const atEnd = cursor >= events.length;
  const canAct = source === "operator" && access.kind === "ready" && atEnd && !playing && !liveRun;
  const last = events[cursor - 1];

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
  const seek = (n: number) => { setPlaying(false); setLiveRun(false); setCursor(n); };

  // ---------------------------------------------------------------- operator actions
  const applyProjection = useCallback((p: Projection) => {
    const before = eventsRef.current.length;
    setProjection(p); setEvents(p.events); setCursor(p.events.length); stamp(p.events, before, p.events.length);
  }, [stamp]);
  async function refreshJobs() { try { const sc = await studioApi.scenarios(); setJobs(sc.jobs); return sc; } catch { return null; } }

  async function startRun(claim: string) {
    if (busy) return;
    setBusy(true); setError(null); setNotice(null); setSource("operator"); setProjection(null); setEvents([]); setCursor(0); setPlaying(false); setSelected(null); setLiveRun(true); lastFlow.current = {};
    eventsRef.current = [];
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
  async function connect() { setToken(tokenInput.trim()); setAccess({ kind: "loading" }); await probe(); }

  // ---------------------------------------------------------------- derived text
  const badge = source === "recording" ? "RECORDED REPLAY" : source === "operator" ? (liveRun ? "LIVE" : playing ? "RECORDED REPLAY" : "STORED JOB") : "IDLE";
  const liveText = !last ? (access.kind === "ready" ? "idle · run a claim to send the stored excerpt through the network" : "showing a saved recording · nothing is running")
    : state === "AWAITING_REVIEW" ? "paused at the approval gate · waiting for a named reviewer" : state === "BLOCKED" ? "held at the gate · this proposal cannot be approved"
    : `${last.stage_id ? NODE_DEFS.find((d) => d.id === NODE_OF_STAGE[last.stage_id!])?.label : "job"} · ${last.type.toLowerCase().replace(/_/g, " ")}${last.message ? " · " + last.message : ""}`;
  const proof = source === "recording" && recording && recClaim === "asserted" ? { before: recording.graph_proof.before_approval, live: recording.graph_proof.after_approval, after: recording.graph_proof.after_rollback } : null;
  const destProj = source === "recording" && recording && recClaim === "asserted" ? { ...recording.asserted[snapshotKey(events, cursor)], destination: { ...recording.asserted.after_approval.destination, status } } as Projection : proj;
  const replayNote = source === "recording" ? "Recorded replay: approval and rollback were performed by the recording script as 'recording-reviewer'. This site cannot approve anything." : playing ? "Replaying a recorded job." : null;
  const open = (tab: Tab) => setDrawer({ open: true, tab });
  const select = (s: Selection) => { setSelected(s); if (s) setDrawer({ open: true, tab: "stage" }); };
  const maxH = Math.max(380, vh - 64 - 92);
  const selNode = selected?.kind === "node" ? nodes.find((n) => n.id === selected.id) : null;
  const selEdge = selected?.kind === "edge" ? edges.find((e) => e.id === selected.id) : null;
  const readOnly = access.kind !== "ready" && access.kind !== "loading";
  const claims = scenario?.claims ?? [{ id: "cooccurrence", label: "Claim A", meaning: "" }, { id: "asserted", label: "Claim B", meaning: "" }];

  return (
    <div className="ds-page" data-testid="studio-page" data-source={source} data-state={state} data-access={access.kind} data-playing={playing} data-drawer={drawer.open}>
      <header className="ds-top">
        <div className="ds-title"><h1>Data Intelligence <i>Studio</i></h1><span className="ds-sub" data-testid="job-id">{proj ? `${proj.job.job_id} · ${proj.job.source_id}` : "stored source → reviewed output"}</span></div>
        <div className="ds-srcchip" data-testid="source-picker" title={preview?.quote}>
          <span className="ds-lab">Source</span><b>Oracle release excerpt</b>{preview && <code title={preview.sha256}>{shortHash(preview.sha256)}</code>}
        </div>
        <div className="ds-claimbar">
          {claims.map((c) => access.kind === "ready"
            ? <button key={c.id} type="button" className="ds-btn primary" data-testid={`run-claim-${c.id}`} disabled={busy} title={c.meaning} onClick={() => startRun(c.id)}>{busy ? "Running…" : c.id === "cooccurrence" ? "▶ Co-occurrence" : "▶ Asserted"}</button>
            : <button key={c.id} type="button" className="ds-btn" data-testid={`rec-claim-${c.id}`} disabled={!recording} aria-pressed={source === "recording" && recClaim === c.id} title={c.meaning} onClick={() => recording && showRecording(recording, c.id as "cooccurrence" | "asserted")}>{c.id === "cooccurrence" ? "Recorded · co-occurrence" : "Recorded · asserted"}</button>)}
          {access.kind === "ready" && jobs.length > 0 && <select className="ds-jobsel" data-testid="job-select" aria-label="Earlier jobs" value={proj?.job.job_id ?? ""} onChange={(e) => void openJob(e.target.value)}><option value="">jobs…</option>{jobs.map((j) => <option key={j.job_id} value={j.job_id}>{j.job_id} · {j.source_id} · {j.status.toLowerCase().replace(/_/g, " ")}</option>)}</select>}
        </div>
        <div className="ds-ctl">
          {events.length > 0 && <button type="button" className="ds-btn" data-testid="replay-btn" onClick={replay}>{playing ? "Restart replay" : "Recorded replay"}</button>}
          {playing && <button type="button" className="ds-btn" data-testid="pause-btn" onClick={() => setPlaying(false)}>Pause</button>}
          {!playing && cursor > 0 && cursor < events.length && <button type="button" className="ds-btn" data-testid="resume-btn" onClick={() => setPlaying(true)}>Resume</button>}
          <div className="ds-seg" role="group" aria-label="Replay speed">{[1, 2, 4].map((s) => <button key={s} type="button" aria-pressed={speed === s} onClick={() => setSpeed(s)}>{s}×</button>)}</div>
          <span className={"ds-mode " + badge.toLowerCase().replace(/ /g, "-")} data-testid="mode-badge">{badge}</span>
          <button type="button" className="ds-btn" data-testid="drawer-toggle" aria-pressed={drawer.open} onClick={() => setDrawer((d) => ({ ...d, open: !d.open }))}>Details</button>
        </div>
      </header>

      {(readOnly || notice || error) && (
        <div className="ds-banner" data-testid="access-note">
          {readOnly && <><b>{access.kind === "needs-token" || access.kind === "rejected" ? "Operator access" : "Read-only"}</b><span>{access.note}</span></>}
          {(access.kind === "needs-token" || access.kind === "rejected") && <span className="ds-row"><input data-testid="token-input" type="password" autoComplete="off" value={tokenInput} onChange={(e) => setTokenInput(e.target.value)} placeholder="operator token (kept for this tab only)" /><button type="button" className="ds-btn" data-testid="token-connect" onClick={connect}>Connect</button></span>}
          {readOnly && source === "recording" && recording && <span data-testid="recording-note">Saved recording of a real run ({recording.recorded_at.slice(0, 10)}): approval and rollback were done by the recording script; this page cannot ingest, approve or roll anything back.</span>}
          {notice && <span data-testid="notice">{notice}</span>}
          {error && !proj?.review.can_approve && <span className="err" data-testid="run-error">{error}</span>}
        </div>
      )}

      <main className="ds-canvaswrap" aria-label="Processing network: source, parse, validate, resolve, language model, verify, review, output">
        <div className="ds-live" data-testid="live-line"><span className={"ds-dot" + (busy || playing || liveRun ? " on" : "")} /><span className="ds-live-t">{liveText}</span></div>
        <FlowCanvas nodes={nodes} edges={edges} lastFlow={lastFlow} selected={selected} onSelect={select} onOpen={(w) => { setSelected({ kind: "node", id: w === "review" ? "REVIEW" : "OUTPUT" }); open(w); }} maxHeight={maxH}
          idleHint={events.length === 0 ? "Run a claim to send the stored excerpt through the network" : null} />
        <div className="ds-legend" aria-hidden="true"><span className="q">queued</span><span className="r">running / awaiting</span><span className="c">completed</span><span className="w">warnings</span><span className="f">refused</span><span className="b">rolled back</span><span className="s">skipped</span></div>
      </main>

      <TimelineStrip events={events} cursor={cursor} onSeek={seek} ledger={proj?.ledger} elapsedMs={proj?.job.elapsed_ms ?? null} />

      <aside className={"ds-drawer" + (drawer.open ? " open" : "")} data-testid="drawer" aria-hidden={!drawer.open} aria-label="Details">
        <div className="ds-drawer-h">
          <nav role="tablist">{TABS.map(([id, label]) => <button key={id} type="button" role="tab" aria-selected={drawer.tab === id} data-testid={`drawer-tab-${id}`} onClick={() => open(id)}>{label}</button>)}</nav>
          <button type="button" className="ds-btn ghost" data-testid="drawer-close" onClick={() => setDrawer((d) => ({ ...d, open: false }))}>✕</button>
        </div>
        {drawer.open && (
          <div className="ds-drawer-b">
            <div hidden={drawer.tab !== "stage"}>
              <div data-testid="stage-tab">
                {selNode && <div className="ds-kind" style={{ ["--k" as string]: `var(--kind-${selNode.kind})` }}>{KIND_LABEL[selNode.kind]} · {NODE_DEFS.find((d) => d.id === selNode.id)?.blurb}</div>}
                {selNode?.id === "LLM" ? <LlmDetail node={selNode} proj={proj} />
                  : selNode ? NODE_DEFS.find((d) => d.id === selNode.id)!.from.map((sid) => <SelectionDock key={sid} selected={{ kind: "node", id: sid }} stages={stages} proj={proj} events={events} cursor={cursor} />)
                  : selEdge ? <EdgeDetail edge={selEdge} nodes={nodes} proj={proj} />
                  : <p className="ds-muted" data-testid="selection-dock">Select a module to see what went in, what came out, its findings and its history; select a cable to see what data passed along it.</p>}
              </div></div>
            <div hidden={drawer.tab !== "source"}><SourceInspector proj={proj} preview={preview} stages={stages} /></div>
            <div hidden={drawer.tab !== "quality"}><QualityInspector proj={proj} stages={stages} /></div>
            <div hidden={drawer.tab !== "review"}><ReviewPanel proj={proj} stages={stages} canAct={canAct} replayNote={replayNote} busy={busy} error={error} decisionsShown={decisionsShown} onApprove={(n, r, a) => void decide("approve", n, r, a)} onReject={(n, r) => void decide("reject", n, r)} /></div>
            <div hidden={drawer.tab !== "output"}><DestinationPanel proj={destProj} status={status} live={source === "operator" && access.kind === "ready"} proof={status !== "NOT_PROMOTED" || cursor >= events.length ? proof : null} canAct={canAct} busy={busy} error={error} onRollback={(n, r) => void rollback(n, r)} /></div>
            <div hidden={drawer.tab !== "events"}>
              <>
                <Timeline events={events} cursor={cursor} ledger={proj?.ledger} onStage={(id) => setSelected({ kind: "node", id: NODE_OF_STAGE[id as keyof typeof NODE_OF_STAGE] })} />
                <div className="ds-lab" style={{ margin: "14px 0 6px" }}>Measurements</div>
                <dl className="ds-kv" data-testid="measurements">
                  <div><dt>job time (measured)</dt><dd data-testid="spec-elapsed">{proj ? fmtMs(proj.job.elapsed_ms) : "—"}</dd></div>
                  <div><dt>throughput</dt><dd className="unavailable" data-testid="spec-throughput" title={proj?.metrics.unavailable.find((m) => m.metric === "throughput")?.reason}>unavailable</dd></div>
                  <div><dt>latency p95</dt><dd className="unavailable">unavailable</dd></div>
                  <div><dt>model usage</dt><dd>{stages.find((s) => s.id === "LLM")?.state === "SKIPPED" ? "none recorded · deterministic path" : stages.find((s) => s.id === "LLM")?.state === "QUEUED" ? "—" : "see the Stage tab"}</dd></div>
                  <div><dt>event ledger</dt><dd>{proj ? `${proj.ledger.events} events · ${proj.ledger.ok ? "verified" : "BROKEN"}` : "—"}</dd></div>
                </dl>
              </></div>
            <div hidden={drawer.tab !== "about"}>
              <div>
                {source === "recording" && recording && <p className="ds-muted" data-testid="recording-about">{recording.note}</p>}
                <div className="ds-lab" style={{ margin: "10px 0 6px" }}>What the Studio supports today</div>
                <SupportTable support={support} />
                <p className="ds-muted">Confidential enterprise data is never sent to public hosting or external AI services from this page. No language model takes part unless a call is recorded; parsing, validation, entity resolution and evidence checks are deterministic.</p>
              </div></div>
          </div>)}
      </aside>
    </div>
  );
}
