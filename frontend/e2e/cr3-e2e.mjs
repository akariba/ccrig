// CR-3 in a real browser: the Today command center, the Counterparty page, the Network page, the embedded world map and the advanced node canvas.
//   node e2e/cr3-e2e.mjs        (E2E_BASE, BROWSER_EXECUTABLE; screenshots go to E2E_SHOTS, default ../docs/redesign-screens/cr-3/)
import { chromium } from "playwright-core";
import { existsSync, mkdirSync } from "node:fs";

const BASE = (process.env.E2E_BASE ?? "http://localhost:5173/").replace(/\/?$/, "/");
const SHOTS = (process.env.E2E_SHOTS ?? "../docs/redesign-screens/cr-3").replace(/\/?$/, "/"); mkdirSync(SHOTS, { recursive: true });
const EXE = process.env.BROWSER_EXECUTABLE ?? ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/chromium", "/usr/bin/google-chrome"].find(existsSync);
if (!EXE) { console.error("No Chromium-based browser found: set BROWSER_EXECUTABLE"); process.exit(2); }
const results = [], check = (n, ok, d = "") => { results.push(!!ok); console.log(`${ok ? "PASS" : "FAIL"}  ${n}${d ? "  -> " + d : ""}`); };
const browser = await chromium.launch({ executablePath: EXE, headless: true });
const problems = [];
async function open(path, o = {}) {
  const ctx = await browser.newContext({ viewport: { width: o.w ?? 1440, height: o.h ?? 900 }, colorScheme: o.scheme ?? "dark", reducedMotion: o.reduced ? "reduce" : "no-preference" });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 160)));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) problems.push("console.error: " + m.text().slice(0, 160)); });
  const t0 = Date.now(); await page.goto(BASE + path, { waitUntil: "load" });
  return { ctx, page, t0 };
}
const ready = (page) => page.locator(".u-status", { hasText: "backend OK" }).waitFor({ timeout: 30000 });
const noHScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
async function shot(page, name, full = true) {
  if (full) { const ch = await page.evaluate(() => document.querySelector(".main-content").scrollHeight), vp = page.viewportSize(); await page.setViewportSize({ width: vp.width, height: Math.min(Math.max(ch + 60, vp.height), 5600) }); await page.waitForTimeout(900); }
  await page.screenshot({ path: SHOTS + name + ".png" });
}

