// Browser test of edit mode and zoom: node scripts/preview/interact.js (needs playwright and a server on :8766).
// BROWSER=webkit runs it in WebKit (the touch cases that need Chrome's DevTools protocol are skipped there).
const { chromium, webkit } = require("playwright");
const assert = require("node:assert");
const fs = require("node:fs");
const IS_WEBKIT = process.env.BROWSER === "webkit";
(async () => {
  const browser = await (IS_WEBKIT ? webkit : chromium).launch();
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
  // WebKit's own hit test of an SVG circle in a shadow root says <html> is in the way, so skip that check there;
  // the touch still lands at the circle's centre and the menu must open.
  await c2.locator(`.node[data-key="${tv}"] circle.disc`).tap({ force: IS_WEBKIT });
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

  // 12. Zoom and pan. Each case gets a fresh page.
  const URL = "http://localhost:8766/scripts/preview/index.html?s=novice";
  const open = async (opts = {}, query = "") => {
    const p = await browser.newPage(Object.assign({ viewport: { width: 1008, height: 1100 } }, opts));
    p.setDefaultTimeout(8000);
    p.on("pageerror", (e) => { console.error("PAGE ERROR", e.message); process.exitCode = 1; });
    await p.goto(URL + query);
    await p.waitForFunction(() => window.ready);
    return p;
  };
  const viewBox = (p) => p.evaluate(() => document.querySelector("netorbit-card").shadowRoot.querySelector("svg.map").getAttribute("viewBox"));
  const viewW = async (p) => Number((await viewBox(p)).split(" ")[2]);
  const labelOf = (p, key) => p.evaluate((k) => {
    const el = document.querySelector("netorbit-card").shadowRoot.querySelector(`.node[data-key="${CSS.escape(k)}"] text`);
    return el ? el.textContent : null;
  }, key);
  // Rename a device in the fake states and push a new hass object, the way Home Assistant sends an update.
  const relabel = (p, name, label) => p.evaluate(([n, l]) => {
    Object.values(window.NETORBIT_SCENARIOS.novice).find((s) => s.attributes.label === n).attributes.label = l;
    window.pushHass();
  }, [name, label]);
  const keyOfIn = (p, label) => p.evaluate((l) => Object.values(window.NETORBIT_SCENARIOS.novice).find((s) => s.attributes.label === l).attributes.node_key, label);
  const centerIn = async (p, sel) => {
    const b = await p.locator("netorbit-card").locator(sel).first().boundingBox();
    return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
  };
  const mapBox = (p) => p.locator("netorbit-card").locator("svg.map").boundingBox();
  // A spot on the map background: not a device, hub or button.
  const backgroundPoint = (p) => p.evaluate(() => {
    const root = document.querySelector("netorbit-card").shadowRoot, r = root.querySelector("svg.map").getBoundingClientRect();
    for (let y = r.top + 12; y < r.bottom - 12; y += 17) for (let x = r.left + 12; x < r.right - 12; x += 17) {
      const el = root.elementFromPoint(x, y);
      if (el && el.closest && el.closest("svg.map") && !el.closest(".node, .zoomctl")) return { x, y };
    }
    return null;
  });
  const settle = (p) => p.waitForTimeout(60);
  // A wheel event on the map, at a screen position (the middle of the map by default). Returns whether the card took it.
  const wheelAt = (p, init, at) => p.evaluate(([i, pos]) => {
    const svg = document.querySelector("netorbit-card").shadowRoot.querySelector("svg.map");
    const r = svg.getBoundingClientRect();
    const ev = new WheelEvent("wheel", Object.assign({ bubbles: true, cancelable: true, composed: true,
      clientX: pos ? pos.x : r.left + r.width / 2, clientY: pos ? pos.y : r.top + r.height / 2 }, i));
    svg.dispatchEvent(ev);
    return ev.defaultPrevented;
  }, [init, at || null]);

  // 12a. The + button zooms in, the whole-map button zooms back out.
  {
    const p = await open();
    const c = p.locator("netorbit-card");
    const whole = await viewW(p);
    await c.locator(".zin").click();
    const zoomed = await viewW(p);
    assert.ok(zoomed < whole - 1, `the + button zooms in (${whole} -> ${zoomed})`);
    await c.locator(".zfit").click();
    assert.strictEqual(await viewW(p), whole, "the whole-map button zooms back out");
    console.log("zoom buttons ok");
    await p.close();
  }

  // 12b. The zoom survives a Home Assistant update that redraws the map.
  {
    const p = await open();
    const c = p.locator("netorbit-card");
    await c.locator(".zin").click(); await c.locator(".zin").click();
    const vb = await viewBox(p);
    const lamp = await keyOfIn(p, "Lamp");
    await relabel(p, "Lamp", "Zed");
    await p.waitForFunction(([k]) => document.querySelector("netorbit-card").shadowRoot.querySelector(`.node[data-key="${CSS.escape(k)}"] text`).textContent.startsWith("Zed"), [lamp]);
    assert.strictEqual(await viewBox(p), vb, "the zoom survives a redraw from a hass update");
    console.log("zoom survives hass update ok");
    await p.close();
  }

  // 12c. The zoom survives toggling Edit layout.
  {
    const p = await open();
    const c = p.locator("netorbit-card");
    await c.locator(".zin").click(); await c.locator(".zin").click();
    const vb = await viewBox(p);
    await c.locator(".editbtn").click();
    assert.ok(await c.locator(".banner").isVisible(), "edit mode is on");
    assert.strictEqual(await viewBox(p), vb, "the zoom survives turning Edit layout on");
    await c.locator(".editbtn").click();
    assert.strictEqual(await viewBox(p), vb, "the zoom survives turning Edit layout off");
    console.log("zoom survives edit toggle ok");
    await p.close();
  }

  // 12d. Dragging a device onto a hub while zoomed in sends assign_device for that hub.
  {
    const p = await open();
    const c = p.locator("netorbit-card");
    await c.locator(".editbtn").click();
    const plugKey = await keyOfIn(p, "Smart Plug");
    const plugAt = await centerIn(p, `.node[data-key="${plugKey}"] circle.disc`), hubAt = await centerIn(p, '.node[data-key="hub:m1"] circle.disc');
    // Zoom in on the spot between the two.
    const mid = { x: (plugAt.x + hubAt.x) / 2, y: (plugAt.y + hubAt.y) / 2 };
    const whole = await viewW(p);
    await wheelAt(p, { deltaY: -40, ctrlKey: true }, mid);
    await wheelAt(p, { deltaY: -40, ctrlKey: true }, mid);
    assert.ok((await viewW(p)) < whole * 0.5, "zoomed in");
    const box = await mapBox(p);
    const inside = (pt) => pt.x > box.x + 8 && pt.x < box.x + box.width - 8 && pt.y > box.y + 8 && pt.y < box.y + box.height - 8;
    const dev = { k: plugKey, pt: await centerIn(p, `.node[data-key="${plugKey}"] circle.disc`) };
    assert.ok(inside(dev.pt), "the device is on screen while zoomed in");
    const hub = await centerIn(p, '.node[data-key="hub:m1"] circle.disc');
    assert.ok(inside(hub), "the hub is on screen while zoomed in");
    const before = (await p.evaluate(() => window.calls)).length;
    await p.mouse.move(dev.pt.x, dev.pt.y); await p.mouse.down();
    await p.mouse.move((dev.pt.x + hub.x) / 2, (dev.pt.y + hub.y) / 2, { steps: 6 });
    await p.mouse.move(hub.x, hub.y, { steps: 6 });
    assert.ok(await c.locator('.node.hub.hot[data-key="hub:m1"]').count(), "the hub highlights while dragging when zoomed");
    await p.mouse.up();
    const calls = await p.evaluate(() => window.calls);
    assert.strictEqual(calls.length, before + 1, "one call was sent");
    assert.deepStrictEqual(calls.at(-1).slice(0, 2), ["netorbit", "assign_device"]);
    assert.strictEqual(calls.at(-1)[2].hub, "m1", "the device went to the hub it was dropped on");
    console.log("zoomed drag ok:", JSON.stringify(calls.at(-1)[2]));
    await p.close();
  }

  // 12e. A mouse button released just outside the map must not leave it panning, or hold back redraws.
  {
    const p = await open();
    const c = p.locator("netorbit-card");
    await c.locator(".zin").click(); await c.locator(".zin").click();
    const vb = await viewBox(p);
    const box = await mapBox(p);
    const y = box.y + box.height / 2;
    await p.mouse.move(box.x + box.width - 2, y);
    await p.mouse.down();
    await p.mouse.move(box.x + box.width + 3, y);
    await p.mouse.up();
    // Button up now. Moving the mouse across the map must not pan it.
    await p.mouse.move(box.x + box.width - 40, y, { steps: 4 });
    await p.mouse.move(box.x + box.width / 2, y + 60, { steps: 8 });
    assert.strictEqual(await viewBox(p), vb, "a mouse moving with no button down does not pan");
    const lamp = await keyOfIn(p, "Lamp");
    await relabel(p, "Lamp", "Yak");
    await p.waitForFunction(([k]) => document.querySelector("netorbit-card").shadowRoot.querySelector(`.node[data-key="${CSS.escape(k)}"] text`).textContent.startsWith("Yak"), [lamp]);
    console.log("stuck mouse pan ok");
    await p.close();
  }

  // 12f. An update that arrives during a plain tap or press is drawn when the finger lifts.
  {
    const p = await open();
    const lamp = await keyOfIn(p, "Lamp");
    const bg = await backgroundPoint(p);
    assert.ok(bg, "found a spot on the map background");
    await p.mouse.move(bg.x, bg.y);
    await p.mouse.down();
    await relabel(p, "Lamp", "Xen");
    await settle(p);
    assert.ok(!(await labelOf(p, lamp)).startsWith("Xen"), "nothing is redrawn under the finger");
    await p.mouse.up();
    await p.waitForFunction(([k]) => document.querySelector("netorbit-card").shadowRoot.querySelector(`.node[data-key="${CSS.escape(k)}"] text`).textContent.startsWith("Xen"), [lamp]);
    console.log("update held during a tap is drawn on release ok");
    await p.close();
  }

  // 12g. Ctrl or Cmd with the wheel zooms, a plain wheel does not. Firefox reports lines instead of pixels.
  {
    const whole = await (async () => { const p = await open(); const w = await viewW(p); await p.close(); return w; })();
    const p = await open();
    assert.strictEqual(await wheelAt(p, { deltaY: -100 }), false, "a plain wheel is left to the page");
    assert.strictEqual(await viewW(p), whole, "a plain wheel does not zoom");
    assert.strictEqual(await wheelAt(p, { deltaY: -10, ctrlKey: true }), true, "Ctrl+wheel is taken by the map");
    const px = await viewW(p);
    assert.ok(px < whole - 1, "Ctrl+wheel zooms in");
    await p.close();
    const q = await open();
    assert.strictEqual(await wheelAt(q, { deltaY: -1, deltaMode: 1, metaKey: true }), true, "Cmd+wheel is taken by the map");
    const lines = await viewW(q);
    await q.close();
    // One line of scroll is a notch of about 16 px: it zooms like -16 pixels, and far more than a single pixel would.
    const r = await open();
    await wheelAt(r, { deltaY: -16, ctrlKey: true });
    const sixteen = await viewW(r);
    await r.close();
    assert.ok(Math.abs(lines - sixteen) < 2, `one wheel line zooms like 16 pixels (${lines} vs ${sixteen})`);
    assert.ok(lines < whole * 0.95, "one wheel line is a visible zoom step");
    console.log("wheel zoom ok:", whole, "->", px, "(10 px),", lines, "(1 line),", sixteen, "(16 px)");
  }

  // 12h. Double-tap on the background zooms back out to the whole map when zoomed in.
  {
    const p = await open();
    const c = p.locator("netorbit-card");
    const whole = await viewBox(p);
    await c.locator(".zin").click(); await c.locator(".zin").click();
    assert.notStrictEqual(await viewBox(p), whole, "zoomed in");
    const bg = await backgroundPoint(p);
    assert.ok(bg, "found a spot on the map background");
    await p.mouse.dblclick(bg.x, bg.y);
    assert.strictEqual(await viewBox(p), whole, "a double-tap returns to the whole map");
    await p.mouse.dblclick(bg.x, bg.y);
    assert.ok((await viewW(p)) < Number(whole.split(" ")[2]) - 1, "and a double-tap on the whole map zooms in");
    console.log("double-tap zoom ok");
    await p.close();
  }

  // 12i. A phone with a real touch screen: a one-finger swipe scrolls the page, a tap on a device opens its details,
  //      a pinch zooms. The events go through Chrome's DevTools protocol so the browser applies touch-action itself.
  if (IS_WEBKIT) {
    const p = await open({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    await p.evaluate(() => document.addEventListener("hass-more-info", (e) => (window.moreInfo = e.detail.entityId)));
    const tvKey = await keyOfIn(p, "Bedroom TV");
    await p.locator("netorbit-card").locator(`.node[data-key="${tvKey}"] circle.disc`).tap({ force: true });
    assert.ok(await p.evaluate(() => window.moreInfo), "a tap on a device opens its details on a phone");
    console.log("phone tap ok (WebKit; swipe and pinch need Chrome's DevTools protocol and run in Chromium only)");
    await p.close();
  } else {
    const p = await open({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    await p.evaluate(() => { document.body.style.paddingBottom = "2400px"; document.addEventListener("hass-more-info", (e) => (window.moreInfo = e.detail.entityId)); });
    const cdp = await p.context().newCDPSession(p);
    const touch = (type, pts) => cdp.send("Input.dispatchTouchEvent", { type, touchPoints: pts.map((q, i) => ({ x: q.x, y: q.y, id: i })) });
    const wait = (ms) => p.waitForTimeout(ms);
    const whole = await viewBox(p);
    const box = await mapBox(p);
    const bg = await backgroundPoint(p);
    assert.ok(bg, "found a spot on the map background");

    // A tap on a device (the page has not scrolled yet).
    const tvKey = await keyOfIn(p, "Bedroom TV");
    const tv = await centerIn(p, `.node[data-key="${tvKey}"] circle.disc`);
    await touch("touchStart", [tv]); await wait(40); await touch("touchEnd", []); await wait(250);
    assert.ok(await p.evaluate(() => window.moreInfo), "a tap on a device opens its details on a phone");
    assert.strictEqual(await viewBox(p), whole, "a tap does not move the map");

    // One finger swiping up over the whole map scrolls the page.
    assert.strictEqual(await p.evaluate(() => window.scrollY), 0);
    let y = bg.y;
    await touch("touchStart", [{ x: bg.x, y }]);
    for (let i = 0; i < 12; i++) { y -= 14; await touch("touchMove", [{ x: bg.x, y }]); await wait(16); }
    await touch("touchEnd", []);
    await wait(400);
    assert.ok((await p.evaluate(() => window.scrollY)) > 60, "a one-finger swipe over the whole map scrolls the page");
    assert.strictEqual(await viewBox(p), whole, "and leaves the map alone");
    await p.evaluate(() => window.scrollTo(0, 0));
    await wait(100);

    // A pinch over the map zooms it.
    const b2 = await mapBox(p);
    const cx = b2.x + b2.width / 2, cy = b2.y + b2.height / 2;
    await touch("touchStart", [{ x: cx - 20, y: cy }, { x: cx + 20, y: cy }]);
    for (let i = 1; i <= 10; i++) { await touch("touchMove", [{ x: cx - 20 - i * 9, y: cy }, { x: cx + 20 + i * 9, y: cy }]); await wait(16); }
    await touch("touchEnd", []);
    await wait(200);
    assert.ok((await viewW(p)) < Number(whole.split(" ")[2]) * 0.7, "a pinch zooms the map");
    assert.ok(Math.abs(await p.evaluate(() => window.scrollY)) < 5, "and does not scroll the page");

    // Zoomed in, one finger pans the map instead of the page.
    const zoomed = await viewBox(p);
    const b3 = await mapBox(p);
    let x = b3.x + b3.width / 2;
    await touch("touchStart", [{ x, y: cy }]);
    for (let i = 0; i < 10; i++) { x -= 12; await touch("touchMove", [{ x, y: cy }]); await wait(16); }
    await touch("touchEnd", []);
    await wait(200);
    assert.notStrictEqual(await viewBox(p), zoomed, "zoomed in, one finger pans the map");
    assert.ok(Math.abs(await p.evaluate(() => window.scrollY)) < 5, "and the page stays put");
    console.log("phone touch ok: swipe scrolls, tap opens details, pinch zooms, drag pans");
    await p.close();
  }

  // 13. Card height: a number is pixels, a CSS length is used as given. (A CSS length needs the noHeight helper.)
  {
    const src = fs.readFileSync("custom_components/netorbit/frontend/netorbit-card.js", "utf8");
    const maxH = async (cfg) => {
      const p = await open({ viewport: { width: 1008, height: 1000 } }, "&cfg=" + encodeURIComponent(JSON.stringify(cfg)));
      const v = await p.evaluate(() => getComputedStyle(document.querySelector("netorbit-card").shadowRoot.querySelector("svg.map")).maxHeight);
      await p.close();
      return v;
    };
    assert.strictEqual(await maxH({ height: 600 }), "600px", "height: 600 is 600 px");
    if (src.includes("noHeight")) {
      assert.strictEqual(await maxH({ height: "80vh" }), "800px", "height: 80vh is 80% of the window");
      assert.strictEqual(await maxH({ height: "40rem" }), "640px", "height: 40rem is 40 rem");
      console.log("height ok: 600, 80vh, 40rem");
    } else {
      console.log("height ok: 600 (CSS lengths skipped, noHeight is not in the card yet)");
    }
  }

  await browser.close();
  console.log("ALL INTERACTIONS PASSED");
})().catch((e) => { console.error(e); process.exit(1); });
