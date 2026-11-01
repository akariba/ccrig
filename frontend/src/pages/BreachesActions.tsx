import { Fragment, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { ErrorState } from "../ui/primitives";

function exposureForLimitType(r: any) {
  // Utilisation/excess is ONLY ever computed against the metric matching
  // the limit's own type - never RC-vs-arbitrary-limit, never PFE-vs-a-
  // settlement-limit (this mirrors the backend fix in core/ccr_priority.py).
  const t = r.limit?.limit_type;
  if (t === "PFE_LIMIT") return r.exposure.pfe_current;
  if (t === "SETTLEMENT_LIMIT") return r.exposure.settlement_exposure;
  if (t === "STRESS_LIMIT") return r.exposure.nse_current;
  return null;
}

export function BreachesActions() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null), [attempt, setAttempt] = useState(0);
  const [statusFilter, setStatusFilter] = useState<"" | "overdue" | "within_sla">("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const nav = useNavigate();

  useEffect(() => {
    setLoading(true); setError(null);
    api.breaches(statusFilter ? { status: statusFilter } : {}).then((d) => {
      setRows(d.results);
      setLoading(false);
    }).catch((e) => { setError(String(e?.message ?? e)); setLoading(false); });
  }, [statusFilter, attempt]);

  return (
    <div className="stack">
      <div className="page-header">
        <h2>Control Exceptions</h2>
        <div className="subtitle">
          Active synthetic limit breaches. Age is the primary sort — an overdue small breach is still a governance
          problem, regardless of size. Expand a row for exposure/limit detail.
        </div>
      </div>

      <div className="hstack" style={{ fontSize: 12.5 }}>
        <a style={{ cursor: "pointer", color: statusFilter === "" ? "var(--primary)" : "var(--text-muted)" }} onClick={() => setStatusFilter("")}>All</a>
        <a style={{ cursor: "pointer", color: statusFilter === "overdue" ? "var(--error)" : "var(--text-muted)" }} onClick={() => setStatusFilter("overdue")}>Overdue only</a>
        <a style={{ cursor: "pointer", color: statusFilter === "within_sla" ? "var(--primary)" : "var(--text-muted)" }} onClick={() => setStatusFilter("within_sla")}>Within SLA</a>
      </div>

      {error && <ErrorState message={error} onRetry={() => setAttempt((n) => n + 1)} />}
      {loading && <div className="loading">Loading control exceptions…</div>}

      {!loading && !error && (
        <div className="card">
          <table className="table">
            <thead>
              <tr>
                <th>Subject</th><th>Control</th><th>Exception</th><th>Age</th><th>Owner</th><th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <Fragment key={r.id}>
                  <tr style={{ cursor: "pointer", background: r.is_overdue ? "color-mix(in srgb, var(--error) 8%, transparent)" : undefined }}
                    onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                    <td><a onClick={(e) => { e.stopPropagation(); nav(`/cp/${r.id}`); }}>{r.name}</a></td>
                    <td style={{ fontSize: 11 }}>{r.limit?.limit_type || "Unavailable"}</td>
                    <td className="mono" style={{ color: "var(--error)" }}>+{r.excess}</td>
                    <td className="mono" style={{ color: r.is_overdue ? "var(--error)" : "var(--text)", fontWeight: r.is_overdue ? 700 : 400 }}>
                      {r.breach?.age_days}d {r.is_overdue && "· OVERDUE"}
                    </td>
                    <td style={{ fontSize: 11.5 }}>{r.coverage_owner || <span style={{ color: "var(--error)" }}>Unassigned</span>}</td>
                    <td style={{ fontSize: 11 }}>{r.decision?.decision}</td>
                  </tr>
                  {expanded === r.id && (
                    <tr>
                      <td colSpan={6} style={{ background: "var(--surface-alt)", padding: 14, fontSize: 12 }}>
                        <div className="grid-3">
                          <div>{r.legal_entity} · {r.product}</div>
                          <div>Exposure {exposureForLimitType(r) ?? "n/a"} vs. limit {r.limit?.limit_value ?? "n/a"}</div>
                          <div>SLA {r.breach?.sla_days}d · root cause: {r.breach?.root_cause || "Unknown"}</div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {rows.length === 0 && <tr><td colSpan={6} className="empty-state">No breaches match this filter.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
