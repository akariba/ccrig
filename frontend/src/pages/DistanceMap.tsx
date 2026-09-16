/**
 * Distance Map: for a selected counterparty, which issuers is it
 * correlated with, through which channel, and how strongly.
 *
 * rho = 1 - d, where d is graph distance over Layer A fact edges (direct
 * ownership/supply-chain) and, failing that, the same bounded Layer B
 * candidate set and weighted composite score every other relatedness view
 * in CCRIG uses (see backend/app/core/distance.py - a VIEW over
 * core/scoring.py and core/candidates.py, not a new model). rho is always
 * an inferred proxy, never an observed market correlation or a
 * trade-position metric - all data comes from /api/distance-map/*.
 */
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { RiskPath } from "../components/RiskPath";
import type { GraphPath } from "../graph/types";

type Channel = "ownership" | "supply" | "historical" | "hidden";

interface PathHop {
  from_id: string; from_label: string;
  to_id: string; to_label: string;
  relation: string | null;
  direction: "FORWARD" | "REVERSE" | null;
}

interface IssuerDistance {
  issuer_id: string;
  issuer_name: string;
  issuer_sector: string;
  issuer_ticker: string | null;
  distance: number;
  rho: number;
  channel: Channel;
  channel_evidence: string;
  direct_relation: string | null;
  direct_criticality: number | null;
  typed_path: PathHop[];
  score_components: Record<string, number>;
  is_direct: boolean;
  hop_count: number;
  is_synthetic: boolean;
}

interface DistanceData {
  counterparty_id: string;
  counterparty_name: string;
  counterparty_sector: string;
  exposure_context: { issuer: string; exposure_pct?: number; relation?: string }[];
  issuers: IssuerDistance[];
  high_rho_count: number;
  concentration_alert: boolean;
  channel_counts: Record<string, number>;
  dominant_channel: string | null;
  methodology_note: string;
}

// No new colour variables (per project convention) - map the four channels
// onto CCRIG's existing semantic palette instead of inventing new hues.
const CHANNEL_META: Record<Channel, { label: string; color: string; desc: string }> = {
  ownership: { label: "Ownership", color: "var(--error)", desc: "Direct Layer A ownership fact edge" },
  supply: { label: "Supply Chain", color: "var(--success)", desc: "Direct or 2-hop Layer A supply-chain edge" },
  historical: { label: "Historical Corr.", color: "var(--warning)", desc: "Derived similarity - market, sector, news" },
  hidden: { label: "Hidden Corr.", color: "var(--chart-3)", desc: "Shared factor exposure, no direct edge" },
};

function tierOf(rho: number): string {
  if (rho >= 0.8) return "Direct — Ownership & Supply Chain (ρ ≥ 0.80)";
  if (rho >= 0.6) return "Significant — Historical & Hidden (ρ 0.60–0.79)";
  if (rho >= 0.4) return "Moderate (ρ 0.40–0.59)";
  return "Weak / Diversified (ρ < 0.40)";
}

function groupByTier(issuers: IssuerDistance[]) {
  const order = [
    "Direct — Ownership & Supply Chain (ρ ≥ 0.80)",
    "Significant — Historical & Hidden (ρ 0.60–0.79)",
    "Moderate (ρ 0.40–0.59)",
    "Weak / Diversified (ρ < 0.40)",
  ];
  const groups = new Map<string, IssuerDistance[]>();
  for (const iss of issuers) {
    const tier = tierOf(iss.rho);
    if (!groups.has(tier)) groups.set(tier, []);
    groups.get(tier)!.push(iss);
  }
  return order.filter((t) => groups.has(t)).map((label) => ({ label, items: groups.get(label)! }));
}

function graphPathFromHops(hops: PathHop[]): GraphPath {
  if (hops.length === 0) return { nodes: [], edges: [] };
  const nodes = [
    { id: hops[0].from_id, type: "ENTITY" as const, label: hops[0].from_label },
    ...hops.map((h) => ({ id: h.to_id, type: "ENTITY" as const, label: h.to_label })),
  ];
  const edges = hops.map((h) => ({ edgeType: h.relation, traversedReverse: h.direction === "REVERSE" }));
  return { nodes, edges };
}

