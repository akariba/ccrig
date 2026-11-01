import { Fragment, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { ErrorState } from "../ui/primitives";

const PRIORITY_COLOR: Record<string, string> = {
  CRITICAL: "var(--error)",
  HIGH: "var(--warning)",
  MEDIUM: "var(--chart-6)",
  LOW: "var(--success)",
  INFORMATIONAL: "var(--text-muted)",
};

function PriorityPill({ priority }: { priority: string }) {
  const color = PRIORITY_COLOR[priority] || "var(--text-muted)";
  return (
    <span style={{
      display: "inline-block", padding: "3px 10px", borderRadius: 999, fontSize: 11, fontWeight: 700,
      letterSpacing: "0.03em", color, border: `1px solid ${color}`, background: `color-mix(in srgb, ${color} 12%, transparent)`,
    }}>
      {priority}
    </span>
  );
}

function keyExposureMove(r: any) {
  if (r.delta_pfe != null) return `ΔPFE ${r.delta_pfe > 0 ? "+" : ""}${r.delta_pfe}`;
  if (r.delta_nse != null) return `ΔNSE ${r.delta_nse > 0 ? "+" : ""}${r.delta_nse}`;
  return "n/a";
}

function controlFlag(r: any) {
  if (r.is_overdue) return { label: "OVERDUE BREACH", color: "var(--error)" };
  if (r.is_breach) return { label: "BREACH", color: "var(--warning)" };
  if (r.decision?.control_flags?.wwr) return { label: "WWR", color: "var(--warning)" };
  if (r.decision?.control_flags?.watchlist) return { label: "WATCHLIST", color: "var(--warning)" };
  if (r.utilisation_pct != null && r.utilisation_pct >= 85) return { label: "NEAR LIMIT", color: "var(--warning)" };
  return { label: "OK", color: "var(--success)" };
}

export function DailyReview() {
  const [rows, setRows] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null), [attempt, setAttempt] = useState(0);
  const [priorityFilter, setPriorityFilter] = useState<string | null>(null);
  const [specialFilter, setSpecialFilter] = useState<"overdue" | "model_data" | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const nav = useNavigate();

  useEffect(() => {
    setLoading(true); setError(null);
    api.priorityQueue(priorityFilter ? { priority: priorityFilter } : {}).then((d) => {
      setRows(d.results);
      setSummary(d.summary);
      setLoading(false);
    }).catch((e) => { setError(String(e?.message ?? e)); setLoading(false); });
  }, [priorityFilter, attempt]);

  const displayed = rows.filter((r) => {
    if (specialFilter === "overdue") return r.is_overdue;
    if (specialFilter === "model_data") return ["MODEL_RECALIBRATION", "DATA_ISSUE", "MODEL_COVERAGE_CHANGE", "DATA_SOURCING_ISSUE"].includes(r.driver);
    return true;
  });
  const visibleRows = showAll ? displayed : displayed.slice(0, 5);

  return (
    <div className="stack">
      <div className="page-header">
        <h2>Inbox</h2>
        <div className="subtitle">
          The 5 things worth a look today, ranked by the same priority logic as everywhere else in CCRIG — not a
          separate model. Full relationship-to-decision detail lives on each counterparty's own page.
        </div>
      </div>

      {summary && (
        <div className="hstack" style={{ fontSize: 12.5, color: "var(--text-muted)", flexWrap: "wrap", gap: "4px 14px" }}>
          <a style={{ cursor: "pointer", color: priorityFilter === "CRITICAL" ? "var(--error)" : undefined }}
            onClick={() => setPriorityFilter(priorityFilter === "CRITICAL" ? null : "CRITICAL")}>
            {summary.critical} critical
          </a>
          <a style={{ cursor: "pointer", color: priorityFilter === "HIGH" ? "var(--warning)" : undefined }}
            onClick={() => setPriorityFilter(priorityFilter === "HIGH" ? null : "HIGH")}>
            {summary.high} high
          </a>
          <a style={{ cursor: "pointer" }}
            onClick={() => setSpecialFilter(specialFilter === "overdue" ? null : "overdue")}>
            {summary.overdue_breaches} overdue breaches
          </a>
          <a style={{ cursor: "pointer" }}
            onClick={() => setSpecialFilter(specialFilter === "model_data" ? null : "model_data")}>
            {summary.model_or_data_items} model/data items
          </a>
          {(priorityFilter || specialFilter) && (
            <a style={{ cursor: "pointer" }} onClick={() => { setPriorityFilter(null); setSpecialFilter(null); }}>clear filter</a>
          )}
        </div>
      )}

      {error && <ErrorState message={error} onRetry={() => setAttempt((n) => n + 1)} />}
      {loading && <div className="loading">Loading Inbox…</div>}

      {!loading && !error && (
        <div className="card">
          <table className="table">
            <thead>
              <tr>
                <th>Priority</th><th>Counterparty</th><th>Trigger</th><th>Key Exposure Move</th>
                <th>Driver</th><th>Control Flag</th><th>Event / Risk Factor</th><th>Owner</th><th>Next Action</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((r) => {
                const cf = controlFlag(r);
                return (
                  <Fragment key={r.id}>
                    <tr style={{ cursor: "pointer" }} onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                      <td><PriorityPill priority={r.priority} /></td>
                      <td>{r.name}<div style={{ fontSize: 10.5, color: "var(--text-faint)" }}>{r.id}</div></td>
                      <td style={{ fontSize: 11.5, maxWidth: 220 }}>{r.reasons[0]}</td>
                      <td className="mono">{keyExposureMove(r)}</td>
                      <td style={{ fontSize: 11 }}>{r.driver}</td>
                      <td><span style={{ fontSize: 10.5, fontWeight: 700, color: cf.color }}>{cf.label}</span></td>
                      <td style={{ fontSize: 11 }}>{r.event.id !== "NONE" ? r.event.label : (r.risk_factor_path?.length ? r.risk_factor_path.join(" → ") : "—")}</td>
                      <td style={{ fontSize: 11 }}>{r.coverage_owner || <span style={{ color: "var(--error)" }}>Unassigned</span>}</td>
                      <td style={{ fontSize: 11 }}>{r.decision?.decision}</td>
                    </tr>
                    {expanded === r.id && (
                      <tr>
                        <td colSpan={9} style={{ background: "var(--surface-alt)", padding: 16 }}>
                          <div className="grid-2">
                            <div>
                              <div className="section-title">Why this is here</div>
                              <ul style={{ margin: "4px 0 0 18px", fontSize: 12.5 }}>
                                {r.reasons.map((reason: string, i: number) => <li key={i}>{reason}</li>)}
                              </ul>

                              <div className="section-title" style={{ marginTop: 12 }}>Exposure (kept separate)</div>
                              <table className="table">
                                <tbody>
                                  <tr><td>PFE (prev → current)</td><td className="mono">{r.exposure.pfe_previous ?? "n/a"} → {r.exposure.pfe_current ?? "n/a"}</td></tr>
                                  <tr><td>NSE / stress (prev → current)</td><td className="mono">{r.exposure.nse_previous ?? "n/a"} → {r.exposure.nse_current ?? "n/a"}</td></tr>
                                  <tr><td>RC (prev → current)</td><td className="mono">{r.exposure.rc_previous ?? "n/a"} → {r.exposure.rc_current ?? "n/a"}</td></tr>
                                  <tr><td>Settlement exposure</td><td className="mono">{r.exposure.settlement_exposure ?? "n/a"}</td></tr>
                                  <tr><td>Limit ({r.limit.limit_type || "none on file"})</td><td className="mono">{r.limit.limit_value ?? "Unavailable"}</td></tr>
                                  <tr><td>Utilisation</td><td className="mono">{r.utilisation_pct != null ? `${r.utilisation_pct}%` : "Unavailable"}</td></tr>
                                  <tr><td>Headroom</td><td className="mono">{r.headroom ?? "Unavailable"}</td></tr>
                                </tbody>
                              </table>
                            </div>
                            <div>
                              <div className="section-title">Driver evidence</div>
                              <ul style={{ margin: "4px 0 0 18px", fontSize: 12.5 }}>
                                {r.driver_evidence_trace.map((e: string, i: number) => <li key={i} className="mono">{e}</li>)}
                              </ul>

                              <div className="section-title" style={{ marginTop: 12 }}>Product / netting</div>
                              <div style={{ fontSize: 12.5 }}>{r.product} · netting set {r.netting_set || "n/a"} · collateral {r.collateral?.type || "n/a"}</div>

                              <div className="section-title" style={{ marginTop: 12 }}>Missing information</div>
                              <div style={{ fontSize: 12.5 }}>{r.decision.missing_information.length ? r.decision.missing_information.join(", ") : "None"}</div>

                              <div className="section-title" style={{ marginTop: 12 }}>Decision</div>
                              <div style={{ fontSize: 12.5 }}>
                                {r.decision.decision} · owner: {r.decision.recommended_owner || "unassigned"}
                                {" "}· <a onClick={() => nav(`/cp/${r.id}`)} style={{ cursor: "pointer" }}>open full Counterparty 360 →</a>
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
          {displayed.length === 0 && <div className="empty-state">No items match the current filter.</div>}
          {displayed.length > 5 && (
            <div style={{ marginTop: 10 }}>
              <a style={{ cursor: "pointer", fontSize: 12 }} onClick={() => setShowAll(!showAll)}>
                {showAll ? "Show top 5 only" : `Show all ${displayed.length}`}
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
