// The Oracle-NVIDIA journey through the Data Intelligence Studio in a real browser, against a real operator backend (nothing is mocked).
//
//   backend:   cd backend && CCRIG_ENABLE_STUDIO=1 CCRIG_STUDIO_TOKEN=dev-token CCRIG_STUDIO_DIR=$(mktemp -d) python -m uvicorn app.main:app --port 8000
//   frontend:  cd frontend && npm run dev
//   run:       node e2e/studio-e2e.mjs            (E2E_BASE, STUDIO_TOKEN, BROWSER_EXECUTABLE, E2E_SHOTS as in browser-e2e.mjs; E2E_W / E2E_H set the window, default 1440x900)
//
// The workspace must be empty when the script starts. Needs playwright-core (npm install --no-save playwright-core).
import { chromium } from "playwright-core";
import { existsSync, mkdirSync } from "node:fs";

const BASE = (process.env.E2E_BASE ?? "http://localhost:5173/").replace(/\/?$/, "/");
const TOKEN = process.env.STUDIO_TOKEN ?? "dev-token";
const W = Number(process.env.E2E_W ?? 1440), H = Number(process.env.E2E_H ?? 900);
const SHOTS = (process.env.E2E_SHOTS ?? "e2e-shots/studio-v2").replace(/\/?$/, "/");
const EXE = process.env.BROWSER_EXECUTABLE ?? ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/chromium", "/usr/bin/google-chrome"].find(existsSync);
if (!EXE) { console.error("No Chromium-based browser found: set BROWSER_EXECUTABLE"); process.exit(2); }
mkdirSync(SHOTS, { recursive: true });

