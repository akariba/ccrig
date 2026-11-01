// Screenshots of the Impact Map in both source modes: node e2e/discovery-shots.mjs <tag>   (needs a backend with the Studio enabled and a discovery run)
import { chromium } from "playwright-core";
import { existsSync } from "node:fs";
const tag = process.argv[2] ?? "disc", base = process.env.E2E_BASE ?? "http://localhost:5173/event-impact-map";
const exe = ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"].find(existsSync);
const b = await chromium.launch({ executablePath: exe, headless: true });
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
const ready = () => p.waitForFunction(() => ["ready", "empty"].includes(document.querySelector('[data-testid="impact-map"]')?.dataset.phase), null, { timeout: 60000 });
await p.goto(`${base}?source=discovered`, { waitUntil: "load" }); await ready(); await p.waitForTimeout(1500);
await p.screenshot({ path: `e2e-shots/visual/${tag}-overview.png` });
const meta = p.locator('[data-testid="event-item"]', { hasText: "Meta" });
if (await meta.count()) { await meta.first().click(); await p.waitForTimeout(1800); await p.screenshot({ path: `e2e-shots/visual/${tag}-meta-selected.png` }); }
const oracle = p.locator('[data-testid="event-item"]', { hasText: "Oracle" });
if (await oracle.count()) { await oracle.first().click(); await p.waitForTimeout(1500); await p.getByTestId("event-panel").screenshot({ path: `e2e-shots/visual/${tag}-oracle-panel.png` }); }
await p.getByTestId("compare-button").scrollIntoViewIfNeeded(); await p.getByTestId("compare-button").click(); await p.getByTestId("compare-panel").waitFor();
await p.getByTestId("compare-card").screenshot({ path: `e2e-shots/visual/${tag}-compare.png` });
await b.close();
