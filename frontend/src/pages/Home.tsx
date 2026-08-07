import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { DataBadge } from "../components/Badge";

const SAMPLE_SCENARIOS = [
  { q: "IBM", kind: "entity", desc: "Single-entity lookup" },
  { q: "Taiwan", kind: "theme/geo", desc: "Theme + geography lookup" },
  { q: "AI bubble", kind: "theme", desc: "Thematic concept lookup" },
  { q: "A major earthquake in Taiwan disrupts semiconductor fabrication facilities.", kind: "event", desc: "Geographic/natural-disaster narrative" },
  { q: "Russia-Ukraine escalation raises energy and defense risks.", kind: "event", desc: "Geopolitical narrative" },
  { q: "Regional bank funding stress after a major bank failure.", kind: "event", desc: "Financial contagion narrative" },
];

export function Home() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [provenance, setProvenance] = useState<any>(null);
  const nav = useNavigate();

  useEffect(() => {
    api.provenance().then(setProvenance).catch(() => {});
  }, []);

  async function runQuery(q: string) {
    setQuery(q);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.search(q);
      setResult(res);
      // Event-like queries (long text) route straight to Event Studio's parse output shown inline
      if (res.resolved_as === "event") {
        // fetch full parse for inline preview
        const parsed = await api.parseEvent({ text: q });
        setResult({ ...res, parsed });
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack">
      <div className="page-header">
        <h1>AI Copilot · Universal Search</h1>
        <div className="subtitle">
          Ask about an entity, a theme, a counterparty, or paste a news headline / event narrative. Candidate generation
          runs first, then relevance is scored — nothing is pairwise-scored against the whole universe.
        </div>
      </div>

      <div className="card">
        <div className="searchbar">
          <input
            className="input"
            placeholder="Try: NVDA, Taiwan, AI bubble, or a headline about a bank failure..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runQuery(query)}
          />
          <button className="btn" onClick={() => runQuery(query)}>Search</button>
        </div>
        <div className="section-title" style={{ marginTop: 16 }}>6 required sample scenarios</div>
        <div className="pill-list">
          {SAMPLE_SCENARIOS.map((s) => (
            <span key={s.q} className="pill" onClick={() => runQuery(s.q)} title={s.desc}>
              {s.q.length > 40 ? s.q.slice(0, 40) + "…" : s.q}
            </span>
          ))}
        </div>
      </div>

      {loading && <div className="loading">Running candidate generation + scoring…</div>}
      {error && <div className="warning-box">Error: {error}</div>}

      {result && !result.parsed && (
        <div className="card">
          <div className="hstack" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>Resolved as: {result.resolved_as ?? "unresolved"}</h2>
            <DataBadge kind="ai" label={result.ai_mode === "ENHANCED_AI" ? "AI intent classification" : "Deterministic intent classification"} />
          </div>
          <p className="subtitle" style={{ marginTop: 6 }}>
            Intent: {result.ai_intent_classification?.intent} — {result.ai_intent_classification?.confidence_basis}
          </p>
          {result.entity_matches?.length > 0 && (
            <>
              <div className="section-title" style={{ marginTop: 14 }}>Entity matches</div>
              <div className="pill-list">
                {result.entity_matches.map((m: any) => (
                  <span key={m.id} className="pill" onClick={() => nav(`/entity?id=${m.id}`)}>{m.name} ({m.id})</span>
                ))}
              </div>
            </>
          )}
          {result.theme_match && (
            <>
              <div className="section-title" style={{ marginTop: 14 }}>Theme match</div>
              <span className="pill" onClick={() => nav(`/theme-radar?theme=${result.theme_match.theme_id}`)}>
                {result.theme_match.label}
              </span>
            </>
          )}
          {result.ai_followup_suggestions?.length > 0 && (
            <div className="ai-box" style={{ marginTop: 14 }}>
              <div className="ai-label">Suggested follow-ups</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {result.ai_followup_suggestions.map((s: string, i: number) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
          {result.resolved_id && (
            <button className="btn" style={{ marginTop: 14 }} onClick={() => nav(`/entity?id=${result.resolved_id}`)}>
              Open Entity 360 →
            </button>
          )}
        </div>
      )}

      {result?.parsed && (
        <div className="card">
          <div className="hstack" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>Event classified: {result.parsed.event_type}</h2>
            <DataBadge kind="ai" label="AI narrative summary" />
          </div>
          <div className="ai-box" style={{ marginTop: 10 }}>
            <div className="ai-label">AI summary ({result.parsed.ai_mode})</div>
            {result.parsed.ai_summary}
          </div>
          <div className="grid-2" style={{ marginTop: 14 }}>
            <div>
              <div className="section-title">Direct + theme-relevant entities ({result.parsed.direct_relevance.length})</div>
              <div className="pill-list">
                {result.parsed.direct_relevance.slice(0, 15).map((d: any) => (
                  <span key={d.entity_id} className="pill" onClick={() => nav(`/entity?id=${d.entity_id}`)}>
                    {d.entity_id} · {d.score.toFixed(2)}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div className="section-title">Relevant counterparties ({result.parsed.relevant_counterparties.length})</div>
              <div className="pill-list">
                {result.parsed.relevant_counterparties.slice(0, 10).map((c: any) => (
                  <span key={c.counterparty} className="pill" onClick={() => nav(`/counterparty?id=${c.counterparty}`)}>
                    {c.counterparty} · {c.exposure_weighted_relevance.toFixed(2)}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <button className="btn" style={{ marginTop: 14 }} onClick={() => nav(`/event-studio?text=${encodeURIComponent(query)}`)}>
            Open in Event Studio →
          </button>
        </div>
      )}

      {provenance && (
        <div className="grid-3">
          <div className="card kpi"><div className="value">{provenance.totals.issuers}</div><div className="label">Real issuers</div></div>
          <div className="card kpi"><div className="value">{provenance.totals.counterparties}</div><div className="label">Synthetic counterparties</div></div>
          <div className="card kpi"><div className="value">{provenance.totals.fact_edges}</div><div className="label">Fact relations (Layer A)</div></div>
        </div>
      )}
    </div>
  );
}
