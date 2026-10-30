// Record the how-to GIFs in docs/: node scripts/preview/record.js
// Needs playwright, ffmpeg, and a server for the repo root on :8766. Uses sample data only.
const { chromium } = require("playwright");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const OUT = path.join(__dirname, "..", "..", "docs");
const TMP = path.join(__dirname, "_video");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// A visible cursor, since headless video has none. Grows a ring on click.
const CURSOR = `
  (() => {
    const c = document.createElement("div");
    c.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l16 9-7 2-3 7z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: "fixed", left: "0", top: "0", zIndex: 99999, pointerEvents: "none", transform: "translate(-4px,-2px)", transition: "none" });
    const ring = document.createElement("div");
    Object.assign(ring.style, { position: "fixed", width: "34px", height: "34px", border: "3px solid #f472b6", borderRadius: "50%", zIndex: 99998, pointerEvents: "none", opacity: "0", transform: "translate(-50%,-50%) scale(.4)", transition: "opacity .35s, transform .35s" });
    document.addEventListener("DOMContentLoaded", () => { document.body.appendChild(ring); document.body.appendChild(c); });
    if (document.body) { document.body.appendChild(ring); document.body.appendChild(c); }
    const move = (e) => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; ring.style.left = e.clientX + "px"; ring.style.top = e.clientY + "px"; };
    addEventListener("pointermove", move, true);
    addEventListener("pointerdown", (e) => { move(e); ring.style.transition = "none"; ring.style.opacity = "1"; ring.style.transform = "translate(-50%,-50%) scale(.4)";
      requestAnimationFrame(() => { ring.style.transition = "opacity .5s, transform .5s"; ring.style.opacity = "0"; ring.style.transform = "translate(-50%,-50%) scale(1.3)"; }); }, true);
  })();`;

async function record(name, viewport, steps) {
  fs.rmSync(TMP, { recursive: true, force: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport, recordVideo: { dir: TMP, size: viewport }, deviceScaleFactor: 1, reducedMotion: "reduce" });
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  page.setDefaultTimeout(8000);
  page.on("pageerror", (e) => { console.error("PAGE ERROR", e.message); process.exitCode = 1; });
  await page.goto("http://localhost:8766/scripts/preview/index.html?s=novice&live=1");
  await page.waitForFunction(() => window.ready);
  await sleep(800);
  const card = page.locator("netorbit-card");
  const at = async (sel) => { const b = await card.locator(sel).first().boundingBox(); return { x: b.x + b.width / 2, y: b.y + b.height / 2 }; };
  let cur = { x: viewport.width / 2, y: viewport.height - 40 };
  await page.mouse.move(cur.x, cur.y);
  const glide = async (to, ms = 700) => { const n = Math.max(8, Math.round(ms / 25)); await page.mouse.move(to.x, to.y, { steps: n }); cur = to; };
  const click = async (sel, opts = {}) => { await glide(await at(sel), opts.ms); await sleep(200); await page.mouse.down(); await sleep(90); await page.mouse.up(); await sleep(opts.after ?? 700); };
  const drag = async (fromSel, toSel) => {
    const a = await at(fromSel); const b = await at(toSel);
    await glide(a); await sleep(250); await page.mouse.down(); await sleep(150);
    await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2 - 30, { steps: 25 });
    await page.mouse.move(b.x + 3, b.y + 2, { steps: 25 }); await sleep(450);
    await page.mouse.up(); cur = b; await sleep(1100);
  };
  const keyOf = (label) => page.evaluate((l) => Object.values(window.NETORBIT_SCENARIOS.novice).find((s) => s.attributes.label === l).attributes.node_key, label);
  const disc = (key) => `.node[data-key="${key}"] circle.disc`;
  await steps({ page, card, click, drag, glide, at, keyOf, disc, sleep });
  await sleep(1200);
  const video = page.video();
  await ctx.close();
  await browser.close();
  const webm = await video.path();
  const gif = path.join(OUT, name);
  const scale = Math.min(680, viewport.width);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-ss", "1.2", "-i", webm, "-vf",
    `fps=10,scale=${scale}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle`, gif]);
  console.log(name, Math.round(fs.statSync(gif).size / 1024) + " KB");
}

(async () => {
  const desk = { width: 760, height: 830 };

  // 1. Drag devices onto the hub they really connect through.
  await record("howto-drag.gif", desk, async ({ card, click, drag, keyOf, disc }) => {
    await click(".editbtn", { after: 1000 });
    await drag(disc(await keyOf("Smart Plug")), disc("hub:m1"));
    await drag(disc(await keyOf("Bedroom TV")), disc("hub:m1"));
    await click(".editbtn", { after: 900 });
  });

  // 2. Confirm a possible hub, then put a device under it.
  await record("howto-confirm-hub.gif", desk, async ({ page, card, click, drag, keyOf, disc, sleep }) => {
    const sug = await page.evaluate(() => "sug:" + window.NETORBIT_SCENARIOS.novice["sensor.netorbit_devices_online"].attributes.suggested_hubs[0].key);
    await click(`.node[data-key="${sug}"] circle.disc`, { after: 1400 });
    await click(".pop .yes", { after: 1500 });
    await click(".editbtn", { after: 1000 });
    await drag(disc(await keyOf("Laptop")), disc("hub:mesh_node_3"));
    await click(".editbtn", { after: 900 });
  });

  // 3. On a phone: tap a device, pick its hub from the menu.
  await record("howto-phone-move.gif", { width: 430, height: 860 }, async ({ page, card, click, keyOf, disc, sleep }) => {
    await click(".editbtn", { after: 1000 });
    await click(disc(await keyOf("Front Cam")), { after: 1200 });
    const sel = card.locator(".pop select.hub");
    await sel.selectOption("m1");
    await sleep(900);
    await click(".pop .move", { after: 1500 });
    await click(".editbtn", { after: 900 });
  });
  fs.rmSync(TMP, { recursive: true, force: true });
})().catch((e) => { console.error(e); process.exit(1); });
