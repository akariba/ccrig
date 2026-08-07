import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { api } from "../api/client";
import { DataBadge, EvidenceBadge } from "../components/Badge";

const COMPONENT_LABEL: Record<string, string> = {
  sector: "Sector match", geography: "Geography", supply_chain: "Supply chain",
  ownership: "Ownership", semantic: "Semantic (TF-IDF)", news: "News co-occurrence",
  market_positive: "Market corr. (+)", market_negative: "Market corr. (–)",
};

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

export function Entity360() {
  const [params, setParams] = useSearchParams();
  const id = params.get("id") || "TSM";
  const [inputId, setInputId] = useState(id);
  const [data, setData] = useState<any>(null);
  const [explain, setExplain] = useState<any>(null);
  const [explainTarget, setExplainTarget] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();

  useEffect(() => {
    setLoading(true);
    setExplain(null);
    api.entity360(id).then((d) => { setData(d); setLoading(false); }).catch(() => setLoading(false));
    setInputId(id);
  }, [id]);

  async function loadExplain(otherId: string) {
    setExplainTarget(otherId);
    const e = await api.explainRelationship(id, otherId);
    setExplain(e);
  }

  if (loading) return <div className="loading">Loading Entity 360…</div>;
  if (!data) return <div className="empty-state">Entity not found.</div>;

  const h = data.header;

  return (
    <div className="stack">
      <div className="page-header">
        <h1>Entity 360</h1>
        <div className="searchbar" style={{ maxWidth: 360 }}>
          <input className="input" value={inputId} onChange={(e) => setInputId(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && setParams({ id: inputId })} placeholder="Ticker/ID e.g. NVDA" />
          <button className="btn secondary" onClick={() => setParams({ id: inputId })}>Load</button>
        </div>
      </div>

      <div className="card">
        <div className="hstack" style={{ justifyContent: "space-between" }}>
          <div>
            <h2 style={{ margin: 0 }}>{h.name} <span style={{ color: "var(--text-faint)", fontWeight: 400 }}>({h.id})</span></h2>
            <p className="subtitle">{h.sector} · {h.industry} · {h.country} ({h.region})</p>
          </div>
          <DataBadge kind={h.is_synthetic ? "synthetic" : "real"} />
        </div>
        {h.lei && (
          <div className="hstack" style={{ marginTop: 10, fontSize: 12, color: "var(--text-muted)" }}>
            <DataBadge kind="real" label="GLEIF LEI" />
            <span className="mono">{h.lei}</span>
            <span>· {h.gleif_legal_name} · {h.gleif_status}</span>
          </div>
        )}
      </div>

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <div className="section-title">Relationship instrumentation</div>
          <div className="grid-3">
            <div className="kpi"><div className="value">{data.relationship_summary.instrumentation.theoretical_pair_count}</div><div className="label">Theoretical pairs</div></div>
            <div className="kpi"><div className="value">{data.relationship_summary.instrumentation.candidate_count}</div><div className="label">Candidates</div></div>
            <div className="kpi"><div className="value">{data.relationship_summary.retained_count}</div><div className="label">Retained (top-k)</div></div>
          </div>
          <p style={{ fontSize: 11.5, color: "var(--text-faint)", marginTop: 8 }}>
            Reduction ratio {(data.relationship_summary.instrumentation.reduction_ratio * 100).toFixed(0)}% — candidates generated
            from 5 blocking sources before any scoring runs.
          </p>
        </div>
      </div>

      <div className="row">
        <div className="card" style={{ flex: 1.3 }}>
          <div className="section-title">Top related entities (composite relatedness score — a VIEW over the feature vector, not the ground truth)</div>
          <table className="table">
            <thead><tr><th>Entity</th><th>Score</th><th></th></tr></thead>
            <tbody>
              {data.relationship_summary.top_related.map((r: any) => (
                <tr key={r.entity_id}>
                  <td><a onClick={() => nav(`/entity?id=${r.entity_id}`)} style={{ cursor: "pointer" }}>{r.name}</a></td>
                  <td className="mono">{r.composite_score.toFixed(3)}</td>
                  <td><button className="btn secondary" style={{ padding: "3px 10px", fontSize: 11 }} onClick={() => loadExplain(r.entity_id)}>Explain</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {explain && (
          <div className="card" style={{ flex: 1 }}>
            <div className="hstack" style={{ justifyContent: "space-between" }}>
              <h3 style={{ margin: 0 }}>{h.id} ↔ {explainTarget}</h3>
              <DataBadge kind="ai" label={explain.ai_mode === "ENHANCED_AI" ? "AI explanation" : "Deterministic explanation"} />
            </div>
            <div style={{ margin: "10px 0" }}>
              {Object.entries(explain.pair.composite.component_values).map(([k, v]) => (
                <ScoreBar key={k} label={COMPONENT_LABEL[k] || k} value={v as number | null} />
              ))}
            </div>
            <div className="ai-box">
              <div className="ai-label">Explanation</div>
              {explain.ai_explanation}
            </div>
            {explain.typed_path && (
              <div style={{ marginTop: 10, fontSize: 12 }}>
                <div className="section-title">Typed path (deterministic, not AI)</div>
                <span className="mono">
                  {explain.typed_path.pattern} — {explain.typed_path.hops?.map((hop: any) => `${hop.from} --${hop.relation}--> ${hop.to}`).join(", ")}
                </span>
                {explain.typed_path.hops?.[0]?.evidence_url && (
                  <div style={{ marginTop: 4 }}>
                    <a href={explain.typed_path.hops[0].evidence_url} target="_blank" rel="noreferrer">evidence source</a>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <div className="section-title">Fact relations · Layer A (directional, sourced)</div>
          <table className="table">
            <thead><tr><th>Dir.</th><th>Other</th><th>Relation</th><th>Crit.</th><th>Evidence</th></tr></thead>
            <tbody>
              {data.fact_links.map((f: any, i: number) => (
                <tr key={i}>
                  <td>{f.direction === "OUT" ? "→" : "←"}</td>
                  <td><a onClick={() => nav(`/entity?id=${f.other_entity}`)} style={{ cursor: "pointer" }}>{f.other_name}</a></td>
                  <td>{f.relation}</td>
                  <td className="mono">{f.criticality?.toFixed(2)}</td>
                  <td>
                    <EvidenceBadge quality={f.evidence_status === "WELL_DOCUMENTED_PUBLIC" ? "High" : f.evidence_status === "REPORTED_NEWS" ? "Medium" : "Low"} />
                    {f.evidence_url && <a href={f.evidence_url} target="_blank" rel="noreferrer" style={{ marginLeft: 6, fontSize: 11 }}>source</a>}
                  </td>
                </tr>
              ))}
              {data.fact_links.length === 0 && <tr><td colSpan={5} className="empty-state">No fact edges for this entity.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <div className="hstack" style={{ justifyContent: "space-between" }}>
            <div className="section-title" style={{ marginBottom: 0 }}>Corporate hierarchy</div>
            <DataBadge kind="real" label="GLEIF Level-2" />
          </div>
          {data.corporate_hierarchy?.has_any_ownership_data ? (
            <>
              {data.corporate_hierarchy.direct_parent && (
                <div style={{ fontSize: 12.5, marginTop: 8 }}>
                  Direct parent: {data.corporate_hierarchy.direct_parent.tracked ? (
                    <a onClick={() => nav(`/entity?id=${data.corporate_hierarchy.direct_parent.entity_id}`)} style={{ cursor: "pointer" }}>{data.corporate_hierarchy.direct_parent.name}</a>
                  ) : <span className="mono">{data.corporate_hierarchy.direct_parent.lei}</span>}
                </div>
              )}
              {data.corporate_hierarchy.ultimate_parent && (
                <div style={{ fontSize: 12.5, marginTop: 4 }}>
                  Ultimate parent: {data.corporate_hierarchy.ultimate_parent.tracked ? (
                    <a onClick={() => nav(`/entity?id=${data.corporate_hierarchy.ultimate_parent.entity_id}`)} style={{ cursor: "pointer" }}>{data.corporate_hierarchy.ultimate_parent.name}</a>
                  ) : <span className="mono">{data.corporate_hierarchy.ultimate_parent.lei}</span>}
                </div>
              )}
              {data.corporate_hierarchy.subsidiaries?.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div className="section-title" style={{ fontSize: 11 }}>Subsidiaries (tracked entities only)</div>
                  <div className="pill-list">
                    {data.corporate_hierarchy.subsidiaries.map((s: any) => (
                      <span key={s.lei} className="pill" onClick={() => s.tracked && nav(`/entity?id=${s.entity_id}`)} style={{ cursor: s.tracked ? "pointer" : "default" }}>{s.name || s.lei}</span>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="empty-state" style={{ marginTop: 8 }}>
              Ownership — N/A / insufficient data. {data.corporate_hierarchy?.note}
            </div>
          )}
        </div>
      </div>

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <div className="section-title">Theme exposure</div>
          <div className="pill-list">
            {data.theme_exposure.map((t: any) => (
              <span key={t.theme_id} className="pill" onClick={() => nav(`/theme-radar?theme=${t.theme_id}`)}>
                {t.label} · {t.weight.toFixed(1)}
              </span>
            ))}
          </div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div className="section-title">Counterparties exposed (Layer C — never comparable to relatedness score units)</div>
          <table className="table">
            <thead><tr><th>Counterparty</th><th>Relation</th><th>Exposure %</th></tr></thead>
            <tbody>
              {data.counterparties_exposed.map((c: any, i: number) => (
                <tr key={i}>
                  <td><a onClick={() => nav(`/counterparty?id=${c.counterparty}`)} style={{ cursor: "pointer" }}>{c.counterparty}</a></td>
                  <td>{c.relation}</td>
                  <td className="mono">{(c.exposure_pct * 100).toFixed(0)}%</td>
                </tr>
              ))}
              {data.counterparties_exposed.length === 0 && <tr><td colSpan={3} className="empty-state">No synthetic counterparty holds this issuer.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {h.has_market_data && data.market.price_series?.length > 0 && (
        <div className="card">
          <div className="hstack" style={{ justifyContent: "space-between" }}>
            <div className="section-title" style={{ marginBottom: 0 }}>Real price history</div>
            <DataBadge kind="real" label="Real public price data" />
          </div>
          <div style={{ height: 220, marginTop: 8 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.market.price_series.filter((_: any, i: number) => i % 3 === 0)}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="var(--text-faint)" minTickGap={60} />
                <YAxis tick={{ fontSize: 10 }} stroke="var(--text-faint)" domain={["auto", "auto"]} />
                <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
                <Line type="monotone" dataKey="close" stroke="var(--chart-1)" dot={false} strokeWidth={1.6} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="section-title" style={{ marginTop: 14 }}>Signed correlations (never absolute-valued)</div>
          <table className="table">
            <thead><tr><th>Entity</th><th>Full-sample</th><th>Stress-window (10d)</th><th>Positive ch.</th><th>Negative ch.</th></tr></thead>
            <tbody>
              {data.market.correlations.slice(0, 8).map((c: any) => (
                <tr key={c.other_entity}>
                  <td>{c.other_name}</td>
                  <td className="mono">{c.full_sample_corr}</td>
                  <td className="mono">{c.stress_window_corr}</td>
                  <td className="mono">{c.positive_channel.toFixed(2)}</td>
                  <td className="mono">{c.negative_channel.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
