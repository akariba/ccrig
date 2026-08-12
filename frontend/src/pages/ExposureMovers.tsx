import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { DataBadge } from "../components/Badge";

type Tab = "pfe" | "stress" | "rc" | "sensitivity";

const TABS: { key: Tab; label: string }[] = [
  { key: "pfe", label: "PFE Movers" },
  { key: "stress", label: "Stress / NSE Movers" },
  { key: "rc", label: "RC / MTM Movers" },
  { key: "sensitivity", label: "Sensitivity Movers" },
];

function moveValue(r: any, tab: Tab): number | null {
  if (tab === "pfe") return r.delta_pfe;
  if (tab === "stress") return r.delta_nse;
  if (tab === "rc") {
    const { rc_previous, rc_current } = r.exposure;
    return rc_previous != null && rc_current != null ? rc_current - rc_previous : null;
  }
  // sensitivity: equity delta move if available, else fx delta magnitude
  const { equity_delta_previous, equity_delta_current, fx_delta } = r.sensitivities;
  if (equity_delta_previous != null && equity_delta_current != null) return equity_delta_current - equity_delta_previous;
  if (fx_delta != null) return fx_delta;
  return null;
}

export function ExposureMovers() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("pfe");
  const nav = useNavigate();

  useEffect(() => {
    api.priorityQueue().then((d) => { setRows(d.results); setLoading(false); });
  }, []);

  const withMove = rows
    .map((r) => ({ r, move: moveValue(r, tab) }))
    .filter((x) => x.move !== null)
    .sort((a, b) => Math.abs(b.move as number) - Math.abs(a.move as number));

  return (
    <div className="stack">
      <div className="page-header">
        <h1>Exposure Movers</h1>
        <div className="subtitle">
          What moved and why — not what is most risky. A large mover here may be a genuine market move, a new
          trade, a model recalibration, a data issue, or a maturing/matured trade. Always check the driver column
          before treating size as urgency; use the Daily Review for governance-aware priority.
        </div>
      </div>

      <div className="card">
        <div className="hstack">
          {TABS.map((t) => (
            <span key={t.key} className="pill" style={tab === t.key ? { borderColor: "var(--primary)" } : {}} onClick={() => setTab(t.key)}>{t.label}</span>
          ))}
        </div>
      </div>

      {loading && <div className="loading">Loading exposure movers…</div>}

      {!loading && (
        <div className="card">
          <table className="table">
            <thead>
              <tr>
                <th>Counterparty</th><th>Move</th><th>Driver</th><th>Product</th><th>Utilisation</th><th>Priority</th>
              </tr>
            </thead>
            <tbody>
              {withMove.map(({ r, move }) => (
                <tr key={r.id}>
                  <td><a onClick={() => nav(`/counterparty?id=${r.id}`)} style={{ cursor: "pointer" }}>{r.name}</a></td>
                  <td className="mono" style={{ color: (move as number) > 0 ? "var(--warning)" : "var(--text)" }}>{(move as number) > 0 ? "+" : ""}{move}</td>
                  <td style={{ fontSize: 11, fontWeight: 600 }}>{r.driver}</td>
                  <td style={{ fontSize: 11 }}>{r.product}</td>
                  <td className="mono">{r.utilisation_pct != null ? `${r.utilisation_pct}%` : "Unavailable"}</td>
                  <td><DataBadge kind={r.priority === "CRITICAL" || r.priority === "HIGH" ? "synthetic" : "derived"} label={r.priority} /></td>
                </tr>
              ))}
              {withMove.length === 0 && <tr><td colSpan={6} className="empty-state">No counterparties have a confirmed move for this metric.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
