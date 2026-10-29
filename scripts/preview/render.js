// Render preview screenshots: node scripts/preview/render.js  (needs playwright and a static server on :8766)
const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1008, height: 1100 }, deviceScaleFactor: 2 });
  for (const s of ["full", "mesh", "flat", "novice"]) {
    await page.goto(`http://localhost:8766/scripts/preview/index.html?s=${s}`);
    await page.waitForFunction(() => window.ready);
    await page.waitForTimeout(1500);
    await (await page.$("netorbit-card")).screenshot({ path: `docs/${s}.png` });
  }
  await browser.close();
})();

// Edit mode with a device menu open.
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1008, height: 1150 }, deviceScaleFactor: 2 });
  await page.goto("http://localhost:8766/scripts/preview/index.html?s=novice");
  await page.waitForFunction(() => window.ready);
  const card = page.locator("netorbit-card");
  await card.locator(".editbtn").click();
  const key = await page.evaluate(() => Object.values(window.NETORBIT_SCENARIOS.novice).find((s) => s.attributes.label === "Bedroom TV").attributes.node_key);
  const b = await card.locator(`.node[data-key="${key}"] circle.disc`).boundingBox();
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
  await page.waitForTimeout(800);
  await card.screenshot({ path: "docs/edit.png" });
  await browser.close();
})();
