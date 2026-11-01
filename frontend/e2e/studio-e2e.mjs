// The Oracle-NVIDIA journey through the Data Intelligence Studio in a real browser, against a real operator backend (nothing is mocked).
//
//   backend:   cd backend && CCRIG_ENABLE_STUDIO=1 CCRIG_STUDIO_TOKEN=dev-token CCRIG_STUDIO_DIR=$(mktemp -d) python -m uvicorn app.main:app --port 8000
//   frontend:  cd frontend && npm run dev
//   run:       node e2e/studio-e2e.mjs            (E2E_BASE, STUDIO_TOKEN, BROWSER_EXECUTABLE, E2E_SHOTS as in browser-e2e.mjs)
//
// The workspace must be empty when the script starts. Needs playwright-core (npm install --no-save playwright-core).
import { chromium } from "playwright-core";
import { existsSync, mkdirSync } from "node:fs";

const BASE = (process.env.E2E_BASE ?? "http://localhost:5173/").replace(/\/?$/, "/");
const TOKEN = process.env.STUDIO_TOKEN ?? "dev-token";
const SHOTS = (process.env.E2E_SHOTS ?? "e2e-shots/studio").replace(/\/?$/, "/");
const EXE = process.env.BROWSER_EXECUTABLE ?? ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/chromium", "/usr/bin/google-chrome"].find(existsSync);
if (!EXE) { console.error("No Chromium-based browser found: set BROWSER_EXECUTABLE"); process.exit(2); }
mkdirSync(SHOTS, { recursive: true });

const results = [];
const check = (name, ok, detail = "") => { results.push(!!ok); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  -> " + detail : ""}`); };
const browser = await chromium.launch({ executablePath: EXE, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1560, height: 2500 } });
await ctx.addInitScript((t) => sessionStorage.setItem("ccrig.studio.token", t), TOKEN);
const page = await ctx.newPage();
const problems = [];
page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
page.on("console", (m) => { if (m.type() === "error" && !/401|Failed to load resource/.test(m.text())) problems.push("console.error: " + m.text().slice(0, 200)); });
const T = (id) => page.getByTestId(id);
const state = () => page.evaluate(() => document.querySelector('[data-testid="studio-page"]').dataset.state);
const nodeState = (id) => T(`flow-node-${id}`).getAttribute("data-state");
const waitState = (s, ms = 20000) => page.waitForFunction((x) => document.querySelector('[data-testid="studio-page"]')?.dataset.state === x, s, { timeout: ms });
const api = async (path) => (await page.request.get(`${BASE}api/studio/${path}`, { headers: { "X-Studio-Token": TOKEN } })).json();
const stagesOf = async () => Object.fromEntries(await Promise.all(["SOURCE", "PARSE", "PROFILE", "VALIDATE", "RESOLVE", "EVIDENCE", "REVIEW", "PROMOTE"].map(async (s) => [s, await nodeState(s)])));

