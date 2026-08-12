import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { DataBadge } from "../components/Badge";
import { RelatednessWaterfall } from "../components/Waterfall";
import { RiskPath, pathFromHops } from "../components/RiskPath";

const EXAMPLES = ["NVDA", "TSM", "interest rate volatility", "Meridian Alpha Rates Fund"];

function Field({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div>
      <div style={{ color: "var(--text-muted)", fontSize: 11 }}>{label}</div>
      <div className="mono" style={{ fontWeight: 600 }}>{value == null ? "n/a" : (value > 0 ? "+" : "") + value.toFixed(3)}</div>
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

              <div className="section-title" style={{ fontSize: 11, marginTop: 4 }}>Why connected</div>
              <div className="ai-box">{explain.ai_explanation}</div>
              {explain.typed_path?.hops?.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 6 }}>Structural path (typed, deterministic)</div>
                  <RiskPath {...pathFromHops(explain.typed_path.hops)} />
                </div>
              )}

              {explain.pair.vector.market_detail && (
                <>
                  <div className="section-title" style={{ fontSize: 11, marginTop: 18 }}>Correlation (signed — never absolute-valued)</div>
                  <div className="grid-3" style={{ fontSize: 12.5 }}>
                    <Field label="Full-sample" value={explain.pair.vector.market_detail.full_sample_corr} />
                    <Field label={`Rolling (${explain.pair.vector.market_detail.rolling_window_days}d)`} value={explain.pair.vector.market_detail.rolling_corr} />
                    <Field label={`Stress window (${explain.pair.vector.market_detail.stress_window_days}d)`} value={explain.pair.vector.market_detail.stress_window_corr} />
                  </div>
                  <p style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 4 }}>
                    This signed value is not the same as the market-correlation bar below — the waterfall contribution is a
                    directional channel derived from it (positive channel = max(ρ,0), inverse channel = max(-ρ,0)).
                  </p>
                </>
              )}

              {explain.pair.composite.score != null && (
                <>
                  <div className="section-title" style={{ fontSize: 11, marginTop: 18 }}>Score waterfall</div>
                  <RelatednessWaterfall
                    waterfall={explain.pair.composite.waterfall}
                    excluded={explain.pair.composite.excluded_components}
                    score={explain.pair.composite.score}
                  />
                </>
              )}

              {entityData.counterparty_materiality?.results?.length > 0 && (
                <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
                  <a style={{ cursor: "pointer", fontSize: 12.5, fontWeight: 600 }}
                    onClick={() => document.getElementById("business-exposure")?.scrollIntoView({ behavior: "smooth" })}>
                    View exposure implications ↓
                  </a>
                </div>
              )}
            </div>
          )}

          {entityData.counterparty_materiality?.results?.length > 0 && (
            <div className="card" id="business-exposure">
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
