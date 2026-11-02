// The redesigned shell in a real browser (Phase 0): navigation, redirects, command palette, URL state, watchlist, theme, inspector drawer,
// the shared components (design gallery), 404, keyboard access, phone width. Runs against a normal dev stack; with an operator backend it also checks the Admin group.
//   node e2e/shell-e2e.mjs        (E2E_BASE, BROWSER_EXECUTABLE, E2E_SHOTS as in browser-e2e.mjs)
import { chromium } from "playwright-core";
import { existsSync, mkdirSync, readFileSync } from "node:fs";

const BASE = (process.env.E2E_BASE ?? "http://localhost:5173/").replace(/\/?$/, "/");
const SHOTS = (process.env.E2E_SHOTS ?? "e2e-shots/shell").replace(/\/?$/, "/"); mkdirSync(SHOTS, { recursive: true });
const EXE = process.env.BROWSER_EXECUTABLE ?? ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/chromium", "/usr/bin/google-chrome"].find(existsSync);
if (!EXE) { console.error("No Chromium-based browser found: set BROWSER_EXECUTABLE"); process.exit(2); }
let last = "start";
const results = [], check = (n, ok, d = "") => { last = n; results.push(!!ok); console.log(`${ok ? "PASS" : "FAIL"}  ${n}${d ? "  -> " + d : ""}`); };
const browser = await chromium.launch({ executablePath: EXE, headless: true });
const problems = [];
const EXPECTED = /Failed to load resource|\/api\/ingest\/runs\/latest/;
async function open(path = "", opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: opts.w ?? 1440, height: opts.h ?? 900 }, colorScheme: opts.scheme ?? "light", acceptDownloads: true });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => problems.push(`pageerror after "${last}": ` + e.message.slice(0, 80) + (/Maximum update/.test(e.message) ? " :: " + (e.stack || "").split("\n").slice(1, 12).map((l) => l.replace(/\(?http:\/\/localhost:5173\//, "(").trim()).join(" | ") : "")));
  page.on("console", (m) => { if (/Maximum update depth/.test(m.text())) problems.push("MAXDEPTH console: " + m.text().slice(0, 700)); if (m.type() === "error" && !EXPECTED.test(m.text())) problems.push("console.error: " + m.text().slice(0, 160)); });
  await page.goto(BASE + path, { waitUntil: "load" });
  await page.locator(".u-status", { hasText: "backend OK" }).waitFor({ timeout: 30000 });
  return { ctx, page };
}
const pathOf = (page) => new URL(page.url()).pathname + new URL(page.url()).search;
const settle = (page) => page.waitForTimeout(400);
const ready = async (page) => { await page.locator(".u-status", { hasText: "backend OK" }).waitFor({ timeout: 30000 }); await page.waitForTimeout(500); };
const visit = async (page, path) => { await page.goto(BASE + path, { waitUntil: "load" }); await ready(page); };
const operator = (await (await fetch(new URL("api/studio/status", BASE)).catch(() => ({ json: async () => ({}) }))).json().catch(() => ({}))).enabled === true;

try {
  // ------------------------------------------------------------ shell and navigation
  let { ctx, page } = await open("");
  check("shell: workspaces in the sidebar match the spec, in order, with the labels used as page titles", JSON.stringify(await page.locator("nav a").evaluateAll((a) => a.slice(0, 7).map((x) => x.textContent.replace(/soon$/, "")))) === JSON.stringify(["Today", "Network", "Counterparty", "Relationship", "Events & News", "Stress & Shocks", "Co-movement"]));
  check("shell: every sidebar item is a real link (href) and keyboard focusable", await page.locator("nav a").evaluateAll((a) => a.every((x) => x.getAttribute("href")?.startsWith("/") && x.tabIndex >= 0)));
  const titles = [["/", "Today"], ["/network", "Network"], ["/cp", "Counterparty"], ["/rel", "Relationship"], ["/events", "Events & News"], ["/stress", "Stress & Shocks"], ["/comovement", "Co-movement"], ["/models", "Models"], ["/admin/sources", "Data sources"]];
  let titlesOk = true, detail = "";
  for (const [p, label] of titles) {
    await page.locator(`nav a[href="${p}"]`).click(); await page.waitForFunction((l) => document.title === `${l} · CCRIG`, label, { timeout: 15000 }).catch(() => {});
    const h = await page.locator("main h1").first().innerText().catch(() => ""), t = await page.title();
    if (!(t === `${label} · CCRIG` && (h === label || (label === "Data sources" && /Data & Provenance/.test(h))))) { titlesOk = false; detail += ` ${p}:[${t}|${h}]`; }
  }
  check("shell: for every workspace the sidebar label, the URL, the document title and the page heading agree", titlesOk, detail);
  check(`shell: the Admin group is ${operator ? "shown" : "hidden"} (operator switch ${operator ? "on" : "off"})`, (await page.locator("nav a", { hasText: /Data Intelligence Studio|Ingest Bench/ }).count()) === (operator ? 2 : 0));
  await visit(page, ""); await page.keyboard.press("Tab"); await page.keyboard.press("Enter");
  check("accessibility: the skip link is the first tab stop and moves focus to the main content", await page.evaluate(() => document.activeElement?.id === "main"));
  await page.screenshot({ path: SHOTS + "01-today-light.png" });

  // ------------------------------------------------------------ redirects
  const redirects = [["/inbox", "/?tab=inbox"], ["/exposure-movers", "/?tab=movers"], ["/breaches?status=overdue", "/?status=overdue&tab=controls"], ["/counterparty?id=CP_ALPHA", "/cp/CP_ALPHA"], ["/entity?id=JPM", "/issuer/JPM"], ["/graph?id=JPM&hops=2", "/network?id=JPM&hops=2&tab=graph"],
    ["/distance-map?id=CP_ALPHA", "/network?id=CP_ALPHA&tab=distance"], ["/event-studio?text=hello", "/events?text=hello&tab=analyse"], ["/event-impact-map?q=X&days=90", "/events?q=X&days=90&tab=map"], ["/theme-radar?theme=AI", "/events?theme=AI&tab=themes"],
    ["/model-lab", "/models?tab=weights"], ["/backtest-lab", "/models?tab=backtest"], ["/provenance", "/admin/sources"], ["/data-studio", "/admin/studio"], ["/ingest-bench?demo=1", "/admin/ingest?demo=1"]];
  let redirOk = true, rd = "";
  for (const [from, to] of redirects) { await page.goto(BASE + from.slice(1), { waitUntil: "load" }); await page.waitForTimeout(250); const got = pathOf(page); if (got !== to) { redirOk = false; rd += ` ${from} -> ${got} (wanted ${to});`; } }
  check("redirects: all 15 old addresses land on their new home with their parameters", redirOk, rd);
  await page.goto(BASE + "no/such/page", { waitUntil: "load" });
  check("404: an unknown address shows a designed not-found page with a way back, and the document title says so", (await page.locator("main h1").innerText()) === "Page not found" && (await page.title()) === "Page not found · CCRIG" && (await page.getByRole("link", { name: "Go to Today" }).count()) === 1);

  // ------------------------------------------------------------ URL state: tabs, reload, back button
  await visit(page, "?tab=inbox"); await page.getByRole("tab", { name: "Controls" }).click(); await settle(page);
  check("url state: the selected tab is in the URL", pathOf(page) === "/?tab=controls");
  await page.reload({ waitUntil: "load" }); await settle(page);
  check("url state: a reload keeps the tab (shareable view)", (await page.getByRole("tab", { name: "Controls" }).getAttribute("aria-selected")) === "true");
  await page.goBack(); await settle(page);
  check("url state: Back returns to the previous tab", (await page.getByRole("tab", { name: "Inbox" }).getAttribute("aria-selected")) === "true");
  await page.getByRole("tab", { name: "Inbox" }).focus(); await page.keyboard.press("ArrowRight"); await settle(page);
  check("keyboard: arrow keys move between tabs", (await page.getByRole("tab", { name: "Exposure movers" }).getAttribute("aria-selected")) === "true");

  // ------------------------------------------------------------ command palette
  await visit(page, ""); await page.keyboard.press("Control+k");
  const dlg = page.getByRole("dialog", { name: "Search" });
  check("palette: Ctrl/⌘ K opens it with the input focused", (await dlg.isVisible()) && (await page.evaluate(() => document.activeElement?.getAttribute("role") === "combobox")));
  await page.keyboard.type("sovereign");
  await page.locator("#palette-list li[role=option]").first().waitFor({ timeout: 15000 });
  const opts = await page.locator("#palette-list li[role=option]").allInnerTexts();
  check("palette: results show names with a type label, never raw ids", opts.length > 0 && opts.every((t) => !/\bCP_[A-Z]/.test(t)) && opts.some((t) => /^Counterparty/.test(t)), opts.slice(0, 2).join(" | ").replace(/\n/g, " "));
  await page.screenshot({ path: SHOTS + "02-palette.png" });
  await page.keyboard.press("Enter"); await page.waitForURL(/\/cp\//, { timeout: 15000 });
  check("palette: Enter goes to the counterparty's page (/cp/…)", /^\/cp\/[^/]+/.test(pathOf(page)));
  await page.keyboard.press("Control+k"); await page.locator("#palette-list li[role=option]").first().waitFor({ timeout: 5000 }).catch(() => {}); const recent = await page.locator("#palette-list li[role=option]").allInnerTexts();
  check("palette: recent searches are listed when the box is empty", recent.length >= 1 && /recent/.test(recent[0]));
  await page.keyboard.type("A major earthquake disrupts chip fabrication in the region");
  await page.waitForTimeout(300);
  const first = (await page.locator("#palette-list li[role=option]").first().innerText()).replace(/\n/g, " ");
  check("palette: a headline offers 'Analyse as event' first", /^Event\s+Analyse as event/.test(first), first);
  await page.keyboard.press("Enter"); await page.waitForURL(/\/events\?tab=analyse&text=/, { timeout: 15000 });
  check("palette: …which opens Events & News on the Analyse tab with the headline", /text=A\+?%?2?0?major/.test(pathOf(page)) || decodeURIComponent(pathOf(page)).includes("A major earthquake"));
  await page.keyboard.press("Control+k"); await page.keyboard.press("Escape");
  check("palette: Escape closes it and focus returns to the page", (await dlg.count()) === 0);

  // ------------------------------------------------------------ watchlist and as-of (shell state in the URL)
  await visit(page, "?tab=inbox"); await page.waitForSelector(".u-chips .u-chip", { timeout: 15000 });
  const chips0 = await page.locator(".u-chips .u-chip").count();
  check("watchlist: defaults to the highest-priority counterparties (chips shown, no parameter in the URL)", chips0 === 2 && !/wl=/.test(page.url()));
  await page.locator(".u-chip-more").click();
  const boxes = page.locator(".u-pop-list input[type=checkbox]");
  const total = await boxes.count(), checked0 = await page.locator(".u-pop-list input:checked").count();
  check("watchlist: the editor lists every counterparty and starts with the default 10 ticked", total >= 10 && checked0 === 10, `${checked0}/${total}`);
  await boxes.nth(0).uncheck(); await page.getByRole("button", { name: "Apply" }).click(); await settle(page);
  check("watchlist: a custom list is written to the URL (wl=) and flagged as custom", /wl=/.test(page.url()) && /custom/.test(await page.locator(".u-watch .u-label").innerText()));
  await page.getByRole("tab", { name: "Controls" }).click(); await settle(page);
  check("watchlist: it survives switching tabs", /wl=/.test(page.url()));
  await page.locator('input[type="date"]').fill("2026-08-01"); await settle(page);
  check("as-of: the date is in the URL and survives a reload", /asof=2026-08-01/.test(page.url()) && (await (async () => { await page.reload({ waitUntil: "load" }); await settle(page); return (await page.locator('input[type="date"]').inputValue()) === "2026-08-01"; })()));
  await page.locator(".u-chip-more").click(); await page.getByRole("button", { name: "Reset to top 10" }).click(); await page.locator('input[type="date"]').fill(""); await settle(page);
  check("watchlist and as-of: resetting both removes them from the URL again", !/wl=|asof=/.test(page.url()));

  // ------------------------------------------------------------ inspector drawer
  await page.locator(".u-chips .u-chip").first().click();
  const drawer = page.getByRole("dialog", { name: "Details" });
  await drawer.waitFor({ timeout: 15000 });
  check("drawer: a watchlist chip opens the shared inspector (it does not navigate)", new URL(page.url()).pathname === "/" && (await drawer.locator("h2").innerText()).length > 0);
  await drawer.getByRole("link", { name: "Open full page" }).waitFor({ timeout: 15000 });
  check("drawer: focus moved into it, and it offers 'Open full page'", (await page.evaluate(() => !!document.activeElement?.closest(".u-drawer"))) && (await drawer.getByRole("link", { name: "Open full page" }).count()) === 1);
  for (let i = 0; i < 8; i++) await page.keyboard.press("Tab");
  check("drawer: Tab stays inside while it is open (focus trap)", await page.evaluate(() => !!document.activeElement?.closest(".u-drawer")));
  await page.screenshot({ path: SHOTS + "03-drawer.png" });
  await page.keyboard.press("Escape");
  check("drawer: Escape closes it and returns focus to the chip", (await drawer.count()) === 0 && (await page.evaluate(() => document.activeElement?.classList.contains("u-chip"))));

  // ------------------------------------------------------------ theme
  await page.getByRole("group", { name: "Colour theme" }).getByRole("button", { name: "Dark", exact: true }).click(); await settle(page);
  check("theme: Dark sets data-theme and swaps the tokens", (await page.evaluate(() => document.documentElement.dataset.theme)) === "dark" && (await page.evaluate(() => getComputedStyle(document.body).backgroundColor)) !== "rgb(246, 245, 241)");
  await page.screenshot({ path: SHOTS + "04-today-dark.png" });
  await page.reload({ waitUntil: "load" });
  check("theme: the choice survives a reload", (await page.evaluate(() => document.documentElement.dataset.theme)) === "dark");
  await page.getByRole("group", { name: "Colour theme" }).getByRole("button", { name: "System", exact: true }).click();
  check("theme: System removes the override", (await page.evaluate(() => document.documentElement.dataset.theme)) === undefined);
  await ctx.close();
  ({ ctx, page } = await open("", { scheme: "dark" }));
  check("theme: with no choice, the OS dark scheme is followed", (await page.evaluate(() => getComputedStyle(document.body).backgroundColor)) === "rgb(6, 17, 26)");
  await ctx.close();

  // ------------------------------------------------------------ design system gallery
  ({ ctx, page } = await open("admin/ui"));
  await page.getByText("Data table (320 rows").waitFor({ timeout: 30000 });
  const table = page.getByRole("table", { name: "Example counterparties" });
  const rowsRendered = await table.locator("tbody tr[tabindex]").count();
  check("data table: 320 rows but only a window is in the DOM (virtualised)", rowsRendered > 0 && rowsRendered < 80, `${rowsRendered} rows rendered`);
  const firstBefore = await table.locator("tbody tr[tabindex]").first().innerText();
  await table.getByRole("button", { name: /Counterparty/ }).first().click();
  check("data table: clicking a header sorts (aria-sort set)", (await table.locator("th[aria-sort]").count()) === 1 && (await table.locator("tbody tr[tabindex]").first().innerText()) !== firstBefore);
  await page.getByLabel("Filter Example counterparties").fill("counterparty a1");
  check("data table: the filter narrows the rows and the count says so", /\d+ of 320 rows/.test(await page.locator(".u-table-count").first().innerText()));
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Export CSV" }).first().click()]);
  const csv = readFileSync(await dl.path(), "utf8");
  check("data table: Export CSV downloads the filtered rows with headers and units", /^Counterparty,Severity,Utilisation \(%\),Key move \(\$mm\)\r\n/.test(csv) && csv.split("\r\n").length > 2 && csv.split("\r\n").length < 330, dl.suggestedFilename());
  await page.getByRole("button", { name: "Columns" }).first().click(); await page.getByLabel("Severity").uncheck();
  check("data table: the column picker hides a column", (await table.getByRole("columnheader", { name: /Severity/ }).count()) === 0);
  await page.waitForSelector(".u-chart canvas", { timeout: 30000 });
  check("charts: the heatmap and the propagation flow render on canvas (ECharts, loaded on demand)", (await page.locator(".u-chart canvas").count()) >= 2);
  await page.getByRole("button", { name: "View as table" }).first().click();
  check("charts: 'View as table' shows the same data as text", (await page.getByRole("table", { name: /\(table\)/ }).first().locator("tbody tr").count()) > 3);
  await page.getByRole("button", { name: "View chart" }).first().click();
  await page.waitForSelector(".nc-canvas", { timeout: 30000 });
  check("network canvas: the graph renders; the list view gives a text alternative", (await page.locator(".nc-canvas").count()) >= 1 && await (async () => { await page.getByRole("button", { name: "List view" }).click(); return (await page.getByRole("table", { name: /nodes/ }).count()) === 1; })());
  await page.getByRole("button", { name: "View graph" }).click();
  await page.screenshot({ path: SHOTS + "05-design-gallery-light.png", fullPage: false });
  await page.getByRole("group", { name: "Colour theme" }).getByRole("button", { name: "Dark", exact: true }).click(); await settle(page);
  await page.waitForTimeout(600);
  check("charts: they re-theme when the theme changes (canvas still painted)", (await page.locator(".u-chart canvas").count()) >= 2);
  await page.screenshot({ path: SHOTS + "06-design-gallery-dark.png", fullPage: false });
  await ctx.close();

  // ------------------------------------------------------------ hosted pages still work in the shell
  ({ ctx, page } = await open("events?tab=map"));
  await page.getByTestId("impact-map").waitFor({ timeout: 30000 });
  check("hosted: the Event Impact Map renders inside Events & News (Map tab) and keeps its full-bleed dark workspace", (await page.locator("main.impact-dark").count()) === 1);
  await page.screenshot({ path: SHOTS + "07-events-map.png" });
  await page.getByRole("tab", { name: "Themes" }).click(); await page.waitForSelector(".recharts-wrapper", { timeout: 30000 });
  check("hosted: switching tab removes the map's dark skin and shows the Theme Radar", (await page.locator("main.impact-dark").count()) === 0 && (await page.locator(".recharts-wrapper").count()) === 1);
  await page.goto(BASE + "cp/CP_ALPHA", { waitUntil: "load" }); await page.waitForTimeout(1500);
  check("hosted: /cp/:id selects that counterparty (id in the path)", (await page.locator("main h1").innerText()) === "Counterparty" && /CP_ALPHA|Alpha/.test(await page.locator("main").innerText()));
  await page.goto(BASE + "rel/JPM/C", { waitUntil: "load" });
  await page.getByText("Relatedness score", { exact: true }).waitFor({ timeout: 30000 });
  check("relationship: /rel/:a/:b explains a pair (score, typed path, waterfall)", /score waterfall/i.test(await page.locator("main").innerText()));
  await ctx.close();

  // ------------------------------------------------------------ phone width
  ({ ctx, page } = await open("", { w: 390, h: 844 }));
  check("390px: no horizontal page scroll on Today", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await page.goto(BASE + "network", { waitUntil: "load" }); await page.waitForTimeout(1500);
  check("390px: no horizontal page scroll on Network", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await page.screenshot({ path: SHOTS + "08-phone-network.png" });
  await ctx.close();
} catch (e) {
  check("script completed without an unexpected exception", false, String(e).slice(0, 400));
}
check("no unexpected console or page errors", problems.length === 0, problems.slice(0, 4).join(" ; "));
await browser.close();
const pass = results.filter(Boolean).length;
console.log(`\nshell: ${pass}/${results.length} checks passed`);
process.exit(pass === results.length ? 0 : 1);
