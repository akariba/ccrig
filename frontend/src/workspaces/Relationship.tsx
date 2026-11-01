// /rel and /rel/:a/:b. Phase 0: a working pair picker and the existing explanation (waterfall, typed path, signed correlations);
// the full page (channels, evidence, co-movement, review actions) is Phase 3.
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { RelatednessWaterfall } from "../components/Waterfall";
import { RiskPath, pathFromHops } from "../components/RiskPath";
import { MetricDefinitionLink } from "../components/MetricDefinition";
import { EmptyState, ErrorState, ProvenanceBadge, Skeleton } from "../ui/primitives";

function Picker({ a, b }: { a?: string; b?: string }) {
  const nav = useNavigate(), issuers = useQuery({ queryKey: ["issuers"], queryFn: () => api.listEntities({ limit: 1000 }) });
  const [x, setX] = useState(a ?? ""), [y, setY] = useState(b ?? "");
  const rows: { id: string; name: string }[] = issuers.data?.results ?? [];
  const sel = (label: string, v: string, set: (s: string) => void) => (
    <label className="u-field"><span className="u-label">{label}</span><select value={v} onChange={(e) => set(e.target.value)}><option value="">Choose an issuer…</option>{rows.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
  );
  return (
    <form className="u-pair" onSubmit={(e) => { e.preventDefault(); if (x && y && x !== y) nav(`/rel/${encodeURIComponent(x)}/${encodeURIComponent(y)}`); }}>
      {sel("Name A", x, setX)}{sel("Name B", y, setY)}<button className="btn" type="submit" disabled={!x || !y || x === y}>Compare</button>
    </form>
  );
}

function Explain({ a, b }: { a: string; b: string }) {
  const q = useQuery({ queryKey: ["explain", a, b], queryFn: () => api.explainRelationship(a, b) });
  if (q.isLoading) return <Skeleton lines={8} />;
  if (q.isError) return <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />;
  const e = q.data, c = e.pair.composite, mk = e.pair.vector.market_detail;
  return (
    <div className="u-stack">
      <div className="card u-row"><div><div className="u-label">Relatedness score</div><div className="u-big">{c.score != null ? c.score.toFixed(3) : "Unavailable"}</div></div><ProvenanceBadge kind="derived" /><MetricDefinitionLink id="COMPOSITE_RELATEDNESS" label="How calculated?" /></div>
      <div className="card"><div className="ai-box">{e.ai_explanation}</div>
        {e.typed_path?.hops?.length > 0 && <div style={{ marginTop: 12 }}><div className="section-title">Typed path (deterministic)</div><RiskPath path={pathFromHops(e.typed_path.hops)} /></div>}</div>
      {c.score != null && <div className="card"><div className="section-title">Score waterfall</div><RelatednessWaterfall waterfall={c.waterfall} excluded={c.excluded_components} score={c.score} /></div>}
      <div className="card"><div className="section-title">Co-movement (signed correlation)</div>
        {mk ? <p className="u-mono">Full sample {mk.full_sample_corr} · rolling {mk.rolling_window_days}d {mk.rolling_corr ?? "n/a"} · stress {mk.stress_window_days}d {mk.stress_window_corr ?? "n/a"}</p> : <p className="u-muted">No market data for one or both names.</p>}</div>
    </div>
  );
}

export default function Relationship() {
  const { a, b } = useParams();
  return (
    <div className="u-host"><div className="u-host-head"><h1>Relationship</h1><p className="u-muted">Why are these two linked, how strongly, and since when?</p></div>
      <div className="u-host-body u-stack"><Picker key={`${a}/${b}`} a={a} b={b} />
        {a && b ? <Explain a={a} b={b} /> : <EmptyState title="Choose two names" hint="Pick two issuers to see why they are linked. You can also open a relationship from a graph edge or a table row." action={<Link className="btn secondary" to="/network">Open the network</Link>} />}</div></div>
  );
}
