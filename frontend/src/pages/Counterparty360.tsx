import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { DataBadge } from "../components/Badge";
import { RiskPath, pathFromChain } from "../components/RiskPath";
import type { GraphPath } from "../graph/types";

function clusterFocusedPath(cluster: any, counterpartyLabel: string): GraphPath | null {
  const product = cluster.products?.[0];
  const referenceEntity = cluster.direct_members?.[0];
  if (!referenceEntity) return null;
  const nodes = [
    { id: "cp", type: "COUNTERPARTY" as const, label: counterpartyLabel },
    { id: referenceEntity.id, type: "ENTITY" as const, label: referenceEntity.label },
  ];
  const edges = [{ edgeType: product ?? "HAS_EXPOSURE", traversedReverse: false }];
  const topStructural = cluster.structural_relationships?.[0];
  if (topStructural) {
    nodes.push({ id: `${referenceEntity.id}:struct`, type: "ENTITY" as const, label: topStructural.entity });
    edges.push({ edgeType: topStructural.type, traversedReverse: topStructural.reverse });
  }
  return { nodes, edges };
}

function ClusterInspector({ cluster, counterpartyLabel }: { cluster: any; counterpartyLabel: string }) {
  const [showContextual, setShowContextual] = useState(false);
  const path = clusterFocusedPath(cluster, counterpartyLabel);
  return (
    <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
      <div className="section-title" style={{ fontSize: 11 }}>Direct exposure</div>
      <div style={{ fontSize: 12.5, marginBottom: 8 }}>{cluster.direct_members.map((m: any) => m.label).join(", ") || "—"}</div>

      {cluster.first_order_members?.length > 0 && (
        <>
          <div className="section-title" style={{ fontSize: 11 }}>First-order relationships</div>
          <div style={{ fontSize: 12.5, marginBottom: 8 }}>{cluster.first_order_members.map((m: any) => m.label).join(", ")}</div>
        </>
      )}

      {cluster.contextual_members?.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <button className="btn secondary" style={{ padding: "2px 8px", fontSize: 10.5 }} onClick={() => setShowContextual(!showContextual)}>
            {showContextual ? "Hide" : `Show ${cluster.contextual_members.length} more contextual relationships`}
          </button>
          {showContextual && (
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 6 }}>
              {cluster.contextual_members.map((m: any) => m.label).join(", ")}
            </div>
          )}
        </div>
      )}

      <div className="section-title" style={{ fontSize: 11 }}>Why grouped</div>
      <ul style={{ margin: "4px 0 12px 18px", fontSize: 12.5 }}>
        {cluster.evidence.map((e: string, i: number) => <li key={i}>{e}</li>)}
      </ul>

      {path && (
        <>
          <div className="section-title" style={{ fontSize: 11 }}>Focused path</div>
          <div style={{ marginBottom: 12 }}><RiskPath path={path} /></div>
        </>
      )}

      {cluster.statistical_relationships?.length > 0 && (
        <>
          <div className="section-title" style={{ fontSize: 11 }}>Correlation evidence (signed)</div>
          <div style={{ fontSize: 12.5, marginBottom: 12 }}>
            {cluster.statistical_relationships.map((s: any, i: number) => (
              <div key={i}>{s.entity}: <span className="mono">{s.signed_correlation > 0 ? "+" : ""}{s.signed_correlation}</span> ({s.method})</div>
            ))}
          </div>
        </>
      )}

      {cluster.relevant_events?.length > 0 && (
        <div style={{ fontSize: 12.5, marginBottom: 8 }}>
          <strong>Relevant event:</strong> {cluster.relevant_events.map((e: any) => e.label).join(", ")}
        </div>
      )}
      {cluster.relevant_controls?.length > 0 && (
        <div style={{ fontSize: 12.5 }}>
          <strong>Relevant control:</strong> {cluster.relevant_controls.map((c: any) => c.label).join(", ")}
        </div>
      )}
    </div>
  );
}

const PRIORITY_COLOR: Record<string, string> = {
  CRITICAL: "var(--error)", HIGH: "var(--warning)", MEDIUM: "var(--chart-6)", LOW: "var(--success)",
  INFORMATIONAL: "var(--text-muted)",
};

