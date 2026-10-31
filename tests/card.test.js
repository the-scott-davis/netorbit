// Layout tests for the card. Run with: node --test tests/card.test.js
const test = require("node:test");
const assert = require("node:assert");
// Minimal browser stand-ins so the card file can load under Node.
globalThis.HTMLElement = class {};
globalThis.customElements = { get: () => undefined, define: () => {} };
globalThis.window = globalThis;
console.info = () => {};
const { netorbitLayout } = require("../custom_components/netorbit/frontend/netorbit-card.js");

function model(hubDefs, devCounts) {
  const hubs = {};
  hubDefs.forEach(([key, parent]) => (hubs[key] = { key, parent, label: key }));
  const devices = [];
  Object.entries(devCounts).forEach(([hub, n]) => {
    for (let i = 0; i < n; i++) devices.push({ key: `${hub}-d${i}`, link: hub, label: `${hub} ${i}` });
  });
  return { hubs, devices, root: hubDefs[0][0] };
}

function dist(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

test("every device and hub gets a position", () => {
  const m = model([["r", null], ["sw", "r"], ["ap1", "sw"], ["ap2", "sw"], ["mesh", "r"]], { r: 2, sw: 3, ap1: 10, ap2: 7, mesh: 4 });
  const L = netorbitLayout(m);
  for (const d of m.devices) assert.ok(L.pos[d.key], d.key);
  for (const k of Object.keys(m.hubs)) assert.ok(L.pos[k], k);
});

test("devices do not overlap", () => {
  const m = model([["r", null], ["a", "r"], ["b", "r"]], { r: 5, a: 30, b: 25 });
  const L = netorbitLayout(m);
  const pts = m.devices.map((d) => L.pos[d.key]);
  for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) assert.ok(dist(pts[i], pts[j]) > 30);
});

test("deeper hubs sit further out than their parents", () => {
  const m = model([["r", null], ["sw", "r"], ["ap", "sw"], ["rep", "ap"]], { rep: 3 });
  const L = netorbitLayout(m);
  const c = L.pos.r;
  assert.ok(dist(c, L.pos.ap) > dist(c, L.pos.sw));
  assert.ok(dist(c, L.pos.rep) > dist(c, L.pos.ap));
  assert.ok(dist(c, L.pos.rep) < 370);
});

test("flat network with only a router", () => {
  const m = model([["r", null]], { r: 12 });
  const L = netorbitLayout(m);
  assert.strictEqual(Object.keys(L.pos).length, 13);
});

test("unknown parent and cycles fall back to the root", () => {
  const m = model([["r", null], ["x", "missing"], ["y", "z"], ["z", "y"]], { x: 1, y: 1, z: 1 });
  m.devices.push({ key: "orphan", link: "nowhere", label: "orphan" });
  const L = netorbitLayout(m);
  for (const k of ["x", "y", "z", "orphan"]) assert.ok(L.pos[k], k);
});

test("large networks stagger device rings", () => {
  const m = model([["r", null], ["a", "r"]], { a: 120 });
  const L = netorbitLayout(m);
  const radii = new Set(m.devices.map((d) => Math.round(L.pos[d.key].r)));
  assert.strictEqual(radii.size, 2);
});

test("devices are grouped by type from their icon", () => {
  const { noGroupFor } = require("../custom_components/netorbit/frontend/netorbit-card.js");
  assert.strictEqual(noGroupFor("mdi:television"), "media");
  assert.strictEqual(noGroupFor("mdi:laptop"), "computers");
  assert.strictEqual(noGroupFor("mdi:cctv"), "cameras");
  assert.strictEqual(noGroupFor("mdi:thermostat"), "home");
  assert.strictEqual(noGroupFor("mdi:lan-connect"), "other");
});

test("group hubs sit near their devices, not in the middle", () => {
  const hubs = { r: { key: "r", label: "Router" }, g: { key: "g", parent: "r", label: "TVs", kind: "group" } };
  const devices = [1, 2, 3].map((i) => ({ key: "d" + i, link: "g", label: "TV " + i }));
  const L = netorbitLayout({ hubs, devices, root: "r" });
  assert.ok(Math.hypot(L.pos.g.x - 500, L.pos.g.y - 500) > 200);
});

test("hubs keep clear of the internet node above the router", () => {
  const m = model([["r", null], ["a", "r"], ["b", "r"], ["c", "r"], ["d", "r"], ["e", "r"], ["f", "r"]], { a: 6, b: 6, c: 6, d: 6, e: 6, f: 6 });
  const L = netorbitLayout(m);
  const inet = { x: L.pos.r.x, y: L.pos.r.y - 62 }; // the default spot; the card moves it to a clear diagonal if a link runs there
  for (const k of "abcdef") assert.ok(dist(L.pos[k], inet) > 16 + 25, k); // node radii: internet 16, hub 25
});
