import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { api } from "../api/client";
import { DataBadge } from "../components/Badge";

export function ThemeRadar() {
  const [themes, setThemes] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [params] = useSearchParams();
  const nav = useNavigate();

  useEffect(() => {
    api.listThemes().then((d) => {
      setThemes(d.results);
      setLoading(false);
      const pre = params.get("theme");
      if (pre) {
        const t = d.results.find((x: any) => x.theme_id === pre);
        if (t) loadDetail(t.theme_id);
      }
    });
  }, []);

  async function loadDetail(id: string) {
    const d = await api.themeDetail(id);
    setSelected(d);
  }

  const toPoint = (t: any) => ({
    x: t.mention_velocity,
    y: t.entity_coverage,
    z: t.portfolio_relevance || 1,
    id: t.theme_id,
    label: t.label,
  });
  const curatedData = useMemo(() => themes.filter((t) => t.kind === "CURATED_THEME").map(toPoint), [themes]);
  const discoveredData = useMemo(() => themes.filter((t) => t.kind === "DISCOVERED_THEME").map(toPoint), [themes]);

  return (
    <div className="stack">
      <div className="page-header">
        <h2>Dynamic Theme Radar</h2>
        <div className="subtitle">
          X = attention velocity: (recent mentions − prior mentions) / prior mentions, over the corpus timeline
          midpoint. Y = entity coverage: distinct issuers linked to the theme. Bubble size = counterparty portfolio
          reach: distinct counterparties exposed to those issuers. CURATED_THEME bubbles come from the 47-item
          hand-maintained taxonomy; DISCOVERED_THEME bubbles come from TF-IDF clustering over the live news corpus and
          can include concepts never in that taxonomy.
        </div>
      </div>

      {loading && <div className="loading">Loading themes…</div>}

      {!loading && (
        <div className="row" style={{ alignItems: "stretch" }}>
          <div className="card" style={{ flex: 2, height: 420 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" />
                <XAxis type="number" dataKey="x" name="velocity" stroke="var(--text-muted)" tick={{ fontSize: 11 }}
                  label={{ value: "Mention velocity", position: "insideBottom", offset: -4, fill: "var(--text-muted)", fontSize: 11 }} />
                <YAxis type="number" dataKey="y" name="coverage" stroke="var(--text-muted)" tick={{ fontSize: 11 }}
                  label={{ value: "Entity coverage", angle: -90, position: "insideLeft", fill: "var(--text-muted)", fontSize: 11 }} />
                <ZAxis type="number" dataKey="z" range={[60, 500]} name="portfolio relevance" />
                <Tooltip
                  cursor={{ stroke: "var(--border)" }}
                  contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                  formatter={(_v, _n, p: any) => [p.payload.label, "theme"]}
                />
                <Scatter
                  name="Curated"
                  data={curatedData}
                  fill="var(--chart-1)"
                  fillOpacity={0.75}
                  onClick={(p: any) => loadDetail(p.id)}
                  cursor="pointer"
                />
                <Scatter
                  name="Discovered"
                  data={discoveredData}
                  fill="var(--chart-4)"
                  fillOpacity={0.9}
                  shape="diamond"
                  onClick={(p: any) => loadDetail(p.id)}
                  cursor="pointer"
                />
              </ScatterChart>
            </ResponsiveContainer>
          </div>

          <div className="card" style={{ flex: 1, maxHeight: 420, overflowY: "auto" }}>
            <div className="section-title">All themes ({themes.length})</div>
            <table className="table">
              <thead><tr><th>Theme</th><th>Kind</th><th>Coverage</th><th>Rel.</th></tr></thead>
              <tbody>
                {[...themes].sort((a, b) => b.mention_count - a.mention_count).map((t) => (
                  <tr key={t.theme_id} style={{ cursor: "pointer" }} onClick={() => loadDetail(t.theme_id)}>
                    <td>{t.label}</td>
                    <td><DataBadge kind={t.kind === "DISCOVERED_THEME" ? "derived" : "fact"} label={t.kind === "DISCOVERED_THEME" ? "Discovered" : "Curated"} /></td>
                    <td>{t.entity_coverage}</td>
                    <td>{t.portfolio_relevance}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {selected && (
        <div className="card">
          <div className="hstack" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>{selected.label}</h2>
            <div className="hstack">
              <DataBadge kind={selected.kind === "DISCOVERED_THEME" ? "derived" : "fact"} label={selected.kind === "DISCOVERED_THEME" ? "Discovered theme" : "Curated theme"} />
              <DataBadge kind="ai" label="AI suggested label" />
            </div>
          </div>
          <p className="subtitle">AI-suggested canonical label: "{selected.ai_suggested_label}" ({selected.ai_mode})</p>
          {selected.kind === "DISCOVERED_THEME" && (
            <div className="ai-box">
              <div className="ai-label">Why this theme was detected</div>
              Formed by TF-IDF + agglomerative clustering over {selected.document_count} news document(s) whose
              representative terms are: <strong>{selected.representative_terms?.join(", ")}</strong>. Not part of the
              curated 47-theme taxonomy (deduplicated against it during discovery).
              <div style={{ marginTop: 6 }}>
                Recent mentions: <span className="mono">{selected.recent_mentions}</span> · Prior mentions: <span className="mono">{selected.prior_mentions}</span> ·
                Velocity: <span className="mono">{selected.velocity}</span> · Novelty score: <span className="mono">{selected.novelty_score}</span>
                {" "}(fraction of member documents carrying no curated theme tag at all)
              </div>
            </div>
          )}
          {selected.kind === "DISCOVERED_THEME" && (
            <>
              <div className="section-title" style={{ marginTop: 12 }}>Representative headlines</div>
              <ul style={{ margin: "4px 0 0 18px", fontSize: 12.5 }}>
                {selected.representative_headlines?.map((h: string, i: number) => <li key={i}>{h}</li>)}
              </ul>
              <div className="section-title" style={{ marginTop: 12 }}>Source document IDs</div>
              <div className="pill-list">
                {selected.member_document_ids?.map((id: string) => <span key={id} className="pill">{id}</span>)}
              </div>
            </>
          )}
          <div className="grid-3" style={{ marginTop: 12 }}>
            <div className="kpi"><div className="value">{selected.mention_count}</div><div className="label">Mentions</div></div>
            <div className="kpi"><div className="value">{selected.entity_coverage}</div><div className="label">Entities covered</div></div>
            <div className="kpi"><div className="value">{selected.portfolio_relevance}</div><div className="label">Counterparties exposed</div></div>
          </div>
          <div className="grid-2" style={{ marginTop: 16 }}>
            <div>
              <div className="section-title">Covered entities</div>
              <div className="pill-list">
                {selected.covered_entities.map((e: string) => (
                  <span key={e} className="pill" onClick={() => nav(`/issuer/${e}`)}>{e}</span>
                ))}
              </div>
            </div>
            <div>
              <div className="section-title">Exposed counterparties</div>
              <div className="pill-list">
                {selected.exposed_counterparties.map((c: string) => (
                  <span key={c} className="pill" onClick={() => nav(`/cp/${c}`)}>{c}</span>
                ))}
              </div>
            </div>
          </div>
          <div className="section-title" style={{ marginTop: 16 }}>Evidence</div>
          <div className="link-list">
            {selected.evidence.map((e: any, i: number) => (
              <div key={i} className="hstack">
                <DataBadge kind={e.is_synthetic ? "synthetic" : "real"} label={e.is_synthetic ? "Synthetic" : "Real"} />
                {e.url ? <a href={e.url} target="_blank" rel="noreferrer">{e.title}</a> : <span>{e.title}</span>}
                <span style={{ color: "var(--text-faint)", fontSize: 11.5 }}>· {e.source} · {e.date}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
