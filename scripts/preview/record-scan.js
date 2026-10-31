// Record docs/scan.gif (the first scan and the map playing in) and docs/share.png (the share image):
//   node scripts/preview/record-scan.js
// Needs playwright, ffmpeg, and a server for the repo root on :8766. Uses the preview's sample data only.
const { chromium } = require("playwright");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const OUT = path.join(__dirname, "..", "..", "docs");
const TMP = path.join(__dirname, "_video");

(async () => {
  fs.rmSync(TMP, { recursive: true, force: true });
  const browser = await chromium.launch();
  const viewport = { width: 800, height: 880 };
  const ctx = await browser.newContext({ viewport, recordVideo: { dir: TMP, size: viewport }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => { console.error("PAGE ERROR", e.message); process.exitCode = 1; });
  const t0 = Date.now();
  // The scan runs for 3.5 s, then the map plays in (about 4 s).
  await page.goto("http://localhost:8766/scripts/preview/index.html?s=firstscan&finish=3500");
  await page.waitForFunction(() => window.ready);
  const start = (Date.now() - t0) / 1000 + 0.6; // icons settle
  await page.waitForFunction(() => window.finished, null, { timeout: 15000 });
  await page.waitForTimeout(5200);
  const box = await page.locator("netorbit-card").boundingBox();
  const dur = (Date.now() - t0) / 1000 - start;
  const video = page.video();
  await ctx.close();
  const src = await video.path();
  const crop = `crop=${Math.round(box.width)}:${Math.round(Math.min(box.height, viewport.height - box.y))}:${Math.round(box.x)}:${Math.round(box.y)}`;
  const vf = `${crop},fps=10,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=48:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle`;
  execFileSync("ffmpeg", ["-v", "error", "-y", "-ss", String(start), "-t", String(dur), "-i", src, "-vf", vf, "-loop", "0", path.join(OUT, "scan.gif")]);
  console.log("docs/scan.gif", Math.round(fs.statSync(path.join(OUT, "scan.gif")).size / 1024), "KB");

  // The share image exactly as the card's Download PNG makes it.
  const sctx = await browser.newContext({ viewport: { width: 1008, height: 1100 }, acceptDownloads: true });
  const sp = await sctx.newPage();
  await sp.goto("http://localhost:8766/scripts/preview/index.html?s=full");
  await sp.waitForFunction(() => window.ready);
  await sp.waitForTimeout(1200);
  await sp.locator("netorbit-card .sharebtn").click();
  const [dl] = await Promise.all([sp.waitForEvent("download"), sp.locator("netorbit-card .sharepop .dl").click()]);
  const png = path.join(TMP, "share-full.png");
  await dl.saveAs(png);
  execFileSync("ffmpeg", ["-v", "error", "-y", "-i", png, "-vf", "scale=900:-1:flags=lanczos", path.join(OUT, "share.png")]);
  console.log("docs/share.png", Math.round(fs.statSync(path.join(OUT, "share.png")).size / 1024), "KB");
  await browser.close();
  fs.rmSync(TMP, { recursive: true, force: true });
})().catch((e) => { console.error(e); process.exit(1); });
