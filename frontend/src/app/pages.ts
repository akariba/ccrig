// The workspaces and where they live. One list drives the sidebar, the page titles, the command palette and the placeholder pages,
// so a label, a URL and a title can never disagree.
export interface PageDef { id: string; label: string; to: string; icon: string; group: "primary" | "secondary"; blurb: string; status?: "planned" }
export const PAGES: PageDef[] = [
  { id: "today", label: "Today", to: "/", icon: "today", group: "primary", blurb: "What needs my attention now?" },
  { id: "network", label: "Network", to: "/network", icon: "network", group: "primary", blurb: "How is my portfolio connected, and where is it concentrated?" },
  { id: "counterparty", label: "Counterparty", to: "/cp", icon: "building", group: "primary", blurb: "Everything about one counterparty." },
  { id: "relationship", label: "Relationship", to: "/rel", icon: "link", group: "primary", blurb: "Why are these two linked, how strongly, and since when?" },
  { id: "events", label: "Events & News", to: "/events", icon: "news", group: "primary", blurb: "What is happening to the names I follow, and who else does it touch?" },
  { id: "stress", label: "Stress & Shocks", to: "/stress", icon: "bolt", group: "primary", blurb: "If X breaks, who gets hit, how hard, and which limits fail?" },
  { id: "comovement", label: "Co-movement", to: "/comovement", icon: "wave", group: "primary", blurb: "Which names move together, in calm vs stress, and is that changing?", status: "planned" },
  { id: "models", label: "Models", to: "/models", icon: "sliders", group: "secondary", blurb: "Are the weights and rankings any good?" },
  { id: "sources", label: "Data sources", to: "/admin/sources", icon: "db", group: "secondary", blurb: "Where does every number come from?" },
  { id: "ingest", label: "Ingest Bench", to: "/admin/ingest", icon: "gauge", group: "secondary", blurb: "Watch data being loaded: an animated console (a labelled simulation unless a live run exists)." },
];
export const ADMIN_PAGES: PageDef[] = [
  { id: "studio", label: "Data Intelligence Studio", to: "/admin/studio", icon: "layers", group: "secondary", blurb: "Governed ingestion with review and rollback." },
];
/** Document title for a path, e.g. "Today · CCRIG". */
export function titleFor(pathname: string): string {
  const all = [...PAGES, ...ADMIN_PAGES];
  const hit = all.filter((p) => (p.to === "/" ? pathname === "/" : pathname === p.to || pathname.startsWith(p.to + "/"))).sort((a, b) => b.to.length - a.to.length)[0];
  if (pathname.startsWith("/issuer")) return "Issuer · CCRIG";
  return hit ? `${hit.label} · CCRIG` : "Page not found · CCRIG";
}
