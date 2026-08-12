// Canonical edge-type registry (BUILD_MANDATE Phase 2, section 13). One
// source of truth for how a graph edge type is displayed to an analyst -
// RiskPath and the Investigation breadcrumb both render through this, so a
// label can never drift between the two surfaces or get hardcoded ad hoc
// in a component.
//
// Direction matters: a directed edge's stored semantic is fixed (e.g. the
// canonical fact is "TSM --SUPPLIES--> NVDA"), but the analyst can traverse
// it from either end. Traversal direction must never be confused with
// semantic direction - when traversed backward, use `inverse`, never
// re-assert `forward` as if the edge had been stored the other way.
export type EdgeDomain = "STRUCTURAL" | "STATISTICAL" | "TRANSMISSION" | "EXPOSURE" | "CONTROL";

export interface EdgeTypeDef {
  domain: EdgeDomain;
  /** Human label when read source -> target (the stored/canonical direction). */
  forward: string;
  /** Human label when read target -> source (traversed against the stored direction). */
  inverse: string;
  directed: boolean;
}

export const EDGE_REGISTRY: Record<string, EdgeTypeDef> = {
  SUPPLIES: { domain: "STRUCTURAL", forward: "supplies", inverse: "supplied by", directed: true },
  CUSTOMER_OF: { domain: "STRUCTURAL", forward: "customer of", inverse: "supplier to", directed: true },
  LICENSES_TO: { domain: "STRUCTURAL", forward: "licenses to", inverse: "licensed from", directed: true },
  LICENSES_FROM: { domain: "STRUCTURAL", forward: "licensed from", inverse: "licenses to", directed: true },
  PARENT_OF: { domain: "STRUCTURAL", forward: "parent of", inverse: "subsidiary of", directed: true },
  SUBSIDIARY_OF: { domain: "STRUCTURAL", forward: "subsidiary of", inverse: "parent of", directed: true },
  OPERATES_IN: { domain: "STRUCTURAL", forward: "operates in", inverse: "home to", directed: true },
  BELONGS_TO_SECTOR: { domain: "STRUCTURAL", forward: "belongs to sector", inverse: "sector of", directed: true },

  MARKET_CORRELATED_WITH: { domain: "STATISTICAL", forward: "market correlated with", inverse: "market correlated with", directed: false },
  SEMANTICALLY_RELATED: { domain: "STATISTICAL", forward: "semantically related to", inverse: "semantically related to", directed: false },

  IMPACTS: { domain: "TRANSMISSION", forward: "impacts", inverse: "impacted by", directed: true },
  TRANSMITS_TO: { domain: "TRANSMISSION", forward: "transmits to", inverse: "receives transmission from", directed: true },

  // Product-typed exposure "edges" surfaced from CCR counterparty records
  // (r.product, e.g. "TRS", "REPO") - not a stored graph fact edge, but
  // still a typed economic-exposure relation and deserves the same
  // direction-aware, human-readable treatment rather than a raw code.
  TRS: { domain: "EXPOSURE", forward: "TRS exposure", inverse: "TRS counterparty", directed: true },
  REPO: { domain: "EXPOSURE", forward: "repo exposure", inverse: "repo counterparty", directed: true },
  REVERSE_REPO: { domain: "EXPOSURE", forward: "reverse repo exposure", inverse: "reverse repo counterparty", directed: true },
  CDS: { domain: "EXPOSURE", forward: "CDS exposure", inverse: "CDS counterparty", directed: true },
  IRS: { domain: "EXPOSURE", forward: "IRS exposure", inverse: "IRS counterparty", directed: true },
  FX_FORWARD: { domain: "EXPOSURE", forward: "FX forward exposure", inverse: "FX forward counterparty", directed: true },
  FX_SWAP: { domain: "EXPOSURE", forward: "FX swap exposure", inverse: "FX swap counterparty", directed: true },
  FX_SPOT: { domain: "EXPOSURE", forward: "FX spot exposure", inverse: "FX spot counterparty", directed: true },
  BOND: { domain: "EXPOSURE", forward: "bond exposure", inverse: "bond counterparty", directed: true },
  SEC_LENDING: { domain: "EXPOSURE", forward: "securities lending exposure", inverse: "securities lending counterparty", directed: true },
  EQUITY_FUTURE: { domain: "EXPOSURE", forward: "equity future exposure", inverse: "equity future counterparty", directed: true },
  EQUITY_OPTION: { domain: "EXPOSURE", forward: "equity option exposure", inverse: "equity option counterparty", directed: true },
  COMMODITY_SWAP: { domain: "EXPOSURE", forward: "commodity swap exposure", inverse: "commodity swap counterparty", directed: true },
  HAS_EXPOSURE: { domain: "EXPOSURE", forward: "has exposure", inverse: "exposure of", directed: true },

  SUBJECT_TO: { domain: "CONTROL", forward: "subject to", inverse: "limit on", directed: true },
  HAS_EXCEPTION: { domain: "CONTROL", forward: "has exception", inverse: "exception on", directed: true },
};

// Sentinel for "these two nodes are linked only by the composite
// relatedness ranking, not a stored graph edge" - intentionally NOT in
// EDGE_REGISTRY, because the ranking score is a DERIVED RELATIONSHIP
// RANKING (see scoring.py), never a canonical typed fact, and must stay
// visually/semantically distinguishable rather than dressed up as one.
export const RANKED_ONLY = "RANKED_ONLY";

export function edgeLabel(type: string | null | undefined, traversedReverse: boolean): string {
  if (!type) return "→";
  if (type === RANKED_ONLY) return "correlated with";
  const def = EDGE_REGISTRY[type];
  if (!def) return type.replace(/_/g, " ").toLowerCase();
  return traversedReverse ? def.inverse : def.forward;
}

export function edgeDomain(type: string | null | undefined): EdgeDomain | null {
  if (!type) return null;
  return EDGE_REGISTRY[type]?.domain ?? null;
}
