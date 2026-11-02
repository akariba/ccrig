import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { RelatednessWaterfall } from "../components/Waterfall";
import { pathBetween, loadReviews, saveReview } from "../lib/graphPath";
import { pct } from "../lib/format";
import { CHANNELS } from "./channels";
import type { NetSelection } from "./NetworkCanvas";
import type { GEdge, GNode } from "./NetworkCanvas/types";
import { ChannelChip, EmptyState, ErrorState, ProvenanceBadge, Skeleton } from "./primitives";

const ref = (id: string) => id.slice(3);
const openHref = (n: GNode): string | null => (n.kind === "counterparty" ? `/cp/${encodeURIComponent(ref(n.id))}` : n.kind === "issuer" ? `/issuer/${encodeURIComponent(ref(n.id))}` : null);
const hasEvidence = (ev: Record<string, unknown>, e: { relation?: string | null }) => ['note', 'exposure_pct', 'jaccard', 'signed_correlation', 'evidence_status', 'studio_evidence'].some((k) => ev[k] !== undefined && ev[k] !== null && ev[k] !== '') || e.relation === 'TRANSMISSION';
const fmt = (v: number | null) => (v === null ? "Unavailable" : v.toFixed(2));

/** What the selected node or link is: channel, strength, confidence, the path from the centre, evidence, and the existing pair explanation when two issuers are involved. */
export function NodeInspector({ centerId, selected, nodes, edges, onClear }: { centerId?: string; selected: NetSelection; nodes: GNode[]; edges: (GEdge & { evidence?: Record<string, unknown> })[]; onClear?: () => void }) {
  const byId = new Map(nodes.map((n) => [n.id, n])), [reviews, setReviews] = useState(loadReviews), [explain, setExplain] = useState(false);
  const edge = selected?.type === "edge" ? edges.find((e) => e.id === selected.id) : null;
  const node = selected?.type === "node" ? byId.get(selected.id) : null;
  const path = node && centerId ? pathBetween(edges, centerId, node.id) : null;
  const via = path && path.edges.length ? edges.find((e) => e.id === path.edges[path.edges.length - 1]) ?? null : null;
  const shown: (GEdge & { evidence?: Record<string, unknown> }) | null = edge ?? via;
  const pair = node?.kind === "issuer" && path && path.nodes.length >= 2 ? byId.get(path.nodes[path.nodes.length - 2]) : null;
  const q = useQuery({ queryKey: ["explain", pair && ref(pair.id), node && ref(node.id)], queryFn: () => api.explainRelationship(ref(pair!.id), ref(node!.id)), enabled: !!pair && pair.kind === "issuer" && !!node && explain, retry: false });
  const confirmed = shown ? reviews[shown.id] : undefined;
  if (!selected) return <EmptyState title="Select a node or a link" hint="Click one on the map or a row in the table. Nothing is opened until you choose Open." />;     // (after every hook: the number of hooks must not depend on the selection)
  const ev = (shown?.evidence ?? {}) as Record<string, unknown>;
  const title = node ? node.label : edge ? `${byId.get(edge.source)?.label ?? edge.source} → ${byId.get(edge.target)?.label ?? edge.target}` : "";
  return (
    <div className="ni" data-testid="inspector">
      <div className="ni-head"><h3>{title}</h3>{onClear && <button type="button" className="u-link" onClick={onClear}>Clear</button>}</div>
      {node && <p className="u-muted">{node.kind === "counterparty" ? (node.cp?.holdingsOnly ? "Counterparty · holdings only" : "Counterparty") : node.kind === "issuer" ? `Issuer · ${node.tag}` : "Risk factor"}{node.group ? ` · ${node.group}` : ""}</p>}
      {shown ? (
        <dl className="u-facts">
          <div><dt>Channel</dt><dd><ChannelChip channel={shown.channel} /></dd></div>
          <div><dt>Direction</dt><dd>{shown.directed ? `${byId.get(shown.source)?.label ?? ""} → ${byId.get(shown.target)?.label ?? ""}` : "None (symmetric)"}</dd></div>
          <div><dt>Strength</dt><dd data-testid="strength">{fmt(shown.strength)}</dd></div>
          <div><dt>Confidence</dt><dd data-testid="confidence">{fmt(shown.confidence)}</dd></div>
          {shown.relation && <div><dt>Relation</dt><dd>{shown.relation}</dd></div>}
        </dl>
      ) : node && <p className="u-muted">No recorded link between this node and the centre within the nodes on screen.</p>}
      {path && path.nodes.length > 1 && <div><div className="u-sec">Path</div><p className="ni-path" data-testid="ni-path">{path.nodes.map((n) => byId.get(n)?.label ?? n).join(" → ")}</p></div>}
      {shown && hasEvidence(ev, shown) && (
        <div><div className="u-sec">Evidence</div>
          <ul className="ni-ev">
            {typeof ev.note === "string" && ev.note && <li>{ev.note}</li>}
            {typeof ev.exposure_pct === "number" && <li>Holds {pct(ev.exposure_pct * 100, 0)} of its book here <ProvenanceBadge kind="synthetic" /></li>}
            {typeof ev.jaccard === "number" && <li>Overlap of holdings (weighted Jaccard): {ev.jaccard.toFixed(2)} · shared issuers: {(ev.shared_issuers as { name: string }[]).map((s) => s.name).join(", ")}</li>}
            {typeof ev.signed_correlation === "number" && <li>Signed correlation of daily returns: {ev.signed_correlation.toFixed(2)} over {String(ev.n_obs)} days <ProvenanceBadge kind="real" /></li>}
            {typeof ev.evidence_status === "string" && <li>Evidence tier: {ev.evidence_status.replace(/_/g, " ").toLowerCase()}{typeof ev.evidence_url === "string" && ev.evidence_url.startsWith("https://") && <> · <a href={ev.evidence_url} target="_blank" rel="noreferrer noopener">source</a></>}</li>}
            {Array.isArray(ev.studio_evidence) && (ev.studio_evidence as { source_publisher: string; source_published_date: string; quotes: string[]; source_url: string; source_sha256: string }[]).map((s, i) => (
              <li key={i} data-testid="studio-evidence"><b>{s.source_publisher}</b> · {s.source_published_date}{s.quotes.map((x, j) => <blockquote key={j} className="impact-quote">{x}</blockquote>)}<a href={s.source_url} target="_blank" rel="noreferrer noopener">open the source</a> <span className="u-muted">sha256 {s.source_sha256.slice(0, 10)}…</span></li>))}
            {shown.relation === "TRANSMISSION" && <li>Inferred next step of a record's risk-factor chain, not a documented link.</li>}
          </ul>
        </div>)}
      {explain && pair && node && (q.isLoading ? <Skeleton lines={5} /> : q.isError ? <ErrorState message={(q.error as Error).message} /> : (
        <div data-testid="explain"><div className="u-sec">Score components · {pair.label} ↔ {node.label}</div>
          {q.data.pair.composite.score != null ? <RelatednessWaterfall waterfall={q.data.pair.composite.waterfall} excluded={q.data.pair.composite.excluded_components} score={q.data.pair.composite.score} /> : <p className="u-muted">No components are available for this pair.</p>}
          <div className="ai-box"><div className="ai-label">{q.data.ai_mode === "ENHANCED_AI" ? "AI explanation" : "Deterministic explanation"}</div>{q.data.ai_explanation}</div></div>))}
      <div className="ni-actions">
        {node && openHref(node) && <Link className="btn" to={openHref(node)!}>Open</Link>}
        <button type="button" className="btn secondary" disabled={!pair || pair.kind !== "issuer"} title={pair ? "Explains why these two issuers are related, from the score components" : "A pair explanation exists only between two issuers"} onClick={() => setExplain(true)}>Explain with AI</button>
        <button type="button" className="btn secondary" disabled={!shown} aria-pressed={!!confirmed} onClick={() => shown && setReviews(saveReview(shown.id, !confirmed))}>{confirmed ? "Link confirmed" : "Confirm link"}</button>
      </div>
      <p className="tp-note">{explain ? "" : "“Explain” uses the deterministic score components; a model only rewrites the sentence when one is connected. "}Confirmations are kept in this browser only; there is no shared review store yet.</p>
    </div>
  );
}
export { CHANNELS };
