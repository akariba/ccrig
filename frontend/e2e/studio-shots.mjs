// Screenshots of the Data Intelligence Studio (E2E_W x E2E_H, default 1440x900; run again with 1920x1080 on a fresh workspace) against an operator backend with an EMPTY workspace (see studio-e2e.mjs for how to start one).
//   node e2e/studio-shots.mjs         -> e2e-shots/studio-final/
import { chromium } from "playwright-core";
import { existsSync, mkdirSync } from "node:fs";
const BASE = (process.env.E2E_BASE ?? "http://localhost:5173/").replace(/\/?$/, "/"), TOKEN = process.env.STUDIO_TOKEN ?? "dev-token";
const OUT = (process.env.E2E_SHOTS ?? "e2e-shots/studio-final").replace(/\/?$/, "/"); mkdirSync(OUT, { recursive: true });
const EXE = process.env.BROWSER_EXECUTABLE ?? ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/chromium"].find(existsSync);
const browser = await chromium.launch({ executablePath: EXE, headless: true });
let first = true;
for (const [w, h] of [[Number(process.env.E2E_W ?? 1440), Number(process.env.E2E_H ?? 900)]]) {   // one window size per run: each run needs an empty workspace
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await ctx.addInitScript((t) => sessionStorage.setItem("ccrig.studio.token", t), TOKEN);
  const p = await ctx.newPage(), T = (i) => p.getByTestId(i);
  const st = (s) => p.waitForFunction((x) => document.querySelector('[data-testid="studio-page"]')?.dataset.state === x, s, { timeout: 20000 });
  await p.goto(BASE + "data-studio", { waitUntil: "load" }); await T("run-claim-asserted").waitFor(); await p.waitForTimeout(800);
  await p.screenshot({ path: OUT + `${w}-01-idle.png` });
  if (first) { await T("run-claim-cooccurrence").click(); await st("BLOCKED"); await p.waitForTimeout(2600); await p.screenshot({ path: OUT + `${w}-02-refused-cooccurrence.png` }); }
  await T("run-claim-asserted").click(); await st("AWAITING_REVIEW"); await p.waitForTimeout(500);
  await p.screenshot({ path: OUT + `${w}-03-awaiting-review-pulses.png` }); await p.waitForTimeout(3000); await p.screenshot({ path: OUT + `${w}-04-awaiting-review.png` });
  // an active stage: replay the recorded job and catch the moment a module is running
  await T("replay-btn").click();
  for (let i = 0; i < 200; i++) { if ((await T("flow-node-VERIFY").getAttribute("data-state")) === "RUNNING") break; await p.waitForTimeout(25); }
  await p.waitForTimeout(120); await p.screenshot({ path: OUT + `${w}-05-active-stage-replay.png` });
  await p.getByRole("button", { name: "4×" }).click();
  await p.waitForFunction(() => document.querySelector('[data-testid="studio-page"]')?.dataset.playing === "false", null, { timeout: 40000 });
  await T("flow-node-LLM").click({ position: { x: 20, y: 20 } }); await T("llm-detail").waitFor(); await p.waitForTimeout(500);
  await p.screenshot({ path: OUT + `${w}-06-llm-skipped-drawer.png` });
  await T("drawer-tab-review").click(); await T("review-name").fill("alice"); await T("review-reason").fill("Checked the quoted sentence against the stored release."); await T("review-ack").check(); await p.waitForTimeout(300);
  await p.screenshot({ path: OUT + `${w}-07-review-drawer.png` });
  await T("review-approve").click(); await st("APPROVED"); await T("drawer-close").click(); await p.waitForTimeout(3200);
  await p.screenshot({ path: OUT + `${w}-08-approved.png` });
  await T("open-output").click(); await T("overlay-edge").waitFor(); await p.waitForTimeout(400); await p.screenshot({ path: OUT + `${w}-09-output-drawer.png` });
  await T("rollback-name").fill("bob"); await T("rollback-reason").fill("Demonstrating rollback."); await T("rollback-btn").click(); await st("ROLLED_BACK"); await T("drawer-close").click(); await p.waitForTimeout(3000);
  await p.screenshot({ path: OUT + `${w}-10-rolled-back.png` });
  first = false; await ctx.close();
}
await browser.close();
console.log("saved to", OUT);