export function DistanceMap() {
  const [params, setParams] = useSearchParams();
  const cpId = params.get("id");

  const [counterparties, setCounterparties] = useState<{ counterparty_id: string; name: string; sector: string }[]>([]);
  const [data, setData] = useState<DistanceData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [minRho, setMinRho] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    api.distanceMapCounterparties().then((r) => {
      setCounterparties(r.results);
      if (!cpId && r.results[0]) setParams({ id: r.results[0].counterparty_id });
    });
  }, []);

  const load = useCallback((id: string, rho: number) => {
    setLoading(true);
    setError(null);
    setExpandedId(null);
    api
      .distanceMapForCounterparty(id, { min_rho: rho })
      .then((d) => setData(d))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (cpId) load(cpId, minRho);
  }, [cpId]);

  const handleMinRho = (v: number) => {
    setMinRho(v);
    if (cpId) load(cpId, v);
  };

  const tiers = data ? groupByTier(data.issuers) : [];

  return (
    <div className="stack">
      <div className="page-header">
        <h1>Distance Map</h1>
        <div className="subtitle">
          For a counterparty, which issuers is it correlated with, through which channel, and how strongly.
          rho = 1 &minus; graph distance &mdash; an inferred proxy over the existing relatedness engine, never an
          observed market correlation.
        </div>
      </div>

      <div className="card">
        <div className="section-title">Counterparty</div>
        <div className="pill-list">
          {counterparties.map((c) => (
            <span
              key={c.counterparty_id}
              className="pill"
              style={cpId === c.counterparty_id ? { borderColor: "var(--primary)", color: "var(--text)" } : {}}
              onClick={() => setParams({ id: c.counterparty_id })}
            >
              {c.name}
            </span>
          ))}
        </div>
      </div>

      {loading && <div className="loading">Computing distances…</div>}
      {error && <div className="warning-box">{error}</div>}

      {data && !loading && (
        <div className="card">
          <div className="hstack" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div className="subtitle" style={{ marginBottom: 2 }}>{data.counterparty_sector}</div>
              <h2 style={{ margin: 0 }}>{data.counterparty_name}</h2>
            </div>
            <div>
              <label style={{ fontSize: 11, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Min &rho;</label>
              <select value={minRho} onChange={(e) => handleMinRho(parseFloat(e.target.value))}>
                <option value={0}>Show all</option>
                <option value={0.4}>&rho; &ge; 0.40</option>
                <option value={0.6}>&rho; &ge; 0.60</option>
                <option value={0.75}>&rho; &ge; 0.75</option>
              </select>
            </div>
          </div>

          <div className="grid-3" style={{ marginTop: 12 }}>
            <div>
              <div style={{ fontSize: 10.5, color: "var(--text-faint)", letterSpacing: "0.04em" }}>&rho; &ge; 0.80</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: "var(--error)" }}>{data.issuers.filter((i) => i.rho >= 0.8).length}</div>
            </div>
            <div>
              <div style={{ fontSize: 10.5, color: "var(--text-faint)", letterSpacing: "0.04em" }}>&rho; 0.60&ndash;0.79</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: "var(--warning)" }}>{data.issuers.filter((i) => i.rho >= 0.6 && i.rho < 0.8).length}</div>
            </div>
            <div>
              <div style={{ fontSize: 10.5, color: "var(--text-faint)", letterSpacing: "0.04em" }}>&rho; &lt; 0.60</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: "var(--chart-3)" }}>{data.issuers.filter((i) => i.rho < 0.6).length}</div>
            </div>
          </div>

          {data.concentration_alert && (
            <div className="warning-box" style={{ marginTop: 14 }}>
              <strong>Concentration signal:</strong> {data.high_rho_count} issuers at &rho; &ge; 0.75. A single shock
              could hit multiple high-&rho; pairs simultaneously.
            </div>
          )}

          <div className="hstack" style={{ flexWrap: "wrap", gap: 14, marginTop: 14 }}>
            {(Object.entries(CHANNEL_META) as [Channel, typeof CHANNEL_META[Channel]][]).map(([k, m]) => (
              <div key={k} className="hstack" style={{ fontSize: 11.5 }}>
                <span style={{ width: 20, height: 4, borderRadius: 2, background: m.color, display: "inline-block" }} />
                <span style={{ fontWeight: 600 }}>{m.label}</span>
                <span style={{ color: "var(--text-faint)" }}>&mdash; {m.desc}</span>
              </div>
            ))}
          </div>

          {tiers.map((tier) => (
            <div key={tier.label} style={{ marginTop: 20 }}>
              <div className="section-title">{tier.label}</div>
              {tier.items.map((iss) => {
                const rank = data.issuers.indexOf(iss) + 1;
                const meta = CHANNEL_META[iss.channel];
                const expanded = expandedId === iss.issuer_id;
                return (
                  <div key={iss.issuer_id} style={{ borderBottom: "1px solid var(--surface-alt)", padding: "10px 0", cursor: "pointer" }} onClick={() => setExpandedId(expanded ? null : iss.issuer_id)}>
                    <div className="hstack" style={{ justifyContent: "space-between" }}>
                      <div className="hstack" style={{ gap: 10 }}>
                        <span style={{ fontSize: 10.5, color: "var(--text-faint)", width: 18 }}>{rank}</span>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: 13.5 }}>{iss.issuer_name}</div>
                          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                            {iss.issuer_sector}{iss.issuer_ticker ? ` · ${iss.issuer_ticker}` : " · Private"}
                          </div>
                        </div>
                      </div>
                      <div className="hstack" style={{ gap: 12 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: meta.color, border: `1px solid ${meta.color}`, borderRadius: 999, padding: "2px 8px", textTransform: "uppercase" }}>
                          {meta.label}
                        </span>
                        <div style={{ width: 130 }}>
                          <div className="score-bar-track"><div className="score-bar-fill" style={{ width: `${iss.rho * 100}%`, background: meta.color }} /></div>
                        </div>
                        <span className="mono" style={{ fontSize: 12.5, fontWeight: 700, color: meta.color, width: 42, textAlign: "right" }}>{iss.rho.toFixed(2)}</span>
                      </div>
                    </div>

                    {expanded && (
                      <div style={{ marginTop: 12, paddingLeft: 28 }} onClick={(e) => e.stopPropagation()}>
                        <div className="grid-3" style={{ marginBottom: 10 }}>
                          <div>
                            <div style={{ fontSize: 10, color: "var(--text-faint)", textTransform: "uppercase" }}>Inferred correlation</div>
                            <div className="mono" style={{ fontSize: 14, fontWeight: 700, color: meta.color }}>&rho; {iss.rho.toFixed(3)}</div>
                          </div>
                          <div>
                            <div style={{ fontSize: 10, color: "var(--text-faint)", textTransform: "uppercase" }}>Graph distance</div>
                            <div className="mono" style={{ fontSize: 14, fontWeight: 700 }}>d {iss.distance.toFixed(3)}</div>
                          </div>
                          <div>
                            <div style={{ fontSize: 10, color: "var(--text-faint)", textTransform: "uppercase" }}>Channel</div>
                            <div style={{ fontSize: 13, fontWeight: 600 }}>{meta.label}</div>
                          </div>
                        </div>

                        <div style={{ marginBottom: 10 }}>
                          <RiskPath path={graphPathFromHops(iss.typed_path)} />
                        </div>

                        {Object.keys(iss.score_components).length > 0 && (
                          <div style={{ marginBottom: 10 }}>
                            <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-faint)", textTransform: "uppercase", marginBottom: 6 }}>
                              Score components (Layer B)
                            </div>
                            {Object.entries(iss.score_components)
                              .sort(([, a], [, b]) => b - a)
                              .map(([k, v]) => (
                                <div key={k} className="hstack" style={{ fontSize: 11.5, marginBottom: 3 }}>
                                  <span style={{ width: 130, color: "var(--text-muted)", textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</span>
                                  <div style={{ flex: 1 }} className="score-bar-track"><div className="score-bar-fill" style={{ width: `${v * 100}%` }} /></div>
                                  <span className="mono" style={{ width: 36, textAlign: "right" }}>{v.toFixed(2)}</span>
                                </div>
                              ))}
                          </div>
                        )}

                        <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginBottom: 6 }}>{iss.channel_evidence}</div>
                        <div style={{ fontSize: 10.5, color: "var(--text-faint)", fontStyle: "italic" }}>
                          &rho; is inferred from graph distance — not observed from trade positions or market prices.
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}

          {data.issuers.length === 0 && <div className="empty-state">No reachable issuers above this &rho; threshold.</div>}

          <p style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 20 }}>{data.methodology_note}</p>
        </div>
      )}
    </div>
  );
}
