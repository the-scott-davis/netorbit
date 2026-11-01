// Browser test of edit mode: node scripts/preview/interact.js (needs playwright and a server on :8766)
const { chromium } = require("playwright");
const assert = require("node:assert");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1008, height: 1100 } });
  page.setDefaultTimeout(8000);
  page.on("pageerror", (e) => { console.error("PAGE ERROR", e.message); process.exitCode = 1; });
  await page.goto("http://localhost:8766/scripts/preview/index.html?s=novice");
  await page.waitForFunction(() => window.ready);
  const card = page.locator("netorbit-card");
  const center = async (sel) => {
    const b = await card.locator(sel).first().boundingBox();
    return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
  };
  const discOf = (key) => `.node[data-key="${key}"] circle.disc`;
  const keyOf = (label) => page.evaluate((l) => {
    const st = Object.values(window.NETORBIT_SCENARIOS.novice).find((s) => s.attributes.label === l);
    return st.attributes.node_key;
  }, label);

  // 1. Turn on edit mode.
  await card.locator(".editbtn").click();
  assert.ok(await card.locator(".banner").isVisible(), "edit banner shown");

  // 2. Drag Smart Plug onto Mesh Node 2.
  const plug = await keyOf("Smart Plug");
  const from = await center(discOf(plug));
  const to = await center(discOf("hub:m1"));
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move((from.x + to.x) / 2, (from.y + to.y) / 2, { steps: 5 });
  await page.mouse.move(to.x + 4, to.y + 3, { steps: 5 });
  assert.ok(await card.locator('.node.hub.hot[data-key="hub:m1"]').count(), "hub highlights while dragging");
  await page.mouse.up();
  let calls = await page.evaluate(() => window.calls);
  assert.deepStrictEqual(calls.at(-1).slice(0, 2), ["netorbit", "assign_device"]);
  assert.strictEqual(calls.at(-1)[2].hub, "m1");
  // The device is drawn under its new hub right away, with a "saving" ring, before Home Assistant answers.
  assert.ok(await card.locator(`.node.pending[data-key="${plug}"] .pendring`).count(), "moved device shows as saving at once");
  // A device you placed by hand shows as pinned in edit mode: blue fill plus a pin badge.
  assert.ok(await card.locator(`.node.pinned[data-key="${plug}"] .pin path`).count(), "moved device shows as pinned");
  console.log("drag ok:", JSON.stringify(calls.at(-1)[2]));

  // 3. Tap a device, use Move to.
  const tv = await keyOf("Bedroom TV");
  const tvAt = await center(discOf(tv));
  await page.mouse.click(tvAt.x, tvAt.y);
  await card.locator(".pop select.hub").selectOption("m1");
  await card.locator(".pop .move").click();
  calls = await page.evaluate(() => window.calls);
  assert.strictEqual(calls.at(-1)[1], "assign_device");
  console.log("tap move ok:", JSON.stringify(calls.at(-1)[2]));

  // 4. Tap a device, make it a hub.
  await page.mouse.click(tvAt.x, tvAt.y);
  await card.locator(".pop select.type").selectOption("mesh_node");
  await card.locator(".pop .mk").click();
  calls = await page.evaluate(() => window.calls);
  assert.strictEqual(calls.at(-1)[1], "confirm_hub");
  assert.strictEqual(calls.at(-1)[2].type, "mesh_node");
  console.log("make hub ok:", JSON.stringify(calls.at(-1)[2]));

  // 5. Rename a hub.
  await card.locator('.node.hub[data-key="hub:m1"]').click();
  await card.locator(".pop input.name").fill("Upstairs Node");
  await card.locator(".pop .save").click();
  calls = await page.evaluate(() => window.calls);
  assert.deepStrictEqual(calls.at(-1).slice(1), ["update_hub", { hub: "m1", name: "Upstairs Node", config_entry_id: "preview" }]);
  console.log("rename ok");

  // 5b. Change a hub's type (a Wi-Fi extender that was added as a plain hub, say).
  await card.locator('.node.hub[data-key="hub:m1"]').click();
  await card.locator(".pop select.type").selectOption("access_point");
  await card.locator(".pop .save").click();
  calls = await page.evaluate(() => window.calls);
  assert.deepStrictEqual(calls.at(-1).slice(1), ["update_hub", { hub: "m1", type: "access_point", config_entry_id: "preview" }]);
  console.log("hub type ok");

  // 6. Leave edit mode, confirm the suggested hub.
  await card.locator(".editbtn").click();
  const sugKey = await page.evaluate(() => "sug:" + window.NETORBIT_SCENARIOS.novice["sensor.netorbit_devices_online"].attributes.suggested_hubs[0].key);
  await card.locator(`.node[data-key="${sugKey}"] circle.disc`).click({ force: true });
  await card.locator(".pop .yes").click();
  calls = await page.evaluate(() => window.calls);
  assert.strictEqual(calls.at(-1)[1], "confirm_hub");
  console.log("suggestion ok:", JSON.stringify(calls.at(-1)[2]));

  // 7. Outside edit mode, tapping a device opens Home Assistant's details.
  await page.evaluate(() => document.addEventListener("hass-more-info", (e) => (window.moreInfo = e.detail.entityId)));
  const tvNow = await center(discOf(tv)); // the edit banner is gone, so the map moved up
  await page.mouse.click(tvNow.x, tvNow.y);
  const opened = await page.evaluate(() => window.moreInfo);
  assert.ok(opened && opened.startsWith("sensor.netorbit_"), "tap opens details");
  console.log("more-info ok:", opened);

  // 8. Touch: drag with a finger on a phone sized screen.
  const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  phone.setDefaultTimeout(8000);
  await phone.goto("http://localhost:8766/scripts/preview/index.html?s=novice");
  await phone.waitForFunction(() => window.ready);
  const c2 = phone.locator("netorbit-card");
  await c2.locator(".editbtn").click();
  const b = await c2.locator(`.node[data-key="${tv}"] circle.disc`).boundingBox();
  await c2.locator(`.node[data-key="${tv}"] circle.disc`).tap();
  assert.ok(await c2.locator(".pop select.hub").isVisible(), "tap opens the menu on a phone");
  console.log("phone tap ok, popup width", (await c2.locator(".pop").boundingBox()).width, "screen 390");
  // 8b. A flick: press, one move partway, release on the hub with no move there.
  {
    const fl = await browser.newPage({ viewport: { width: 1008, height: 1100 } });
    await fl.goto("http://localhost:8766/scripts/preview/index.html?s=novice");
    await fl.waitForFunction(() => window.ready);
    const c4 = fl.locator("netorbit-card");
    await c4.locator(".editbtn").click();
    const bb = async (sel) => { const r = await c4.locator(sel).first().boundingBox(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; };
    const lamp = await fl.evaluate(() => Object.values(window.NETORBIT_SCENARIOS.novice).find((s) => s.attributes.label === "Lamp").attributes.node_key);
    const f = await bb(`.node[data-key="${lamp}"] circle.disc`), t2 = await bb('.node[data-key="hub:m1"] circle.disc');
    await fl.mouse.move(f.x, f.y); await fl.mouse.down();
    await fl.mouse.move(f.x + (t2.x - f.x) * 0.2, f.y + (t2.y - f.y) * 0.2);
    await fl.evaluate(([x, y]) => {
      const card = document.querySelector("netorbit-card");
      const el = card.shadowRoot.querySelector(".node.dev.draggable");
      // Release straight over the hub, as a fast flick or some touch screens do.
      card.shadowRoot.querySelectorAll(".node").forEach(() => {});
      const target = card._drag && card.shadowRoot.querySelector(`.node[data-key="${CSS.escape(card._drag.n.key)}"]`);
      (target || el).dispatchEvent(new PointerEvent("pointerup", { bubbles: true, clientX: x, clientY: y, pointerId: card._drag ? card._drag.id : 1 }));
    }, [t2.x, t2.y]);
    await fl.mouse.up();
    const c = await fl.evaluate(() => window.calls);
    assert.ok(c.length && c.at(-1)[1] === "assign_device" && c.at(-1)[2].hub === "m1", "flick release lands on the hub");
    console.log("flick drop ok");
    await fl.close();
  }

  // 9. Drag still lands on a narrower card (tablets, side panels).
  for (const w of [760, 600]) {
    const nar = await browser.newPage({ viewport: { width: w, height: 1000 } });
    await nar.goto("http://localhost:8766/scripts/preview/index.html?s=novice");
    await nar.waitForFunction(() => window.ready);
    const c3 = nar.locator("netorbit-card");
    await c3.locator(".editbtn").click();
    const bb = async (sel) => { const r = await c3.locator(sel).first().boundingBox(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; };
    const f = await bb(`.node[data-key="${plug}"] circle.disc`), t2 = await bb('.node[data-key="hub:m1"] circle.disc');
    await nar.mouse.move(f.x, f.y); await nar.mouse.down();
    await nar.mouse.move(t2.x, t2.y, { steps: 12 }); await nar.mouse.up();
    const c = await nar.evaluate(() => window.calls);
    assert.ok(c.length && c.at(-1)[1] === "assign_device" && c.at(-1)[2].hub === "m1", `drag works at ${w}px`);
    console.log(`narrow drag ok at ${w}px`);
    await nar.close();
  }
  // 10. Drop on a suggested hub (pink ring): asks to make it a hub, then confirms it and moves the device in one call.
  //     A drop on empty space moves nothing.
  {
    const sp = await browser.newPage({ viewport: { width: 1008, height: 1100 } });
    sp.on("pageerror", (e) => { console.error("PAGE ERROR", e.message); process.exitCode = 1; });
    await sp.goto("http://localhost:8766/scripts/preview/index.html?s=novice");
    await sp.waitForFunction(() => window.ready);
    const c5 = sp.locator("netorbit-card");
    await c5.locator(".editbtn").click();
    const bb = async (sel) => { const r = await c5.locator(sel).first().boundingBox(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; };
    const sug = await sp.evaluate(() => window.NETORBIT_SCENARIOS.novice["sensor.netorbit_devices_online"].attributes.suggested_hubs[0].key);
    const f = await bb(`.node[data-key="${plug}"] circle.disc`), t3 = await bb(`.node[data-key="sug:${sug}"] circle.disc`);
    const before = (await sp.evaluate(() => window.calls)).length;

    // Empty space: far from every hub and suggestion.
    const box = await c5.locator("svg.map").boundingBox();
    await sp.mouse.move(f.x, f.y); await sp.mouse.down();
    await sp.mouse.move(box.x + box.width - 8, box.y + 8, { steps: 10 }); await sp.mouse.up();
    assert.strictEqual((await sp.evaluate(() => window.calls)).length, before, "a drop on empty space moves nothing");

    await sp.mouse.move(f.x, f.y); await sp.mouse.down();
    await sp.mouse.move(t3.x, t3.y, { steps: 10 });
    assert.ok(await c5.locator(`.node.hot[data-key="sug:${sug}"]`).count(), "suggested hub highlights while dragging");
    await sp.mouse.up();
    assert.ok(await c5.locator(".pop .yes").isVisible(), "drop on a suggestion asks first");
    assert.strictEqual((await sp.evaluate(() => window.calls)).length, before, "nothing changes until confirmed");
    await c5.locator(".pop .yes").click();
    const c = await sp.evaluate(() => window.calls);
    const last = c.at(-1);
    assert.strictEqual(last[1], "confirm_hub");
    assert.strictEqual(last[2].device, sug);
    assert.ok(Array.isArray(last[2].assign) && last[2].assign.length === 1, "the dragged device is moved under the new hub");
    console.log("drop on suggestion ok:", JSON.stringify(last[2]));
    await sp.close();
  }

  // 11. The internet node: above the router, green when up, red with "Internet down" when not, and gone when turned off.
  for (const [q, want] of [["", "online"], ["&internet=down", "stale"], ["&internet=off", null]]) {
    const ip = await browser.newPage({ viewport: { width: 1008, height: 1100 } });
    ip.on("pageerror", (e) => { console.error("PAGE ERROR", e.message); process.exitCode = 1; });
    await ip.goto("http://localhost:8766/scripts/preview/index.html?s=novice" + q);
    await ip.waitForFunction(() => window.ready);
    const c6 = ip.locator("netorbit-card");
    const node = c6.locator('.node.inet[data-key="internet"]');
    if (!want) {
      assert.strictEqual(await node.count(), 0, "no internet node when the sensor is missing");
    } else {
      assert.ok(await c6.locator(`.node.inet.${want}`).count(), `internet node is ${want}`);
      const ib = await node.locator("circle.disc").boundingBox(), rb = await c6.locator('.node.hub[data-key="hub:gw"] circle.disc, .node.hub circle.disc').first().boundingBox();
      assert.ok(ib.y < rb.y, "internet sits above the router");
      const text = await c6.locator("text.ilab").textContent();
      assert.strictEqual(text, want === "stale" ? "Internet down" : "Internet");
      await node.locator("circle.disc").hover();
      assert.ok((await c6.locator(".tip").textContent()).includes(want === "stale" ? "Down" : "Up"), "tooltip says up or down");
    }
    console.log(`internet ${want || "off"} ok`);
    await ip.close();
  }

  // 12. The first scan: radar, a "Scanning N%" chip and a pill with what was found so far, instead of the
  //     status chips, legend and buttons.
  {
    const sc = await browser.newPage({ viewport: { width: 1008, height: 1100 } });
    sc.on("pageerror", (e) => { console.error("PAGE ERROR", e.message); process.exitCode = 1; });
    await sc.goto("http://localhost:8766/scripts/preview/index.html?s=firstscan");
    await sc.waitForFunction(() => window.ready);
    const c7 = sc.locator("netorbit-card");
    assert.strictEqual((await c7.locator(".scanpill .l1").textContent()).trim(), "Scanning your network... found 12 devices");
    assert.strictEqual((await c7.locator(".scanpill .l2").textContent()).trim(), "Pinging every address");
    assert.strictEqual((await c7.locator(".head .scanchip").textContent()).trim(), "Scanning 30%");
    assert.strictEqual(await c7.locator(".head .chip, .head .editbtn, .head .sharebtn").count(), 0, "status chips and buttons make way for the scan");
    assert.strictEqual(await c7.locator(".legend").evaluate((e) => getComputedStyle(e).visibility), "hidden", "legend hidden while scanning");
    assert.strictEqual(await c7.locator(".node.dev").count(), 0, "devices only arrive when the scan is done");
    assert.ok(await c7.locator(".radar .beam").evaluate((e) => getComputedStyle(e).display !== "none"), "beam sweeps");
    // The found count follows the sensor without redrawing the radar.
    await sc.evaluate(() => {
      const card = document.querySelector("netorbit-card");
      const st = window.NETORBIT_SCENARIOS.firstscan;
      card.shadowRoot.querySelector(".radar").dataset.mark = "same";
      Object.assign(st["sensor.netorbit_devices_online"].attributes, { found: 21, scan_phase: "names", scan_progress: 55 });
      card.hass = Object.assign({}, card._hass, { states: Object.assign({}, st) });
    });
    assert.strictEqual((await c7.locator(".scanpill .l1").textContent()).trim(), "Scanning your network... found 21 devices");
    assert.strictEqual((await c7.locator(".scanpill .l2").textContent()).trim(), "Asking devices their names");
    assert.strictEqual((await c7.locator(".head .scanchip").textContent()).trim(), "Scanning 55%");
    assert.strictEqual(await c7.locator(".radar").getAttribute("data-mark"), "same", "progress updates in place");
    console.log("first scan takeover ok");
    await sc.close();

    // Reduced motion: no beam, no pulses, the rings stay; words and progress still update.
    const rm = await browser.newPage({ viewport: { width: 1008, height: 1100 }, reducedMotion: "reduce" });
    await rm.goto("http://localhost:8766/scripts/preview/index.html?s=firstscan");
    await rm.waitForFunction(() => window.ready);
    const c8 = rm.locator("netorbit-card");
    assert.strictEqual(await c8.locator(".radar .beam").evaluate((e) => getComputedStyle(e).display), "none", "no beam with reduced motion");
    assert.strictEqual(await c8.locator(".radar .pr").first().evaluate((e) => getComputedStyle(e).display), "none", "no pulses with reduced motion");
    assert.strictEqual(await c8.locator(".radar .st").count(), 3, "range rings stay");
    assert.strictEqual(await c8.locator(".scanchip .rb").evaluate((e) => getComputedStyle(e).animationName), "none");
    assert.ok((await c8.locator(".scanpill .l1").textContent()).includes("found 12"));
    console.log("reduced motion ok");
    await rm.close();

    // A later scan: the normal map, plus a small chip before Edit layout.
    const rs = await browser.newPage({ viewport: { width: 1008, height: 1100 } });
    await rs.goto("http://localhost:8766/scripts/preview/index.html?s=rescan");
    await rs.waitForFunction(() => window.ready);
    const c9 = rs.locator("netorbit-card");
    assert.strictEqual((await c9.locator(".head .scanchip").textContent()).trim(), "Scanning...");
    assert.ok(await c9.locator(".head .chip").count() >= 3, "status chips stay");
    assert.ok(await c9.locator(".head .editbtn").isVisible(), "Edit layout stays");
    assert.strictEqual(await c9.locator(".scanpill, .radar").count(), 0, "no takeover on a later scan");
    assert.ok(await c9.locator(".head .scanchip + .sharebtn").count(), "chip sits before Share and Edit layout");
    console.log("rescan chip ok");
    await rs.close();

    // The first scan finishes: the map plays in, then the normal header and legend come back.
    const fin = await browser.newPage({ viewport: { width: 1008, height: 1100 } });
    fin.on("pageerror", (e) => { console.error("PAGE ERROR", e.message); process.exitCode = 1; });
    await fin.goto("http://localhost:8766/scripts/preview/index.html?s=firstscan&finish=800");
    await fin.waitForFunction(() => window.finished);
    const c10 = fin.locator("netorbit-card");
    assert.ok(await c10.locator("ha-card.revealing .radar.js").count(), "reveal plays when the first map arrives");
    assert.ok((await c10.locator(".scanpill .l1").textContent()).startsWith("Found "));
    await fin.waitForTimeout(4500);
    assert.strictEqual(await c10.locator(".scanpill, .radar, .scanchip").count(), 0, "reveal cleaned up");
    assert.ok(await c10.locator(".head .editbtn").isVisible() && await c10.locator(".legend").isVisible(), "normal header and legend are back");
    assert.ok(await c10.locator(".node.dev").count() > 20, "devices on the map");
    console.log("reveal ok");

    // Replay it from the Share popup.
    await c10.locator(".sharebtn").click();
    await c10.locator(".sharepop .replay").click();
    assert.ok(await c10.locator("ha-card.revealing .radar.js").count(), "replay plays the reveal");
    await fin.waitForTimeout(4500);
    assert.strictEqual(await c10.locator(".radar").count(), 0, "replay cleaned up");
    console.log("replay ok");

    // Replaying twice, 1.5 s apart: the older run must not cut the newer one short (it would end 2.5 s in).
    await fin.evaluate(() => document.querySelector("netorbit-card").replayScan());
    await fin.waitForTimeout(1500);
    await fin.evaluate(() => document.querySelector("netorbit-card").replayScan());
    await fin.waitForTimeout(2600);
    assert.ok(await c10.locator("ha-card.revealing .radar.js").count(), "a second replay still plays 2.6 s in");
    await fin.waitForTimeout(2000);
    assert.strictEqual(await c10.locator(".radar").count(), 0, "second replay cleaned up");
    console.log("double replay ok");
    await fin.close();
  }

  // 13. Share: an image with names hidden by default and never an address, and the scan as a video.
  {
    const sctx = await browser.newContext({ viewport: { width: 1008, height: 1100 }, acceptDownloads: true });
    const sh = await sctx.newPage();
    sh.setDefaultTimeout(8000);
    sh.on("pageerror", (e) => { console.error("PAGE ERROR", e.message); process.exitCode = 1; });
    await sh.goto("http://localhost:8766/scripts/preview/index.html?s=full");
    await sh.waitForFunction(() => window.ready);
    await sh.waitForTimeout(500);
    const c11 = sh.locator("netorbit-card");
    await c11.locator(".sharebtn").click();
    assert.ok(await c11.locator(".sharepop").isVisible(), "Share opens");
    assert.strictEqual(await c11.evaluate((e) => getComputedStyle(e).display), "block", "the card is a block element");
    assert.strictEqual(await c11.locator(".sharepop .tg").getAttribute("aria-checked"), "true", "names hidden by default");
    const shared = () => c11.locator(".sharepop .thumb").evaluate((img) => decodeURIComponent(img.src.split(",").slice(1).join(",")));
    const names = await sh.evaluate(() => Object.values(window.NETORBIT_SCENARIOS.full).map((s) => s.attributes.label).filter((l) => l && !/^(Router|Internet)$/.test(l)));
    let svg = await shared();
    assert.ok(svg.startsWith("<svg") && svg.includes("made with NetOrbit") && svg.includes("My home network"));
    assert.ok(!svg.includes("192.0.2."), "no IP addresses in the shared image");
    assert.ok(!/\b[0-9a-f]{2}([:-][0-9a-f]{2})+\b/i.test(svg), "no MAC addresses in the shared image");
    const leaked = names.filter((n) => svg.includes(">" + n + "<"));
    assert.deepStrictEqual(leaked, [], "no real names in the shared image");
    assert.ok(svg.includes(">TV 1<") && svg.includes(">Access point<"), "generic names instead");
    assert.ok(!svg.includes("New devices") && !svg.includes("esp-7c2d1a") && !svg.includes("Edit layout"), "no waiting devices, suggestions or buttons");
    const [png] = await Promise.all([sh.waitForEvent("download"), c11.locator(".sharepop .dl").click()]);
    const pngPath = await png.path();
    const buf = require("fs").readFileSync(pngPath);
    assert.strictEqual(buf.slice(1, 4).toString(), "PNG");
    const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
    assert.ok(buf.length > 50000 && buf.length < 12e6 && w >= 1000 && h >= 1000, `PNG ${w}x${h}, ${buf.length} bytes`);
    console.log(`share PNG ok: ${png.suggestedFilename()} ${w}x${h} ${buf.length} bytes`);
    await c11.locator(".sharepop .tg").click();
    svg = await shared();
    assert.ok(svg.includes(">Core Switch<") && svg.includes(">Bedroom TV<"), "names come back with the toggle off");
    assert.ok(!svg.includes("192.0.2.") && !/\b[0-9a-f]{2}([:-][0-9a-f]{2})+\b/i.test(svg), "still no addresses with names shown");
    await c11.locator(".sharepop .tg").click();
    // The system share sheet gets the PNG when there is one; closing it does nothing; a refusal falls back to a download.
    await sh.evaluate(() => {
      const card = document.querySelector("netorbit-card");
      window.__dl = 0;
      window.__shared = [];
      window.__shareErr = null;
      card._download = () => { window.__dl++; };
      Object.defineProperty(navigator, "canShare", { configurable: true, value: (d) => !!(d && d.files && d.files.length) });
      Object.defineProperty(navigator, "share", { configurable: true, value: (d) => {
        window.__shared.push(d.files[0].name + ":" + d.files[0].type);
        return window.__shareErr ? Promise.reject(Object.assign(new Error("no"), { name: window.__shareErr })) : Promise.resolve();
      } });
    });
    await c11.locator(".sharepop .dl").click();
    await sh.waitForFunction(() => window.__shared.length === 1);
    assert.deepStrictEqual(await sh.evaluate(() => window.__shared), ["netorbit-map.png:image/png"]);
    await sh.waitForTimeout(300);
    assert.strictEqual(await sh.evaluate(() => window.__dl), 0, "no download when the share sheet took it");
    await sh.evaluate(() => (window.__shareErr = "AbortError"));
    await c11.locator(".sharepop .dl").click();
    await sh.waitForFunction(() => window.__shared.length === 2);
    await sh.waitForTimeout(300);
    assert.strictEqual(await sh.evaluate(() => window.__dl), 0, "closing the share sheet does not download");
    await sh.evaluate(() => (window.__shareErr = "NotAllowedError"));
    await c11.locator(".sharepop .dl").click();
    await sh.waitForFunction(() => window.__dl === 1);
    console.log("share sheet ok");
    await sh.evaluate(() => { delete navigator.canShare; delete navigator.share; });

    // Chromium can record a canvas: the Animation option is there and gives a video.
    assert.ok(await c11.locator('.sharepop .seg button[data-m="video"]').isVisible(), "animation option offered");
    await c11.locator('.sharepop .seg button[data-m="video"]').click();
    const status = () => c11.locator(".sharepop .status").textContent();
    const allEnded = () => sh.evaluate(() => window.__streams.length > 0 && window.__streams.every((s) => s.getTracks().every((t) => t.readyState === "ended")));
    // A recorder that throws on creation: the button comes back, the error shows, the stream is released.
    await sh.evaluate(() => {
      window.__streams = [];
      const cs = HTMLCanvasElement.prototype.captureStream;
      HTMLCanvasElement.prototype.captureStream = function () { const s = cs.apply(this, arguments); window.__streams.push(s); return s; };
      window.__MR = window.MediaRecorder;
      window.MediaRecorder = class { constructor() { throw new Error("boom"); } static isTypeSupported() { return true; } };
    });
    await c11.locator(".sharepop .rec").click();
    await sh.waitForFunction(() => document.querySelector("netorbit-card").shadowRoot.querySelector(".sharepop .status").textContent.includes("boom"));
    assert.ok((await status()).startsWith("Couldn't record"), await status());
    assert.ok(await c11.locator(".sharepop .rec").isEnabled(), "Save video is enabled again after a failure");
    assert.ok(await allEnded(), "tracks stopped after a failure");
    await sh.evaluate(() => { window.MediaRecorder = window.__MR; window.__streams = []; window.__dl = 0; });
    // Closing the popup mid-recording cancels it: nothing is downloaded and the stream is released.
    await c11.locator(".sharepop .rec").click();
    await sh.waitForTimeout(700);
    await c11.locator(".sharepop .x").click();
    await sh.waitForTimeout(1500);
    assert.strictEqual(await sh.evaluate(() => window.__dl), 0, "a cancelled recording is not downloaded");
    assert.ok(await allEnded(), "tracks stopped after a cancel");
    await sh.evaluate(() => { delete document.querySelector("netorbit-card")._download; });
    await c11.locator(".sharebtn").click();
    assert.ok(await c11.locator(".sharepop .tg").isVisible(), "Share opens again after a cancel");
    await c11.locator('.sharepop .seg button[data-m="video"]').click();
    assert.ok(await c11.locator(".sharepop .rec").isEnabled(), "Save video is ready again");
    console.log("video failure and cancel ok");
    const [vid] = await Promise.all([sh.waitForEvent("download", { timeout: 30000 }), c11.locator(".sharepop .rec").click()]);
    const size = require("fs").statSync(await vid.path()).size;
    assert.ok(size > 20000, `video has ${size} bytes`);
    assert.ok(/^netorbit-scan\.(mp4|webm)$/.test(vid.suggestedFilename()), vid.suggestedFilename());
    console.log(`share video ok: ${vid.suggestedFilename()} ${size} bytes`);
    await c11.locator(".sharepop .x").click();
    assert.strictEqual(await c11.locator(".sharepop").count(), 0, "popup closes");
    await sctx.close();
  }

  await browser.close();
  console.log("ALL INTERACTIONS PASSED");
})().catch((e) => { console.error(e); process.exit(1); });
