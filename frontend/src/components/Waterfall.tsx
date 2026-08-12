type WaterfallEntry = { component: string; label: string; raw_value: number; weight: number; contribution: number };
type ExcludedEntry = { component: string; label: string; reason: string };

// Exact decomposition of the composite relatedness score: each bar's width
// is component_value * renormalized_weight, and the bars sum EXACTLY to the
// final score (see backend/app/core/scoring.py composite_score). This is
// direct arithmetic decomposition of an explicit linear formula, not a
// SHAP/attribution estimate - do not describe it as such in copy.
export function RelatednessWaterfall({
  waterfall, excluded, score,
}: { waterfall: WaterfallEntry[]; excluded: ExcludedEntry[]; score: number }) {
  const maxScale = Math.max(score, ...waterfall.map((w) => w.contribution), 0.01);
  let cumulative = 0;

  return (
    <div>
      {waterfall.map((entry) => {
        const startPct = (cumulative / maxScale) * 100;
        const widthPct = (entry.contribution / maxScale) * 100;
        cumulative += entry.contribution;
        return (
          <div key={entry.component} style={{ marginBottom: 9 }}>
            <div className="hstack" style={{ justifyContent: "space-between", fontSize: 11.5, color: "var(--text-muted)", marginBottom: 3 }}>
              <span>{entry.label}</span>
              <span className="mono">
                {entry.raw_value.toFixed(2)} × {(entry.weight * 100).toFixed(0)}% = <strong style={{ color: "var(--text)" }}>+{entry.contribution.toFixed(3)}</strong>
              </span>
            </div>
            <div className="score-bar-track" style={{ position: "relative" }}>
              <div style={{
                position: "absolute", left: `${startPct}%`, width: `${widthPct}%`, height: "100%",
                background: "var(--chart-1)", borderRadius: 4,
              }} />
            </div>
          </div>
        );
      })}

      <div style={{ marginTop: 14, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
        <div className="hstack" style={{ justifyContent: "space-between", fontSize: 12.5, fontWeight: 700 }}>
          <span>FINAL RELATIONSHIP SCORE</span>
          <span className="mono">{score.toFixed(3)}</span>
        </div>
        <div className="score-bar-track" style={{ marginTop: 4 }}>
          <div style={{ width: `${(score / maxScale) * 100}%`, height: "100%", background: "var(--primary)", borderRadius: 4 }} />
        </div>
      </div>

      {excluded.length > 0 && (
        <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-faint)" }}>
          {excluded.map((e) => (
            <div key={e.component}>{e.label} — unavailable, excluded from denominator ({e.reason})</div>
          ))}
        </div>
      )}

      <p style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 10 }}>
        Exact decomposition of the weighted-average formula — bars sum to the final score, not an estimate. A
        composite relationship indicator used for ranking candidates, not a probability or exposure measure.
      </p>
    </div>
  );
}
