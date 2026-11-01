import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, apiErrorMessage } from "../api/client";
import { DataBadge } from "../components/Badge";
import { RiskPath, pathFromChain } from "../components/RiskPath";

const SAMPLES = [
  "A major earthquake in Taiwan disrupts semiconductor fabrication facilities.",
  "Russia-Ukraine escalation raises energy and defense risks.",
  "Regional bank funding stress after a major bank failure.",
];

const SOURCE_BADGE: Record<string, { kind: "fact" | "ai" | "derived" | "synthetic"; label: string }> = {
  DETERMINISTIC_MATCH: { kind: "fact", label: "RULE" },
  LLM_CANDIDATE_RESOLVED: { kind: "ai", label: "AI-RESOLVED" },
  LLM_CANDIDATE_UNVALIDATED: { kind: "synthetic", label: "AI-UNVALIDATED" },
  CURATED_THEME: { kind: "fact", label: "CURATED" },
  DISCOVERED_THEME: { kind: "derived", label: "DISCOVERED" },
  EPHEMERAL_EVENT_CONCEPT: { kind: "synthetic", label: "EPHEMERAL" },
};

function SourceBadge({ source }: { source: string }) {
  const b = SOURCE_BADGE[source] || { kind: "fact" as const, label: source };
  return <DataBadge kind={b.kind} label={b.label} />;
}

function Collapsible({ label, children, defaultOpen = false }: { label: string; children: any; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card">
      <span className="pill" onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} {label}</span>
      {open && <div style={{ marginTop: 12 }}>{children}</div>}
    </div>
  );
}

