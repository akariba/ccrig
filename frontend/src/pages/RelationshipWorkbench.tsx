import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { DataBadge } from "../components/Badge";
import { RelatednessWaterfall } from "../components/Waterfall";
import { RiskPath, pathFromHops } from "../components/RiskPath";
import { useInvestigation } from "../context/InvestigationContext";

const EXAMPLES = ["NVDA", "TSM", "interest rate volatility", "Meridian Alpha Rates Fund"];

const linklikeBtn: React.CSSProperties = {
  background: "none", border: "none", padding: 0, color: "var(--primary)", cursor: "pointer", font: "inherit",
};

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
  const [pairMateriality, setPairMateriality] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showExposure, setShowExposure] = useState(false);
  const { resetInvestigation, pushStep } = useInvestigation();

  async function runSearch(query: string) {
    if (!query.trim()) return;
    setLoading(true);
    setResult(null);
    setEntityData(null);
    setExplain(null);
    setInspecting(null);
    setShowExposure(false);
    const r = await api.search(query).catch(() => null);
    setResult(r);
    if (r && (r.resolved_as === "entity" || r.resolved_as === "counterparty")) {
      const d = await api.entity360(r.resolved_id).catch(() => null);
      setEntityData(d);
      if (d) {
        resetInvestigation({
          nodeId: d.header.id,
          nodeType: r.resolved_as === "counterparty" ? "COUNTERPARTY" : "ENTITY",
          label: d.header.name,
          route: `/?q=${encodeURIComponent(query)}`,
        });
      }
    }
    setLoading(false);
  }

  async function inspect(otherId: string, otherName: string) {
    if (!entityData) return;
    setInspecting(otherId);
    setExplain(null);
    setShowExposure(false);
    setPairMateriality([]);
    const [e, otherEntityData] = await Promise.all([
      api.explainRelationship(entityData.header.id, otherId).catch(() => null),
      api.entity360(otherId).catch(() => null),
    ]);
    setExplain(e);
    // Portfolio relevance for a PAIR must include counterparties connected
    // to either side of it - a counterparty whose typed exposure references
    // only the inspected entity (not the root) is still relevant to this
    // relationship, so we union both entities' materiality rather than
    // showing only the root entity's (which would silently miss it).
    const rootResults = entityData.counterparty_materiality?.results ?? [];
    const otherResults = otherEntityData?.counterparty_materiality?.results ?? [];
    const byId = new Map<string, any>();
    for (const r of [...rootResults, ...otherResults]) byId.set(r.id, r);
    setPairMateriality([...byId.values()]);
    // Push only once we know the typed relation (if any). A single-hop
    // structural path's relation directly connects the two nodes and is
    // safe to use as the edge label; a multi-hop path (e.g. TSM -SUPPLIES->
    // NVDA -SUPPLIES-> SSNLF) does NOT mean TSM's relation to SSNLF is
    // "SUPPLIES" - that would misrepresent an indirect chain as a direct
    // edge, so multi-hop (or absent) paths fall back to the generic,
    // honest label instead of fabricating a direct relation type.
    const hops = e?.typed_path?.hops;
    const relation = hops?.length === 1 ? hops[0].relation : "correlated with";
    pushStep({
      nodeId: otherId, nodeType: "ENTITY", label: otherName,
      route: `/?q=${encodeURIComponent(entityData.header.id)}`,
      relationFromPrevious: relation, evidenceRef: e,
    });
  }

  const productChannelCount = new Set(pairMateriality.map((r: any) => r.product).filter(Boolean)).size;
  const collateralLinkageCount = pairMateriality.filter((r: any) => r.collateral).length;

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
              {result.entity_matches.map((m: any) =>
                m.node_type === "Counterparty" ? (
                  <Link key={m.id} to={`/counterparty?id=${m.id}`}>
                    {m.name} <span style={{ color: "var(--text-faint)", fontSize: 11 }}>({m.node_type})</span>
                  </Link>
                ) : (
                  <button key={m.id} style={linklikeBtn} onClick={() => runSearch(m.id)}>
                    {m.name} <span style={{ color: "var(--text-faint)", fontSize: 11 }}>({m.node_type})</span>
                  </button>
                )
              )}
            </div>
          ) : (
            <div className="empty-state">No match. Try a different name, or a full sentence for an event/narrative query.</div>
          )}
        </div>
      )}

      {result && result.resolved_as === "theme" && (
        <div className="card">
          <div className="section-title">Theme match</div>
          <Link to={`/theme-radar?theme=${result.theme_match.theme_id}`}>{result.theme_match.label} — open Theme Radar →</Link>
        </div>
      )}

      {result && result.resolved_as === "event" && (
        <div className="card">
          <div className="section-title">Reads as an event / narrative query</div>
          <Link to={`/event-studio?text=${encodeURIComponent(q)}`}>Open in Event Studio →</Link>
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
                      <button className="btn secondary" style={{ padding: "3px 10px", fontSize: 11 }} onClick={() => inspect(r.entity_id, r.name)}>
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ marginTop: 8, fontSize: 12 }}>
              <Link to={`/entity?id=${entityData.header.id}`}>Open full Entity 360 (all relationships, diagnostics, price history) →</Link>
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

              {/* Relationship -> exposure bridge: answers "does this relationship intersect
                  the portfolio?" before any PFE is shown, per business requirement. */}
              <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
                <div className="hstack" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div style={{ fontSize: 12.5 }}>
                    <strong>Portfolio relevance</strong>
                    {pairMateriality.length > 0 ? (
                      <ul style={{ margin: "4px 0 0 18px" }}>
                        <li>{pairMateriality.length} counterpart{pairMateriality.length === 1 ? "y" : "ies"} connected</li>
                        {productChannelCount > 0 && <li>{productChannelCount} product channel{productChannelCount === 1 ? "" : "s"}</li>}
                        {collateralLinkageCount > 0 && <li>{collateralLinkageCount} collateral linkage{collateralLinkageCount === 1 ? "" : "s"}</li>}
                      </ul>
                    ) : (
                      <div style={{ color: "var(--text-faint)", marginTop: 2 }}>No connected counterparties on file.</div>
                    )}
                  </div>
                  {pairMateriality.length > 0 && !showExposure && (
                    <button style={{ ...linklikeBtn, fontWeight: 600 }} onClick={() => setShowExposure(true)}>
                      View exposure implications →
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {showExposure && pairMateriality.length > 0 && (
            <div className="card">
              <div className="section-title">Business exposure — asked only after the relationship is established</div>
              <table className="table">
                <thead><tr><th>Counterparty</th><th>Product</th><th>Priority</th><th>PFE</th></tr></thead>
                <tbody>
                  {pairMateriality.slice(0, 5).map((r: any) => (
                    <tr key={r.id}>
                      <td>
                        <Link
                          to={`/counterparty?id=${r.id}`}
                          onClick={() => pushStep({
                            nodeId: r.id, nodeType: "COUNTERPARTY", label: r.name,
                            route: `/counterparty?id=${r.id}`, relationFromPrevious: r.product ?? "exposed via",
                          })}
                        >
                          {r.name}
                        </Link>
                      </td>
                      <td style={{ fontSize: 11.5 }}>{r.product ?? "—"}</td>
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
