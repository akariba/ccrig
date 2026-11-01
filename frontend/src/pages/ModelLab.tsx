import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiErrorMessage } from "../api/client";
import { DataBadge } from "../components/Badge";

const WEIGHT_LABELS: Record<string, string> = {
  sector: "Sector", geography: "Geography", supply_chain: "Supply chain", ownership: "Ownership",
  semantic: "Semantic", news: "News co-mention", market_positive: "Market corr. (+)", market_negative: "Market corr. (–)",
};

export function ModelLab() {
  const [presets, setPresets] = useState<any>(null);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [entityId, setEntityId] = useState("TSM");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [calibration, setCalibration] = useState<any>(null);
  const [calibrating, setCalibrating] = useState(false);
  const [marketAgreement, setMarketAgreement] = useState<any>(null);
  const nav = useNavigate();

  useEffect(() => {
    api.modelLabPresets().then((d) => {
      setPresets(d.presets);
      setWeights(d.default_weights);
    });
  }, []);

  async function runCalibration() {
    setCalibrating(true);
    try {
      const r = await api.calibrationRun({});
      setCalibration(r);
      const m = await api.calibrationMarketAgreement({ weights: r.calibrated_weights });
      setMarketAgreement(m);
    } finally {
      setCalibrating(false);
    }
  }

  function applyCalibratedWeights() {
    if (calibration) setWeights(calibration.calibrated_weights);
  }

  function restoreHeuristicWeights() {
    if (presets) setWeights(presets.general.weights);
  }

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.modelLabScore({ entity_id: entityId, weights });
      setResult(r);
    } catch (e) {
      setResult(null);   // never leave a ranking on screen that does not match the weights just submitted
      setError(apiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  function applyPreset(key: string) {
    setWeights(presets[key].weights);
  }

  if (!presets) return <div className="loading">Loading Model Lab…</div>;

  return (
    <div className="stack">
      <div className="page-header">
        <h2>Model Lab</h2>
        <div className="subtitle">
          Exploratory weight tuning over the same feature vector used everywhere else in the platform. These are
          heuristic starting weights for scenario exploration — not a calibrated production model.
        </div>
      </div>

      {error && <div className="warning-box">{error}</div>}

      <div className="row">
        <div className="card" style={{ flex: 1 }}>
          <div className="section-title">Presets</div>
          <div className="pill-list">
            {Object.entries(presets).map(([key, p]: any) => (
              <span key={key} className="pill" onClick={() => applyPreset(key)}>{p.label}</span>
            ))}
          </div>

          <div className="section-title" style={{ marginTop: 18 }}>Weights</div>
          {Object.entries(weights).map(([k, v]) => (
            <div key={k} style={{ marginBottom: 12 }}>
              <div className="hstack" style={{ justifyContent: "space-between", fontSize: 12 }}>
                <span>{WEIGHT_LABELS[k] || k}</span><span className="mono">{v.toFixed(2)}</span>
              </div>
              <input type="range" min={0} max={0.5} step={0.01} value={v} style={{ width: "100%" }}
                onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) })} />
            </div>
          ))}

          <div className="hstack" style={{ marginTop: 12 }}>
            <input className="input" style={{ maxWidth: 120 }} value={entityId} onChange={(e) => setEntityId(e.target.value.toUpperCase())} />
            <button className="btn" onClick={run} disabled={loading}>{loading ? "Scoring…" : "Recompute rank"}</button>
          </div>
        </div>

        <div className="card" style={{ flex: 1.3 }}>
          <div className="hstack" style={{ justifyContent: "space-between" }}>
            <div className="section-title" style={{ marginBottom: 0 }}>Ranked results for {entityId}</div>
            {result && <DataBadge kind="derived" label={`${result.scored_pair_count} scored / ${result.retained_count} retained`} />}
          </div>
          {!result && <div className="empty-state">Adjust weights and recompute to see live re-ranking.</div>}
          {result && (
            <table className="table" style={{ marginTop: 10 }}>
              <thead><tr><th>#</th><th>Entity</th><th>Score</th></tr></thead>
              <tbody>
                {result.results.map((r: any, i: number) => (
                  <tr key={r.entity_id}>
                    <td>{i + 1}</td>
                    <td><a onClick={() => nav(`/issuer/${r.entity_id}`)} style={{ cursor: "pointer" }}>{r.name}</a></td>
                    <td className="mono">{r.score.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="card">
        <div className="hstack" style={{ justifyContent: "space-between" }}>
          <div className="section-title" style={{ marginBottom: 0 }}>Experimental Anchor Calibration</div>
          <DataBadge kind="derived" label="POC weak-supervision experiment" />
        </div>
        <div className="subtitle">
          Nudges the same weighted composite formula toward a small set of hand-picked relative-ranking anchors
          (Score(A, preferred) &gt; Score(A, less-related)), regularised back toward the heuristic starting weights so
          a small anchor set cannot produce extreme coefficients. <strong>Coefficients are not statistically
          validated.</strong>
        </div>

        <div className="hstack" style={{ marginTop: 10 }}>
          <button className="btn" onClick={runCalibration} disabled={calibrating}>
            {calibrating ? "Calibrating…" : "Run calibration"}
          </button>
          <button className="btn" onClick={applyCalibratedWeights} disabled={!calibration}>
            Apply calibrated weights to Model Lab
          </button>
          <button className="btn" onClick={restoreHeuristicWeights} disabled={!presets}>
            Restore heuristic weights
          </button>
        </div>

        {calibration && (
          <>
            <table className="table" style={{ marginTop: 14 }}>
              <thead><tr><th>Component</th><th>Starting</th><th>Calibrated</th></tr></thead>
              <tbody>
                {Object.keys(calibration.starting_weights).map((k) => (
                  <tr key={k}>
                    <td>{WEIGHT_LABELS[k] || k}</td>
                    <td className="mono">{k === "ownership" ? "N/A" : calibration.starting_weights[k].toFixed(3)}</td>
                    <td className="mono">{k === "ownership" ? "N/A" : calibration.calibrated_weights[k].toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="grid-2" style={{ marginTop: 14 }}>
              <div style={{ fontSize: 12.5, lineHeight: 1.8 }}>
                <div className="section-title">TRAIN ({calibration.n_train} anchors)</div>
                <div>Anchor constraints satisfied: <strong>{calibration.train.satisfied} / {calibration.train.count}</strong> ({calibration.train.satisfied_pct}%)</div>
                <div>Mean ranking margin: <span className="mono">{calibration.train.mean_margin}</span></div>
                <div>Pairwise loss: <span className="mono">{calibration.train.pairwise_loss}</span> (heuristic: <span className="mono">{calibration.train_at_starting_weights.pairwise_loss}</span>)</div>
              </div>
              <div style={{ fontSize: 12.5, lineHeight: 1.8 }}>
                <div className="section-title">HOLDOUT ({calibration.n_holdout} anchors, never used in optimization)</div>
                <div>Anchor constraints satisfied: <strong>{calibration.holdout.satisfied} / {calibration.holdout.count}</strong> ({calibration.holdout.satisfied_pct}%)</div>
                <div>Mean ranking margin: <span className="mono">{calibration.holdout.mean_margin}</span></div>
                <div>Pairwise loss: <span className="mono">{calibration.holdout.pairwise_loss}</span> (heuristic: <span className="mono">{calibration.holdout_at_starting_weights.pairwise_loss}</span>)</div>
              </div>
            </div>

            {marketAgreement && (
              <div className="ai-box" style={{ marginTop: 14 }}>
                <div className="ai-label">Market agreement diagnostic (evidence only, not a calibration target)</div>
                Top-{5}-ranked pairs with market data: mean |correlation| = <span className="mono">{marketAgreement.mean_top_k_abs_correlation}</span>,
                vs. baseline across all market-data pairs = <span className="mono">{marketAgreement.baseline_mean_abs_correlation}</span>
                {" "}({marketAgreement.n_top_k_pairs_evaluated} pairs evaluated).
              </div>
            )}

            <div className="ai-box" style={{ marginTop: 14, borderColor: "var(--warning)" }}>
              {calibration.disclaimer}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
