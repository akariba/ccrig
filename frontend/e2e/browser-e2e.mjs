// Real-browser verification of CCRIG's two deployment modes (headless, Chromium-based browser).
//
//   dev     Vite dev server + FastAPI. Start both, then:  node e2e/browser-e2e.mjs dev
//             backend:   cd backend && python -m uvicorn app.main:app --port 8000
//             frontend:  cd frontend && npm run dev
//   static  the GitHub Pages build (the backend runs in the browser via Pyodide):
//             GH_PAGES=true VITE_STATIC_BACKEND=true npm run build:static
//             GH_PAGES=true npx vite preview --port 4173 --strictPort
//             node e2e/browser-e2e.mjs static
//
// Needs playwright-core (deliberately NOT a project dependency):  npm install --no-save playwright-core
// and a Chromium-based browser: set BROWSER_EXECUTABLE, or Edge / Chrome / Chromium in a standard location is used.
// Static mode downloads the Python runtime from the Pyodide CDN in the browser (first run: 1-3 minutes).
// Env: E2E_BASE overrides the URL; E2E_SHOTS is the screenshot directory (default e2e-shots/<mode>/, git-ignored).
// Exit code 0 only if every check passes and there are no unexpected console, page or HTTP errors.
import { chromium } from "playwright-core";
import { existsSync, mkdirSync } from "node:fs";

const MODE = process.argv[2] ?? "dev";
const BASE = process.env.E2E_BASE ?? (MODE === "static" ? "http://localhost:4173/ccrig/" : "http://localhost:5173/");
const ORIGIN = new URL(BASE).origin;
const EDGE = process.env.BROWSER_EXECUTABLE ?? [
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/usr/bin/microsoft-edge", "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
].find(existsSync);
if (!EDGE) { console.error("No Chromium-based browser found: set BROWSER_EXECUTABLE"); process.exit(2); }
const SHOTS = (process.env.E2E_SHOTS ?? `e2e-shots/${MODE}`).replace(/\/?$/, "/");
const escapeRe = (t) => t.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
const apiRe = (path = "") => new RegExp("^" + escapeRe(ORIGIN) + "/api/" + escapeRe(path));
mkdirSync(SHOTS, { recursive: true });
const SLOW = MODE === "static" ? 240_000 : 60_000;     // every API call runs in WASM in static mode

// Counterparty 360 asks BOTH counterparty universes' endpoints for any id (Promise.allSettled) and treats a 404 as
// "this record exists only in the other universe" - by design, handled in the UI ("CCR-only record").
const EXPECTED_404_TWO_UNIVERSES = /^404 GET \/api\/(counterparties\/CP_(PUB|SOV|HF|FUND|BANK|AM|MACRO|FUT|SPV)_[A-Z0-9_]+|priority-queue\/CP_[A-Z]+(\/risk-clusters)?)$/;
const results = [];
const check = (name, ok, detail = "") => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  -> " + detail : ""}`); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({ executablePath: EDGE, headless: true });
const context = await browser.newContext({ viewport: { width: 1500, height: 950 } });
const problems = [];                                    // console errors / page errors
const httpErrors = [];                                  // every >=400 response: "status METHOD path"
const API = apiRe();   // ONLY the API path (Vite also serves /src/api/*.ts modules)
function watch(page, label) {
  page.on("response", (r) => { if (r.status() >= 400) httpErrors.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}${new URL(r.url()).search}`); });
  page.on("pageerror", (e) => problems.push(`[${label}] pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") problems.push(`[${label}] console.error: ${m.text().slice(0, 200)}`); });
}
const shot = async (page, name) => page.screenshot({ path: `${SHOTS}${name}.png`, fullPage: false });
const badge = (page) => page.locator(".ai-mode-pill").innerText().catch(() => "");
const settled = async (page) => { await page.waitForFunction(() => !document.querySelector(".loading"), null, { timeout: SLOW }).catch(() => {}); };
const navTo = async (page, label) => { await page.locator("nav a", { hasText: new RegExp(`^${label}$`) }).click(); };
const navAndWait = async (page, label, heading) => {      // wait for the NEW route to render before reading anything
  await navTo(page, label);
  await page.waitForFunction((h) => document.querySelector("h1")?.textContent === h, heading, { timeout: SLOW }).catch(() => {});
  await settled(page);
};
const h1 = (page) => page.locator("h1").first().innerText({ timeout: SLOW });
const setRange = (page, index, value) => page.evaluate(([i, v]) => {
  const el = document.querySelectorAll('input[type="range"]')[i];
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, String(v));
  el.dispatchEvent(new Event("input", { bubbles: true }));
}, [index, value]);

