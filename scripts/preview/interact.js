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

  await browser.close();
  console.log("ALL INTERACTIONS PASSED");
})().catch((e) => { console.error(e); process.exit(1); });
