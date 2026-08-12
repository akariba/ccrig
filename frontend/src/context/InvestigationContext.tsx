import { createContext, useCallback, useContext, useState } from "react";
import type { NodeType } from "../graph/types";

export type InvestigationStep = {
  /** Stable identity - the entity/counterparty id, event slug, etc. Two
   * different nodes that happen to share a display label must never be
   * treated as the same step - identity is (nodeId, nodeType), not label. */
  nodeId: string;
  nodeType: NodeType;
  label: string;
  route: string;
  /** Canonical edge type from the previous step to this one (e.g.
   * "SUPPLIES", "TRS"), or null for an untyped/ranking-based hop. This is
   * a GraphPathEdge in miniature - see graph/types.ts - so the breadcrumb
   * and RiskPath (via pathFromInvestigation) render the exact same
   * underlying path object rather than maintaining separate semantics. */
  edgeType: string | null;
  /** True when the analyst traversed this hop against the edge's stored
   * semantic direction. The underlying fact is never rewritten - only its
   * presentation (via graph/edgeLabels.ts) inverts. */
  traversedReverse: boolean;
  evidenceRef?: unknown;
};

type InvestigationContextValue = {
  steps: InvestigationStep[];
  /** Start a new investigation, discarding any prior path. */
  resetInvestigation: (step: Omit<InvestigationStep, "edgeType" | "traversedReverse">) => void;
  /** Continue the current investigation with one more typed hop. */
  pushStep: (step: InvestigationStep) => void;
  /** Pure state truncation back to a prior step - callers that need to
   * navigate should do so themselves (e.g. via a router <Link>) rather
   * than rely on this returning a target, since state updates are not
   * synchronously observable. */
  truncateTo: (index: number) => void;
  clearInvestigation: () => void;
};

const InvestigationCtx = createContext<InvestigationContextValue | null>(null);

// Lives in memory only, at the top of the React tree - survives normal
// client-side route changes (the SPA never unmounts this provider) but
// resets on a hard reload, which is correct: an investigation is a working
// session, not something that needs to outlive the tab.
export function InvestigationProvider({ children }: { children: React.ReactNode }) {
  const [steps, setSteps] = useState<InvestigationStep[]>([]);

  const resetInvestigation = useCallback((step: Omit<InvestigationStep, "edgeType" | "traversedReverse">) => {
    setSteps([{ ...step, edgeType: null, traversedReverse: false }]);
  }, []);

  const pushStep = useCallback((step: InvestigationStep) => {
    setSteps((prev) => {
      if (prev.length === 0) return [step];
      const last = prev[prev.length - 1];
      // Identity is (nodeId, nodeType, route) - never label, so two
      // distinct nodes that happen to share a display name are never
      // silently collapsed into one step.
      if (last.nodeId === step.nodeId && last.nodeType === step.nodeType && last.route === step.route) return prev;
      return [...prev, step];
    });
  }, []);

  // Pure - reads/writes state, performs no navigation. The caller (a
  // router <Link to={step.route}> in practice) owns navigation via its
  // own href, which is also what makes breadcrumb entries real, keyboard-
  // and screen-reader-accessible links rather than div/span click targets.
  const truncateTo = useCallback((index: number) => {
    setSteps((prev) => (index >= 0 && index < prev.length ? prev.slice(0, index + 1) : prev));
  }, []);

  const clearInvestigation = useCallback(() => setSteps([]), []);

  return (
    <InvestigationCtx.Provider value={{ steps, resetInvestigation, pushStep, truncateTo, clearInvestigation }}>
      {children}
    </InvestigationCtx.Provider>
  );
}

export function useInvestigation() {
  const ctx = useContext(InvestigationCtx);
  if (!ctx) throw new Error("useInvestigation must be used within InvestigationProvider");
  return ctx;
}