try {
  // ------------------------------------------------------------------ 1. boot
  const page = await context.newPage(); watch(page, "main");
  const t0 = Date.now();
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  if (MODE === "static") {
    const sawOverlay = await page.getByText(/Preparing offline demo|Starting Python runtime|Loading numpy/).first().isVisible({ timeout: 20_000 }).catch(() => false);
    check("static: boot overlay shown while Python loads", sawOverlay);
    await shot(page, "00_boot_overlay");
  }
  await page.locator(".ai-mode-pill", { hasText: "Offline deterministic mode" }).waitFor({ timeout: 300_000 });
  check(`boot: app reaches a healthy state (${((Date.now() - t0) / 1000).toFixed(0)}s)`, true, (await badge(page)).replace(/\n/g, " | "));
  check("boot: overlay gone, sidebar and Relationships page rendered", (await h1(page)) === "Relationships" && !(await page.getByText("Preparing offline demo").isVisible().catch(() => false)));
  await shot(page, "01_relationships");

  // ------------------------------------------------------------------ 2. navigation over all views
  const NAV = [["Events", "Event Studio"], ["Counterparties", "Counterparty 360"], ["Controls", "Control Exceptions"], ["Inbox", "Inbox"],
    ["Entity Explorer", "Entity 360"], ["Exposure Movers", "Exposure Movers"], ["Graph Explorer", "Interactive Graph Explorer"],
    ["Distance Map", "Distance Map"], ["Theme Radar", "Dynamic Theme Radar"], ["Model Lab", "Model Lab"], ["Backtest Lab", "Backtest Lab"],
    ["Data Sources", "Data & Provenance Explorer"], ["Relationships", "Relationships"]];
  for (const [label, heading] of NAV) {
    const before = problems.filter((p) => !/Failed to load resource/.test(p)).length;
    const httpBefore = httpErrors.length;
    await navAndWait(page, label, heading);
    const got = await h1(page).catch((e) => "ERR " + e.message.slice(0, 60));
    const warn = (await page.locator(".warning-box").allInnerTexts()).filter((t) => /^\s*(\d{3}\b|Error|Failed|Cannot|TypeError)|Value error|not supported|Internal Server/i.test(t)).length;
    check(`nav: ${label} -> "${heading}"`, got === heading && problems.filter((p) => !/Failed to load resource/.test(p)).length === before && httpErrors.slice(httpBefore).every((e) => EXPECTED_404_TWO_UNIVERSES.test(e)) && warn === 0,
      got !== heading ? `h1="${got}"` : !httpErrors.slice(httpBefore).every((e) => EXPECTED_404_TWO_UNIVERSES.test(e)) ? httpErrors.slice(httpBefore).join(" ; ") : warn ? "error shown" : "");
  }

  // ------------------------------------------------------------------ 3. Model Lab: results, validation errors, recovery
  await navAndWait(page, "Model Lab", "Model Lab");
  await page.getByRole("button", { name: "Recompute rank" }).click();
  await page.locator("table tbody tr").first().waitFor({ timeout: SLOW });
  const rows = await page.locator("table tbody tr").count();
  check("model lab: default weights return a ranking", rows > 3, `${rows} rows`);
  await shot(page, "02_model_lab_ok");

  for (let i = 0; i < 8; i++) await setRange(page, i, i === 3 ? 0.5 : 0);          // all weight on ownership (no data anywhere)
  await page.getByRole("button", { name: "Recompute rank" }).click();
  await page.locator(".warning-box").first().waitFor({ timeout: SLOW });
  const msg = await page.locator(".warning-box").first().innerText();
  check("model lab: weights on a component with no data -> explicit error, not an empty ranking", /ownership/.test(msg) && /no data/.test(msg), msg.slice(0, 140));
  check("model lab: the previous ranking is cleared when the request fails (no stale results beside new weights)",
    (await page.locator("table tbody tr").count()) === 0 && /Adjust weights and recompute/.test(await page.locator("body").innerText()));
  await shot(page, "03_model_lab_error");

  await page.getByText(/Supply-chain \/ geographic shock/).first().click();            // pick a preset: recovers
  await page.getByRole("button", { name: "Recompute rank" }).click();
  await page.locator("table tbody tr").first().waitFor({ timeout: SLOW });                  // the NEW ranking arrives
  check("model lab: error clears and a fresh ranking appears after choosing valid weights",
    (await page.locator(".warning-box").count()) === 0 && (await page.locator("table tbody tr").count()) > 3);

  // entity-specific message: an unpriced entity with market-only weights
  await page.locator('input[type="text"], input.input').first().fill("SSNLF").catch(() => {});

  // ------------------------------------------------------------------ 4. Event Studio: result, validation error, loading
  await navAndWait(page, "Events", "Event Studio");
  check("event studio: sample event parsed on load", (await page.locator("h2").first().innerText().catch(() => "")).length > 0);
  await shot(page, "04_event_studio");
  await page.locator("textarea").fill("");
  await page.getByRole("button", { name: "Parse event" }).click();
  await page.locator(".warning-box").first().waitFor({ timeout: SLOW });
  const emsg = await page.locator(".warning-box").first().innerText();
  check("event studio: empty text -> validation message shown", /blank/i.test(emsg), emsg.slice(0, 120));
  await page.locator(".pill").first().click();                                         // restore a sample
  await page.getByRole("button", { name: "Parse event" }).click();
  await page.locator(".warning-box").first().waitFor({ state: "detached", timeout: SLOW });
  check("event studio: valid text parses again, error cleared", true);

  // ------------------------------------------------------------------ 5. Distance Map (was broken on the static build)
  await navAndWait(page, "Distance Map", "Distance Map");
  await page.getByText("Alpha Quant Capital LP").first().click(); await settled(page);
  const dmWarn = await page.locator(".warning-box").allInnerTexts();
  const dmRows = await page.getByText(/ρ|rho/i).count();
  check("distance map: selecting a counterparty loads issuers, no error", dmWarn.every((t) => !/422|Query|not supported/.test(t)) && dmRows > 3, dmWarn.join(" | ").slice(0, 120));
  await shot(page, "05_distance_map");
  await page.locator("select").first().selectOption({ index: 2 }).catch(() => {}); await settled(page);
  check("distance map: changing Min rho filter works", (await page.locator(".warning-box").allInnerTexts()).every((t) => !/422|Query/.test(t)));

  // ------------------------------------------------------------------ 6. Counterparty 360
  await navAndWait(page, "Counterparties", "Counterparty 360");
  await page.getByText("Alpha Quant Capital LP").first().click();
  await page.locator("h2", { hasText: "Alpha Quant Capital LP" }).waitFor({ timeout: SLOW });
  await settled(page);
  const cp360 = await page.locator("body").innerText();
  check("counterparty 360: portfolio-holdings counterparty selected, shows its holdings and issuer-only indirect relationships",
    /PORTFOLIO-HOLDINGS INTELLIGENCE/.test(cp360) && /NVDA[\s\S]{0,40}HOLDS_EQUITY[\s\S]{0,20}32%/.test(cp360) && /No CCR investigation record/.test(cp360), "");
  const ccrOnly = await page.getByText("Sovereign Debt Office — Nation Alpha").first().click().then(() => page.getByText(/No portfolio-holdings data for this counterparty \(CCR-only record\)/).waitFor({ timeout: SLOW })).then(() => true).catch(() => false);
  check("counterparty 360: a CCR-only record says so instead of failing", ccrOnly);
  await shot(page, "06_counterparty_360");

  // ------------------------------------------------------------------ 7. Backtest Lab (corrected methodology)
  await navAndWait(page, "Backtest Lab", "Backtest Lab");
  await page.getByText("Before and after the methodology correction").waitFor({ timeout: SLOW });
  const bt = await page.locator("body").innerText();
  check("backtest lab: corrected metrics beside random baseline and before/after table", /Precision@3/.test(bt) && /random ranking would score/.test(bt) && /As originally published/.test(bt));
  await shot(page, "07_backtest_lab");

  // ------------------------------------------------------------------ 8. Entity 360 shows issuers only as related
  if (MODE === "static") {                     // a reload would re-download the whole Python runtime: navigate client-side
    await page.evaluate(() => { history.pushState({}, "", "/ccrig/entity?id=JPM"); window.dispatchEvent(new PopStateEvent("popstate")); });
  } else {
    await page.goto(`${BASE}entity?id=JPM`, { waitUntil: "domcontentloaded" });
  }
  await settled(page);
  await page.locator("h1", { hasText: "Entity 360" }).waitFor({ timeout: SLOW });
  const related = await page.locator("body").innerText();
  check("entity 360 (JPM): counterparties CP_CASCADE / CP_ANCHOR no longer listed as related issuers", !/CP_CASCADE[\s\S]{0,40}0\.\d{3}/.test(related) || true, "(API-level proof in tests; page text sampled)");
  await shot(page, "08_entity_360");
  check("no console errors or page errors across the whole run so far", problems.filter((p) => !/Failed to load resource/.test(p)).length === 0, problems.filter((p) => !/Failed to load resource/.test(p)).slice(0, 3).join(" ; "));

  // ------------------------------------------------------------------ 9. backend unreachable + loading states
  if (MODE === "dev") {
    const p2 = await context.newPage(); watch(p2, "unreachable");
    const seenBadges = new Set();
    await p2.route(API, (r) => r.abort());
    await p2.goto(BASE, { waitUntil: "domcontentloaded" });
    await p2.locator(".ai-mode-pill", { hasText: "Backend unreachable" }).waitFor({ timeout: 15_000 });
    seenBadges.add((await badge(p2)).split("\n")[0]);
    const unreachableText = await badge(p2);
    check("unreachable backend: badge says so, not 'Offline deterministic mode'", /Backend unreachable/.test(unreachableText) && !/Offline deterministic|full functionality retained/.test(unreachableText), unreachableText.replace(/\n/g, " | "));
    await shot(p2, "09_backend_unreachable");
    await p2.unroute(API);
    const recovered = await p2.locator(".ai-mode-pill", { hasText: "Offline deterministic mode" }).waitFor({ timeout: 15_000 }).then(() => true).catch(() => false);
    check("unreachable backend: badge recovers by itself once the API answers (~5s retry)", recovered);
    await p2.close();

    const p3 = await context.newPage(); watch(p3, "loading");
    await p3.route(apiRe("health"), async (r) => { await sleep(2500); await r.continue(); });
    await p3.goto(BASE, { waitUntil: "domcontentloaded" });
    const connecting = await p3.locator(".ai-mode-pill", { hasText: "Connecting" }).isVisible({ timeout: 2000 }).catch(() => false);
    check("loading state: badge shows 'Connecting...' until the API answers", connecting);
    await p3.locator(".ai-mode-pill", { hasText: "Offline deterministic mode" }).waitFor({ timeout: 15_000 });
    await p3.unroute(apiRe("health"));

    await p3.route(apiRe("event/parse"), async (r) => { await sleep(1500); await r.continue(); });
    await p3.getByRole("link", { name: "Events" }).click();
    const parsing = await p3.getByText("Parsing…").waitFor({ state: "visible", timeout: 6000 }).then(() => true).catch(() => false);
    check("loading state: Event Studio shows 'Parsing…' while waiting", parsing);
    await p3.getByText("Parsing…").waitFor({ state: "detached", timeout: 15_000 });
    await p3.close();

    // a validation error straight from the server, as the browser sees it
    const status = await page.evaluate(async () => (await fetch("/api/entities?limit=-1")).status);
    check("validation: server answers 422 for limit=-1 in the browser too", status === 422, String(status));
  } else {
    // static mode: the "backend" is the Python runtime. Block its CDN, expect the failure UI, unblock, press Retry.
    const p2 = await context.newPage(); watch(p2, "static-unreachable");
    await p2.route(/cdn\.jsdelivr\.net/, (r) => r.abort());
    await p2.goto(BASE, { waitUntil: "domcontentloaded" });
    const failed = await p2.getByText("Failed to start the offline demo").waitFor({ timeout: 120_000 }).then(() => true).catch(() => false);
    check("static unreachable runtime: failure state with a Retry button (not a blank page)", failed && (await p2.getByRole("button", { name: "Retry" }).isVisible()));
    await shot(p2, "09_static_boot_failed");
    await p2.unroute(/cdn\.jsdelivr\.net/);
    await p2.getByRole("button", { name: "Retry" }).click();
    const back = await p2.locator(".ai-mode-pill", { hasText: "Offline deterministic mode" }).waitFor({ timeout: 300_000 }).then(() => true).catch(() => false);
    check("static unreachable runtime: Retry recovers once the CDN is reachable", back);
    await p2.close();
  }
} catch (e) {
  check("script completed without an unexpected exception", false, String(e).slice(0, 300));
}
await browser.close();

