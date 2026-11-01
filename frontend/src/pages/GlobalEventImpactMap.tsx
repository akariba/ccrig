import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, apiErrorMessage } from "../api/client";
import { DataBadge } from "../components/Badge";
import { GeoStage, type Mode } from "../components/GeoStage";
import {
  RELATIONSHIP_LABEL, buildScene, categoryStyle, formatDate, pathChips, phaseOf, safeHttpsUrl,
  type Comparison, type ImpactEvent, type ImpactResponse, REVIEW_LABEL,
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
  const [animate, setAnimate] = useState(true);
  const source: "curated" | "discovered" = params.get("source") === "discovered" ? "discovered" : "curated";
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [comparing, setComparing] = useState(false);
  const mode: Mode = params.get("view") === "flat" ? "flat" : params.get("view") === "globe" ? "globe" : "auto";
  function setMode(m: Mode) {
    setParams((prev) => { const next = new URLSearchParams(prev); if (m === "auto") next.delete("view"); else next.set("view", m); return next; }, { replace: true });
  }
  useEffect(() => {                                     // the workspace is dark and full-bleed; the sidebar and navigation stay as they are
    const el = document.querySelector(".main-content");
    el?.classList.add("impact-dark");
    return () => el?.classList.remove("impact-dark");
  }, []);
  const latest = useRef(0);
  const selectedEventId = params.get("event");

  async function run(q: string, windowDays: number, chosen?: string, src: "curated" | "discovered" = source) {
    const id = ++latest.current;
    setStatus("loading"); setError(null); setMessage(null); setSelectedEntity(null); setComparison(null);
    try {
      const found = await api.impactMapSearch(q);
      if (id !== latest.current) return;
      setMatches(found.matches);
      if (found.matches.length === 0) { setData(null); setEntityId(null); setMessage(found.message); setStatus("ok"); return; }
      const target = chosen ?? found.matches[0].entity_id;
      const result: ImpactResponse = await api.impactMapEvents(target, src === "discovered" ? { recency_days: windowDays, mode: "discovered" } : { recency_days: windowDays });
      if (id !== latest.current) return;
      setEntityId(target); setData(result); setStatus("ok");
      // The page opens in the Global Overview (nothing selected). A valid ?event= deep link opens that event; an unknown one is dropped.
      // (Read the live URL: a functional setParams would use the render-time params and could undo a change made while the request was in flight.)
      const live = new URLSearchParams(window.location.search), wanted = live.get("event");
      if (wanted && !result.events.some((e) => e.id === wanted)) { live.delete("event"); setParams(live, { replace: true }); }
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

  function chooseSource(next: "curated" | "discovered") {
    if (next === source) return;
    setParams((prev) => { const p = new URLSearchParams(prev); if (next === "discovered") p.set("source", "discovered"); else p.delete("source"); p.delete("event"); return p; }, { replace: true });
    run(query, days, entityId ?? undefined, next);
  }
  async function compare() {
    if (!entityId) return;
    setComparing(true);
    try { setComparison(await api.impactMapCompare(entityId, { recency_days: days })); } catch (e) { setError(apiErrorMessage(e)); } finally { setComparing(false); }
  }

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
  const overview = useMemo(() => {
    if (!data || data.events.length === 0) return null;
    const relations = scene.cables.filter((c) => c.type === "DOCUMENTED_RELATION");
    return {
      events: data.events.length, places: new Set(data.events.flatMap((e) => (e.location.mapped ? [e.location.label] : []))).size,
      relations: relations.length, companies: new Set(relations.flatMap((c) => [c.from, c.to])).size, unplotted: data.events.filter((e) => !e.location.mapped).length,
    };
  }, [data, scene]);
  const selected: ImpactEvent | undefined = data?.events.find((e) => e.id === selectedEventId);

  return (
    <div className="iw">
      <header className="iw-toolbar">
        <div className="iw-title">
          <h1>Global Event Impact Map</h1>
          <span>Verified events and documented relationships · impact is not estimated</span>
        </div>
        <form className="iw-search" onSubmit={submit} aria-label="Search a company">
          <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Company or ticker, e.g. NVIDIA" aria-label="Company" data-testid="impact-query" />
          <select value={days} onChange={(e) => { const d = Number(e.target.value); setDays(d); run(query, d, entityId ?? undefined); }} aria-label="Recency window" data-testid="impact-window">
            {WINDOWS.map((w) => <option key={w} value={w}>last {w} days</option>)}
          </select>
          <button className="btn" type="submit" disabled={status === "loading" || !query.trim()}>{status === "loading" ? "Searching…" : "Search"}</button>
        </form>
        <div className="seg iw-source" role="group" aria-label="Where events come from" data-testid="source-mode">
          <button type="button" aria-pressed={source === "curated"} onClick={() => chooseSource("curated")} title="A fixed, human-reviewed register: reproducible, the benchmark">Curated register</button>
          <button type="button" aria-pressed={source === "discovered"} onClick={() => chooseSource("discovered")} title="Events found in approved sources by an operator-run discovery, machine-verified">Dynamic discovery</button>
        </div>
        <div className="iw-stats" data-testid="impact-status" data-phase={phase} aria-label="Search summary">
          <span><em>Entity</em><b>{data ? `${data.entity.name.replace(/ Corporation$/, "")}${data.entity.ticker ? ` · ${data.entity.ticker}` : ""}` : "—"}</b></span>
          <span><em>Events</em><b>{data ? `${data.events.length} of ≤${data.query.limit}` : "—"}</b></span>
          <span><em>Window</em><b>{data ? `${data.query.recency_days} d to ${formatDate(data.query.as_of)}` : "—"}</b></span>
          <span title={source === "curated" ? "Events are read from a reviewed register; this page never searches the live web" : "Events come from the latest discovery run an operator made; this page never searches the live web"}><em>Source</em>
            <b>{!data ? "—" : source === "curated" ? `Curated register · built ${formatDate(data.register.built_at)}` : data.available ? `Dynamic discovery · ${formatDate(data.query.as_of)}` : "Dynamic discovery · unavailable"}</b></span>
        </div>
        {matches.length > 1 && (
          <div className="pill-list" style={{ flexBasis: "100%" }}>
            {matches.map((m) => <span key={m.entity_id} className="pill" role="button" tabIndex={0} onClick={() => run(query, days, m.entity_id)}>{m.name}{m.event_coverage ? "" : " (no events)"}</span>)}
          </div>
        )}
      </header>

      {error && (
        <div className="warning-box" role="alert" data-testid="impact-error">
          Could not load events: {error} <button className="btn secondary" style={{ marginLeft: 10 }} type="button" onClick={() => run(query, days, entityId ?? undefined)}>Retry</button>
        </div>
      )}
      {message && <div className="warning-box" data-testid="impact-message">{message}</div>}
      {source === "discovered" && data && data.available === false && (
        <div className="warning-box" role="status" data-testid="discovery-unavailable">
          <b>Dynamic discovery is not available here.</b> {data.explanation}{" "}
          <button className="btn secondary" style={{ marginLeft: 8 }} type="button" onClick={() => chooseSource("curated")}>Show the curated register</button>
        </div>
      )}
      {source === "discovered" && data?.available && data.provenance && (
        <div className="iw-banner" data-testid="discovery-provenance">
          <b>Dynamic discovery</b> · run <code>{data.provenance.run_id}</code> · {formatDate(data.provenance.as_of)} · <b data-testid="review-status">{REVIEW_LABEL[data.review?.status ?? ""] ?? data.review?.status}</b> · {data.provenance.ai.mode}
          <div className="pill-list" style={{ marginTop: 6 }}>
            {data.provenance.providers.map((p) => <span key={p.id} className="pill" title={p.reason}>{p.label.split(" (")[0]}: {p.status.toLowerCase().replace("_", " ")}</span>)}
          </div>
          <details style={{ marginTop: 6 }}><summary>How these events were chosen</summary><ul>{data.provenance.selection_criteria.map((c, i) => <li key={i}>{c}</li>)}</ul></details>
        </div>
      )}

      <div className="iw-body">
        <section className="iw-map" aria-label="Map">
          <GeoStage scene={scene} phase={phase} selectedEventId={selectedEventId} selectedEntityId={selectedEntity} hoverEventId={hoverEventId}
            mode={mode} animate={animate} onMode={setMode} onAnimate={setAnimate}
            canInvestigate={!!data && data.events.length > 0} onOverview={() => selectEvent(null)} onInvestigate={() => data?.events[0] && selectEvent(data.events[0].id)}
            onSelectEvent={selectEvent} onSelectEntity={(id) => { setSelectedEntity(id); }} onHoverEvent={setHoverEventId} />
        </section>

        <aside className="iw-panel" aria-label="Events and evidence">
          <div className="iw-top5" data-testid="top5">
            <div className="iw-top5-head">
              <span className="iw-h">Top 5 events</span>
              <span className="impact-note">newest first · date order, not importance</span>
            </div>
            {phase === "loading" && <div className="impact-skeleton" aria-hidden="true">{[0, 1, 2].map((i) => <div key={i} />)}</div>}
            {data && data.events.length === 0 && phase !== "loading" && <p style={{ margin: "8px 0 0", fontSize: 12 }}>No verified events for this search.</p>}
            <div className="impact-event-list" role="list">
              {phase !== "loading" && data?.events.map((e, i) => (
                <button key={e.id} role="listitem" type="button" data-testid="event-item" data-event-id={e.id} aria-pressed={e.id === selectedEventId}
                  className={`impact-event-item${e.id === selectedEventId ? " selected" : ""}`} style={{ ["--cat" as string]: categoryStyle(e.category).color }} onClick={() => selectEvent(e.id === selectedEventId ? null : e.id)}
                  onMouseEnter={() => setHoverEventId(e.id)} onMouseLeave={() => setHoverEventId(null)} onFocus={() => setHoverEventId(e.id)} onBlur={() => setHoverEventId(null)}>
                  <span className="rank">{i + 1}</span>
                  <span><b>{e.title}</b><span className="meta">{formatDate(e.published_date)} · {e.location.mapped ? e.location.label : "location not mapped"} · {categoryStyle(e.category).label}</span></span>
                </button>
              ))}
            </div>
          </div>

          {selectedEntity && data && <EntityBlock data={data} entityId={selectedEntity} onOpen={() => nav(`/entity?id=${selectedEntity}`)} onClose={() => setSelectedEntity(null)} />}
          {selected ? <EventPanel event={selected} names={names} onClose={() => selectEvent(null)} /> : (
            <div className="iw-card" data-testid="no-selection">
              <div className="iw-h">Global overview</div>
              {overview ? (
                <>
                  <p style={{ margin: "6px 0", fontSize: 12.5 }} data-testid="overview-summary">
                    {overview.events} verified event{overview.events === 1 ? "" : "s"} at {overview.places} place{overview.places === 1 ? "" : "s"}.
                    {" "}{overview.relations} stored relationship{overview.relations === 1 ? "" : "s"} link {overview.companies} compan{overview.companies === 1 ? "y" : "ies"} that these events name; they are drawn faintly, with arrows in their stored direction.{overview.unplotted > 0 && <> {overview.unplotted} {overview.unplotted === 1 ? "has" : "have"} no place evidenced by {overview.unplotted === 1 ? "its" : "their"} source, so {overview.unplotted === 1 ? "it is" : "they are"} listed but not plotted (a location is never assumed).</>}
                  </p>
                  <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>Choose an event on the map or in the list to investigate its source evidence, the documented path to the company and what this analysis cannot say. No impact is estimated.</p>
                </>
              ) : <p style={{ margin: "6px 0 0", fontSize: 12.5 }}>{data?.available === false ? data.explanation : "Search a company to see its recent verified events."}</p>}
            </div>
          )}
        </aside>
      </div>

      <footer className="iw-foot">
        <div className="pill-list" data-testid="semantics-key" aria-label="What each kind of information means">
          <span className="pill" title="Events are read from a reviewed register or from a discovery run an operator made; this page never searches the live web">{source === "curated" ? "Curated register, not live news search" : "Operator-run discovery in approved sources, not live news search"}</span>
          {source === "discovered" && <span className="pill" title="The retrieved source contains the quoted text and date; that is not independent corroboration">Machine-verified, not corroborated</span>}
          <span className="pill" title="Quoted from the source and checked against the retrieved page">Confirmed: quoted in a source</span>
          <span className="pill" title="Stored relationship in the platform's dataset, with its own evidence status">Documented: stored relationship</span>
          <span className="pill" title="Nothing documented connects these; no path is drawn">Unavailable: no documented path</span>
          <span className="pill" title="No defensible impact metric exists yet">Impact: not estimated</span>
        </div>
        <div className="iw-about" data-testid="compare-card">
          <div className="hstack" style={{ justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <b style={{ fontSize: 12.5 }}>Curated register vs dynamic discovery</b>
            <button className="btn secondary" type="button" disabled={!entityId || comparing} onClick={compare} data-testid="compare-button">{comparing ? "Comparing…" : comparison ? "Refresh comparison" : "Compare the two modes"}</button>
          </div>
          {comparison && <ComparisonTable c={comparison} />}
        </div>
        {data && (
          <details className="iw-about" data-testid="impact-about">
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
                <div className="iw-h">Other records in the register that are not shown ({data.not_returned.length})</div>
                <table className="table"><tbody>{data.not_returned.map((r) => <tr key={r.id}><td>{formatDate(r.published_date)}</td><td>{r.title}</td><td style={{ color: "var(--text-muted)" }}>{r.reason}</td></tr>)}</tbody></table>
              </div>
            )}
            <ul style={{ paddingLeft: 18, margin: "8px 0 0", fontSize: 12, color: "var(--text-muted)" }}>{data.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
          </details>
        )}
      </footer>
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
          {event.discovery && <><dt>How found</dt><dd data-testid="how-found">Dynamic discovery via {event.discovery.provider_id.replace(/_/g, " ")}; category by {event.discovery.category_method}. <b>{REVIEW_LABEL[event.discovery.review_status] ?? event.discovery.review_status}.</b>
            {event.discovery.also_reported_by.length > 0 && <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Also reported by {event.discovery.also_reported_by.length} other source(s).</div>}</dd></>}
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

function ComparisonTable({ c }: { c: Comparison }) {
  const list = (events: Comparison["curated"]["events"]) => events.length === 0 ? <em style={{ color: "var(--text-muted)" }}>none</em> : (
    <ul style={{ margin: 0, paddingLeft: 16 }}>{events.map((e) => <li key={e.id}><a href={safeHttpsUrl(e.url) ?? undefined} target="_blank" rel="noreferrer noopener">{e.title}</a> <span style={{ color: "var(--text-muted)" }}>· {formatDate(e.published_date)} · {e.location ?? "location not evidenced"}</span></li>)}</ul>);
  return (
    <div data-testid="compare-panel" style={{ marginTop: 10, fontSize: 12 }}>
      <table className="table">
        <thead><tr><th></th><th>Curated register</th><th>Dynamic discovery</th></tr></thead>
        <tbody>
          <tr><td>What it is</td><td>{c.curated.label}</td><td>{c.discovered.label}</td></tr>
          <tr><td>Events returned</td><td data-testid="compare-curated-count">{c.curated.count}</td><td data-testid="compare-discovered-count">{c.discovered.available ? c.discovered.count : "not available here"}</td></tr>
          <tr><td>As of</td><td>{formatDate(c.curated.as_of)}</td><td>{c.discovered.available ? formatDate(c.discovered.as_of) : "—"}</td></tr>
          <tr><td>Review</td><td>human-reviewed when built</td><td>{c.discovered.available ? (REVIEW_LABEL[c.discovered.review_status ?? ""] ?? c.discovered.review_status) : "—"}</td></tr>
          {!c.discovered.available && <tr><td>Why not available</td><td colSpan={2}>{c.discovered.reason_unavailable}</td></tr>}
          <tr><td>In both (same source document)</td><td colSpan={2}>{c.overlap.in_both.length === 0 ? <em style={{ color: "var(--text-muted)" }}>none</em> : <ul style={{ margin: 0, paddingLeft: 16 }}>{c.overlap.in_both.map((x) => <li key={x.curated.id}>{x.curated.title}</li>)}</ul>}</td></tr>
          <tr><td>Only in the curated register</td><td colSpan={2}>{list(c.overlap.only_curated)}</td></tr>
          <tr><td>Only in dynamic discovery</td><td colSpan={2}>{c.discovered.available ? list(c.overlap.only_discovered) : <em style={{ color: "var(--text-muted)" }}>not available here</em>}</td></tr>
        </tbody>
      </table>
      <p style={{ color: "var(--text-muted)", margin: "6px 0 0" }}>Matching rule: {c.basis}.</p>
      <ul style={{ margin: "6px 0 0", paddingLeft: 18, color: "var(--text-muted)" }}>{c.how_they_differ.map((t, i) => <li key={i}>{t}</li>)}</ul>
    </div>
  );
}
