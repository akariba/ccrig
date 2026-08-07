import { NavLink, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { Logo } from "./Logo";
import { api } from "../api/client";

const NAV = [
  { section: "Analyst" },
  { to: "/", label: "Home / Copilot", icon: "◆" },
  { to: "/theme-radar", label: "Theme Radar", icon: "◇" },
  { to: "/entity", label: "Entity 360", icon: "●" },
  { to: "/counterparty", label: "Counterparty 360", icon: "▲" },
  { to: "/event-studio", label: "Event Studio", icon: "⚡" },
  { to: "/graph", label: "Graph Explorer", icon: "◈" },
  { section: "Modeling" },
  { to: "/model-lab", label: "Model Lab", icon: "⚙" },
  { to: "/backtest-lab", label: "Backtest Lab", icon: "▦" },
  { section: "System" },
  { to: "/provenance", label: "Data & Provenance", icon: "▤" },
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
                <span style={{ width: 14, textAlign: "center" }}>{item.icon}</span>
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
