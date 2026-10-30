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
  await browser.close();
  console.log("ALL INTERACTIONS PASSED");
})().catch((e) => { console.error(e); process.exit(1); });