export function EventStudio() {
  const [params] = useSearchParams();
  const [text, setText] = useState(params.get("text") || SAMPLES[0]);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAllMateriality, setShowAllMateriality] = useState(false);
  const nav = useNavigate();
  // Guards against out-of-order responses (e.g. the mount-time parse of the
  // default sample resolving after a later user-triggered parse) clobbering
  // a newer result with a stale one.
  const requestIdRef = useRef(0);

  async function run() {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const r = await api.parseEvent({ text });
      if (requestId === requestIdRef.current) {
        setResult(r);
      }
    } catch (e) {
      if (requestId === requestIdRef.current) {
        setResult(null);   // the previous event's result must not sit under the text that just failed
        setError(apiErrorMessage(e));
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }

  useEffect(() => { run(); }, []);

  return (
    <div className="stack">
      <div className="page-header">
        <h2>Event Studio</h2>
        <div className="subtitle">
          Paste any headline or narrative. Two ranking modes are computed and never mixed in the same table: Mode 1 is
          a bounded typed-path traversal (decayed criticality per hop); Mode 2 is relation-aware Personalized PageRank
          over Layer A + B only (exposure is joined afterward, never before).
        </div>
      </div>

      <div className="card">
        <textarea className="input" style={{ width: "100%", minHeight: 80, resize: "vertical" }} value={text} onChange={(e) => setText(e.target.value)} />
        <div className="hstack" style={{ marginTop: 10 }}>
          <button className="btn" onClick={run}>Parse event</button>
          {SAMPLES.map((s) => (
            <span key={s} className="pill" onClick={() => setText(s)}>{s.slice(0, 30)}…</span>
          ))}
        </div>
      </div>

      {error && <div className="warning-box">{error}</div>}

      {loading && <div className="loading">Parsing…</div>}

      {result && !loading && (
        <>
          <div className="card">
            <h2 style={{ margin: 0 }}>{result.event_type}</h2>
            <p className="subtitle" style={{ marginTop: 4 }}>{result.ai_summary}</p>
          </div>

          {result.materiality_join && (
            <div className="card">
              <div className="hstack" style={{ justifyContent: "space-between" }}>
                <div className="section-title" style={{ marginBottom: 0 }}>Exposure, materiality &amp; decision</div>
                <DataBadge kind="fact" label={`${result.materiality_join.nominated_issuer_count} issuers nominated`} />
              </div>
              <div className="warning-box" style={{ marginTop: 8 }}>{result.materiality_join.note}</div>

              {(() => {
                const seen = new Set<string>();
                const paths: string[][] = [];
                for (const r of result.materiality_join.results) {
                  if (!r.risk_factor_path?.length) continue;
                  const key = r.risk_factor_path.join(" → ");
                  if (seen.has(key)) continue;
                  seen.add(key);
                  paths.push(r.risk_factor_path);
                }
                if (paths.length === 0) return null;
                return (
                  <div style={{ marginTop: 10 }}>
                    <div className="section-title" style={{ fontSize: 11 }}>Transmission — how the risk actually propagates</div>
                    {paths.map((p, i) => (
                      <div key={i} style={{ marginBottom: 8 }}>
                        <RiskPath path={pathFromChain(p)} />
                      </div>
                    ))}
                  </div>
                );
              })()}

              {result.materiality_join.results.length === 0 && (
                <div className="empty-state" style={{ marginTop: 10 }}>
                  No synthetic CCR counterparty has a typed exposure referencing any nominated issuer.
                </div>
              )}
              {result.materiality_join.results.length > 0 && (
                <table className="table" style={{ marginTop: 10 }}>
                  <thead>
                    <tr>
                      <th>Priority</th><th>Counterparty</th><th>Reference issuer</th><th>Product</th>
                      <th>Δ PFE / Δ NSE</th><th>Utilisation</th><th>Headroom</th><th>Driver</th>
                      <th>Risk-factor path</th><th>Control flags</th><th>Decision</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(showAllMateriality ? result.materiality_join.results : result.materiality_join.results.slice(0, 5)).map((r: any) => (
                      <tr key={r.id}>
                        <td>
                          <span style={{
                            display: "inline-block", padding: "2px 8px", borderRadius: 999, fontSize: 10.5, fontWeight: 700,
                            color: r.priority === "CRITICAL" ? "var(--error)" : r.priority === "HIGH" ? "var(--warning)" : r.priority === "MEDIUM" ? "var(--chart-6)" : "var(--text-muted)",
                            border: `1px solid currentColor`,
                          }}>{r.priority}</span>
                        </td>
                        <td><a onClick={() => nav(`/cp/${r.id}`)} style={{ cursor: "pointer" }}>{r.name}</a></td>
                        <td><a onClick={() => nav(`/issuer/${r.reference_entity_id}`)} style={{ cursor: "pointer" }}>{r.reference_entity_id}</a></td>
                        <td style={{ fontSize: 11 }}>{r.product}</td>
                        <td className="mono">{r.delta_pfe != null ? `${r.delta_pfe > 0 ? "+" : ""}${r.delta_pfe}` : (r.delta_nse != null ? `${r.delta_nse > 0 ? "+" : ""}${r.delta_nse} (NSE)` : "n/a")}</td>
                        <td className="mono">{r.utilisation_pct != null ? `${r.utilisation_pct}%` : "Unavailable"}</td>
                        <td className="mono">{r.headroom ?? "Unavailable"}</td>
                        <td style={{ fontSize: 11 }}>{r.driver}</td>
                        <td style={{ fontSize: 10.5 }}>{r.risk_factor_path?.join(" → ") || "—"}</td>
                        <td style={{ fontSize: 10.5 }}>{r.is_overdue ? <span style={{ color: "var(--error)" }}>OVERDUE</span> : r.decision.control_flags.wwr ? <span style={{ color: "var(--warning)" }}>WWR</span> : "OK"}</td>
                        <td style={{ fontSize: 11 }}>{r.decision.decision}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {result.materiality_join.results.length > 5 && (
                <div style={{ marginTop: 8 }}>
                  <a style={{ cursor: "pointer", fontSize: 12 }} onClick={() => setShowAllMateriality(!showAllMateriality)}>
                    {showAllMateriality ? "Show top 5 only" : `Show all ${result.materiality_join.results.length}`}
                  </a>
                </div>
              )}
            </div>
          )}

          <Collapsible label="How was this derived?">
            {result.ai_context_extraction && (
              <div className="ai-box" style={{ marginBottom: 12 }}>
                <div className="ai-label">AI context extraction ({result.ai_context_extraction.ai_mode})</div>
                {result.ai_context_extraction.ai_reasoning_summary}
                {result.ai_context_extraction.ai_event_type_suggestion && (
                  <div style={{ marginTop: 4 }}>
                    AI-suggested event type: <span className="mono">{result.ai_context_extraction.ai_event_type_suggestion}</span>
                    {" "}(deterministic classification above remains authoritative)
                  </div>
                )}
              </div>
            )}

            <div className="grid-3">
              <div>
                <div className="section-title">Detected entities</div>
                <div className="pill-list">
                  {(!result.ai_context_extraction || result.ai_context_extraction.entities.length === 0) && <span className="empty-state">None detected</span>}
                  {result.ai_context_extraction?.entities.map((e: any) => (
                    <span key={e.entity_id} className="hstack" style={{ gap: 4 }}>
                      <span className="pill" onClick={() => nav(`/issuer/${e.entity_id}`)} style={{ cursor: "pointer" }}>{e.name}</span>
                      <SourceBadge source={e.source} />
                    </span>
                  ))}
                </div>
                {result.ai_context_extraction?.unresolved_llm_entity_candidates?.length > 0 && (
                  <div className="subtitle" style={{ marginTop: 6, fontSize: 11 }}>
                    Rejected AI candidates (did not resolve to a known entity): {result.ai_context_extraction.unresolved_llm_entity_candidates.join(", ")}
                  </div>
                )}
              </div>
              <div>
                <div className="section-title">Detected concepts / themes</div>
                <div className="pill-list">
                  {(!result.ai_context_extraction || result.ai_context_extraction.concepts.length === 0) && <span className="empty-state">None detected</span>}
                  {result.ai_context_extraction?.concepts.map((c: any, i: number) => (
                    <span key={i} className="hstack" style={{ gap: 4 }}>
                      <span className="pill">{c.concept}</span>
                      <SourceBadge source={c.source} />
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <div className="section-title">Detected countries</div>
                <div className="pill-list">
                  {(!result.ai_context_extraction || result.ai_context_extraction.countries.length === 0) && <span className="empty-state">None detected</span>}
                  {result.ai_context_extraction?.countries.map((c: any) => (
                    <span key={c.country} className="hstack" style={{ gap: 4 }}>
                      <span className="pill">{c.country}</span>
                      <SourceBadge source={c.source} />
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div className="row" style={{ marginTop: 14 }}>
              <div style={{ flex: 1 }}>
                <div className="section-title">Mode 1 — Bounded typed traversal (decay 0.65/hop)</div>
                <table className="table">
                  <thead><tr><th>Entity</th><th>Score</th></tr></thead>
                  <tbody>
                    {result.mode1_bounded_traversal.results.length === 0 && <tr><td colSpan={2} className="empty-state">No hops within bound.</td></tr>}
                    {result.mode1_bounded_traversal.results.map((r: any) => (
                      <tr key={r.entity_id}><td><a onClick={() => nav(`/issuer/${r.entity_id}`)} style={{ cursor: "pointer" }}>{r.entity_id}</a></td><td className="mono">{r.score.toFixed(3)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ flex: 1 }}>
                <div className="section-title">Mode 2 — Relation-aware Personalized PageRank (units NOT comparable to Mode 1)</div>
                <table className="table">
                  <thead><tr><th>Entity</th><th>PPR score</th></tr></thead>
                  <tbody>
                    {result.mode2_personalized_pagerank.results.map((r: any) => (
                      <tr key={r.entity_id}><td><a onClick={() => nav(`/issuer/${r.entity_id}`)} style={{ cursor: "pointer" }}>{r.entity_id}</a></td><td className="mono">{r.ppr_score.toFixed(4)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="section-title" style={{ marginTop: 14 }}>Relevant counterparties (exposure joined AFTER relevance is computed — Layer C, not business priority)</div>
            <table className="table">
              <thead><tr><th>Counterparty</th><th>Exposure-weighted relevance</th><th>Issuers</th></tr></thead>
              <tbody>
                {result.relevant_counterparties.map((c: any) => (
                  <tr key={c.counterparty}>
                    <td><a onClick={() => nav(`/cp/${c.counterparty}`)} style={{ cursor: "pointer" }}>{c.counterparty}</a></td>
                    <td className="mono">{c.exposure_weighted_relevance.toFixed(3)}</td>
                    <td>{c.issuers.map((i: any) => i.issuer).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Collapsible>
        </>
      )}
    </div>
  );
}
