// Ingest Bench in a real browser.
//   node e2e/ingest-bench-e2e.mjs            demo (simulator) behaviour, fallback when no live run answers, themes, responsiveness. Works against a normal dev stack.
//   E2E_LIVE=1 node e2e/ingest-bench-e2e.mjs also drives the live path against an operator backend (CCRIG_ENABLE_STUDIO=1, CCRIG_STUDIO_TOKEN=dev-token): the page connects to a scripted,
//                                            simulated=true run streamed over Server-Sent Events.
// Env: E2E_BASE, STUDIO_TOKEN, BROWSER_EXECUTABLE, E2E_SHOTS (default e2e-shots/ib/).
import { chromium } from "playwright-core";
import { existsSync, mkdirSync } from "node:fs";

const BASE = (process.env.E2E_BASE ?? "http://localhost:5173/").replace(/\/?$/, "/"), TOKEN = process.env.STUDIO_TOKEN ?? "dev-token", LIVE = process.env.E2E_LIVE === "1";
const SHOTS = (process.env.E2E_SHOTS ?? "e2e-shots/ib").replace(/\/?$/, "/"); mkdirSync(SHOTS, { recursive: true });
const EXE = process.env.BROWSER_EXECUTABLE ?? ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/chromium", "/usr/bin/google-chrome"].find(existsSync);
if (!EXE) { console.error("No Chromium-based browser found: set BROWSER_EXECUTABLE"); process.exit(2); }
const results = [], check = (n, ok, d = "") => { results.push(!!ok); console.log(`${ok ? "PASS" : "FAIL"}  ${n}${d ? "  -> " + d : ""}`); };
const browser = await chromium.launch({ executablePath: EXE, headless: true });
const problems = [];
async function open(url, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: opts.w ?? 1440, height: opts.h ?? 1000 }, colorScheme: opts.scheme ?? "light" });
  await ctx.addInitScript((t) => sessionStorage.setItem("ccrig.studio.token", t), TOKEN);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message)); page.on("console", (m) => { if (m.type() === "error" && !/404|Failed to load resource/.test(m.text())) problems.push("console.error: " + m.text().slice(0, 160)); });
  await page.goto(BASE + url, { waitUntil: "load" });
  await page.getByTestId("ib-root").waitFor({ timeout: 30000 });
  return { ctx, page };
}
const T = (p, id) => p.getByTestId(id);
const stage = (p) => T(p, "ib-k-stage").innerText();
const waitStage = (p, s, ms = 60000) => p.waitForFunction((x) => document.querySelector('[data-testid="ib-k-stage"]')?.textContent === x, s, { timeout: ms });
const painted = (p, id) => p.evaluate((i) => { const c = document.querySelector(`[data-testid="${i}"]`), d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data; let n = 0; for (let k = 3; k < d.length; k += 4 * 50) if (d[k] > 0) n++; return n; }, id);