function PriorityPill({ priority }: { priority: string }) {
  const color = PRIORITY_COLOR[priority] || "var(--text-muted)";
  return (
    <span style={{
      display: "inline-block", padding: "3px 10px", borderRadius: 999, fontSize: 11, fontWeight: 700,
      color, border: `1px solid ${color}`,
    }}>{priority}</span>
  );
}

function Field({ label, value }: { label: string; value: any }) {
  return (
    <div className="hstack" style={{ justifyContent: "space-between", fontSize: 12.5, padding: "3px 0" }}>
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span className="mono">{value === null || value === undefined ? <em style={{ color: "var(--text-faint)" }}>Unavailable</em> : String(value)}</span>
    </div>
  );
}

function Collapsible({ label, children }: { label: string; children: any }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 16, borderTop: "1px solid var(--border)", paddingTop: 10 }}>
      <span className="pill" onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} {label}</span>
      {open && <div style={{ marginTop: 8 }}>{children}</div>}
    </div>
  );
}

const TABS = [
  { key: "relationships", label: "Relationships" },
  { key: "exposure", label: "Exposure & Controls" },
  { key: "decision", label: "Decision" },
] as const;
type TabKey = typeof TABS[number]["key"];

function TabBar({ active, onChange }: { active: TabKey; onChange: (k: TabKey) => void }) {
  return (
    <div className="hstack" style={{ gap: 18, borderBottom: "1px solid var(--border)", marginTop: 14, marginBottom: 16 }}>
      {TABS.map((t) => (
        <span
          key={t.key}
          onClick={() => onChange(t.key)}
          style={{
            cursor: "pointer", fontSize: 13, padding: "8px 2px", fontWeight: active === t.key ? 600 : 500,
            color: active === t.key ? "var(--primary)" : "var(--text-muted)",
            borderBottom: active === t.key ? "2px solid var(--primary)" : "2px solid transparent",
          }}
        >
          {t.label}
        </span>
      ))}
    </div>
  );
}

