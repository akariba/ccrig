import { createContext, useCallback, useContext, useState } from "react";

export type NodeType = "ENTITY" | "COUNTERPARTY" | "EVENT" | "RISK_FACTOR" | "PRODUCT" | "THEME" | "COUNTRY";

export type InvestigationStep = {
  /** Stable identity - the entity/counterparty id, event slug, etc. Two
   * different nodes that happen to share a display label must never be
   * treated as the same step - identity is (nodeId, nodeType), not label. */
  nodeId: string;
  nodeType: NodeType;
  label: string;
  route: string;
  /** The typed graph edge from the previous step to this one, e.g.
   * "SUPPLIES", "TRS", "MARKET_CORRELATED_WITH" - null when the hop isn't
   * a typed graph relation (a bare navigational move). This is what lets
   * RiskPath render the investigation as a real typed path, not just a
   * page-history breadcrumb. */
  relationFromPrevious: string | null;
  /** Optional pointer to the evidence behind this hop (a typed_path hop,
   * an explain() response, etc.) - carried through for inspectors that
   * want to re-show why this step was taken, never required. */
  evidenceRef?: unknown;
};

type InvestigationContextValue = {
  steps: InvestigationStep[];
  /** Start a new investigation, discarding any prior path. */
  resetInvestigation: (step: Omit<InvestigationStep, "relationFromPrevious">) => void;
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

  const resetInvestigation = useCallback((step: Omit<InvestigationStep, "relationFromPrevious">) => {
    setSteps([{ ...step, relationFromPrevious: null }]);
  }, []);

  const pushStep = useCallback((step: InvestigationStep) => {
    setSteps((prev) => {
      if (prev.length === 0) return [{ ...step, relationFromPrevious: null }];
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
