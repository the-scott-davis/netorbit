/* NetOrbit card for Home Assistant
 * Draws a live radial map from the NetOrbit integration's sensors.
 * https://github.com/the-scott-davis/netorbit  (MIT)
 */
const NETORBIT_VERSION = "0.1.0";

const NO_STATUS = {
  online: { color: "#34d399", label: "Online" },
  recent: { color: "#fbbf24", label: "Seen recently" },
  stale: { color: "#f87171", label: "Not seen" },
  new: { color: "#c084fc", label: "New" },
  unknown: { color: "#64748b", label: "Unknown" },
};

const NO_HUB_TYPE = {
  router: "Router",
  switch: "Switch",
  access_point: "Access point",
  mesh_node: "Mesh node",
  other: "Hub",
};

function noEsc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function noRel(iso) {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "never";
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 90) return "just now";
  if (s < 3600) return Math.round(s / 60) + " min ago";
  if (s < 86400) return Math.round(s / 3600) + " h ago";
  return Math.round(s / 86400) + " d ago";
}

function noTrunc(s, n) {
  s = String(s || "");
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

/** Pure layout: returns positions for hubs and leaves. Exported for tests. */
function netorbitLayout(model, opts) {
  const o = Object.assign({ cx: 500, cy: 500, rDev: 370, rHub1: 135, hubStep: 125, rHubMax: 290 }, opts || {});
  const { hubs, root, devices } = model;
  const kidsHub = {};
  const kidsDev = {};
  Object.keys(hubs).forEach((k) => { kidsHub[k] = []; kidsDev[k] = []; });
  Object.values(hubs).forEach((h) => {
    if (h.key === root) return;
    const p = hubs[h.parent] ? h.parent : root;
    kidsHub[p].push(h.key);
  });
  devices.forEach((d) => {
    const p = hubs[d.link] ? d.link : root;
    kidsDev[p].push(d);
  });
  const byLabel = (a, b) => String(a.label).localeCompare(String(b.label));
  Object.values(kidsDev).forEach((a) => a.sort(byLabel));
  Object.values(kidsHub).forEach((a) => a.sort((x, y) => {
    // keep the "new devices" bubble last
    if (x === "__new") return 1;
    if (y === "__new") return -1;
    return String(hubs[x].label).localeCompare(String(hubs[y].label));
  }));

  // DFS producing slots
  const slots = []; // {type:'dev', d, hub} or {type:'gap', hub}
  const range = {};
  const depth = {};
  const guard = new Set();
  const walk = (h, dep) => {
    if (guard.has(h)) return;
    guard.add(h);
    depth[h] = dep;
    const start = slots.length;
    kidsDev[h].forEach((d) => slots.push({ type: "dev", d, hub: h }));
    kidsHub[h].forEach((c) => walk(c, dep + 1));
    if (slots.length === start && h !== root) slots.push({ type: "gap", hub: h });
    range[h] = [start, slots.length - 1];
  };
  walk(root, 0);
  // orphans (cycles) hang off root
  Object.keys(hubs).forEach((h) => { if (!guard.has(h)) { kidsHub[root].push(h); walk(h, 1); } });

  const N = Math.max(slots.length, 1);
  const step = (Math.PI * 2) / N;
  const start = -Math.PI / 2 - (N > 1 ? step * (range[root] ? 0 : 0) : 0);
  const angle = (i) => start + step * i + step / 2;
  const pos = {};
  pos[root] = { x: o.cx, y: o.cy, a: -Math.PI / 2, depth: 0 };
  const stagger = N > 64;
  slots.forEach((s, i) => {
    if (s.type !== "dev") return;
    const a = angle(i);
    const r = o.rDev - (stagger && i % 2 ? 36 : 0);
    pos[s.d.key] = { x: o.cx + r * Math.cos(a), y: o.cy + r * Math.sin(a), a, r, hub: s.hub };
  });
  const maxDepth = Math.max(1, ...Object.keys(depth).map((k) => depth[k]));
  const hubStep = Math.min(o.hubStep, (o.rHubMax - o.rHub1) / Math.max(1, maxDepth - 1));
  Object.keys(hubs).forEach((h) => {
    if (h === root || !range[h]) return;
    const [a0, a1] = range[h];
    const a = (angle(a0) + angle(a1)) / 2;
    const r = Math.min(o.rHubMax, o.rHub1 + (depth[h] - 1) * hubStep);
    pos[h] = { x: o.cx + r * Math.cos(a), y: o.cy + r * Math.sin(a), a, depth: depth[h] };
  });
  return { pos, slots, N, arc: (Math.PI * 2 * o.rDev) / N, kidsHub, depth };
}

class NetOrbitCard extends HTMLElement {
  static getStubConfig() {
    return { title: "Network" };
  }

  setConfig(config) {
    this._config = Object.assign({ title: "Network", height: 900, show_ip: false, show_legend: true, hide_sleepy_offline: false }, config || {});
    this._sig = "";
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  getCardSize() { return 12; }
  getGridOptions() { return { columns: "full", rows: "auto", min_rows: 8 }; }

  set hass(hass) {
    this._hass = hass;
    const model = this._model();
    const sig = JSON.stringify([model.sig, this._popKey || ""]);
    if (sig === this._sig) return;
    this._sig = sig;
    this._render(model);
  }

  _entities() {
    const hass = this._hass;
    const cfg = this._config;
    let ids = Object.keys(hass.states).filter((e) => e.startsWith("sensor.") && hass.states[e].attributes.netorbit === true);
    if (cfg.entities) ids = ids.filter((e) => cfg.entities.includes(e));
    if (cfg.device_id && hass.entities) ids = ids.filter((e) => (hass.entities[e] || {}).device_id === cfg.device_id);
    return ids.map((e) => hass.states[e]);
  }

  _model() {
    const hass = this._hass;
    const states = this._entities();
    const hubs = {};
    const devices = [];
    let summary = null;
    let root = null;
    const sig = [];
    states.forEach((s) => {
      const a = s.attributes;
      if (a.kind === "summary") {
        summary = s;
        sig.push((a.new_devices || []).map((d) => d.key).join(","));
        return;
      }
      const icon = ((hass.entities || {})[s.entity_id] || {}).icon || a.icon || "mdi:lan-connect";
      const n = {
        key: a.node_key, entity: s.entity_id, label: a.label || a.friendly_name, ip: a.ip, mac: a.mac,
        kind: a.kind, link: a.link, parent: a.link, sleepy: a.sleepy === true, last_seen: a.last_seen,
        hub_type: a.hub_type, hostname: a.hostname, icon,
        status: NO_STATUS[s.state] ? s.state : "unknown",
      };
      sig.push(n.key + n.status + n.link + n.label + icon + (n.sleepy ? 1 : 0));
      if (a.kind === "hub") {
        hubs[n.key] = n;
        if (!n.link && !root) root = n.key;
      } else if (!(this._config.hide_sleepy_offline && n.sleepy && n.status !== "online")) {
        devices.push(n);
      }
    });
    if (!root && Object.keys(hubs).length) root = Object.keys(hubs)[0];
    const fresh = summary ? summary.attributes.new_devices || [] : [];
    if (fresh.length && root) {
      hubs.__new = { key: "__new", label: "New devices", kind: "newhub", parent: root, status: "new", icon: "mdi:tag-plus-outline" };
      fresh.forEach((d) => devices.push({
        key: "new:" + d.key, raw: d, label: d.name || d.mac || d.ip, ip: d.ip, mac: d.mac, kind: "new", link: "__new",
        status: "new", icon: "mdi:help-circle-outline", last_seen: d.last_seen,
      }));
    }
    return { hubs, devices, root, summary, sig: sig.join("|") };
  }

  _render(model) {
    const cfg = this._config;
    const { hubs, devices, root, summary } = model;
    if (!root) {
      this.shadowRoot.innerHTML = `<ha-card header="${noEsc(cfg.title)}"><div style="padding:16px">No NetOrbit sensors found. Add the NetOrbit integration under Settings, Devices &amp; services.</div></ha-card>`;
      return;
    }
    const L = netorbitLayout(model, {});
    const pos = L.pos;
    const C = pos[root];
    const col = (s) => (NO_STATUS[s] || NO_STATUS.unknown).color;
    const live = (s) => s === "online";
    const fs = Math.max(9, Math.min(12.5, L.arc * 0.42));
    const maxChars = L.N > 60 ? 16 : 22;

    const curve = (p, q, bend) => {
      const mx = (p.x + q.x) / 2, my = (p.y + q.y) / 2;
      const k = bend == null ? 0.18 : bend;
      const cx = mx + (C.x - mx) * k, cy = my + (C.y - my) * k;
      return `M${p.x.toFixed(1)},${p.y.toFixed(1)} Q${cx.toFixed(1)},${cy.toFixed(1)} ${q.x.toFixed(1)},${q.y.toFixed(1)}`;
    };
    let links = "";
    Object.values(hubs).forEach((h) => {
      if (h.key === root || !pos[h.key]) return;
      const p = pos[hubs[h.parent] ? h.parent : root];
      const s = h.kind === "newhub" ? "new" : h.status;
      links += `<path class="lk strong ${live(s) ? "live" : ""} ${h.kind === "newhub" ? "dashed" : ""}" d="${curve(p, pos[h.key], 0)}" stroke="${col(s)}"/>`;
    });
    devices.forEach((d) => {
      const p = pos[d.key];
      if (!p) return;
      const hp = pos[p.hub];
      if (!hp) return;
      links += `<path class="lk ${live(d.status) ? "live" : ""} ${d.kind === "new" ? "dashed" : ""}" d="${curve(hp, p)}" stroke="${col(d.status)}"/>`;
    });

    const iconFO = (p, r, icon, color) =>
      `<foreignObject x="${(p.x - r).toFixed(1)}" y="${(p.y - r).toFixed(1)}" width="${2 * r}" height="${2 * r}" pointer-events="none"><div xmlns="http://www.w3.org/1999/xhtml" class="ic" style="width:${2 * r}px;height:${2 * r}px;color:${color};--mdc-icon-size:${Math.round(r * 1.05)}px"><ha-icon icon="${noEsc(icon)}"></ha-icon></div></foreignObject>`;

    let gfx = "";
    Object.values(hubs).forEach((h) => {
      const p = pos[h.key];
      if (!p) return;
      const isRoot = h.key === root;
      const isNew = h.kind === "newhub";
      const r = isRoot ? 32 : 25;
      const c = col(isNew ? "new" : h.status);
      const below = isRoot || p.y >= C.y - 4;
      const ly1 = below ? p.y + r + 21 : p.y - r - 27;
      const ly2 = ly1 + 16;
      let sub = isNew
        ? `${devices.filter((d) => d.kind === "new").length} waiting`
        : (cfg.show_ip && h.ip) ? h.ip : (NO_HUB_TYPE[h.hub_type] || "");
      if (String(sub).toLowerCase() === String(h.label).toLowerCase()) sub = "";
      gfx += `<g class="node hub" data-key="${noEsc(h.key)}">` +
        `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${r + 9}" class="halo" fill="${c}"/>` +
        `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${r}" class="disc ${isNew ? "dashed" : ""} ${h.status === "stale" ? "pulse" : ""}" stroke="${c}"/>` +
        iconFO(p, r, h.icon, c) +
        `<text x="${p.x.toFixed(1)}" y="${ly1.toFixed(1)}" class="hlab">${noEsc(noTrunc(h.label, 26))}</text>` +
        (sub ? `<text x="${p.x.toFixed(1)}" y="${ly2.toFixed(1)}" class="hsub">${noEsc(sub)}</text>` : "") +
        `</g>`;
    });

    devices.forEach((d) => {
      const p = pos[d.key];
      if (!p) return;
      const c = col(d.status);
      const deg = (p.a * 180) / Math.PI;
      const nd = ((deg % 360) + 360) % 360;
      const flip = nd > 90 && nd < 270;
      const tr = p.r + 24;
      const tx = C.x + tr * Math.cos(p.a), ty = C.y + tr * Math.sin(p.a);
      const rot = flip ? deg + 180 : deg;
      gfx += `<g class="node dev ${d.status} ${d.sleepy ? "sleepy" : ""}" data-key="${noEsc(d.key)}">` +
        (live(d.status) ? `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="21" class="halo" fill="${c}"/>` : "") +
        `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="15" class="disc ${d.status === "stale" ? "pulse" : ""} ${d.kind === "new" ? "dashed" : ""}" stroke="${c}"/>` +
        iconFO(p, 15, d.icon, c) +
        (d.sleepy ? `<circle cx="${(p.x + 11).toFixed(1)}" cy="${(p.y - 11).toFixed(1)}" r="5" class="zz"/>` : "") +
        `<text x="${tx.toFixed(1)}" y="${ty.toFixed(1)}" transform="rotate(${rot.toFixed(1)} ${tx.toFixed(1)} ${ty.toFixed(1)})" text-anchor="${flip ? "end" : "start"}" dominant-baseline="middle" class="dlab" style="font-size:${fs.toFixed(1)}px">${noEsc(noTrunc(d.label, maxChars))}</text></g>`;
    });

    const counts = { online: 0, recent: 0, stale: 0, new: 0 };
    devices.forEach((d) => { if (counts[d.status] !== undefined) counts[d.status]++; });
    const chip = (k) => `<span class="chip"><i style="background:${NO_STATUS[k].color}"></i>${counts[k]} ${NO_STATUS[k].label}</span>`;
    const staleH = summary ? summary.attributes.stale_hours : 24;
    const isAdmin = !!(this._hass.user && this._hass.user.is_admin);

    this.shadowRoot.innerHTML = `
<style>
  :host { display:block; }
  ha-card { overflow:hidden; background: radial-gradient(ellipse at 50% 48%, #13213a 0%, #0b1220 55%, #070b14 100%); color:#e2e8f0; border:1px solid rgba(148,163,184,.12); }
  .head { display:flex; flex-wrap:wrap; align-items:center; gap:10px 12px; padding:16px 18px 4px; }
  .title { font-size:20px; font-weight:600; margin-right:auto; display:flex; align-items:center; gap:8px; }
  .title ha-icon { --mdc-icon-size:22px; color:#60a5fa; }
  .chip { display:inline-flex; align-items:center; gap:6px; font-size:12.5px; color:#cbd5e1; background:rgba(148,163,184,.08); border:1px solid rgba(148,163,184,.14); padding:4px 10px; border-radius:999px; font-variant-numeric:tabular-nums; }
  .chip i { width:8px; height:8px; border-radius:50%; display:inline-block; }
  .wrap { position:relative; }
  svg { font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif); width:100%; height:auto; display:block; max-height:${Number(cfg.height) || 900}px; }
  .ring { fill:none; stroke:rgba(148,163,184,.07); stroke-width:1; }
  .lk { fill:none; stroke-width:1.4; opacity:.45; }
  .lk.strong { stroke-width:2.6; opacity:.75; }
  .lk.dashed { stroke-dasharray:3 6; }
  .lk.live { stroke-dasharray:6 10; animation: flow 1.6s linear infinite; opacity:.8; }
  .lk.strong.live { stroke-dasharray:10 8; }
  @keyframes flow { to { stroke-dashoffset:-32; } }
  .disc { fill:#0f172a; stroke-width:2.2; }
  .disc.dashed { stroke-dasharray:4 4; }
  .halo { opacity:.13; filter:url(#noblur); }
  .pulse { animation: pulse 1.8s ease-in-out infinite; }
  @keyframes pulse { 50% { stroke-width:5; } }
  .ic { display:flex; align-items:center; justify-content:center; }
  .hlab { fill:#f1f5f9; font-size:15px; font-weight:600; text-anchor:middle; paint-order:stroke; stroke:#0b1220; stroke-width:4px; }
  .hsub { fill:#94a3b8; font-size:12px; text-anchor:middle; paint-order:stroke; stroke:#0b1220; stroke-width:4px; }
  .dlab { fill:#cbd5e1; }
  .dev.recent .dlab { fill:#fde68a; }
  .dev.stale .dlab { fill:#fecaca; }
  .dev.new .dlab { fill:#e9d5ff; }
  .dev.sleepy:not(.online) { opacity:.7; }
  .zz { fill:#a78bfa; stroke:#0f172a; stroke-width:1.5; }
  .node { cursor:pointer; }
  .node:hover .disc { stroke-width:4; }
  .node:hover .dlab { fill:#fff; font-weight:600; }
  .tip { position:absolute; pointer-events:none; background:rgba(15,23,42,.96); border:1px solid rgba(148,163,184,.25); border-radius:10px; padding:10px 12px; font-size:12.5px; line-height:1.55; color:#e2e8f0; min-width:190px; box-shadow:0 10px 30px rgba(0,0,0,.45); opacity:0; transition:opacity .12s; z-index:2; }
  .tip b { font-size:13.5px; display:block; margin-bottom:2px; }
  .tip .k { color:#94a3b8; display:inline-block; width:70px; }
  .pop { position:absolute; background:rgba(15,23,42,.98); border:1px solid rgba(192,132,252,.5); border-radius:10px; padding:10px 12px; font-size:13px; color:#e2e8f0; z-index:3; min-width:200px; box-shadow:0 10px 30px rgba(0,0,0,.5); }
  .pop .row { display:flex; gap:8px; margin-top:8px; }
  .pop button { flex:1; font:inherit; padding:6px 10px; border-radius:8px; border:1px solid rgba(148,163,184,.3); background:#1e293b; color:#e2e8f0; cursor:pointer; }
  .pop button.go { background:#7c3aed; border-color:#7c3aed; }
  .legend { display:flex; flex-wrap:wrap; gap:14px; padding:2px 18px 14px; font-size:12px; color:#94a3b8; }
  .legend span { display:inline-flex; align-items:center; gap:6px; }
  .legend .dot { width:9px; height:9px; border-radius:50%; display:inline-block; }
  @media (prefers-reduced-motion: reduce) { .lk.live, .pulse { animation:none; } }
</style>
<ha-card>
  <div class="head">
    <div class="title"><ha-icon icon="mdi:orbit"></ha-icon>${noEsc(cfg.title)}</div>
    ${chip("online")}${chip("recent")}${chip("stale")}${counts.new ? chip("new") : ""}
  </div>
  <div class="wrap">
    <svg viewBox="-70 -40 1140 1090" role="img" aria-label="Network map">
      <defs><filter id="noblur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter></defs>
      <circle class="ring" cx="${C.x}" cy="${C.y}" r="370"/>
      ${links}
      ${gfx}
    </svg>
    <div class="tip"></div>
  </div>
  ${cfg.show_legend ? `<div class="legend">
    <span>Moving line = answering pings</span>
    <span><i class="dot" style="background:${NO_STATUS.recent.color}"></i>Seen in the last ${noEsc(staleH)} h</span>
    <span><i class="dot" style="background:${NO_STATUS.stale.color}"></i>Not seen for ${noEsc(staleH)} h+</span>
    <span><i class="dot" style="background:#a78bfa"></i>Allowed to sleep</span>
  </div>` : ""}
</ha-card>`;

    const all = {};
    Object.values(hubs).forEach((h) => (all[h.key] = h));
    devices.forEach((d) => (all[d.key] = d));
    const tip = this.shadowRoot.querySelector(".tip");
    const wrap = this.shadowRoot.querySelector(".wrap");
    const place = (el, ev, w, h) => {
      const r = wrap.getBoundingClientRect();
      let x = ev.clientX - r.left + 14, y = ev.clientY - r.top + 14;
      if (x + w > r.width) x -= w + 24;
      if (y + h > r.height) y -= h + 20;
      el.style.left = Math.max(4, x) + "px"; el.style.top = Math.max(4, y) + "px";
    };
    this.shadowRoot.querySelectorAll(".node[data-key]").forEach((el) => {
      const n = all[el.dataset.key];
      if (!n) return;
      el.addEventListener("mouseenter", () => {
        if (n.kind === "newhub") {
          tip.innerHTML = `<b>New devices</b><div>Found on the network but not tracked yet.</div>`;
        } else {
          const via = n.kind === "hub" ? (hubs[n.parent] ? hubs[n.parent].label : "") : (hubs[n.link] ? hubs[n.link].label : "");
          tip.innerHTML = `<b>${noEsc(n.label)}</b>` +
            `<div><span class="k">Status</span><span style="color:${col(n.status)}">${(NO_STATUS[n.status] || NO_STATUS.unknown).label}</span>${n.sleepy ? " · sleeps" : ""}</div>` +
            (n.ip ? `<div><span class="k">IP</span>${noEsc(n.ip)}</div>` : "") +
            (n.mac ? `<div><span class="k">MAC</span>${noEsc(n.mac)}</div>` : "") +
            (n.hostname && n.hostname !== n.label ? `<div><span class="k">Host</span>${noEsc(n.hostname)}</div>` : "") +
            (via ? `<div><span class="k">Via</span>${noEsc(via)}</div>` : "") +
            `<div><span class="k">Last seen</span>${n.status === "online" ? "now" : noRel(n.last_seen)}</div>`;
        }
        tip.style.opacity = "1";
      });
      el.addEventListener("mousemove", (ev) => place(tip, ev, 220, 150));
      el.addEventListener("mouseleave", () => (tip.style.opacity = "0"));
      el.addEventListener("click", (ev) => {
        if (n.kind === "new") { this._popup(n, ev, wrap, place, isAdmin); return; }
        if (n.entity) this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: n.entity }, bubbles: true, composed: true }));
      });
    });
  }

  _popup(n, ev, wrap, place, isAdmin) {
    const old = wrap.querySelector(".pop");
    if (old) old.remove();
    const pop = document.createElement("div");
    pop.className = "pop";
    const entryId = this._summaryEntry();
    pop.innerHTML = `<b>${noEsc(n.label)}</b><div style="color:#94a3b8">${noEsc(n.ip || "")} ${noEsc(n.mac || "")}</div>` +
      (isAdmin
        ? `<div class="row"><button class="go">Track</button><button class="ign">Ignore</button><button class="x">Close</button></div>`
        : `<div style="margin-top:6px;color:#94a3b8">An admin can track or ignore this device.</div><div class="row"><button class="x">Close</button></div>`);
    wrap.appendChild(pop);
    place(pop, ev, 240, 110);
    const call = (svc) => {
      const data = { mac: n.raw.mac || undefined, ip: n.raw.ip || undefined };
      if (entryId) data.config_entry_id = entryId;
      this._hass.callService("netorbit", svc, data).catch((e) => console.error("NetOrbit:", e));
      pop.remove();
    };
    const q = (s) => pop.querySelector(s);
    if (q(".go")) q(".go").addEventListener("click", () => call("track_device"));
    if (q(".ign")) q(".ign").addEventListener("click", () => call("ignore_device"));
    q(".x").addEventListener("click", () => pop.remove());
  }

  _summaryEntry() {
    const s = this._entities().find((x) => x.attributes.kind === "summary");
    return s ? s.attributes.config_entry_id : undefined;
  }
}

if (!customElements.get("netorbit-card")) customElements.define("netorbit-card", NetOrbitCard);
window.customCards = window.customCards || [];
if (!window.customCards.find((c) => c.type === "netorbit-card")) {
  window.customCards.push({
    type: "netorbit-card",
    name: "NetOrbit",
    description: "Live radial map of your network from the NetOrbit integration.",
    preview: false,
    documentationURL: "https://github.com/the-scott-davis/netorbit",
  });
}
if (typeof module !== "undefined") module.exports = { netorbitLayout };
console.info("%c NETORBIT %c " + NETORBIT_VERSION, "color:#0b1220;background:#34d399;font-weight:700", "color:#34d399");