try {
  // ---- demo mode: stages A -> D, controls, jump, completion
  let { ctx, page } = await open("ingest-bench?demo=1");
  check("demo: the sheet is labelled SIMULATED and says so in its note", (await T(page, "ib-badge").innerText()) === "SIMULATED" && /Simulated run with sample data/.test(await T(page, "ib-note").innerText()) && (await T(page, "ib-root").getAttribute("data-mode")) === "demo");
  check("demo: every canvas is painted (bench, network, ridgelines, convergence)", (await Promise.all(["ib-canvas-bench", "ib-canvas-net", "ib-canvas-ridge", "ib-canvas-conv"].map((i) => painted(page, i)))).every((n) => n > 50));
  check("demo: it starts in stage A at 1x", (await stage(page)) === "A" && (await T(page, "ib-speed-1").getAttribute("aria-pressed")) === "true");
  await T(page, "ib-speed-4").click();
  const recs0 = await T(page, "ib-k-records").innerText();
  await page.waitForTimeout(1500);
  await T(page, "ib-pause").click();
  await page.waitForTimeout(350);
  const frozen = [await T(page, "ib-k-records").innerText(), await T(page, "ib-k-loss").innerText(), await T(page, "ib-status").innerText()];
  await page.waitForTimeout(1500);
  check("demo: Pause freezes the display (KPIs and status stop; the status says Paused) and Resume continues", JSON.stringify(frozen) === JSON.stringify([await T(page, "ib-k-records").innerText(), await T(page, "ib-k-loss").innerText(), await T(page, "ib-status").innerText()]) && /Paused/.test(frozen[2]) && (await T(page, "ib-pause").innerText()) === "Resume" && frozen[0] !== recs0);
  await T(page, "ib-pause").click();
  const stagesSeen = new Set(), lossSeen = [];
  const t0 = Date.now();
  while (Date.now() - t0 < 30000 && (await T(page, "ib-root").getAttribute("data-status")) !== "done") { stagesSeen.add(await stage(page)); const l = parseFloat(await T(page, "ib-k-loss").innerText()); if (!Number.isNaN(l)) lossSeen.push(l); await page.waitForTimeout(150); }
  check("demo: the run passes through stages A, B, C and D and completes (about 36 s at 1x; 4x here)", ["A", "B", "C", "D"].every((x) => stagesSeen.has(x)) && (await T(page, "ib-root").getAttribute("data-status")) === "done", [...stagesSeen].join(""));
  check("demo: the loss falls as the run progresses (the focus improves)", lossSeen.length > 20 && lossSeen[lossSeen.length - 1] < lossSeen[0] / 3, `${lossSeen[0]?.toFixed(4)} -> ${lossSeen[lossSeen.length - 1]?.toFixed(4)}`);
  await page.waitForTimeout(600);
  check("demo: on completion the status reads 'Load complete · dashboard is live', the dot is teal, and the button becomes 'Run again'", /Load complete · dashboard is live/.test(await T(page, "ib-status").innerText()) && (await T(page, "ib-dot").getAttribute("class")).includes("done") && (await T(page, "ib-pause").innerText()) === "Run again");
  check("demo: all four revision rows are done, with residuals and losses filled in", (await Promise.all(["A", "B", "C", "D"].map((r) => T(page, `ib-rev-${r}`).getAttribute("data-status")))).every((s) => s === "done") && /\d/.test(await T(page, "ib-rev-D").innerText()));
  await page.screenshot({ path: SHOTS + "demo-complete-light.png" });
  await T(page, "ib-pause").click();                                     // Run again
  await page.waitForTimeout(500);
  check("demo: 'Run again' starts a fresh run", (await stage(page)) === "A" && (await T(page, "ib-root").getAttribute("data-status")) === "running");
  await T(page, "ib-speed-1").click();
  await T(page, "ib-rev-C").click();
  await page.waitForTimeout(400);
  check("demo: clicking a revision row jumps to that stage and fills in history (A and B done, C active, log populated)", (await stage(page)) === "C" && (await T(page, "ib-rev-A").getAttribute("data-status")) === "done" && (await T(page, "ib-rev-B").getAttribute("data-status")) === "done" && (await T(page, "ib-rev-C").getAttribute("data-status")) === "active" && (await T(page, "ib-log").locator("li").count()) === 7);
  await T(page, "ib-rev-D").focus(); await page.keyboard.press("Enter"); await page.waitForTimeout(300);
  check("demo: revision rows are keyboard operable", (await stage(page)) === "D");
  await T(page, "ib-restart").click(); await page.waitForTimeout(300);
  check("demo: Restart returns to stage A", (await stage(page)) === "A");
  // themes
  const paperLight = await page.evaluate(() => getComputedStyle(document.querySelector('[data-testid="ib-root"]')).getPropertyValue("--paper").trim());
  await T(page, "ib-theme-dark").click(); await page.waitForTimeout(300);
  const paperDark = await page.evaluate(() => getComputedStyle(document.querySelector('[data-testid="ib-root"]')).getPropertyValue("--paper").trim());
  check("themes: the dark theme swaps the tokens, and the canvases are redrawn with them (gold accent present)", paperLight === "#e7e5df" && paperDark === "#0b1117" && (await painted(page, "ib-canvas-bench")) > 50);
  await page.screenshot({ path: SHOTS + "demo-dark.png" });
  const hs = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1 && document.querySelector(".main-content").scrollWidth <= document.querySelector(".main-content").clientWidth + 1);
  check("1440px: no horizontal page scroll", hs);
  await ctx.close();

  // ---- phone width and OS dark scheme
  ({ ctx, page } = await open("ingest-bench?demo=1", { w: 390, h: 844, scheme: "dark" }));
  await page.waitForTimeout(2500);
  check("390px (OS dark scheme): no horizontal page scroll; the bench and the network keep their size inside scrollable containers; side rulers are hidden",
    (await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1 && document.querySelector(".main-content").scrollWidth <= document.querySelector(".main-content").clientWidth + 1))
    && (await page.evaluate(() => document.querySelector('[data-testid="ib-canvas-bench"]').getBoundingClientRect().width >= 719 && document.querySelector('[data-testid="ib-canvas-net"]').getBoundingClientRect().width >= 859 && getComputedStyle(document.querySelector(".ib-rul.v")).visibility === "hidden")));
  check("390px: the OS dark scheme is honoured; KPIs form a 2x2 grid", (await page.evaluate(() => getComputedStyle(document.querySelector('[data-testid="ib-root"]')).getPropertyValue("--paper").trim())) === "#0b1117" && (await page.evaluate(() => getComputedStyle(document.querySelector(".ib-kpis")).gridTemplateColumns.split(" ").length)) === 2);
  await page.screenshot({ path: SHOTS + "phone-dark.png", fullPage: true });
  await ctx.close();

  // ---- reduced motion: static states still update
  const rm = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: "reduce" });
  const rp = await rm.newPage(); rp.on("pageerror", (e) => problems.push("pageerror: " + e.message));
  await rp.goto(BASE + "ingest-bench?demo=1", { waitUntil: "load" }); await T(rp, "ib-root").waitFor({ timeout: 30000 });
  await rp.getByTestId("ib-speed-4").click(); await waitStage(rp, "B", 20000);
  check("reduced motion: the run still advances and the canvases still draw", (await painted(rp, "ib-canvas-bench")) > 50);
  await rm.close();

  // ---- no live run: falls back to the simulator and says so
  if (!LIVE) {
    ({ ctx, page } = await open("ingest-bench"));
    await page.waitForFunction(() => document.querySelector('[data-testid="ib-root"]')?.dataset.mode === "demo", null, { timeout: 30000 });
    check("no live run: the page falls back to the simulator, labelled SIMULATED, with the reason in its note", (await T(page, "ib-badge").innerText()) === "SIMULATED" && /No live run answered|Public static site/.test(await T(page, "ib-note").innerText()), (await T(page, "ib-note").innerText()).slice(0, 120));
    await ctx.close();
  } else {
    // ---- live path: a scripted run streamed over SSE
    const made = await (await fetch(`${BASE}api/ingest/demo-run?seconds=10`, { method: "POST", headers: { "X-Studio-Token": TOKEN } })).json();
    ({ ctx, page } = await open(`ingest-bench?run=${made.run_id}`));
    await page.waitForFunction(() => document.querySelector('[data-testid="ib-root"]')?.dataset.mode === "live", null, { timeout: 30000 });
    check("live: the page connects to the run over Server-Sent Events", (await T(page, "ib-root").getAttribute("data-mode")) === "live");
    check("live: a scripted run is flagged simulated by the backend, so it is still labelled SIMULATED and its note says it is not a measurement", (await T(page, "ib-badge").innerText()) === "SIMULATED" && /Simulated run/.test(await T(page, "ib-note").innerText()));
    check("live: controls that only make sense for the simulator are disabled (restart, speed) and revision rows say jumping is unavailable", (await T(page, "ib-restart").isDisabled()) && (await T(page, "ib-speed-4").isDisabled()) && (await T(page, "ib-rev-B").getAttribute("aria-disabled")) === "true");
    await page.waitForFunction(() => document.querySelector('[data-testid="ib-root"]')?.dataset.status === "done", null, { timeout: 25000 }); await page.waitForTimeout(400);
    check("live: the streamed run reaches stage D and completes with the same completion state", /Load complete/.test(await T(page, "ib-status").innerText()) && (await T(page, "ib-sheet").innerText()) === "4 / 4");
    await page.screenshot({ path: SHOTS + "live-complete.png" });
    await T(page, "ib-rev-A").click({ force: true }); await page.waitForTimeout(300);          // aria-disabled rows are not clickable for a user; force it to prove the handler ignores it
    check("live: clicking a revision row does nothing (a real run cannot be rewound)", (await T(page, "ib-root").getAttribute("data-status")) === "done");
    await ctx.close();
    // a reconnecting client resumes without replaying: open mid-run, drop nothing
    const made2 = await (await fetch(`${BASE}api/ingest/demo-run?seconds=8`, { method: "POST", headers: { "X-Studio-Token": TOKEN } })).json();
    ({ ctx, page } = await open(`ingest-bench?run=${made2.run_id}`));
    await page.waitForTimeout(2500);
    check("live: joining a run that is already under way shows its history (the stream replays from the start)", (await T(page, "ib-log").locator("li").count()) > 0 && (await T(page, "ib-root").getAttribute("data-status")) !== "waiting");
    await ctx.close();
  }
} catch (e) { check("script completed without an unexpected exception", false, String(e).slice(0, 400)); }
check("no unexpected console or page errors", problems.length === 0, problems.slice(0, 3).join(" | "));
await browser.close();
const ok = results.filter(Boolean).length;
console.log(`\ningest-bench: ${ok}/${results.length} checks passed`);
process.exit(ok === results.length ? 0 : 1);
