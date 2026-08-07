import { useEffect, useState } from "react";
import { api } from "../api/client";
import { DataBadge } from "../components/Badge";

export function BacktestLab() {
  const [scenarios, setScenarios] = useState<any[]>([]);
  const [scenarioId, setScenarioId] = useState("taiwan_earthquake_2026");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.backtestScenarios().then((d) => setScenarios(d.scenarios));
  }, []);

  async function run(id: string) {
    setScenarioId(id);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.backtestRun(id);
      setResult(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { run(scenarioId); }, []);

  return (
    <div className="stack">
      <div className="page-header">
        <h1>Backtest Lab</h1>
        <div className="subtitle">
          Look-ahead is prevented by design: the model score is computed as-of the event date using only fact-graph
          and pre-event correlation windows; observed labels use strictly forward price moves (`forward_move()`).
        </div>
      </div>

      <div className="card">
        <div className="pill-list">
          {scenarios.map((s: any) => (
            <span key={s.id} className="pill" onClick={() => run(s.id)} style={s.id === scenarioId ? { borderColor: "var(--primary)", color: "var(--text)" } : {}}>
              {s.label} {s.status !== "IMPLEMENTED" && "(not implemented)"}
            </span>
          ))}
        </div>
      </div>

      {loading && <div className="loading">Running backtest…</div>}
      {error && <div className="warning-box">{error}</div>}

      {result && !loading && (
        <>
          <div className="card">
            <div className="hstack" style={{ justifyContent: "space-between" }}>
              <h2 style={{ margin: 0 }}>{result.scenario.label}</h2>
              <DataBadge kind="real" label="Real bundled price + news data" />
            </div>
            <p className="subtitle">{result.event_narrative_at_t0}</p>
            <p style={{ fontSize: 11.5, color: "var(--text-faint)" }}>T0: {result.t0} · data cutoff: {result.data_cutoff} (no data after this date used for the model score)</p>
          </div>

          <div className="grid-3">
            <div className="card kpi"><div className="value">{result.metrics.precision_at_5}</div><div className="label">Precision@5</div></div>
            <div className="card kpi"><div className="value">{result.metrics.recall_at_5}</div><div className="label">Recall@5</div></div>
            <div className="card kpi"><div className="value">{result.metrics.ndcg_at_5}</div><div className="label">NDCG@5</div></div>
          </div>

          <div className="row">
            <div className="card" style={{ flex: 1 }}>
              <div className="section-title">Model-predicted top movers (as-of event date, no look-ahead)</div>
              <table className="table">
                <thead><tr><th>Entity</th><th>Model score</th></tr></thead>
                <tbody>
                  {result.model_ranking_top_k.map((r: any) => (
                    <tr key={r.entity_id}><td>{r.entity_id}</td><td className="mono">{r.model_score}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card" style={{ flex: 1 }}>
              <div className="section-title">Observed forward movers (realized-return proxy, not causal ground truth)</div>
              <table className="table">
                <thead><tr><th>Entity</th><th>Return ({'->'} +5d)</th></tr></thead>
                <tbody>
                  {result.observed_subsequent_movers_top_k.map((r: any) => (
                    <tr key={r.entity_id}><td>{r.entity_id}</td><td className="mono">{(r.return * 100).toFixed(1)}%</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {result.warnings?.length > 0 && (
            <div className="warning-box">
              {result.warnings.map((w: string, i: number) => <div key={i}>{w}</div>)}
            </div>
          )}
        </>
      )}
    </div>
  );
}
