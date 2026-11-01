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
  const [hoverEventId, setHoverEventId] = useState<string | null>(null);
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
      // Open on the newest returned event (the list is ordered by date; that is not a ranking of importance). A valid ?event= deep link wins.
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        const wanted = next.get("event");
        if (result.events.length === 0) next.delete("event");
        else if (!result.events.some((e) => e.id === wanted)) next.set("event", result.events[0].id);
        return next;
      }, { replace: true });
    } catch (e) {
      if (id !== latest.current) return;
      setData(null); setError(apiErrorMessage(e)); setStatus("error");   // never leave results from a previous query on screen
    }
  }

  const abandon = () => { latest.current++; };
  useEffect(() => {
    run(query, days);                                   // once, with the default search
    return abandon;                 // leaving the page abandons any request still in flight (it must not navigate back here)
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    <div className="stack impact-page">
      <div className="page-header">
        <h1>Global Event Impact Map</h1>
        <div className="subtitle">Verified events about a company, placed where they happened, with the documented relationships that connect the companies they name. Pilot: NVIDIA. <b>Impact size is not estimated.</b></div>
      </div>

      <form className="impact-toolbar" onSubmit={submit} aria-label="Search a company">
        <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Company name or ticker, e.g. NVIDIA" aria-label="Company" data-testid="impact-query" />
        <select value={days} onChange={(e) => { const d = Number(e.target.value); setDays(d); run(query, d, entityId ?? undefined); }} aria-label="Recency window" data-testid="impact-window">
          {WINDOWS.map((w) => <option key={w} value={w}>last {w} days</option>)}
        </select>
        <button className="btn" type="submit" disabled={status === "loading" || !query.trim()}>{status === "loading" ? "Searching…" : "Search"}</button>
        {matches.length > 1 && (
          <div className="pill-list" style={{ flexBasis: "100%" }}>
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
        <div className="stack impact-main">
          <div className="card impact-map-card">
            <div className="impact-map-status" data-testid="impact-status" data-phase={phase}>
              <span>ENTITY <b>{data ? `${data.entity.name}${data.entity.ticker ? ` (${data.entity.ticker})` : ""}` : "—"}</b></span>
              <span>EVENTS <b>{data ? `${data.events.length} of ≤${data.query.limit}` : "—"}</b></span>
              <span>WINDOW <b>{data ? `${data.query.recency_days} days to ${formatDate(data.query.as_of)}` : "—"}</b></span>
              <span className={phase === "loading" ? "busy" : ""}>STATE <b>{phase === "loading" ? "requesting…" : phase}</b></span>
            </div>
            <ImpactMapCanvas scene={scene} phase={phase} selectedEventId={selectedEventId} selectedEntityId={selectedEntity} hoverEventId={hoverEventId}
              onSelectEvent={selectEvent} onSelectEntity={(id) => { setSelectedEntity(id); }} onHoverEvent={setHoverEventId} />
            <div className="impact-legend" aria-label="Legend">
              <span><i className="lg-event" />event location (numbered; all markers the same size, order is by date)</span>
              <span><i className="lg-hq" />company headquarters country (approximate, not a facility)</span>
              <span><i className="lg-doc" />documented relationship, arrow = stored direction</span>
              <span><i className="lg-mention" />event names the company</span>
              <span><i className="lg-region" />country named in the evidence</span>
            </div>
          </div>

          <div className="pill-list" data-testid="semantics-key" aria-label="What each kind of information means">
            <span className="pill" title="Events are read from a reviewed register; this page never searches the live web">Curated register, not live news search</span>
            <span className="pill" title="Quoted from the source and checked against the retrieved page">Confirmed: quoted in a source</span>
            <span className="pill" title="Stored relationship in the platform's dataset, with its own evidence status">Documented: stored relationship</span>
            <span className="pill" title="Nothing documented connects these; no path is drawn">Unavailable: no documented path</span>
          </div>

          {data && (
            <details className="card impact-about" data-testid="impact-about">
              <summary>About this view, coverage and records not shown</summary>
              <div aria-live="polite" data-testid="impact-explanation">
                <p>{data.explanation}</p>
                <p style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
                  Events come from the approved-source register built {formatDate(data.register.built_at)} ({data.register.events_total} verified records; coverage: {data.register.coverage}). The page does not search the live web.
                </p>
              </div>
              {scene.unmapped.length > 0 && <p style={{ fontSize: 11.5, color: "var(--text-muted)" }}>Not plotted: {scene.unmapped.map((u) => `${u.label} (${u.reason})`).join("; ")}.</p>}
              {data.not_returned.length > 0 && (
                <div data-testid="not-returned">
                  <div className="section-title">Other records in the register that are not shown ({data.not_returned.length})</div>
                  <table className="table"><tbody>{data.not_returned.map((r) => <tr key={r.id}><td>{formatDate(r.published_date)}</td><td>{r.title}</td><td style={{ color: "var(--text-muted)" }}>{r.reason}</td></tr>)}</tbody></table>
                </div>
              )}
              <ul style={{ paddingLeft: 18, margin: "8px 0 0", fontSize: 12, color: "var(--text-muted)" }}>{data.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
            </details>
          )}
        </div>

        <aside className="impact-side" aria-label="Events and evidence">
          <div className="card impact-top5" data-testid="top5">
            <div className="hstack" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
              <div className="section-title" style={{ marginBottom: 0 }}>Top 5 events</div>
              <span className="impact-note">newest first · date order, not importance</span>
            </div>
            {phase === "loading" && <div className="impact-skeleton" aria-hidden="true">{[0, 1, 2].map((i) => <div key={i} />)}</div>}
            {data && data.events.length === 0 && phase !== "loading" && <p style={{ margin: "8px 0 0", fontSize: 12 }}>No verified events for this search.</p>}
            <div className="impact-event-list" role="list">
              {phase !== "loading" && data?.events.map((e, i) => (
                <button key={e.id} role="listitem" type="button" data-testid="event-item" data-event-id={e.id} aria-pressed={e.id === selectedEventId}
                  className={`impact-event-item${e.id === selectedEventId ? " selected" : ""}`} onClick={() => selectEvent(e.id === selectedEventId ? null : e.id)}
                  onMouseEnter={() => setHoverEventId(e.id)} onMouseLeave={() => setHoverEventId(null)} onFocus={() => setHoverEventId(e.id)} onBlur={() => setHoverEventId(null)}>
                  <span className="rank">{i + 1}</span>
                  <span><b>{e.title}</b><span className="meta">{formatDate(e.published_date)} · {e.location.mapped ? e.location.label : "location not mapped"} · {e.sources[0]?.publisher}</span></span>
                </button>
              ))}
            </div>
          </div>

          {selectedEntity && data && <EntityBlock data={data} entityId={selectedEntity} onOpen={() => nav(`/entity?id=${selectedEntity}`)} onClose={() => setSelectedEntity(null)} />}
          {selected ? <EventPanel event={selected} names={names} onClose={() => selectEvent(null)} /> : (
            <div className="card" data-testid="no-selection">
              <div className="section-title">Selected event</div>
              <p style={{ margin: 0, fontSize: 12.5 }}>{data && data.events.length ? "Choose an event on the map or in the list to see its source evidence, the documented path to the company and what this analysis cannot say." : "Search a company to see its recent verified events."}</p>
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