try {
  // ---- 1. select the stored source
  await page.goto(BASE + "data-studio", { waitUntil: "load" });
  await T("run-claim-asserted").waitFor({ timeout: 30000 });
  check("operator mode: the page connects with the operator token and offers to run real jobs", (await page.getByTestId("studio-page").getAttribute("data-access")) === "ready" && (await T("mode-badge").innerText()) === "IDLE");
  await T("mention-chip-NVDA").waitFor({ timeout: 15000 });
  check("stored Oracle release excerpt: company mentions are extracted (NVIDIA and Oracle), with the rule that a mention is not a relationship", (await T("mention-chip-ORCL").count()) === 1 && /mention is not a relationship/i.test(await T("source-inspector").innerText()));
  check("before any job every stage is queued", Object.values(await stagesOf()).every((s) => s === "QUEUED"));
  await page.screenshot({ path: SHOTS + "01-select-source.png" });

  // ---- 2. claim A: co-occurrence only -> rejected as insufficient relationship evidence
  await T("run-claim-cooccurrence").click();
  await waitState("BLOCKED");
  const a = await stagesOf();
  check("co-occurrence claim: parsed, validated and resolved, then failed at the evidence stage and held at the gate", a.SOURCE === "COMPLETED" && a.RESOLVE === "COMPLETED" && a.EVIDENCE === "FAILED_CHECKS" && a.REVIEW === "BLOCKED" && a.PROMOTE === "SKIPPED", JSON.stringify(a));
  check("co-occurrence claim: the assessment is REJECTED and says both companies are named but nothing states a relationship", (await T("assessment-verdict").first().innerText()).toLowerCase() === "rejected" && /nothing states a SUPPLIES relationship/i.test(await T("quality-inspector").innerText()));
  check("co-occurrence claim: the text between the names and the missing wording are shown", /wording for SUPPLIES found: none/.test(await T("assessment-quote").first().innerText()));
  check("co-occurrence claim: it cannot be approved (no approve control, reason given)", (await T("review-approve").count()) === 0 && (await T("review-blocked").count()) === 1);
  await page.screenshot({ path: SHOTS + "02-cooccurrence-rejected.png" });
  const jobA = await page.evaluate(() => document.querySelector('[data-testid="source-picker"] select')?.value ?? "");

  // ---- 3. claim B: asserted -> awaiting the reviewer
  await T("run-claim-asserted").click();
  await waitState("AWAITING_REVIEW");
  const b = await stagesOf();
  check("asserted claim: runs through every stage and pauses at the approval gate; promote stays queued", b.EVIDENCE === "COMPLETED_WITH_WARNINGS" && b.REVIEW === "AWAITING_REVIEW" && b.PROMOTE === "QUEUED", JSON.stringify(b));
  check("asserted claim: the typed relationship is shown as an assertion that needs the reviewer", (await T("assessment").first().getAttribute("data-verdict")) === "ASSERTED_NEEDS_ACKNOWLEDGEMENT" && /NVDA .*SUPPLIES.* ORCL/s.test(await T("review-assert-note").innerText()));
  const jobB = (await T("kpi-job").innerText()) && (await page.evaluate(() => document.querySelector('[data-testid="source-picker"] select').value));
  check("review gate: the explicit acknowledgement is unchecked and approval is disabled until reviewer, reason and acknowledgement are given",
    !(await T("review-ack").isChecked()) && (await T("review-approve").isDisabled()));
  await T("review-name").fill("alice"); await T("review-reason").fill("Checked the quoted sentence against the stored release.");
  check("review gate: a name and a reason are not enough without the acknowledgement", await T("review-approve").isDisabled());
  await page.screenshot({ path: SHOTS + "03-awaiting-review.png" });
  // events on screen == the backend's recorded events
  const backendEvents = (await api(`flow/events?since=0&job_id=${jobB}`)).events.map((e) => e.id);
  const shown = await T("timeline-row").evaluateAll((els) => els.map((e) => e.dataset.eventId));
  check("the execution timeline shows exactly the events the backend recorded for this job", JSON.stringify(shown) === JSON.stringify(backendEvents), `${shown.length} vs ${backendEvents.length}`);
  const raw = (await api(`jobs/${jobB}`)).events;
  check("every recorded ledger row appears once or more in the timeline, none invented", new Set(shown.map((i) => i.split(".")[0])).size === raw.length && raw.every((r) => shown.includes(String(r.seq))));

  // ---- 4. approve through the existing review mechanism
  await T("review-ack").check();
  await T("review-approve").click();
  await waitState("APPROVED");
  await T("overlay-edge").waitFor();
  const c = await stagesOf();
  check("approval: review is approved and promotion completes; the destination is the Studio overlay, not canonical data", c.REVIEW === "APPROVED" && c.PROMOTE === "COMPLETED" && (await T("destination-panel").getAttribute("data-status")) === "LIVE_IN_OVERLAY" && /canonical data modified\s*no/i.test((await T("destination-panel").innerText()).replace(/\n/g, " ")));
  check("approval: the decision history names the reviewer", /APPROVE\s+alice/.test(await T("decision-history").innerText()));
  check("approval: the effect on the graph is stated, with the gaps (no exposure, wrong-way risk not assessed)", /1 ?→|21 → 22/.test(await T("adoption").innerText()) && /wrong-way risk is not assessed/i.test(await T("adoption").innerText()));
  await page.screenshot({ path: SHOTS + "04-approved.png" });

  // ---- 5. the relationship in CCRIG
  await T("open-graph-ORCL").click();
  await T("studio-overlay-note").waitFor({ timeout: 30000 });
  const note = await T("studio-overlay-note").innerText();
  check("Graph Explorer: opened from the Studio with approved relationships on, and it says so", /studio=1/.test(page.url()) && /approved/i.test(note), note.slice(0, 100));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: SHOTS + "05-graph-explorer-overlay.png" });
  const gx = await page.request.get(`${BASE}api/graph/ego/ORCL?layers=fact&hops=1&include_studio=true`).then((r) => r.json());
  const gplain = await page.request.get(`${BASE}api/graph/ego/ORCL?layers=fact&hops=1`).then((r) => r.json());
  const edge = gx.edges.find((e) => e.relation === "SUPPLIES" && e.source === "NVDA");
  check("Graph API: the approved edge is present with provenance and no criticality; the default view is unchanged", edge && edge.weight === null && edge.evidence.studio_evidence[0].source_url && !gplain.edges.some((e) => e.relation === "SUPPLIES" && e.source === "NVDA"));

  // ---- 6. back to the Studio: history restored from the server; then roll back
  await page.goto(BASE + "data-studio", { waitUntil: "load" });
  await T("job-select").waitFor({ timeout: 30000 });
  await T("job-select").selectOption(jobB);
  await waitState("APPROVED");
  check("history restoration: after leaving the page and returning, the approved job and its decision are restored from the server", (await T("destination-panel").getAttribute("data-status")) === "LIVE_IN_OVERLAY" && /alice/.test(await T("decision-history").innerText()));
  await T("rollback-name").fill("bob"); await T("rollback-reason").fill("Demonstrating rollback.");
  await T("rollback-btn").click();
  await waitState("ROLLED_BACK");
  check("rollback: the destination effect is reversed and the history is retained", (await T("destination-panel").getAttribute("data-status")) === "ROLLED_BACK" && (await nodeState("PROMOTE")) === "ROLLED_BACK" && /alice/.test(await T("decision-history").innerText()) && (await T("rolled-back-note").count()) === 1);
  const after = await page.request.get(`${BASE}api/graph/ego/ORCL?layers=fact&hops=1&include_studio=true`).then((r) => r.json());
  check("rollback: the edge is gone from the Graph Explorer's data", !after.edges.some((e) => e.relation === "SUPPLIES" && e.source === "NVDA"));
  const types = await T("timeline-row").evaluateAll((els) => els.map((e) => e.dataset.type));
  check("rollback: the audit history keeps the approval and the rollback events in order", types.indexOf("REVIEW_APPROVED") > 0 && types.indexOf("PROMOTED") > types.indexOf("REVIEW_APPROVED") && types.indexOf("ROLLED_BACK") > types.indexOf("PROMOTED"));
  await page.screenshot({ path: SHOTS + "06-rolled-back.png" });

  // ---- 7. recorded replay of the real job
  await T("replay-btn").click();
  check("replay is labelled as a recorded replay", (await T("mode-badge").innerText()) === "RECORDED REPLAY");
  await page.getByRole("button", { name: "4×" }).click();
  const seen = new Set();
  const t0 = Date.now();
  while (Date.now() - t0 < 40000) {
    seen.add(await nodeState("REVIEW") + "/" + await nodeState("PROMOTE"));
    if ((await state()) === "ROLLED_BACK" && (await page.getByTestId("studio-page").getAttribute("data-playing")) === "false") break;
    await page.waitForTimeout(60);
  }
  const s = [...seen].join(" ");
  check("replay: the gate is shown waiting, then approved and promoted, then rolled back, in recorded order", /QUEUED\/QUEUED/.test(s) && /AWAITING_REVIEW\/QUEUED/.test(s) && /APPROVED\/COMPLETED/.test(s) && /APPROVED\/ROLLED_BACK|ROLLED_BACK\/ROLLED_BACK/.test(s.replace("APPROVED/ROLLED_BACK", "APPROVED/ROLLED_BACK")), s);
  check("replay: ends in the recorded final state", (await state()) === "ROLLED_BACK");

  // ---- 8. duplicate ingestion
  await T("run-claim-asserted").click();
  await T("notice").waitFor({ timeout: 20000 });
  check("duplicate ingestion: no new job, the resubmission is recorded", /no new job was created/.test(await T("notice").innerText()) && (await T("timeline-row").evaluateAll((els) => els.some((e) => e.dataset.type === "DUPLICATE_SUBMISSION"))));
  const jobsNow = await api("jobs");
  check("duplicate ingestion: the backend holds two jobs, not three", jobsNow.jobs.length === 2, String(jobsNow.jobs.length));
  void jobA;

  // ---- 9. wrong token
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
