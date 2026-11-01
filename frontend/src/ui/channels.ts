// Relationship channels and severities: one definition, used by chips, the graph and the charts (colours come from the tokens).
export type Channel = "ownership" | "supply" | "shared" | "historical" | "hidden" | "exposure";
export const CHANNELS: Record<Channel, { label: string; cssVar: string; dash: string; desc: string }> = {
  ownership: { label: "Ownership", cssVar: "--ch-ownership", dash: "", desc: "Parent, subsidiary or guarantor link" },
  supply: { label: "Supply chain", cssVar: "--ch-supply", dash: "", desc: "Supplies, licenses or depends on" },
  shared: { label: "Shared issuer", cssVar: "--ch-shared", dash: "6 3", desc: "Holds the same issuers" },
  historical: { label: "Historical", cssVar: "--ch-historical", dash: "2 3", desc: "Moves together in market data" },
  hidden: { label: "Hidden", cssVar: "--ch-hidden", dash: "10 4 2 4", desc: "Inferred from graph structure, no direct link" },
  exposure: { label: "Exposure", cssVar: "--ch-exposure", dash: "1 3", desc: "Counterparty holds the issuer" },
};
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
