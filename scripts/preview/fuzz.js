// Draw every dumped state and check the result: node scripts/preview/fuzz.js
const { chromium } = require("playwright");
const fs = require("fs");
(async () => {
  const files = fs.readdirSync("scripts/preview/_simstates").filter((f) => f.endsWith(".json"));
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 960, height: 1100 } });
  page.setDefaultTimeout(8000);
  const problems = [];
  let errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let worst = { overlap: 0 };
  for (const f of files) {
    errors = [];
    await page.goto(`http://localhost:8766/scripts/preview/fuzz.html?f=${encodeURIComponent(f)}`);
    await page.waitForFunction(() => window.ready);
    const r = await page.evaluate(() => {
      const root = document.querySelector("netorbit-card").shadowRoot;
      const svg = root.querySelector("svg");
      if (!svg) return { empty: root.textContent.slice(0, 80) };
      const html = svg.outerHTML;
      const nan = /NaN|Infinity|undefined/.test(html);
      const hubs = [...root.querySelectorAll(".node.hub circle.disc")].map((c) => ({ x: +c.getAttribute("cx"), y: +c.getAttribute("cy"), r: +c.getAttribute("r") }));
      const devs = [...root.querySelectorAll(".node.dev circle.disc")].map((c) => ({ x: +c.getAttribute("cx"), y: +c.getAttribute("cy") }));
      let overlap = 0;
      for (let i = 0; i < hubs.length; i++) for (let j = i + 1; j < hubs.length; j++) {
        const d = Math.hypot(hubs[i].x - hubs[j].x, hubs[i].y - hubs[j].y);
        if (d < hubs[i].r + hubs[j].r - 4) overlap++;
      }
      let devClash = 0;
      for (let i = 0; i < devs.length; i++) for (let j = i + 1; j < devs.length; j++) if (Math.hypot(devs[i].x - devs[j].x, devs[i].y - devs[j].y) < 12) devClash++;
      const states = Object.values(window.__s || {});
      return { nan, hubs: hubs.length, devs: devs.length, overlap, devClash };
    });
    if (errors.length) problems.push(`${f}: page error ${errors[0]}`);
    if (r.empty) problems.push(`${f}: nothing drawn (${r.empty})`);
    if (r.nan) problems.push(`${f}: NaN/undefined in drawing`);
    if (r.overlap) problems.push(`${f}: ${r.overlap} overlapping hubs (${r.hubs} hubs, ${r.devs} devices)`);
    if (r.devClash) problems.push(`${f}: ${r.devClash} device pairs drawn on top of each other (${r.devs} devices)`);
    if ((r.overlap || 0) > worst.overlap) worst = { f, ...r };
  }
  console.log(`drew ${files.length} networks, ${problems.length} problems`);
  [...new Set(problems)].slice(0, 30).forEach((p) => console.log("  " + p));
  fs.writeFileSync("/tmp/claude-0/-home-claude/1ddf03a3-649b-59ec-b8f5-c36ac310208a/scratchpad/fuzz_problems.txt", problems.join("\n"));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