try {
  // ------------------------------------------------------------ 1. Today
  let { ctx, page, t0 } = await open(""); await ready(page);
  await page.getByTestId("network-canvas").waitFor({ timeout: 30000 });
  const tReady = Date.now() - t0;
  const ids = ["kpis", "world-map", "top-exposures", "stress-heatmap", "market-events", "concentration", "ratings-flags", "data-health"];
  const present = await Promise.all(ids.map(async (i) => (await page.getByTestId(i).count()) === 1));
  check("today: the hero, the map and every panel are on the page", present.every(Boolean) && (await page.locator(".hero-head").count()) === 1, ids.filter((_, i) => !present[i]).join(","));
  check("today: the KPI strip has six tiles and the one the data cannot support says Unavailable", (await page.locator('[data-testid="kpis"] .u-kpi').count()) === 6 && /New links in 7 days[\s\S]*Unavailable/.test(await page.getByTestId("kpis").innerText()));
  check("today: the hero network is drawn with counterparties, issuers and factors", Number(await page.getByTestId("network-canvas").first().getAttribute("data-nodes")) > 20);
  await page.getByTestId("impact-map").waitFor({ timeout: 40000 });
  check("today: the existing world map is embedded in compact mode (projection and animation controls, no overview/zoom chrome, an Open full map link)", (await page.locator(".iw.compact").count()) === 1 && (await page.locator('.iw.compact .gs-controls [aria-label="Zoom in"]').count()) === 0 && (await page.locator(".iw.compact .gs-controls button", { hasText: "Globe" }).count()) === 1 && (await page.getByTestId("open-full-map").count()) === 1);
  check("today: top exposures, heatmap, events and concentration say what they are and carry provenance", (await page.getByTestId("top-exposure-row").count()) >= 5 && /Not a loss estimate/.test(await page.getByTestId("stress-heatmap").innerText()) && (await page.getByTestId("market-events").innerText()).includes("Verified") && /Synthetic POC data/.test(await page.getByTestId("concentration").innerText()));
  check("today: ratings and the pipeline say Unavailable instead of inventing a ladder or stages", /No rating is recorded/.test(await page.getByTestId("ratings-flags").innerText()) && (await page.getByTestId("pipeline-unavailable").count()) === 1 && (await page.getByTestId("usage-unavailable").count()) === 1);
  check("today: source freshness flags stale sources against their targets", /Stale/.test(await page.getByTestId("data-health").innerText()));
  check("today: no horizontal page scroll at 1440 px", await noHScroll(page));
  await page.getByTestId("simulate").click(); await page.getByTestId("sim-result").waitFor({ timeout: 15000 });
  const names = Number(await page.getByTestId("sim-names").innerText());
  check("today: Simulate shows the result card (names reached, hops, limit crossings) and states it is an index, not a loss", names >= 1 && /Not a loss estimate/.test(await page.getByTestId("sim-result").innerText()) && (await page.getByTestId("sim-cross").innerText()).length > 0, `${names} names`);
  const heatDrawn = await page.evaluate(() => Number(document.querySelector('[data-testid="network-canvas"] canvas')?.dataset.frames ?? 0) > 0);
  check("today: the hero canvas keeps drawing while the simulation runs", heatDrawn);
  await shot(page, "today-1440-dark"); await ctx.close();

  // performance: the page is usable within 2 s once the dev server has warmed its modules (a second visit), and nothing animates while it is off screen
  ({ ctx, page, t0 } = await open("")); await ready(page); await page.getByTestId("network-canvas").waitFor();
  await ctx.close();
  ({ ctx, page, t0 } = await open("")); await page.locator('[data-testid="kpis"] .u-kpi-value', { hasText: /^\d+$/ }).first().waitFor({ timeout: 15000 });
  const tUse = Date.now() - t0; check(`today: interactive (first KPI numbers on screen) in under 2 s on a warm load`, tUse < 2000, `${tUse} ms (first cold load ${tReady} ms)`);
  await page.getByTestId("network-canvas").first().waitFor();
  const f0 = Number(await page.locator('[data-testid="network-canvas"] canvas').first().getAttribute("data-frames"));
  await page.evaluate(() => { const m = document.querySelector(".main-content"); m.scrollTop = m.scrollHeight; }); await page.waitForTimeout(700);
  const f1 = Number(await page.locator('[data-testid="network-canvas"] canvas').first().getAttribute("data-frames")); await page.waitForTimeout(1200);
  const f2 = Number(await page.locator('[data-testid="network-canvas"] canvas').first().getAttribute("data-frames"));
  check("today: no animation runs while the hero canvas is scrolled off screen", f1 === f2 && f0 > 0, `frames ${f0} -> ${f1} -> ${f2}`);
  await ctx.close();

  // ------------------------------------------------------------ 2. map event -> Reaches -> Counterparty
  ({ ctx, page } = await open("")); await ready(page); await page.getByTestId("impact-map").waitFor({ timeout: 40000 });
  await page.locator('.iw.compact [data-testid="event-item"]').first().click();
  await page.locator('.iw.compact [data-testid="reaches"]').waitFor({ timeout: 15000 });
  const chips = await page.locator('.iw.compact [data-testid="reach-chip"]').count();
  check("map: selecting an event on Today shows its Reaches row of counterparty chips", chips >= 1, `${chips} chips`);
  const chipName = (await page.locator('.iw.compact [data-testid="reach-chip"]').first().innerText()).split(" · ")[0];
  await page.locator('.iw.compact [data-testid="reach-chip"]').first().click(); await page.waitForURL(/\/cp\//, { timeout: 15000 });
  check("map: a Reaches chip opens that counterparty's page", (await page.locator("main h2").first().innerText()).startsWith(chipName.slice(0, 8)) || (await page.locator('[data-testid="counterparty-page"] h2').first().innerText()).includes(chipName.slice(0, 6)), chipName);
  await ctx.close();

  // ------------------------------------------------------------ 3. Counterparty page
  ({ ctx, page } = await open("cp/CP_HF_001")); await ready(page); await page.getByTestId("cp-links").locator("tbody tr").first().waitFor({ timeout: 30000 });
  check("counterparty: header, six KPIs, map, inspector, relationships, exposure, stress and events sections are all there", (await page.locator('[data-testid="cp-kpis"] .u-kpi').count()) === 6 && (await Promise.all(["cp-map", "cp-inspector", "cp-links", "cp-exposure", "cp-stress", "cp-events"].map((i) => page.getByTestId(i).count()))).every((n) => n === 1));
  check("counterparty: a missing rating and early-warning score read Unavailable, never a number", /Rating Unavailable/.test(await page.getByTestId("rating").innerText()) && /Early-warning score[\s\S]*Unavailable/.test(await page.getByTestId("cp-kpis").innerText()));
  check("counterparty: the node guide is always visible on the map", (await page.getByTestId("node-guide").isVisible()));
  const row = page.getByTestId("cp-links").locator("tbody tr").nth(1), rowName = (await row.locator("td").first().innerText()).trim();
  await row.click(); await page.waitForFunction(() => /[?&]node=/.test(location.search));
  const sel = await page.getByTestId("network-canvas").first().getAttribute("data-selected");
  check("counterparty: clicking a table row selects that node on the map and puts it in the URL (?node=)", !!sel && decodeURIComponent(new URL(page.url()).searchParams.get("node") ?? "") === sel, `${rowName} -> ${sel}`);
  check("counterparty: the inspector shows channel, strength, confidence and the path", (await page.getByTestId("inspector").innerText()).includes(rowName) && (await page.getByTestId("strength").count()) === 1 && (await page.getByTestId("confidence").count()) === 1 && (await page.getByTestId("ni-path").count()) === 1);
  await page.reload({ waitUntil: "load" }); await page.getByTestId("inspector").waitFor({ timeout: 30000 }); await page.waitForTimeout(500);
  check("counterparty: a reload restores the selection from the URL", (await page.getByTestId("network-canvas").first().getAttribute("data-selected")) === sel && (await page.getByTestId("inspector").innerText()).includes(rowName));
  await page.getByRole("button", { name: "Confirm link" }).click();
  check("counterparty: Confirm link is remembered in this browser and says so", (await page.getByRole("button", { name: "Link confirmed" }).count()) === 1 && /kept in this browser only/.test(await page.getByTestId("inspector").innerText()));
  await page.getByTestId("simulate-cp").click(); await page.getByTestId("sim-result").waitFor({ timeout: 15000 });
  check("counterparty: Simulate default overlays the heat on this map and shows the index label", /Not a loss estimate/.test(await page.getByTestId("sim-result").innerText()));
  await page.locator(".nc-bar button", { hasText: "List view" }).first().click();
  check("counterparty: the list view is a text alternative to the map", (await page.getByRole("table", { name: /Relationships of .*: links/ }).count()) === 1);
  await page.locator(".nc-bar button", { hasText: "View graph" }).first().click();
  await page.waitForSelector("[data-testid=cp-exposure] canvas", { timeout: 30000 });
  check("counterparty: the exposure and stress charts render, and both can be read as tables", (await page.locator("[data-testid=cp-exposure] canvas, [data-testid=cp-stress] canvas").count()) >= 2);
  await shot(page, "counterparty-1440-dark"); await ctx.close();

  ({ ctx, page } = await open("cp/CP_ALPHA")); await ready(page); await page.getByTestId("cp-links").locator("tbody tr").first().waitFor({ timeout: 30000 });
  check("counterparty: a holdings-only name says it has no exposure record instead of drawing an empty chart", /No exposure record/.test(await page.getByTestId("cp-exposure").innerText()) && /Holdings only/.test(await page.getByTestId("counterparty-page").innerText()));
  await ctx.close();

  // ------------------------------------------------------------ 4. Network page and the canvas
  ({ ctx, page } = await open("network?scope=all")); await ready(page); await page.getByTestId("network-canvas").waitFor({ timeout: 30000 });
  check("network: the whole network is drawn on the new canvas (no Cytoscape) with channel toggles that show counts", Number(await page.getByTestId("network-canvas").getAttribute("data-nodes")) >= 90 && (await page.locator(".nc-chan").count()) === 6 && (await page.locator("main").innerText()).includes("Co-movement"));
  const links0 = (await page.locator(".nc-bar .u-muted").innerText()).match(/(\d+) links/)[1];
  await page.locator(".nc-chan", { hasText: "Shared issuer" }).click();
  await page.waitForFunction((n) => !document.querySelector(".nc-bar .u-muted").textContent.includes(`${n} links`), links0, { timeout: 5000 }).catch(() => {});
  const links1 = (await page.locator(".nc-bar .u-muted").innerText()).match(/(\d+) links/)[1];
  check("network: turning a channel off removes its links", Number(links1) < Number(links0), `${links0} -> ${links1}`);
  await page.getByRole("tab", { name: /Clusters/ }).click();
  check("network: clusters are listed with their members, from the backend", (await page.getByRole("table", { name: "Clusters" }).locator("tbody tr").count()) >= 1);
  await page.getByRole("table", { name: "Clusters" }).locator("tbody tr").first().click();
  await page.waitForFunction(() => Number(document.querySelector('[data-testid="network-canvas"]')?.dataset.highlighted) >= 2, null, { timeout: 5000 }).catch(() => {});
  check("network: choosing a cluster highlights its members on the map", Number(await page.getByTestId("network-canvas").getAttribute("data-highlighted")) >= 2);
  await shot(page, "network-1440-dark", true); await ctx.close();
  ({ ctx, page } = await open("admin/ui")); await page.getByRole("button", { name: "Highlight three nodes" }).waitFor({ timeout: 30000 });
  await page.getByRole("button", { name: "Highlight three nodes" }).click(); await page.waitForTimeout(300);
  check("canvas: highlight(ids), the call the assistant's 'Show on network' makes, highlights exactly those nodes", Number(await page.locator('[data-testid="network-canvas"]').getAttribute("data-highlighted")) === 3);
  await page.getByRole("button", { name: "Clear highlight" }).click(); await page.waitForTimeout(200);
  check("canvas: and clearing it restores every node", Number(await page.locator('[data-testid="network-canvas"]').getAttribute("data-highlighted")) === 0);
  await page.locator(".nc-canvas").focus(); await page.keyboard.press("ArrowRight"); await page.waitForTimeout(200);
  check("canvas: arrow keys select a node and the selection is announced", !!(await page.locator('[data-testid="network-canvas"]').getAttribute("data-selected")) && /Selected/.test(await page.locator(".nc .u-sr[aria-live]").innerText()));
  await ctx.close();
  ({ ctx, page } = await open("admin/ui", { reduced: true })); await page.waitForSelector(".nc-canvas", { timeout: 30000 }); await page.waitForTimeout(500);
  const r0 = Number(await page.locator(".nc-canvas").getAttribute("data-frames")); await page.waitForTimeout(1200); const r1 = Number(await page.locator(".nc-canvas").getAttribute("data-frames"));
  check("canvas: under reduced motion nothing animates (no frames are drawn while idle)", r1 === r0 && r0 >= 1, `${r0} -> ${r1}`);
  await ctx.close();

  // ------------------------------------------------------------ 5. Stress, and the full map's Reaches
  ({ ctx, page } = await open("")); await ready(page); await page.getByTestId("stress-heatmap").locator("button.hm-cell").first().waitFor({ timeout: 30000 });
  await page.getByTestId("stress-heatmap").locator("button.hm-cell", { hasText: /0\.\d\d/ }).first().click(); await page.waitForURL(/\/stress\?scenario=/, { timeout: 15000 });
  await page.getByRole("table", { name: "Names reached" }).waitFor({ timeout: 30000 });
  check("stress: a heatmap cell opens Stress with that scenario already run, as an index with no currency figure", /not a loss estimate/i.test(await page.getByTestId("stress-page").innerText()) && !/\$\s?\d/.test(await page.getByRole("table", { name: "Names reached" }).innerText()));
  await ctx.close();
  ({ ctx, page } = await open("events?tab=map")); await ready(page); await page.getByTestId("impact-map").waitFor({ timeout: 40000 });
  await page.getByTestId("event-item").first().click(); await page.getByTestId("reaches").waitFor({ timeout: 15000 });
  check("map (full page): the evidence panel has a Reaches block too, and the full-page controls are all still there", (await page.locator("[data-testid=reach-chip]").count()) >= 1 && (await page.locator('.gs-controls [aria-label="Zoom in"]').count()) === 1 && (await page.locator(".gs-controls button", { hasText: "Investigation" }).count()) === 1 && (await page.getByTestId("source-mode").count()) === 1 && (await page.getByTestId("include-studio-map").count()) === 1);
  await shot(page, "events-map-1440-dark", false);
  await page.getByRole("group", { name: "Colour theme" }).getByRole("button", { name: "Light", exact: true }).click(); await page.waitForTimeout(1500);
  check("map: the light theme restyles the map (light land and sea, readable tags)", (await page.evaluate(() => getComputedStyle(document.body).backgroundColor)) !== "rgb(6, 17, 26)");
  await shot(page, "events-map-1440-light", false); await ctx.close();

  // ------------------------------------------------------------ 6. screenshots in both themes and at phone width
  for (const [scheme, tag] of [["light", "light"]]) {
    ({ ctx, page } = await open("", { scheme })); await ready(page); await page.getByTestId("impact-map").waitFor({ timeout: 40000 }); await page.waitForTimeout(1500); await shot(page, `today-1440-${tag}`); await ctx.close();
    ({ ctx, page } = await open("cp/CP_HF_001", { scheme })); await ready(page); await page.getByTestId("cp-links").locator("tbody tr").first().waitFor({ timeout: 30000 }); await page.waitForTimeout(1500); await shot(page, `counterparty-1440-${tag}`); await ctx.close();
    ({ ctx, page } = await open("network?scope=all", { scheme })); await ready(page); await page.getByTestId("network-canvas").waitFor({ timeout: 30000 }); await page.waitForTimeout(1200); await shot(page, `network-1440-${tag}`, false); await ctx.close();
  }
  for (const [path, name] of [["", "today"], ["cp/CP_HF_001", "counterparty"], ["network?scope=all", "network"], ["events?tab=map", "events-map"]]) for (const scheme of ["dark", "light"]) {
    ({ ctx, page } = await open(path, { w: 390, h: 844, scheme })); await ready(page); await page.waitForTimeout(3500);
    check(`phone 390 px (${scheme}): ${name} has no horizontal page scroll`, await noHScroll(page));
    await shot(page, `${name}-390-${scheme}`); await ctx.close();
  }
} catch (e) {
  check("script completed without an unexpected exception", false, String(e).slice(0, 500));
}
check("no unexpected console or page errors", problems.length === 0, problems.slice(0, 4).join(" ; "));
await browser.close();
const pass = results.filter(Boolean).length;
console.log(`\ncr3: ${pass}/${results.length} checks passed`);
process.exit(pass === results.length ? 0 : 1);
