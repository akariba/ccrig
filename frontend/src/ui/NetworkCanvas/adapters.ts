// The API's network payload -> what the canvas draws. Presentation only: no number is computed here.
import type { Channel } from "../channels";
import type { Cluster, GEdge, GNode } from "./types";

export interface ApiNode { id: string; kind: "counterparty" | "issuer" | "factor"; label: string; tag: string; group?: string | null; sector?: string | null; holdings_only?: boolean; priority?: string | null;
  utilisation_pct?: number | null; rating?: string | null; outlook?: string | null; ews?: number | null; flags?: { wwr?: boolean; overdue?: boolean; near_limit?: boolean; negative_outlook?: boolean | null } }
export interface ApiEdge { id: string; source: string; target: string; channel: string; strength: number | null; confidence: number | null; directed: boolean; relation?: string | null; evidence?: Record<string, unknown>; studio?: boolean }
export interface ApiCluster { id: string; name: string; members: string[] }

export function toNode(n: ApiNode): GNode {
  if (n.kind !== "counterparty") return { id: n.id, kind: n.kind, label: n.label, tag: n.tag, group: n.group ?? n.sector ?? null };
  const f = n.flags ?? {};
  return { id: n.id, kind: "counterparty", label: n.label, tag: n.tag, group: n.sector ?? null, cp: {
    utilisation: n.utilisation_pct ?? null, rating: n.rating ?? null, outlook: (n.outlook as "positive" | "stable" | "negative" | null) ?? null, priority: (n.priority as GNode["cp"] extends infer T ? T extends { priority: infer P } ? P : never : never) ?? null,
    ews: n.ews ?? null, holdingsOnly: !!n.holdings_only, flags: { wwr: !!f.wwr, overdue: !!f.overdue, nearLimit: !!f.near_limit, negativeOutlook: f.negative_outlook ?? null } } };
}
export const toEdge = (e: ApiEdge): GEdge => ({ id: e.id, source: e.source, target: e.target, channel: e.channel as Channel, strength: e.strength, confidence: e.confidence, directed: e.directed, relation: e.relation ?? null, evidence: e.evidence, studio: e.studio });
export const toGraph = (nodes: ApiNode[], edges: ApiEdge[], clusters: ApiCluster[] = []): { nodes: GNode[]; edges: GEdge[]; clusters: Cluster[] } => ({ nodes: nodes.map(toNode), edges: edges.map(toEdge), clusters });
