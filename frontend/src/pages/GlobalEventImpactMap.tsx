import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, apiErrorMessage } from "../api/client";
import { DataBadge } from "../components/Badge";
import { ImpactMapCanvas } from "../components/ImpactMapCanvas";
import {
  RELATIONSHIP_LABEL, buildScene, formatDate, pathChips, phaseOf, safeHttpsUrl,
  type ImpactEvent, type ImpactResponse,
} from "../impactmap/model";

const WINDOWS = [30, 90, 180, 365, 730];
type Status = "idle" | "loading" | "error" | "ok";

export function GlobalEventImpactMap() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const [query, setQuery] = useState(params.get("q") ?? "NVIDIA");
  const [days, setDays] = useState(WINDOWS.includes(Number(params.get("days"))) ? Number(params.get("days")) : 180);
  const [status, setStatus] = useState<Status>("idle");
  const [data, setData] = useState<ImpactResponse | null>(null);
  const [matches, setMatches] = useState<{ entity_id: string; name: string; ticker?: string; event_coverage: boolean }[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [entityId, setEntityId] = useState<string | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const latest = useRef(0);
  const selectedEventId = params.get("event");

  async function run(q: string, windowDays: number, chosen?: string) {
    const id = ++latest.current;
    setStatus("loading"); setError(null); setMessage(null); setSelectedEntity(null);
    try {
      const found = await api.impactMapSearch(q);
      if (id !== latest.current) return;
      setMatches(found.matches);
      if (found.matches.length === 0) { setData(null); setEntityId(null); setMessage(found.message); setStatus("ok"); return; }
      const target = chosen ?? found.matches[0].entity_id;
      const result: ImpactResponse = await api.impactMapEvents(target, { recency_days: windowDays });
      if (id !== latest.current) return;
      setEntityId(target); setData(result); setStatus("ok");
    } catch (e) {
      if (id !== latest.current) return;
      setData(null); setError(apiErrorMessage(e)); setStatus("error");   // never leave results from a previous query on screen
    }
  }

  useEffect(() => { run(query, days); /* once, with the default search */ // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const next = new URLSearchParams(); next.set("q", query); next.set("days", String(days));
    setParams(next, { replace: true });
    run(query, days);
  }
  function selectEvent(id: string | null) {
    const next = new URLSearchParams(params);
    if (id) next.set("event", id); else next.delete("event");
    setParams(next, { replace: true });
    setSelectedEntity(null);
  }

  const phase = phaseOf(status, data);
  const scene = useMemo(() => (data ? buildScene(data) : { markers: [], cables: [], unmapped: [] }), [data]);
  const names = useMemo(() => Object.fromEntries((data?.graph.nodes ?? []).filter((n) => n.entity_id).map((n) => [n.entity_id as string, n.label])), [data]);
  const selected: ImpactEvent | undefined = data?.events.find((e) => e.id === selectedEventId);

  return (
    <div className="stack">
      <div className="page-header">
        <h1>Global Event Impact Map</h1>
        <div className="subtitle">
          Recent events about a company, taken from approved primary sources and verified by retrieval, placed on the map with the documented
          relationships that connect the companies they name. Pilot: NVIDIA. <b>The size of any impact is not estimated.</b>
        </div>
        <div className="pill-list" style={{ marginTop: 8 }} data-testid="semantics-key" aria-label="What each kind of information means">
          <span className="pill" title="Events are read from a reviewed register; this page never searches the live web">Curated register, not live news search</span>
          <span className="pill" title="Quoted from the source and checked against the retrieved page">Confirmed: quoted in a source</span>
          <span className="pill" title="Stored relationship in the platform's dataset, with its own evidence status">Documented: stored relationship</span>
          <span className="pill" title="Nothing documented connects these; no path is drawn">Unavailable: no documented path</span>
        </div>
      </div>

      <form className="card" onSubmit={submit} aria-label="Search a company">
        <div className="searchbar">
          <input className="input" style={{ flex: 1 }} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Company name or ticker, e.g. NVIDIA" aria-label="Company" data-testid="impact-query" />
          <select value={days} onChange={(e) => { const d = Number(e.target.value); setDays(d); run(query, d, entityId ?? undefined); }} aria-label="Recency window" data-testid="impact-window">
            {WINDOWS.map((w) => <option key={w} value={w}>last {w} days</option>)}
          </select>
          <button className="btn" type="submit" disabled={status === "loading" || !query.trim()}>{status === "loading" ? "Searching…" : "Search"}</button>
        </div>
        {matches.length > 1 && (
          <div className="pill-list" style={{ marginTop: 8 }}>
            {matches.map((m) => <span key={m.entity_id} className="pill" role="button" tabIndex={0} onClick={() => run(query, days, m.entity_id)}>{m.name}{m.event_coverage ? "" : " (no events)"}</span>)}
          </div>
        )}
      </form>

      {error && (
        <div className="warning-box" role="alert" data-testid="impact-error">
          Could not load events: {error} <button className="btn secondary" style={{ marginLeft: 10 }} type="button" onClick={() => run(query, days, entityId ?? undefined)}>Retry</button>
        </div>
      )}
      {message && <div className="warning-box" data-testid="impact-message">{message}</div>}

      <div className="impact-layout">
        <div className="stack">
          <div className="card impact-map-card">
            <div className="impact-map-status" data-testid="impact-status" data-phase={phase}>
              <span>ENTITY: <b>{data ? `${data.entity.name}${data.entity.ticker ? ` (${data.entity.ticker})` : ""}` : "—"}</b></span>
              <span>EVENTS: <b>{data ? `${data.events.length} of ≤${data.query.limit}` : "—"}</b></span>
              <span>WINDOW: <b>{data ? `${data.query.recency_days} days to ${formatDate(data.query.as_of)}` : "—"}</b></span>
              <span>CABLES: <b>{scene.cables.length}</b></span>
              <span className={phase === "loading" ? "busy" : ""}>STATE: <b>{phase === "loading" ? "requesting…" : phase}</b></span>
            </div>
            <ImpactMapCanvas scene={scene} phase={phase} selectedEventId={selectedEventId} selectedEntityId={selectedEntity} onSelectEvent={selectEvent} onSelectEntity={(id) => { setSelectedEntity(id); }} />
            <div className="impact-legend" aria-label="Legend">
              <span><i style={{ width: 18, height: 2, background: "linear-gradient(90deg,#4aa8e8,#3fd1c1)" }} />documented relationship (pulse runs in its stored direction)</span>
              <span><i style={{ width: 18, borderTop: "1.5px dashed #6f86b3" }} />event names the entity</span>
              <span><i style={{ width: 18, borderTop: "1.5px dotted #d9a06a" }} />country named in the evidence</span>
              <span><i style={{ width: 10, height: 10, borderRadius: 5, background: "#f2a93b" }} />event (numbered newest first)</span>
              <span><i style={{ width: 12, height: 10, background: "#7fb2e0" }} />company at its HQ country (approximate)</span>
            </div>
          </div>

          {data && (
            <div className="card" aria-live="polite" data-testid="impact-explanation">
              <div className="section-title">What this shows</div>
              <p style={{ margin: "0 0 6px" }}>{data.explanation}</p>
              <p style={{ margin: 0, fontSize: 11.5, color: "var(--text-muted)" }}>
                Events come from the approved-source register built {formatDate(data.register.built_at)} ({data.register.events_total} verified records; coverage: {data.register.coverage}).
                The page does not search the live web.
              </p>
            </div>
          )}

          {data && data.events.length > 0 && (
            <div className="card">
              <div className="section-title">Events (newest first)</div>
              <div className="impact-event-list" role="list">
                {data.events.map((e, i) => (
                  <button key={e.id} role="listitem" type="button" data-testid="event-item" data-event-id={e.id} aria-pressed={e.id === selectedEventId}
                    className={`impact-event-item${e.id === selectedEventId ? " selected" : ""}`} onClick={() => selectEvent(e.id === selectedEventId ? null : e.id)}>
                    <span className="rank">{i + 1}</span>
                    <span><b>{e.title}</b><span className="meta">{formatDate(e.published_date)} · {e.location.mapped ? e.location.label : "location not mapped"} · {e.sources[0]?.publisher}</span></span>
                  </button>
                ))}
              </div>
              {scene.unmapped.length > 0 && <p style={{ fontSize: 11.5, color: "var(--text-muted)" }}>Not plotted: {scene.unmapped.map((u) => `${u.label} (${u.reason})`).join("; ")}.</p>}
            </div>
          )}

          {data && data.not_returned.length > 0 && (
            <details className="card" data-testid="not-returned">
              <summary>Other records in the register that are not shown ({data.not_returned.length})</summary>
              <table className="table" style={{ marginTop: 8 }}>
                <tbody>{data.not_returned.map((r) => <tr key={r.id}><td>{formatDate(r.published_date)}</td><td>{r.title}</td><td style={{ color: "var(--text-muted)" }}>{r.reason}</td></tr>)}</tbody>
              </table>
            </details>
          )}
        </div>

        <aside className="stack" aria-label="Selected event">
          {selectedEntity && data && <EntityBlock data={data} entityId={selectedEntity} onOpen={() => nav(`/entity?id=${selectedEntity}`)} onClose={() => setSelectedEntity(null)} />}
          {selected ? <EventPanel event={selected} names={names} onClose={() => selectEvent(null)} /> : (
            <div className="card" data-testid="no-selection">
              <div className="section-title">Select an event</div>
              <p style={{ marginTop: 0 }}>
                {data && data.events.length ? "Choose an event on the map or in the list to see its source evidence, the documented path to the company, and what this analysis cannot say."
                  : "Search a company to see its recent verified events."}
              </p>
              {data && <ul style={{ paddingLeft: 18, margin: 0, fontSize: 12, color: "var(--text-muted)" }}>{data.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function EntityBlock({ data, entityId, onOpen, onClose }: { data: ImpactResponse; entityId: string; onOpen: () => void; onClose: () => void }) {
  const rows = data.events.flatMap((e) => e.entities.filter((x) => x.entity_id === entityId).map((x) => ({ e, x })));
  const first = rows[0]?.x;
  return (
    <div className="card" data-testid="entity-panel">
      <div className="hstack" style={{ justifyContent: "space-between" }}>
        <div className="section-title" style={{ marginBottom: 0 }}>{first?.name ?? entityId}</div>
        <button type="button" className="btn secondary" onClick={onClose}>Close</button>
      </div>
      <p style={{ fontSize: 12, color: "var(--text-muted)" }}>Position on the map is its headquarters country (approximate).</p>
      <ul style={{ paddingLeft: 18, margin: "6px 0" }}>
        {rows.map(({ e, x }) => <li key={e.id}><b>{formatDate(e.published_date)}</b> {e.title}<br /><span style={{ fontSize: 12 }}>{RELATIONSHIP_LABEL[x.relationship_to_target]}. {x.explanation}</span></li>)}
      </ul>
      <button type="button" className="btn secondary" onClick={onOpen}>Open Entity 360</button>
    </div>
  );
}

function EventPanel({ event, names, onClose }: { event: ImpactEvent; names: Record<string, string>; onClose: () => void }) {
  const loc = event.location;
  return (
    <div className="card" data-testid="event-panel" data-event-id={event.id}>
      <div className="hstack" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>{event.title}</h2>
        <button type="button" className="btn secondary" onClick={onClose} aria-label="Close event details">Close</button>
      </div>
      <div className="pill-list" style={{ margin: "8px 0" }}>
        <DataBadge kind="real" label="Real publication" />
        <DataBadge kind="fact" label={event.verification.status === "VERIFIED_BY_RETRIEVAL" ? "Verified by retrieval" : event.verification.status} />
        <DataBadge kind="derived" label={event.category.replace(/_/g, " ").toLowerCase()} />
      </div>

      <div className="impact-block">
        <h4>Source and dates</h4>
        <dl className="impact-kv">
          <dt>Published</dt><dd data-testid="published-date">{formatDate(event.published_date)}</dd>
          <dt>Event date</dt><dd>{formatDate(event.event_date)} <span style={{ color: "var(--text-muted)" }}>({event.event_date_basis})</span></dd>
          <dt>Source</dt>
          <dd>{event.sources.map((s) => { const href = safeHttpsUrl(s.url); return (
            <div key={s.id}>{s.publisher} · <span style={{ color: "var(--text-muted)" }}>{s.tier.replace(/_/g, " ").toLowerCase()}</span> · {href ? <a href={href} target="_blank" rel="noreferrer noopener" data-testid="source-link">open source</a> : "link unavailable"}
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>retrieved {formatDate(s.retrieved_at.slice(0, 10))}; {event.verification.quotes_found}/{event.verification.quotes_total} passages and the date confirmed in the source</div></div>); })}</dd>
          <dt>Event location</dt>
          <dd data-testid="event-location">{loc.mapped ? <>{loc.label} <span style={{ color: "var(--text-muted)" }}>({loc.precision})</span><div style={{ fontSize: 11, color: "var(--text-muted)" }}>Basis: {loc.basis}</div></> : `Not mapped: ${loc.reason}`}</dd>
          {event.regions_mentioned.length > 0 && <><dt>Countries named</dt><dd>{event.regions_mentioned.map((r) => r.label).join(", ")}</dd></>}
        </dl>
      </div>

      <div className="impact-block">
        <h4>Evidence (verbatim from the source)</h4>
        {event.evidence.map((ev, i) => <blockquote key={i} className="impact-quote" data-testid="evidence-quote">{ev.quote}</blockquote>)}
      </div>

      <div className="impact-block">
        <h4>Documented path to the company</h4>
        {event.entities.map((ent) => (
          <div key={ent.entity_id} style={{ marginBottom: 10 }} data-testid="entity-relationship" data-entity-id={ent.entity_id} data-class={ent.relationship_to_target}>
            <div><b>{ent.name}</b> — {RELATIONSHIP_LABEL[ent.relationship_to_target]}</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{ent.explanation}</div>
            {event.paths.filter((p) => p.entity_id === ent.entity_id).map((p) => (
              <div key={p.id} className="impact-chain" data-testid="path" data-relationship-type={p.relationship_type}>
                {pathChips(p, event.title, names).map((c, i) => <span key={i} className={`impact-chip ${c.kind}`} title={c.detail}>{c.kind === "event" ? "Event" : c.text}</span>)}
              </div>
            ))}
            {ent.relationship_to_target === "NO_DOCUMENTED_PATH" && <div style={{ fontSize: 12 }}>No path is drawn.</div>}
          </div>
        ))}
        <details><summary style={{ fontSize: 12 }}>How to read a path</summary>
          <p style={{ fontSize: 12 }}>Each link is either "names" (the quoted text names the company) or a stored relationship from the platform's data (its stored direction, evidence status and a curated criticality — a judgement, not a measured exposure). A path shows documented connectivity, not that this event moves the company.</p>
        </details>
      </div>

      <div className="impact-block neutral" data-testid="impact-block">
        <h4>Impact</h4>
        <dl className="impact-kv">
          <dt>Estimated impact</dt><dd data-testid="impact-status"><b>Not estimated.</b> {event.impact.reason}</dd>
          <dt>Verified exposure</dt><dd>Not available. {event.verified_exposure.reason}</dd>
          <dt>Relationship evidence</dt><dd>Shown above, kept separate from any impact.</dd>
        </dl>
      </div>

      <div className="impact-block" data-testid="limitations">
        <h4>Analytical limitations</h4>
        <ul style={{ paddingLeft: 18, margin: 0, fontSize: 12 }}>{event.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
      </div>
    </div>
  );
}
