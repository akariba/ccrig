// Relationship channels and severities: one definition, used by chips, the graph and the charts (colours come from the tokens).
export type Channel = "ownership" | "exposure" | "supply" | "shared" | "comovement" | "hidden";
export const CHANNELS: Record<Channel, { label: string; cssVar: string; dash: string; desc: string; directed: boolean }> = {
  ownership: { label: "Ownership", cssVar: "--ch-ownership", dash: "", desc: "Parent, subsidiary or guarantor link", directed: true },
  exposure: { label: "Exposure", cssVar: "--ch-exposure", dash: "1 3", desc: "A counterparty holds or references the issuer or risk factor", directed: true },
  supply: { label: "Supply chain", cssVar: "--ch-supply", dash: "", desc: "Supplies, licenses or depends on", directed: true },
  shared: { label: "Shared issuer", cssVar: "--ch-shared", dash: "6 3", desc: "Holds the same issuers", directed: false },
  comovement: { label: "Co-movement", cssVar: "--ch-comovement", dash: "2 3", desc: "Daily returns move together (price data only)", directed: false },
  hidden: { label: "Hidden", cssVar: "--ch-hidden", dash: "10 4 2 4", desc: "Inferred from graph structure, not a documented link", directed: false },
};
export const CHANNEL_ORDER = Object.keys(CHANNELS) as Channel[];
export type Severity = "crit" | "high" | "med" | "low" | "info";
export const SEVERITY: Record<Severity, { label: string; glyph: string }> = {
  crit: { label: "Critical", glyph: "▲" }, high: { label: "High", glyph: "◆" }, med: { label: "Medium", glyph: "●" }, low: { label: "Low", glyph: "▼" }, info: { label: "Info", glyph: "○" },
};
/** The CCR priority labels the backend returns, as severities. */
export const severityOf = (priority: string): Severity =>
  ({ CRITICAL: "crit", HIGH: "high", MEDIUM: "med", LOW: "low", INFORMATIONAL: "info" } as Record<string, Severity>)[priority.toUpperCase()] ?? "info";
export type Provenance = "real" | "synthetic" | "derived" | "ai";
export const PROVENANCE: Record<Provenance, { label: string; code: string }> = {
  real: { label: "Real public data", code: "REAL_PUBLIC_DATA" }, synthetic: { label: "Synthetic POC data", code: "SYNTHETIC_POC_DATA" },
  derived: { label: "Derived data", code: "DERIVED_DATA" }, ai: { label: "AI-assisted", code: "AI_ASSISTED_EXTRACTION" },
};
