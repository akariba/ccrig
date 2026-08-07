import { useEffect, useState } from "react";
import { api } from "../api/client";
import { DataBadge } from "../components/Badge";

export function Provenance() {
  const [data, setData] = useState<any>(null);
  const [coverage, setCoverage] = useState<any[]>([]);
  const [scalability, setScalability] = useState<any>(null);

  useEffect(() => {
    api.provenance().then(setData);
    api.provenanceCoverage().then((d) => setCoverage(d.rows));
    api.scalability().then(setScalability);
  }, []);

  if (!data) return <div className="loading">Loading Data & Provenance Explorer…</div>;

  return (
    <div className="stack">
      <div className="page-header">
        <h1>Data & Provenance Explorer</h1>
        <div className="subtitle">
          Every data source in this POC is tagged REAL_PUBLIC_DATA, SYNTHETIC_POC_DATA, DERIVED_DATA, or
          AI_ASSISTED_EXTRACTION. Generated {data.generated_at}.
        </div>
      </div>

      <div className="grid-3">
        {Object.entries(data.totals).map(([k, v]: any) => (
          <div key={k} className="card kpi">
            <div className="value">{v}</div>
            <div className="label">{k.replace(/_/g, " ")}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="section-title">Data sources registry</div>
        <table className="table">
          <thead><tr><th>Source</th><th>Classification</th><th>Records</th><th>Coverage note</th></tr></thead>
          <tbody>
            {data.sources.map((s: any) => (
              <tr key={s.id}>
                <td>{s.name}</td>
                <td>
                  <DataBadge
                    kind={
                      s.classification === "REAL_PUBLIC_DATA" ? "real"
                      : s.classification === "SYNTHETIC_POC_DATA" ? "synthetic"
                      : s.classification === "DERIVED_DATA" ? "derived" : "ai"
                    }
                    label={s.classification.replace(/_/g, " ")}
                  />
                </td>
                <td className="mono">{s.record_count}</td>
                <td style={{ maxWidth: 420, fontSize: 12 }}>{s.coverage_note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ maxHeight: 320, overflowY: "auto" }}>
        <div className="section-title">Per-entity coverage ({coverage.length} entities)</div>
        <table className="table">
          <thead><tr><th>Entity</th><th>Has market data</th><th>Has GLEIF LEI</th><th>Fact edges</th><th>Themes</th></tr></thead>
          <tbody>
            {coverage.map((c: any) => (
              <tr key={c.entity_id}>
                <td>{c.name} ({c.entity_id})</td>
                <td>{c.has_market_data ? "✓" : "—"}</td>
                <td>{c.has_gleif_record ? "✓" : "—"}</td>
                <td>{c.fact_edge_count}</td>
                <td>{c.theme_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {scalability && (
        <div className="card">
          <div className="section-title">Scalability simulation (brute-force baseline vs. candidate-first pipeline)</div>
          <table className="table">
            <thead><tr><th>N entities</th><th>Theoretical pairs</th><th>Candidate pairs (est.)</th><th>Reduction</th></tr></thead>
            <tbody>
              {scalability.projections.map((p: any) => (
                <tr key={p.n_entities}>
                  <td>{p.n_entities.toLocaleString()}</td>
                  <td>{p.theoretical_pairs.toLocaleString()}</td>
                  <td>{p.estimated_candidate_pairs.toLocaleString()}</td>
                  <td>{p.reduction_vs_dense_pct.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 11.5, color: "var(--text-faint)", marginTop: 8 }}>
            Measured brute-force benchmark timings (numpy, real-time): {scalability.measured_benchmark.map((b: any) => `N=${b.n_entities}: ${b.measured_seconds_for_sample}s/${b.sample_queries}q`).join(" · ")}.
            Brute-force nearest-neighbor does not scale past roughly 10k without an ANN index (FAISS/HNSW) — documented limitation.
          </p>
        </div>
      )}
    </div>
  );
}
