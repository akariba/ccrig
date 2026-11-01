import { NavLink, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { Logo } from "./Logo";
import { api } from "../api/client";
import { InvestigationBreadcrumb } from "./InvestigationBreadcrumb";
import { describeBackendStatus, type BackendHealth } from "./healthStatus";

// Text-only institutional navigation - no decorative icon set. Active state
// is communicated by a left accent rule + color (see .nav-link.active in
// index.css), not by a different glyph per row.
const NAV = [
  { section: "Relationship Intelligence" },
  { to: "/", label: "Relationships" },
  { to: "/event-studio", label: "Events" },
  { to: "/counterparty", label: "Counterparties" },
  { to: "/breaches", label: "Controls" },
  { section: "Research" },
  { to: "/inbox", label: "Inbox" },
  { to: "/entity", label: "Entity Explorer" },
  { to: "/exposure-movers", label: "Exposure Movers" },
  { to: "/graph", label: "Graph Explorer" },
  { to: "/distance-map", label: "Distance Map" },
  { to: "/theme-radar", label: "Theme Radar" },
  { to: "/model-lab", label: "Model Lab" },
  { to: "/backtest-lab", label: "Backtest Lab" },
  { section: "System" },
  { to: "/provenance", label: "Data Sources" },
];

export function Layout() {
  const [health, setHealth] = useState<BackendHealth>(null);
  useEffect(() => {
    // An unreachable backend is reported as such (never as "offline mode") and
    // re-checked until it answers, so the badge recovers without a page reload.
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const check = () =>
      api
        .health()
        .then((h) => { if (!cancelled) setHealth(h); })
        .catch(() => {
          if (cancelled) return;
          setHealth({ unreachable: true });
          timer = setTimeout(check, 5000);
        });
    check();
    return () => { cancelled = true; clearTimeout(timer); };
  }, []);
  const status = describeBackendStatus(health);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <Logo />
          <div>
            <div className="sidebar-logo-text">CCRIG</div>
            <div style={{ fontSize: 9.5, color: "var(--text-faint)", letterSpacing: "0.04em" }}>AI ANALYST PLATFORM · POC</div>
          </div>
        </div>
        <nav>
          {NAV.map((item, i) =>
            "section" in item ? (
              <div className="sidebar-tag" key={i}>{item.section}</div>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
              >
                {item.label}
              </NavLink>
            )
          )}
        </nav>
        <div style={{ flex: 1 }} />
        <div className="ai-mode-pill">
          <div style={{ fontWeight: 600, color: status.tone === "error" ? "var(--error)" : "var(--text)" }}>
            {status.title}
          </div>
          {status.detail && <div style={{ marginTop: 2 }}>{status.detail}</div>}
        </div>
      </aside>
      <main className="main-content">
        <InvestigationBreadcrumb />
        <Outlet />
      </main>
    </div>
  );
}
