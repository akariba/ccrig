import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { DataBadge } from "../components/Badge";

export function Counterparty360() {
  const [params, setParams] = useSearchParams();
  const [list, setList] = useState<any[]>([]);
  const id = params.get("id");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();

  useEffect(() => {
    api.listCounterparties().then((d) => {
      setList(d.results);
      if (!id && d.results.length) setParams({ id: d.results[0].id });
    });
  }, []);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api.counterparty360(id).then((d) => { setData(d); setLoading(false); });
  }, [id]);

  return (
    <div className="stack">
      <div className="page-header">
        <h1>Counterparty 360</h1>
        <div className="subtitle">
          All counterparties and exposures on this page are synthetic POC data — no real fund, bank, or institution
          is represented. Exposure % (Layer C) is always kept in separate units from relatedness scores (Layer B).
        </div>
      </div>

      <div className="card">
        <div className="pill-list">
          {list.map((c) => (
            <span key={c.id} className={"pill" + (c.id === id ? "" : "")} style={id === c.id ? { borderColor: "var(--primary)", color: "var(--text)" } : {}} onClick={() => setParams({ id: c.id })}>
              {c.name}
            </span>
          ))}
        </div>
      </div>

      {loading && <div className="loading">Loading Counterparty 360…</div>}

      {!loading && data && (
        <>
          <div className="card">
            <div className="hstack" style={{ justifyContent: "space-between" }}>
              <div>
                <h2 style={{ margin: 0 }}>{data.header.name}</h2>
                <p className="subtitle">{data.header.industry} · {data.header.country}</p>
              </div>
              <DataBadge kind="synthetic" />
            </div>
            <div className="warning-box" style={{ marginTop: 10 }}>{data.header.synthetic_disclaimer}</div>
          </div>

          <div className="row">
            <div className="card" style={{ flex: 1 }}>
              <div className="section-title">Direct holdings (Layer C — exposure_pct)</div>
              <table className="table">
                <thead><tr><th>Issuer</th><th>Relation</th><th>Exposure %</th></tr></thead>
                <tbody>
                  {data.direct_holdings.map((h: any, i: number) => (
                    <tr key={i}>
                      <td><a onClick={() => nav(`/entity?id=${h.issuer}`)} style={{ cursor: "pointer" }}>{h.issuer}</a></td>
                      <td>{h.relation}</td>
                      <td className="mono">{(h.exposure_pct * 100).toFixed(0)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p style={{ fontSize: 11.5, color: "var(--text-faint)", marginTop: 8 }}>
                Total direct exposure sums to {(data.total_direct_exposure_pct * 100).toFixed(0)}%.
              </p>
            </div>
            <div className="card" style={{ flex: 1 }}>
              <div className="section-title">Concentration by sector</div>
              {Object.entries(data.concentration_by_sector).map(([sector, pct]: any) => (
                <div key={sector} style={{ marginBottom: 8 }}>
                  <div className="hstack" style={{ justifyContent: "space-between", fontSize: 12 }}>
                    <span>{sector}</span><span className="mono">{(pct * 100).toFixed(0)}%</span>
                  </div>
                  <div className="score-bar-track"><div className="score-bar-fill" style={{ width: `${pct * 100}%` }} /></div>
                </div>
              ))}
              <div className="section-title" style={{ marginTop: 14 }}>Top theme concentration</div>
              <div className="pill-list">
                {data.concentration_by_theme_top8.map((t: any) => (
                  <span key={t.theme_id} className="pill" onClick={() => nav(`/theme-radar?theme=${t.theme_id}`)}>
                    {t.label} · {(t.weighted_exposure * 100).toFixed(0)}%
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="section-title">Indirect relationships (Layer B relatedness — never sum with exposure_pct)</div>
            <table className="table">
              <thead><tr><th>Via direct holding</th><th>Indirect entity</th><th>Relatedness score</th></tr></thead>
              <tbody>
                {data.indirect_relationships.slice(0, 15).map((r: any, i: number) => (
                  <tr key={i}>
                    <td>{r.via_direct_holding}</td>
                    <td><a onClick={() => nav(`/entity?id=${r.indirect_entity}`)} style={{ cursor: "pointer" }}>{r.indirect_entity}</a></td>
                    <td className="mono">{r.relatedness_score.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="warning-box">{data.risk_cluster_note}</div>
        </>
      )}
    </div>
  );
}
