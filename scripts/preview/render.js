// Render preview screenshots: node scripts/preview/render.js  (needs playwright and a static server on :8766)
const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1008, height: 1100 }, deviceScaleFactor: 2 });
  for (const s of ["full", "mesh", "flat"]) {
    await page.goto(`http://localhost:8766/scripts/preview/index.html?s=${s}`);
    await page.waitForFunction(() => window.ready);
    await page.waitForTimeout(1500);
    await (await page.$("netorbit-card")).screenshot({ path: `docs/${s}.png` });
  }
  await browser.close();
})();
