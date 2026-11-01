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
          and pre-event correlation windows; observed labels use strictly forward, market-adjusted price moves over one
          identical window for every entity. Entities named in the event text are inputs, not predictions.
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
            <div className="card kpi"><div className="value">{result.metrics.precision_at_3}</div><div className="label">Precision@3</div></div>
            <div className="card kpi"><div className="value">{result.metrics.recall_at_3}</div><div className="label">Recall@3</div></div>
            <div className="card kpi"><div className="value">{result.metrics.ndcg_at_3}</div><div className="label">NDCG@3</div></div>
          </div>
          <p style={{ fontSize: 11.5, color: "var(--text-muted)", margin: 0 }}>
            Corrected evaluation (methodology v{result.methodology_version}) over {result.metrics.universe_size} issuers with {result.metrics.n_positive} label
            positives. A random ranking would score precision@3 = {result.metrics.random_precision_at_3} and precision@5 = {result.metrics.random_precision_at_5};
            the probability of doing at least this well by chance is {result.metrics.p_value_at_3} (@3) and {result.metrics.p_value_at_5} (@5).
            One event is not enough to tell skill from luck.
          </p>

          <div className="card">
            <div className="section-title">Before and after the methodology correction (@5)</div>
            <table className="table">
              <thead><tr><th>Step</th><th>Change</th><th>Evaluated</th><th>Positives</th><th>Precision@5</th><th>Recall@5</th><th>NDCG@5</th><th>Random P@5</th></tr></thead>
              <tbody>
                {result.correction_steps.map((st: any) => (
                  <tr key={st.step}>
                    <td>{st.step}</td><td>{st.change}</td><td className="mono">{st.universe_size}</td><td className="mono">{st.n_positive}</td>
                    <td className="mono">{st.precision_at_5}</td><td className="mono">{st.recall_at_5}</td><td className="mono">{st.ndcg_at_5}</td>
                    <td className="mono">{st.random_precision_at_5 ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={{ fontSize: 11.5, color: "var(--text-faint)" }}>
              Step 0 is exactly what was published before: it ranked the entities named in the event text ({result.seed_entities.entities.join(", ")}),
              measured SKHY over a window starting four days late, used raw returns, and called 8 of 12 entities "positives".
            </p>
            {result.evaluation.excluded.length > 0 && (
              <p style={{ fontSize: 11.5, color: "var(--text-faint)" }}>
                Not evaluated: {result.evaluation.excluded.map((x: any) => `${x.entity_id} (${x.reason ?? x.status})`).join(", ")}.
              </p>
            )}
          </div>

          <div className="row">
            <div className="card" style={{ flex: 1 }}>
              <div className="section-title">Model-predicted movers among non-named entities (as-of event date, no look-ahead)</div>
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
              <div className="section-title">Observed movers by abnormal return (realized-return proxy, not causal ground truth)</div>
              <table className="table">
                <thead><tr><th>Entity</th><th>Return ({'->'} +5d)</th><th>Abnormal</th><th>Label</th></tr></thead>
                <tbody>
                  {result.observed_subsequent_movers_top_k.map((r: any) => (
                    <tr key={r.entity_id}>
                      <td>{r.entity_id}</td>
                      <td className="mono">{(r.return * 100).toFixed(1)}%</td>
                      <td className="mono">{(r.abnormal_return * 100).toFixed(1)}%</td>
                      <td>{r.is_label_positive ? "positive" : ""}</td>
                    </tr>
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
