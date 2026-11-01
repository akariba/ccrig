import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { ADMIN_PAGES, PAGES, titleFor, type PageDef } from "../app/pages";
import { useOperatorMode } from "../api/query";
import { InvestigationBreadcrumb } from "../components/InvestigationBreadcrumb";
import { Logo } from "../components/Logo";
import { CommandPalette, useEntries } from "./CommandPalette";
import { InspectorProvider } from "./InspectorDrawer";
import { Icon } from "./Icon";
import { TopBar } from "./TopBar";
import { ShellProvider } from "../app/ShellContext";

function NavItem({ p }: { p: PageDef }) {
  return <NavLink to={p.to} end={p.to === "/"} className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}><Icon name={p.icon} /><span>{p.label}</span>{p.status === "planned" && <span className="nav-badge">soon</span>}</NavLink>;
}

function Shell() {
  const [palette, setPalette] = useState(false), loc = useLocation(), op = useOperatorMode();
  const closePalette = useCallback(() => setPalette(false), []);
  const [warm, setWarm] = useState(false);          // the search index loads the first time the palette opens, then stays
  useEffect(() => { if (palette) setWarm(true); }, [palette]);
  const entries = useEntries(warm);
  useEffect(() => { document.title = titleFor(loc.pathname); }, [loc.pathname]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((v) => !v); } };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, []);
  const primary = PAGES.filter((p) => p.group === "primary"), secondary = PAGES.filter((p) => p.group === "secondary");
  return (
    <div className="app-shell">
      <a className="u-skip" href="#main">Skip to content</a>
      <aside className="sidebar">
        <Link to="/" className="sidebar-logo" aria-label="CCRIG home"><Logo /><div><div className="sidebar-logo-text">CCRIG</div><div className="sidebar-sub">Risk console</div></div></Link>
        <nav aria-label="Workspaces">
          <div className="sidebar-tag">Workspaces</div>{primary.map((p) => <NavItem key={p.id} p={p} />)}
          <div className="sidebar-tag">More</div>{secondary.map((p) => <NavItem key={p.id} p={p} />)}
          {op.data && <><div className="sidebar-tag">Admin</div>{ADMIN_PAGES.map((p) => <NavItem key={p.id} p={p} />)}</>}
        </nav>
      </aside>
      <div className="app-col">
        <TopBar onSearch={() => setPalette(true)} />
        <main className="main-content" id="main" tabIndex={-1}><InvestigationBreadcrumb /><Outlet /></main>
      </div>
      <CommandPalette open={palette} onClose={closePalette} entries={entries} />
    </div>
  );
}

export function AppShell() {
  return <ShellProvider><InspectorProvider><Shell /></InspectorProvider></ShellProvider>;
}
