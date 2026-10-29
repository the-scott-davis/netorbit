// Screenshots of simulated networks for the docs: node scripts/preview/gallery.js
const { chromium } = require("playwright");
const SCENES = [
  ["docs_flat_25", "Router only, 25 devices", "sim-flat-25"],
  ["docs_mesh_22", "Mesh system, nothing reporting placement", "sim-mesh"],
  ["docs_unifi_30", "UniFi", "sim-unifi"],
  ["docs_snmp_home", "Managed switches with SNMP", "sim-snmp"],
  ["docs_big_mesh_dhcp", "360 devices on a busy mesh network", "sim-big-mesh"],
  ["docs_big_snmp", "330 devices behind managed switches", "sim-big-snmp"],
];
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 960, height: 1100 }, deviceScaleFactor: 2 });
  page.setDefaultTimeout(10000);
  for (const [file, title, out] of SCENES) {
    await page.goto(`http://localhost:8766/scripts/preview/gallery.html?f=${file}.json&title=${encodeURIComponent(title)}`);
    await page.waitForFunction(() => window.ready);
    await page.waitForTimeout(600);
    await page.locator("netorbit-card").screenshot({ path: `docs/${out}.png` });
  }
  // DHCP: hover the device whose IP moved most.
  await page.goto(`http://localhost:8766/scripts/preview/gallery.html?f=docs_big_mesh_dhcp.json&title=${encodeURIComponent("After three rounds of DHCP changes")}`);
  await page.waitForFunction(() => window.ready);
  const key = await page.evaluate(() => {
    const root = document.querySelector("netorbit-card").shadowRoot;
    const shown = new Set([...root.querySelectorAll(".node.dev[data-key]")].map((e) => e.dataset.key));
    const devs = Object.values(window.states).filter((s) => s.attributes.kind === "device" && shown.has(s.attributes.node_key));
    devs.sort((a, b) => (b.attributes.ip_changes || 0) - (a.attributes.ip_changes || 0));
    return devs[0] && devs[0].attributes.node_key;
  });
  const disc = page.locator("netorbit-card").locator(`.node[data-key="${key}"] circle.disc`);
  await disc.hover({ force: true });
  await page.waitForTimeout(400);
  await page.locator("netorbit-card").screenshot({ path: "docs/sim-dhcp-tip.png" });
  await browser.close();
  console.log("done", key);
})().catch((e) => { console.error(e); process.exit(1); });
