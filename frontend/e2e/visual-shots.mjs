// Screenshots of the impact map at several viewport sizes:  node e2e/visual-shots.mjs <tag> [url]
import { chromium } from "playwright-core";
import { existsSync } from "node:fs";
const tag = process.argv[2] ?? "after", url = process.argv[3] ?? "http://localhost:5173/event-impact-map";
const exe = ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"].find(existsSync);
const b = await chromium.launch({ executablePath: exe, headless: true });
for (const [name, w, h] of [["desktop", 1500, 950], ["laptop", 1100, 800], ["tablet", 820, 1100], ["phone", 420, 900]]) {
  const p = await b.newPage({ viewport: { width: w, height: h } });
  await p.goto(url, { waitUntil: "load" });
  await p.waitForFunction(() => document.querySelector('[data-testid="impact-map"]')?.dataset.phase === "ready", null, { timeout: 60000 });
  await p.waitForTimeout(1500);
  await p.screenshot({ path: `e2e-shots/visual/${tag}-${name}.png`, fullPage: name === "phone" || name === "tablet", timeout: 60000 });
  for (const [i, label] of [[4, "seoul"], [2, "santa-clara"]]) {          // a far event and the crowded North America cluster
    await p.getByTestId("event-item").nth(i).click(); await p.waitForTimeout(1300);
    await p.getByTestId("impact-map").screenshot({ path: `e2e-shots/visual/${tag}-${name}-map-${label}.png` });
  }
  await p.close();
}
await b.close();