const results = [];
const check = (name, ok, detail = "") => { results.push(!!ok); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  -> " + detail : ""}`); };
const browser = await chromium.launch({ executablePath: EXE, headless: true });
const ctx = await browser.newContext({ viewport: { width: W, height: H } });
await ctx.addInitScript((t) => {
  sessionStorage.setItem("ccrig.studio.token", t);
  window.__llm = new Set();                                                  // every state the model module ever showed
  setInterval(() => { const n = document.querySelector('[data-testid="flow-node-LLM"]'); if (n) window.__llm.add(n.dataset.state); }, 15);
}, TOKEN);
const page = await ctx.newPage();
const problems = [];
page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
page.on("console", (m) => { if (m.type() === "error" && !/401|Failed to load resource/.test(m.text())) problems.push("console.error: " + m.text().slice(0, 200)); });
const T = (id) => page.getByTestId(id);
const state = () => page.evaluate(() => document.querySelector('[data-testid="studio-page"]').dataset.state);
const node = (id) => T(`flow-node-${id}`);
const nodeState = (id) => node(id).getAttribute("data-state");
const waitState = (s, ms = 20000) => page.waitForFunction((x) => document.querySelector('[data-testid="studio-page"]')?.dataset.state === x, s, { timeout: ms });
const api = async (path) => (await page.request.get(`${BASE}api/studio/${path}`, { headers: { "X-Studio-Token": TOKEN } })).json();
const IDS = ["SOURCE", "PARSE", "VALIDATE", "RESOLVE", "LLM", "VERIFY", "REVIEW", "OUTPUT"];
const nodesOf = async () => Object.fromEntries(await Promise.all(IDS.map(async (s) => [s, await nodeState(s)])));
const tab = async (name) => { if ((await T("drawer").getAttribute("aria-hidden")) === "true") await T("drawer-toggle").click(); await T(`drawer-tab-${name}`).click(); };
const closeDrawer = async () => { await T("drawer-close").click(); await page.waitForTimeout(350); };

try {
  // ---- 1. the instrument at rest
  await page.goto(BASE + "data-studio", { waitUntil: "load" });
  await T("run-claim-asserted").waitFor({ timeout: 30000 });
  await page.waitForTimeout(500);
  const cb = await T("flow-canvas").boundingBox();
  check(`the processing network dominates the window (${Math.round(cb.height)}px of ${H}px high = ${(cb.height / H * 100).toFixed(0)}%)`, cb.height / H >= 0.7 && cb.width >= W * 0.8);
  const inView = (await Promise.all(IDS.map(async (s) => { const b = await node(s).boundingBox(); return b && b.x >= 0 && b.y >= 0 && b.x + b.width <= W && b.y + b.height <= H; }))).every(Boolean);
  check("all eight modules are visible in the first screen: source, parse, validate, resolve, LLM, verify, review, output", inView);
  check("the details drawer is closed by default and its contents are not even rendered", (await page.getByTestId("studio-page").getAttribute("data-drawer")) === "false" && (await T("source-inspector").count()) === 0 && (await T("timeline").count()) === 0);
  check("operator mode: connected with the operator token, idle, nothing lit", (await page.getByTestId("studio-page").getAttribute("data-access")) === "ready" && (await T("mode-badge").innerText()) === "IDLE" && Object.values(await nodesOf()).every((s) => s === "QUEUED") && (await T("idle-hint").count()) === 1);
  await page.screenshot({ path: SHOTS + `${W}-1-idle.png` });
  await tab("source");
  await T("mention-chip-NVDA").waitFor({ timeout: 15000 });
  check("stored Oracle excerpt: company mentions (NVIDIA, Oracle) are extracted, and a mention is not a relationship", (await T("mention-chip-ORCL").count()) === 1 && /mention is not a relationship/i.test(await T("source-inspector").innerText()));
  await closeDrawer();

  // ---- 2. claim A: co-occurrence only -> rejected as insufficient relationship evidence
  await T("run-claim-cooccurrence").click();
  await waitState("BLOCKED");
  const a = await nodesOf();
  check("co-occurrence claim: lit through parse, validate and resolve, then refused at verify and held at the gate; output not reached", a.SOURCE === "COMPLETED" && a.PARSE === "COMPLETED" && a.RESOLVE === "COMPLETED" && a.VERIFY === "FAILED_CHECKS" && a.REVIEW === "BLOCKED" && a.OUTPUT === "SKIPPED", JSON.stringify(a));
  check("co-occurrence claim: the cable into the gate is held (refused) and the verify module says rejected", (await T("flow-conn-VERIFY-REVIEW").getAttribute("data-state")) === "HELD" && /rejected/.test(await node("VERIFY").innerText()));
  check("the language-model module is shown as skipped, not running: no model call was recorded", a.LLM === "SKIPPED" && /not invoked/.test(await node("LLM").innerText()) && (await T("flow-conn-RESOLVE-LLM").getAttribute("data-state")) === "SKIPPED" && (await T("flow-conn-RESOLVE-VERIFY").getAttribute("data-state")) === "FLOWED");
  await page.screenshot({ path: SHOTS + `${W}-2-cooccurrence-refused.png` });
  await node("VERIFY").click({ position: { x: 20, y: 20 } });
  await T("stage-tab").waitFor();
  check("clicking a module opens the contextual drawer on that module's findings", (await page.getByTestId("studio-page").getAttribute("data-drawer")) === "true" && /UNSUPPORTED_RELATIONSHIP_ASSERTION/.test(await T("stage-tab").innerText()));
  await tab("quality");
  check("co-occurrence claim: the assessment is REJECTED: both companies are named but nothing states a relationship", (await T("assessment-verdict").first().innerText()).toLowerCase() === "rejected" && /nothing states a SUPPLIES relationship/i.test(await T("quality-inspector").innerText()) && /wording for SUPPLIES found: none/.test(await T("assessment-quote").first().innerText()));
  await tab("review");
  check("co-occurrence claim: it cannot be approved: no approve control, reasons shown", (await T("review-approve").count()) === 0 && (await T("review-blocked").count()) === 1);
  await closeDrawer();

  // ---- 3. claim B: asserted -> awaiting the reviewer
  await T("run-claim-asserted").click();
  await waitState("AWAITING_REVIEW");
  const b = await nodesOf();
  check("asserted claim: runs through every module and pauses at the approval gate; output stays queued", b.VERIFY === "COMPLETED_WITH_WARNINGS" && b.REVIEW === "AWAITING_REVIEW" && b.OUTPUT === "QUEUED", JSON.stringify(b));
  check("asserted claim: the cable into the gate is paused there, and a decision control appears on the module", (await T("flow-conn-VERIFY-REVIEW").getAttribute("data-state")) === "AWAITING" && (await T("open-review").count()) === 1);
  await page.screenshot({ path: SHOTS + `${W}-3-awaiting-review.png` });
  const jobB = await page.evaluate(() => document.querySelector('[data-testid="job-select"]').value);
  await T("open-review").click();
  await T("review-panel").waitFor();
  check("review gate: the explicit acknowledgement is unchecked; approval stays disabled until reviewer, reason and acknowledgement are given", !(await T("review-ack").isChecked()) && (await T("review-approve").isDisabled()) && /NVDA .*SUPPLIES.* ORCL/s.test(await T("review-assert-note").innerText()));
  await T("review-name").fill("alice"); await T("review-reason").fill("Checked the quoted sentence against the stored release.");
  check("review gate: a name and a reason are not enough without the acknowledgement", await T("review-approve").isDisabled());
  await tab("events");
  const backendEvents = (await api(`flow/events?since=0&job_id=${jobB}`)).events.map((e) => e.id);
  const shown = await T("timeline-row").evaluateAll((els) => els.map((e) => e.dataset.eventId));
  const ticks = await T("tick").evaluateAll((els) => els.map((e) => e.dataset.eventId));
  check("the timeline (list and strip) shows exactly the events the backend recorded for this job", JSON.stringify(shown) === JSON.stringify(backendEvents) && JSON.stringify(ticks) === JSON.stringify(backendEvents), `${shown.length}/${ticks.length} vs ${backendEvents.length}`);
  const raw = (await api(`jobs/${jobB}`)).events;
  check("every recorded ledger row appears in the timeline; none invented", raw.every((r) => shown.includes(String(r.seq))));
  check("measurements: elapsed time is measured; throughput is declared unavailable, not estimated", /ms/.test(await T("spec-elapsed").innerText()) && /unavailable/.test(await T("spec-throughput").innerText()));

  // ---- 4. approve through the existing review mechanism
  await tab("review");
  await T("review-ack").check();
  await T("review-approve").click();
  await waitState("APPROVED");
  await page.waitForFunction(() => document.querySelector('[data-testid="flow-node-OUTPUT"]')?.dataset.state === "COMPLETED");
  const c = await nodesOf();
  check("approval: review approved, output completes; the lit network reaches the output module", c.REVIEW === "APPROVED" && c.OUTPUT === "COMPLETED" && (await T("flow-conn-REVIEW-OUTPUT").getAttribute("data-state")) === "FLOWED", JSON.stringify(c));
  check("approval: the decision history names the reviewer", /APPROVE\s+alice/.test(await T("decision-history").innerText()));
  await closeDrawer();
  await page.screenshot({ path: SHOTS + `${W}-4-approved.png` });
  await T("open-output").click();
  await T("overlay-edge").waitFor();
  check("output: the destination is the Studio overlay, canonical data untouched; the effect on the graph and the gaps are stated", (await T("destination-panel").getAttribute("data-status")) === "LIVE_IN_OVERLAY" && /canonical data modified\s*no/i.test((await T("destination-panel").innerText()).replace(/\n/g, " ")) && /wrong-way risk is not assessed/i.test(await T("adoption").innerText()));

  // ---- 5. the relationship in CCRIG
  await T("open-graph-ORCL").click();
  await T("studio-overlay-note").waitFor({ timeout: 30000 });
  const note = await T("studio-overlay-note").innerText();
  check("Graph Explorer: opened from the Studio with approved relationships on, and it says so", /studio=1/.test(page.url()) && /approved/i.test(note), note.slice(0, 90));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: SHOTS + `${W}-5-graph-explorer-overlay.png` });
  const gx = await page.request.get(`${BASE}api/graph/ego/ORCL?layers=fact&hops=1&include_studio=true`).then((r) => r.json());
  const gplain = await page.request.get(`${BASE}api/graph/ego/ORCL?layers=fact&hops=1`).then((r) => r.json());
  const edge = gx.edges.find((e) => e.relation === "SUPPLIES" && e.source === "NVDA");
  check("Graph API: the approved edge carries provenance and no criticality; the default view is unchanged", edge && edge.weight === null && edge.evidence.studio_evidence[0].source_url && !gplain.edges.some((e) => e.relation === "SUPPLIES" && e.source === "NVDA"));

  // ---- 6. back to the Studio: history restored from the server; then roll back
  await page.goto(BASE + "data-studio", { waitUntil: "load" });
  await T("job-select").waitFor({ timeout: 30000 });
  await T("job-select").selectOption(jobB);
  await waitState("APPROVED");
  await tab("output");
  check("history restoration: after leaving the page and returning, the approved job and its decision are restored from the server", (await T("destination-panel").getAttribute("data-status")) === "LIVE_IN_OVERLAY");
  await T("rollback-name").fill("bob"); await T("rollback-reason").fill("Demonstrating rollback.");
  await T("rollback-btn").click();
  await waitState("ROLLED_BACK");
  check("rollback: the output module shows it, the destination effect is reversed and the history is retained", (await nodeState("OUTPUT")) === "ROLLED_BACK" && (await T("destination-panel").getAttribute("data-status")) === "ROLLED_BACK" && (await T("rolled-back-note").count()) === 1);
  const after = await page.request.get(`${BASE}api/graph/ego/ORCL?layers=fact&hops=1&include_studio=true`).then((r) => r.json());
  check("rollback: the edge is gone from the Graph Explorer's data", !after.edges.some((e) => e.relation === "SUPPLIES" && e.source === "NVDA"));
  await tab("events");
  const types = await T("timeline-row").evaluateAll((els) => els.map((e) => e.dataset.type));
  check("rollback: the audit history keeps the approval and the rollback events in order", types.indexOf("REVIEW_APPROVED") > 0 && types.indexOf("PROMOTED") > types.indexOf("REVIEW_APPROVED") && types.indexOf("ROLLED_BACK") > types.indexOf("PROMOTED"));
  await closeDrawer();
  await page.screenshot({ path: SHOTS + `${W}-6-rolled-back.png` });

  // ---- 7. recorded replay of the real job, and seeking along the timeline
  await T("replay-btn").click();
  check("replay is labelled as a recorded replay", (await T("mode-badge").innerText()) === "RECORDED REPLAY");
  await page.getByRole("button", { name: "4×" }).click();
  const seen = new Set(), t0 = Date.now();
  while (Date.now() - t0 < 40000) {
    seen.add((await nodeState("REVIEW")) + "/" + (await nodeState("OUTPUT")));
    if ((await state()) === "ROLLED_BACK" && (await page.getByTestId("studio-page").getAttribute("data-playing")) === "false") break;
    await page.waitForTimeout(50);
  }
  const s = [...seen].join(" ");
  check("replay: the gate waits, then approves and promotes, then rolls back, in recorded order", /QUEUED\/QUEUED/.test(s) && /AWAITING_REVIEW\/QUEUED/.test(s) && /APPROVED\/COMPLETED/.test(s) && /ROLLED_BACK/.test(s), s);
  const firstTick = T("tick").first();
  await firstTick.click();
  check("timeline: clicking an event moves the replay there (only modules recorded by then are lit)", (await nodeState("PARSE")) === "QUEUED" && (await state()) !== "ROLLED_BACK" && /JOB/.test(await T("timeline-now").innerText()));
  await T("tick").nth(Math.floor((await T("tick").count()) / 2)).click();
  check("timeline: a point in the middle shows a partially lit network", (await nodeState("SOURCE")) === "COMPLETED" && ["QUEUED", "SKIPPED"].includes(await nodeState("OUTPUT")));

  // ---- 8. duplicate ingestion
  await T("run-claim-asserted").click();
  await T("notice").waitFor({ timeout: 20000 });
  check("duplicate ingestion: no new job, the resubmission is recorded", /no new job was created/.test(await T("notice").innerText()));
  check("duplicate ingestion: the backend holds two jobs, not three", (await api("jobs")).jobs.length === 2);

  // ---- 9. no model was ever shown running; wrong token
  const llm = await page.evaluate(() => [...window.__llm]);
  check("the language-model module only ever appeared queued or skipped: no model call was recorded, so none is shown", llm.every((x) => ["QUEUED", "SKIPPED"].includes(x)) && llm.includes("SKIPPED"), llm.join(","));
  const bad = await ctx.newPage();
  await bad.addInitScript(() => sessionStorage.setItem("ccrig.studio.token", "wrong"));
  await bad.goto(BASE + "data-studio", { waitUntil: "load" });
  await bad.getByTestId("access-note").waitFor({ timeout: 30000 });
  check("a wrong operator token is refused: the page falls back to read-only, offers the token field and runs nothing", (await bad.getByTestId("studio-page").getAttribute("data-access")) === "rejected" && (await bad.getByTestId("run-claim-asserted").count()) === 0 && (await bad.getByTestId("token-input").count()) === 1);
  await bad.close();
} catch (e) {
  check("script completed without an unexpected exception", false, String(e).slice(0, 400));
  await page.screenshot({ path: SHOTS + "failure.png" }).catch(() => {});
}
check("no unexpected console or page errors", problems.length === 0, problems.slice(0, 3).join(" | "));
await browser.close();
const passed = results.filter(Boolean).length;
console.log(`\nstudio: ${passed}/${results.length} checks passed`);
process.exit(passed === results.length ? 0 : 1);
