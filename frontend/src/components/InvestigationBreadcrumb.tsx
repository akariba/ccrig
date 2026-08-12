import { Link } from "react-router-dom";
import { useInvestigation } from "../context/InvestigationContext";

// Subtle by design: renders nothing when there's no active investigation,
// a single quiet line when there is. Never a card, never competing with
// the page header for attention. Every entry is a real <a href> (router
// Link), not a click-only span, so it's keyboard- and screen-reader-
// reachable and works with cmd-click/open-in-new-tab like any other link.
export function InvestigationBreadcrumb() {
  const { steps, truncateTo, clearInvestigation } = useInvestigation();

  if (steps.length < 2) return null;

  return (
    <div className="hstack" style={{ fontSize: 12, color: "var(--text-faint)", marginBottom: 14, flexWrap: "wrap", gap: 4 }}>
      <span>Investigation:</span>
      {steps.map((step, i) => (
        <span key={`${step.nodeType}:${step.nodeId}:${i}`} className="hstack" style={{ gap: 4 }}>
          {i > 0 && <span>{step.relationFromPrevious ? step.relationFromPrevious.replace(/_/g, " ").toLowerCase() : "›"}</span>}
          {i === steps.length - 1 ? (
            <span style={{ color: "var(--text)", fontWeight: 600 }}>{step.label}</span>
          ) : (
            <Link to={step.route} onClick={() => truncateTo(i)} style={{ color: "var(--primary)" }}>
              {step.label}
            </Link>
          )}
        </span>
      ))}
      <button
        className="btn secondary"
        style={{ marginLeft: 8, padding: "1px 8px", fontSize: 11, fontWeight: 500 }}
        onClick={clearInvestigation}
      >
        Clear
      </button>
    </div>
  );
}
