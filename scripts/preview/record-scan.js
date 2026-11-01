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
  fs.mkdirSync(TMP, { recursive: true });
  const browser = await chromium.launch();
  // The GIF is drawn the same way the card's "Share > Animation" video is (netorbitPaintFrame), with the
  // sample names shown. Every frame is painted at an exact time, so nothing is dropped or sped up the
  // way a screen recording of a busy page is.
  const FPS = 15;
  const ctx = await browser.newContext({ viewport: { width: 1008, height: 1100 } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => { console.error("PAGE ERROR", e.message); process.exitCode = 1; });
  await page.goto("http://localhost:8766/scripts/preview/index.html?s=full");
  await page.waitForFunction(() => window.ready);
  await page.waitForTimeout(1200); // icons settle
  const n = await page.evaluate((fps) => {
    const card = document.querySelector("netorbit-card");
    const smodel = shareModel(card._model(), { hideNames: false });
    const D = netorbitDraw(smodel, { show_ip: false }, {});
    const total = D.scene.nodes.filter((x) => !x.hub && x.k !== "internet").length;
    const PRE = NO_REVEAL.turn;
    const HOLD = 1.6;
    const phases = ["ping", "arp", "names", "snmp", "layout"];
    const frac = (t) => noClamp((t + PRE) / PRE);
    const o = {
      title: card._shareTitle(false), counts: noShareCounts(smodel),
      pct: (t) => frac(t) * 100,
      found: (t) => total * noEase(frac(t)),
      phase: (t) => NO_SCAN_PHASE[phases[Math.min(phases.length - 1, Math.floor(frac(t) * phases.length))]],
    };
    const canvas = document.createElement("canvas");
    canvas.width = 960;
    canvas.height = Math.round((960 * NO_SHARE.h) / NO_SHARE.w / 2) * 2;
    const c2 = canvas.getContext("2d");
    const dur = PRE + NO_REVEAL.end + HOLD;
    window.__frames = [];
    const count = Math.round(dur * fps);
    for (let i = 0; i < count; i++) {
      netorbitPaintFrame(c2, D.scene, i / fps - PRE, o);
      window.__frames.push(canvas.toDataURL("image/png"));
    }
    return count;
  }, FPS);
  for (let i = 0; i < n; i++) {
    const url = await page.evaluate((k) => window.__frames[k], i);
    fs.writeFileSync(path.join(TMP, `f${String(i).padStart(4, "0")}.png`), Buffer.from(url.split(",")[1], "base64"));
  }
  await ctx.close();
  const vf = "scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=256:stats_mode=full[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle";
  execFileSync("ffmpeg", ["-v", "error", "-y", "-framerate", String(FPS), "-i", path.join(TMP, "f%04d.png"), "-vf", vf, "-loop", "0", path.join(OUT, "scan.gif")]);
  console.log("docs/scan.gif", Math.round(fs.statSync(path.join(OUT, "scan.gif")).size / 1024), "KB,", n, "frames");

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
  if (!process.env.KEEP_FRAMES) fs.rmSync(TMP, { recursive: true, force: true });
})().catch((e) => { console.error(e); process.exit(1); });
