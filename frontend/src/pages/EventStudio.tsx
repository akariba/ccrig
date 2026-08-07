import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { DataBadge } from "../components/Badge";

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

export function EventStudio() {
  const [params] = useSearchParams();
  const [text, setText] = useState(params.get("text") || SAMPLES[0]);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();
  // Guards against out-of-order responses (e.g. the mount-time parse of the
  // default sample resolving after a later user-triggered parse) clobbering
  // a newer result with a stale one.
  const requestIdRef = useRef(0);

  async function run() {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    try {
      const r = await api.parseEvent({ text });
      if (requestId === requestIdRef.current) {
        setResult(r);
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
        <h1>Event Studio</h1>
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

      {loading && <div className="loading">Parsing…</div>}

      {result && !loading && (
        <>
          <div className="card">
            <div className="hstack" style={{ justifyContent: "space-between" }}>
              <h2 style={{ margin: 0 }}>Classified as: {result.event_type}</h2>
              <DataBadge kind="ai" label={result.ai_mode === "ENHANCED_AI" ? "AI summary" : "Deterministic summary"} />
            </div>
            <div className="ai-box" style={{ marginTop: 10 }}>
              <div className="ai-label">AI summary</div>{result.ai_summary}
            </div>

            {result.ai_context_extraction && (
              <div className="ai-box" style={{ marginTop: 10 }}>
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

            <div className="grid-3" style={{ marginTop: 12 }}>
              <div>
                <div className="section-title">Detected entities</div>
                <div className="pill-list">
                  {(!result.ai_context_extraction || result.ai_context_extraction.entities.length === 0) && <span className="empty-state">None detected</span>}
                  {result.ai_context_extraction?.entities.map((e: any) => (
                    <span key={e.entity_id} className="hstack" style={{ gap: 4 }}>
                      <span className="pill" onClick={() => nav(`/entity?id=${e.entity_id}`)} style={{ cursor: "pointer" }}>{e.name}</span>
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
          </div>

          <div className="row">
            <div className="card" style={{ flex: 1 }}>
              <div className="section-title">Mode 1 — Bounded typed traversal (decay 0.65/hop)</div>
              <table className="table">
                <thead><tr><th>Entity</th><th>Score</th></tr></thead>
                <tbody>
                  {result.mode1_bounded_traversal.results.length === 0 && <tr><td colSpan={2} className="empty-state">No hops within bound.</td></tr>}
                  {result.mode1_bounded_traversal.results.map((r: any) => (
                    <tr key={r.entity_id}><td><a onClick={() => nav(`/entity?id=${r.entity_id}`)} style={{ cursor: "pointer" }}>{r.entity_id}</a></td><td className="mono">{r.score.toFixed(3)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card" style={{ flex: 1 }}>
              <div className="section-title">Mode 2 — Relation-aware Personalized PageRank (units NOT comparable to Mode 1)</div>
              <table className="table">
                <thead><tr><th>Entity</th><th>PPR score</th></tr></thead>
                <tbody>
                  {result.mode2_personalized_pagerank.results.map((r: any) => (
                    <tr key={r.entity_id}><td><a onClick={() => nav(`/entity?id=${r.entity_id}`)} style={{ cursor: "pointer" }}>{r.entity_id}</a></td><td className="mono">{r.ppr_score.toFixed(4)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <div className="section-title">Relevant counterparties (exposure joined AFTER relevance is computed)</div>
            <table className="table">
              <thead><tr><th>Counterparty</th><th>Exposure-weighted relevance</th><th>Issuers</th></tr></thead>
              <tbody>
                {result.relevant_counterparties.map((c: any) => (
                  <tr key={c.counterparty}>
                    <td><a onClick={() => nav(`/counterparty?id=${c.counterparty}`)} style={{ cursor: "pointer" }}>{c.counterparty}</a></td>
                    <td className="mono">{c.exposure_weighted_relevance.toFixed(3)}</td>
                    <td>{c.issuers.map((i: any) => i.issuer).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