export function Counterparty360() {
  const [params, setParams] = useSearchParams();
  const [portfolioList, setPortfolioList] = useState<any[]>([]);
  const [ccrList, setCcrList] = useState<any[]>([]);
  const id = params.get("id");
  const [portfolioData, setPortfolioData] = useState<any>(null);
  const [ccrData, setCcrData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<TabKey>("relationships");
  const [clusters, setClusters] = useState<any[]>([]);
  const [openCluster, setOpenCluster] = useState<string | null>(null);
  const nav = useNavigate();

  useEffect(() => {
    Promise.all([api.listCounterparties(), api.priorityQueue()]).then(([portfolio, ccr]) => {
      setPortfolioList(portfolio.results);
      setCcrList(ccr.results);
      if (!id) setParams({ id: ccr.results[0]?.id || portfolio.results[0]?.id });
    });
  }, []);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setPortfolioData(null);
    setCcrData(null);
    setClusters([]);
    setOpenCluster(null);
    Promise.allSettled([api.counterparty360(id), api.priorityDetail(id), api.riskClusters(id)]).then(([portfolio, ccr, rc]) => {
      if (portfolio.status === "fulfilled") setPortfolioData(portfolio.value);
      if (ccr.status === "fulfilled") setCcrData(ccr.value);
      if (rc.status === "fulfilled") setClusters(rc.value.results);
      setLoading(false);
    });
  }, [id]);

  const name = ccrData?.name || portfolioData?.header?.name || id;
  const r = ccrData; // shorthand for the CCR record (already enriched + classified + decision-attached)

  return (
    <div className="stack">
      <div className="page-header">
        <h1>Counterparty 360</h1>
        <div className="subtitle">
          Synthetic, fictional POC data — no real fund, bank, or institution is represented. Three questions, in
          order: what is this counterparty connected to, how is that exposed and controlled, and what should I do
          about it.
        </div>
      </div>

      <div className="card">
        <div className="section-title">CCR counterparties</div>
        <div className="pill-list">
          {ccrList.map((c) => (
            <span key={c.id} className="pill" style={id === c.id ? { borderColor: "var(--primary)", color: "var(--text)" } : {}} onClick={() => setParams({ id: c.id })}>
              {c.name} <span style={{ opacity: 0.6 }}>· {c.priority}</span>
            </span>
          ))}
        </div>
        <div className="section-title" style={{ marginTop: 12 }}>Portfolio-holdings counterparties</div>
        <div className="pill-list">
          {portfolioList.map((c) => (
            <span key={c.id} className="pill" style={id === c.id ? { borderColor: "var(--primary)", color: "var(--text)" } : {}} onClick={() => setParams({ id: c.id })}>
              {c.name}
            </span>
          ))}
        </div>
      </div>

      {loading && <div className="loading">Loading Counterparty 360…</div>}

      {!loading && (ccrData || portfolioData) && (
        <>
          <div className="card">
            <div className="hstack" style={{ justifyContent: "space-between" }}>
              <div>
                <h2 style={{ margin: 0 }}>{name}</h2>
                <p className="subtitle" style={{ marginTop: 2 }}>{r?.legal_entity || portfolioData?.header?.industry}</p>
              </div>
              <div className="hstack">
                {r && <PriorityPill priority={r.priority} />}
                <DataBadge kind="synthetic" />
              </div>
            </div>

            {!r && (
              <div className="empty-state" style={{ marginTop: 10 }}>No CCR investigation record for this counterparty (portfolio-holdings only — see supporting intelligence below).</div>
            )}

            {r && <TabBar active={tab} onChange={setTab} />}

            {r && tab === "relationships" && (
              <>
                {clusters.length > 0 && (
                  <>
                    <div className="section-title">Key risk clusters</div>
                    <p className="subtitle" style={{ marginTop: -6, marginBottom: 10 }}>
                      Derived from the counterparty's actual exposure graph — structural relationships, market
                      correlation, and risk-factor transmission — never a hardcoded label.
                    </p>
                    {clusters.map((c) => (
                      <div key={c.id} style={{ marginBottom: 10, padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                        <div className="hstack" style={{ justifyContent: "space-between" }}>
                          <div>
                            <div style={{ fontWeight: 600, fontSize: 13.5 }}>{c.label}</div>
                            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{c.summary}</div>
                          </div>
                          <button className="btn secondary" style={{ padding: "3px 10px", fontSize: 11 }}
                            onClick={() => setOpenCluster(openCluster === c.id ? null : c.id)}>
                            {openCluster === c.id ? "Hide" : "View path"}
                          </button>
                        </div>
                        {openCluster === c.id && <ClusterInspector cluster={c} counterpartyLabel={name} />}
                      </div>
                    ))}
                  </>
                )}

                <div className="section-title" style={{ marginTop: clusters.length > 0 ? 20 : 0 }}>Counterparty details</div>
                <div className="grid-3">
                  <Field label="Counterparty type" value={r.counterparty_type} />
                  <Field label="Rating" value={r.rating} />
                  <Field label="Watchlist" value={r.watchlist ? "Yes" : "No"} />
                </div>
                {r.risk_factor_path?.length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 6 }}>Risk-factor transmission path</div>
                    <RiskPath path={pathFromChain(r.risk_factor_path)} />
                  </div>
                )}
                {r.reference_entity_id && (
                  <div style={{ fontSize: 12.5, marginTop: 4 }}>
                    <strong>Reference issuer:</strong> <a onClick={() => nav(`/entity?id=${r.reference_entity_id}`)} style={{ cursor: "pointer" }}>{r.reference_entity_id}</a> (public relationship-discovery data, not a real position)
                  </div>
                )}
                {r.event.id !== "NONE" && (
                  <div className="ai-box" style={{ marginTop: 8 }}>
                    <div className="ai-label">Active event</div>
                    {r.event.label} — {r.event.description}
                  </div>
                )}

                {portfolioData ? (
                  <>
                    <div className="section-title" style={{ marginTop: 20 }}>Direct holdings (Layer C — exposure_pct)</div>
                    <table className="table">
                      <thead><tr><th>Issuer</th><th>Relation</th><th>Exposure %</th></tr></thead>
                      <tbody>
                        {portfolioData.direct_holdings.map((h: any, i: number) => (
                          <tr key={i}>
                            <td><a onClick={() => nav(`/entity?id=${h.issuer}`)} style={{ cursor: "pointer" }}>{h.issuer}</a></td>
                            <td>{h.relation}</td>
                            <td className="mono">{(h.exposure_pct * 100).toFixed(0)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                    <Collapsible label="Concentration &amp; indirect relationships">
                      <div className="row">
                        <div style={{ flex: 1 }}>
                          <div className="section-title">Concentration by sector</div>
                          {Object.entries(portfolioData.concentration_by_sector).map(([sector, pct]: any) => (
                            <div key={sector} style={{ marginBottom: 8 }}>
                              <div className="hstack" style={{ justifyContent: "space-between", fontSize: 12 }}>
                                <span>{sector}</span><span className="mono">{(pct * 100).toFixed(0)}%</span>
                              </div>
                              <div className="score-bar-track"><div className="score-bar-fill" style={{ width: `${pct * 100}%` }} /></div>
                            </div>
                          ))}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div className="section-title">Indirect relationships (Layer B — never sum with exposure_pct)</div>
                          <table className="table">
                            <thead><tr><th>Via</th><th>Indirect entity</th><th>Score</th></tr></thead>
                            <tbody>
                              {portfolioData.indirect_relationships.slice(0, 10).map((rel: any, i: number) => (
                                <tr key={i}>
                                  <td style={{ fontSize: 11 }}>{rel.via_direct_holding}</td>
                                  <td><a onClick={() => nav(`/entity?id=${rel.indirect_entity}`)} style={{ cursor: "pointer" }}>{rel.indirect_entity}</a></td>
                                  <td className="mono">{rel.relatedness_score.toFixed(3)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                      <p style={{ fontSize: 11.5, color: "var(--text-faint)", marginTop: 8 }}>{portfolioData.risk_cluster_note}</p>
                    </Collapsible>
                  </>
                ) : (
                  <div className="empty-state" style={{ marginTop: 12 }}>No portfolio-holdings data for this counterparty (CCR-only record).</div>
                )}
              </>
            )}

            {r && tab === "exposure" && (
              <>
                {r.decision.economic_exposure_paths?.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    {r.decision.economic_exposure_paths.map((p: string, i: number) => (
                      <div key={i} style={{ marginBottom: 6 }}>
                        <RiskPath path={pathFromChain(p.split(" → "))} />
                      </div>
                    ))}
                  </div>
                )}
                <div className="grid-3">
                  <Field label="Product" value={r.product} />
                  <Field label="Netting set" value={r.netting_set} />
                  <Field label="Notional" value={r.notional} />
                </div>
                <div className="grid-3">
                  <Field label="Direction" value={r.direction} />
                  <Field label="Unmatched trades" value={r.unmatched_trades === null ? null : (r.unmatched_trades ? "Yes" : "No")} />
                  <Field label="Collateral type" value={r.collateral?.type} />
                </div>

                <div className="section-title" style={{ marginTop: 20 }}>Risk drivers</div>
                <ul style={{ margin: "4px 0 0 18px", fontSize: 12.5 }}>
                  {r.decision.risk_drivers.map((s: string, i: number) => <li key={i}>{s}</li>)}
                </ul>

                <div className="section-title" style={{ marginTop: 20 }}>Materiality</div>
                <table className="table">
                  <thead><tr><th>Metric</th><th>Value</th><th>Status</th></tr></thead>
                  <tbody>
                    {r.decision.materiality_metrics.map((m: any) => (
                      <tr key={m.metric}>
                        <td>{m.metric}</td>
                        <td className="mono">{m.value ?? "—"}</td>
                        <td style={{ fontSize: 11, color: m.status === "AVAILABLE" ? "var(--success)" : "var(--text-faint)" }}>{m.status}</td>
                      </tr>
                    ))}
                    <tr><td>Δ PFE</td><td className="mono">{r.delta_pfe != null ? (r.delta_pfe > 0 ? "+" : "") + r.delta_pfe : "—"}</td><td style={{ fontSize: 11, color: r.delta_pfe != null ? "var(--success)" : "var(--text-faint)" }}>{r.delta_pfe != null ? "AVAILABLE" : "UNAVAILABLE"}</td></tr>
                    <tr><td>Δ NSE</td><td className="mono">{r.delta_nse != null ? (r.delta_nse > 0 ? "+" : "") + r.delta_nse : "—"}</td><td style={{ fontSize: 11, color: r.delta_nse != null ? "var(--success)" : "var(--text-faint)" }}>{r.delta_nse != null ? "AVAILABLE" : "UNAVAILABLE"}</td></tr>
                  </tbody>
                </table>

                {r.event.id !== "NONE" && (
                  <div style={{ fontSize: 12.5, marginTop: 16 }}>
                    <strong>Linked stress scenario:</strong> {r.event.label} — {r.event.description}
                  </div>
                )}

                <div className="section-title" style={{ marginTop: 20 }}>Controls</div>
                <table className="table">
                  <thead><tr><th>Constraint</th><th>Value</th><th>Status</th></tr></thead>
                  <tbody>
                    {r.decision.control_constraints.map((c: any, i: number) => (
                      <tr key={i}>
                        <td>{c.constraint}</td>
                        <td className="mono">{c.value ?? "—"}</td>
                        <td style={{ fontSize: 11, color: c.status === "AVAILABLE" ? "var(--success)" : "var(--text-faint)" }}>{c.status}</td>
                      </tr>
                    ))}
                    <tr><td>Headroom</td><td className="mono">{r.headroom ?? "—"}</td><td style={{ fontSize: 11, color: r.headroom != null ? "var(--success)" : "var(--text-faint)" }}>{r.headroom != null ? "AVAILABLE" : "UNAVAILABLE"}</td></tr>
                    <tr><td>Coverage owner</td><td>{r.coverage_owner || "—"}</td><td style={{ fontSize: 11, color: r.coverage_owner ? "var(--success)" : "var(--error)" }}>{r.coverage_owner ? "AVAILABLE" : "NOT_PROVIDED"}</td></tr>
                  </tbody>
                </table>
                {r.is_breach && (
                  <div className="warning-box" style={{ marginTop: 8 }}>
                    Breach: {r.breach.age_days} business days old vs. {r.breach.sla_days}-day SLA, excess {r.excess}.
                    Root cause: {r.breach.root_cause || "unknown"}. {r.is_overdue && <strong>OVERDUE.</strong>}
                  </div>
                )}
              </>
            )}

            {r && tab === "decision" && (
              <>
                <div className="ai-box">
                  <div className="ai-label">{r.decision.decision}</div>
                  <ul style={{ margin: "6px 0 0 18px", fontSize: 12.5 }}>
                    {r.decision.decision_reasons.map((reason: string, i: number) => <li key={i}>{reason}</li>)}
                  </ul>
                  {r.decision.missing_information.length > 0 && (
                    <div style={{ marginTop: 8, fontSize: 12 }}>
                      <strong>Missing information:</strong> {r.decision.missing_information.join(", ")}
                    </div>
                  )}
                </div>

                <Collapsible label="Technical evidence (raw flags, for auditability)">
                  <div style={{ fontSize: 11.5 }}>
                    <div className="mono" style={{ marginBottom: 6 }}>driver = {r.driver}</div>
                    <ul style={{ margin: "0 0 0 18px" }}>
                      {r.driver_evidence_trace.map((e: string, i: number) => <li key={i} className="mono">{e}</li>)}
                    </ul>
                  </div>
                </Collapsible>
              </>
            )}
          </div>

          {!r && portfolioData && (
            <div className="card">
              <div className="section-title">Portfolio-holdings intelligence</div>
              <table className="table">
                <thead><tr><th>Issuer</th><th>Relation</th><th>Exposure %</th></tr></thead>
                <tbody>
                  {portfolioData.direct_holdings.map((h: any, i: number) => (
                    <tr key={i}>
                      <td><a onClick={() => nav(`/entity?id=${h.issuer}`)} style={{ cursor: "pointer" }}>{h.issuer}</a></td>
                      <td>{h.relation}</td>
                      <td className="mono">{(h.exposure_pct * 100).toFixed(0)}%</td>
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