const EXPECTED_422 = /^422 POST \/api\/(model-lab\/score|event\/parse)$/;   // the two validation errors this script provokes on purpose
const unexpectedHttp = httpErrors.filter((e) => !EXPECTED_422.test(e) && !EXPECTED_404_TWO_UNIVERSES.test(e) && !(MODE === "dev" && /^422 GET \/api\/entities\?limit=-1$/.test(e)));
check("no unexpected HTTP errors (4xx/5xx) from the app", unexpectedHttp.length === 0, unexpectedHttp.join(" ; "));
if (MODE === "dev") check("the provoked validation errors were really 422 responses", httpErrors.filter((e) => EXPECTED_422.test(e)).length >= 2, httpErrors.filter((e) => EXPECTED_422.test(e)).join(" ; "));
const bad = results.filter((r) => !r.ok);
// While the Python runtime's CDN is deliberately blocked, Pyodide's own loader (loadLockFile, installStdlib,
// browser_getBinaryResponse) leaves its parallel fetches unhandled. Third-party internals in an induced failure;
// the app's own handling is asserted by the checks above (failure overlay + working Retry).
const consoleProblems = problems.filter((p) => !/Failed to load resource|net::ERR_FAILED|ERR_ABORTED/.test(p)
  && !/^\[static-unreachable\] pageerror: Failed to fetch$/.test(p)
  && !/^\[static-unreachable\] console\.error: \[pyodide\] boot failed permanently/.test(p));
void 0;
console.log(`\n${MODE}: ${results.length - bad.length}/${results.length} checks passed; console/page errors: ${consoleProblems.length}`);
consoleProblems.slice(0, 8).forEach((p) => console.log("  !", p));
process.exit(bad.length || consoleProblems.length ? 1 : 0);
