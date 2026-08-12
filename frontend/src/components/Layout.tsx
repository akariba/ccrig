import { NavLink, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { Logo } from "./Logo";
import { api } from "../api/client";

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
  { to: "/theme-radar", label: "Theme Radar" },
  { to: "/model-lab", label: "Model Lab" },
  { to: "/backtest-lab", label: "Backtest Lab" },
  { section: "System" },
  { to: "/provenance", label: "Data Sources" },
];

export function Layout() {
  const [health, setHealth] = useState<any>(null);
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ ai_mode: "UNREACHABLE" }));
  }, []);

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
          <div style={{ fontWeight: 600, color: "var(--text)" }}>
            {health ? (health.ai_enabled ? "Enhanced AI mode" : "Offline deterministic mode") : "Connecting..."}
          </div>
          <div style={{ marginTop: 2 }}>
            {health?.ai_model ? `Model: ${health.ai_model}` : "No AI_API_KEY set — full functionality retained"}
          </div>
        </div>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
