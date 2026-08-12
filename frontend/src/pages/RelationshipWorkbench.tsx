import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { DataBadge } from "../components/Badge";

const COMPONENT_LABEL: Record<string, string> = {
  sector: "Sector match", geography: "Geography", supply_chain: "Supply chain",
  ownership: "Ownership", semantic: "Semantic (TF-IDF)", news: "News co-occurrence",
  market_positive: "Market corr. (+)", market_negative: "Market corr. (–)",
};

const EXAMPLES = ["NVDA", "TSM", "interest rate volatility", "Meridian Alpha Rates Fund"];

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div className="hstack" style={{ justifyContent: "space-between", fontSize: 11.5, color: "var(--text-muted)" }}>
        <span>{label}</span>
        <span className="mono">{value === null ? "n/a" : value.toFixed(2)}</span>
      </div>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${value === null ? 0 : value * 100}%`, opacity: value === null ? 0.15 : 1 }} />
      </div>
    </div>
  );
}

// The default landing page. Relationship-first: a single search box resolves
// to an entity, counterparty, theme, or event narrative, and whatever comes
// back leads with WHO/WHAT this is connected to. Exposure numbers (PFE,
// priority, breach counts) only appear beneath that, and only once a
// relationship has already been shown - never before it.
export function RelationshipWorkbench() {
  const [q, setQ] = useState("");
  const [result, setResult] = useState<any>(null);
  const [entityData, setEntityData] = useState<any>(null);
  const [inspecting, setInspecting] = useState<string | null>(null);
  const [explain, setExplain] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();

  async function runSearch(query: string) {
    if (!query.trim()) return;
    setLoading(true);
    setResult(null);
    setEntityData(null);
    setExplain(null);
    setInspecting(null);
    const r = await api.search(query).catch(() => null);
    setResult(r);
    if (r && (r.resolved_as === "entity" || r.resolved_as === "counterparty")) {
      const d = await api.entity360(r.resolved_id).catch(() => null);
      setEntityData(d);
    }
    setLoading(false);
  }

  async function inspect(otherId: string) {
    if (!entityData) return;
    setInspecting(otherId);
    setExplain(null);
    const e = await api.explainRelationship(entityData.header.id, otherId).catch(() => null);
    setExplain(e);
  }

  return (
    <div className="stack">
      <div className="page-header">
        <h1>Relationships</h1>
        <div className="subtitle">
          Search any entity, counterparty, country, theme, or risk factor. The graph nominates what's connected —
          exposure is a separate question, asked after.
        </div>
      </div>

      <div className="card">
        <div className="searchbar">
          <input
            className="input" style={{ flex: 1 }}
            placeholder="e.g. a company, counterparty, country, or theme"
            value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch(q)}
          />
          <button className="btn" onClick={() => runSearch(q)}>Search</button>
        </div>
        {!result && !loading && (
          <div className="hstack" style={{ marginTop: 10, flexWrap: "wrap", gap: 6 }}>
            <span style={{ fontSize: 11.5, color: "var(--text-faint)" }}>Try:</span>
            {EXAMPLES.map((s) => (
              <span key={s} className="pill" onClick={() => { setQ(s); runSearch(s); }}>{s}</span>
            ))}
          </div>
        )}
      </div>

      {loading && <div className="loading">Searching…</div>}

      {result && result.resolved_as === "ambiguous" && (
        <div className="card">
          <div className="section-title">Multiple or no exact matches</div>
          {result.entity_matches.length > 0 ? (
            <div className="link-list">
              {result.entity_matches.map((m: any) => (
                <a key={m.id} style={{ cursor: "pointer" }}
                  onClick={() => (m.node_type === "Counterparty" ? nav(`/counterparty?id=${m.id}`) : runSearch(m.id))}>
                  {m.name} <span style={{ color: "var(--text-faint)", fontSize: 11 }}>({m.node_type})</span>
                </a>
              ))}
            </div>
          ) : (
            <div className="empty-state">No match. Try a different name, or a full sentence for an event/narrative query.</div>
          )}
        </div>
      )}

      {result && result.resolved_as === "theme" && (
        <div className="card">
          <div className="section-title">Theme match</div>
          <a style={{ cursor: "pointer" }} onClick={() => nav(`/theme-radar?theme=${result.theme_match.theme_id}`)}>
            {result.theme_match.label} — open Theme Radar →
          </a>
        </div>
      )}

      {result && result.resolved_as === "event" && (
        <div className="card">
          <div className="section-title">Reads as an event / narrative query</div>
          <a style={{ cursor: "pointer" }} onClick={() => nav(`/event-studio?text=${encodeURIComponent(q)}`)}>
            Open in Event Studio →
          </a>
        </div>
      )}

      {entityData && (
        <>
          <div className="card">
            <div className="hstack" style={{ justifyContent: "space-between" }}>
              <div>
                <h2 style={{ margin: 0 }}>
                  {entityData.header.name} <span style={{ color: "var(--text-faint)", fontWeight: 400 }}>({entityData.header.id})</span>
                </h2>
                <p className="subtitle">{entityData.header.sector} · {entityData.header.country}</p>
              </div>
              <DataBadge kind={entityData.header.is_synthetic ? "synthetic" : "real"} />
            </div>
          </div>

          <div className="card">
            <div className="section-title">Top related</div>
            <table className="table">
              <thead><tr><th>Entity</th><th>Score</th><th></th></tr></thead>
              <tbody>
                {entityData.relationship_summary.top_related.slice(0, 5).map((r: any) => (
                  <tr key={r.entity_id}>
                    <td>{r.name}</td>
                    <td className="mono">{r.composite_score.toFixed(3)}</td>
                    <td>
                      <button className="btn secondary" style={{ padding: "3px 10px", fontSize: 11 }} onClick={() => inspect(r.entity_id)}>
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ marginTop: 8, fontSize: 12 }}>
              <a style={{ cursor: "pointer" }} onClick={() => nav(`/entity?id=${entityData.header.id}`)}>
                Open full Entity 360 (all relationships, diagnostics, price history) →
              </a>
            </div>
          </div>

          {explain && inspecting && (
            <div className="card">
              <div className="section-title">Relationship inspector — {entityData.header.id} ↔ {inspecting}</div>
              <div className="grid-2">
                <div>
                  {Object.entries(explain.pair.composite.component_values).map(([k, v]) => (
                    <ScoreBar key={k} label={COMPONENT_LABEL[k] || k} value={v as number | null} />
                  ))}
                </div>
                <div>
                  <div className="ai-box">
                    <div className="ai-label">Why connected</div>
                    {explain.ai_explanation}
                  </div>
                  {explain.typed_path && (
                    <div style={{ marginTop: 10, fontSize: 12 }}>
                      <div className="section-title">Structural path (typed, deterministic)</div>
                      <span className="mono">{explain.typed_path.pattern}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {entityData.counterparty_materiality?.results?.length > 0 && (
            <div className="card">
              <div className="section-title">Business exposure — asked only after the relationship is established</div>
              <table className="table">
                <thead><tr><th>Counterparty</th><th>Priority</th><th>PFE</th></tr></thead>
                <tbody>
                  {entityData.counterparty_materiality.results.slice(0, 5).map((r: any) => (
                    <tr key={r.id}>
                      <td><a style={{ cursor: "pointer" }} onClick={() => nav(`/counterparty?id=${r.id}`)}>{r.name}</a></td>
                      <td style={{ fontSize: 11.5 }}>{r.priority}</td>
                      <td className="mono">{r.exposure?.pfe_current ?? "Unavailable"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
