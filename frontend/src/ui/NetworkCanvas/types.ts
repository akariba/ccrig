import type { Channel } from "../channels";

export type NodeKind = "counterparty" | "issuer" | "factor";
export type Outlook = "positive" | "stable" | "negative";
export interface CpInfo {
  utilisation: number | null;          // % of the limit; null when there is no limit on file
  rating: string | null;               // null: no rating is recorded (the core shows a dash, nothing is invented)
  outlook: Outlook | null;
  priority: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFORMATIONAL" | null;
  ews: number | null;                  // early-warning score from the backend; null when none exists
  holdingsOnly: boolean;               // a holdings-only counterparty has no limit, rating or priority
  flags: { wwr: boolean; overdue: boolean; nearLimit: boolean; negativeOutlook: boolean | null };
}
export interface GNode { id: string; kind: NodeKind; label: string; tag: string; group?: string | null; cp?: CpInfo }
export interface GEdge { id: string; source: string; target: string; channel: Channel; strength: number | null; confidence: number | null; directed: boolean; relation?: string | null; evidence?: Record<string, unknown>; studio?: boolean }
export interface Cluster { id: string; name: string; members: string[] }
export interface Pt { x: number; y: number }
export interface Rect { x: number; y: number; w: number; h: number }
export interface Camera { k: number; x: number; y: number }       // screen = world * k + (x, y)
export type HeatMap = Record<string, { d: number; hop: number }>;  // distress 0-1 and the hop it was reached at; hop 0 = the shock
export interface Palette {
  bg: string; surface: string; text: string; text2: string; text3: string; accent: string; border: string;
  crit: string; high: string; med: string; low: string; info: string; channel: Record<Channel, string>; groups: string[];
}
