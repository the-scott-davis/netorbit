// Stand-ins for the Home Assistant elements the card uses, shaped like the real ones: <ha-icon> renders an
// <ha-svg-icon> in its shadow root, which draws the <path> in its own shadow root. The card reads icon paths
// from there, so a flatter stub would leave every map icon blank.
// Icon paths come from window.MDI (filled from @mdi/js by the page); without it every icon is a dot.
window.MDI = window.MDI || {};
const NO_STUB_DOT = "M12,4A8,8 0 1,0 12,20A8,8 0 1,0 12,4Z";

customElements.define("ha-svg-icon", class extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: "open" }); }
  set path(d) {
    this.shadowRoot.innerHTML = `<svg viewBox="0 0 24 24" style="width:var(--mdc-icon-size,24px);height:var(--mdc-icon-size,24px);display:block;fill:currentColor"><path d="${d}"/></svg>`;
  }
});

customElements.define("ha-icon", class extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: "open" }); }
  connectedCallback() {
    this.style.display = "inline-flex";
    if (this.shadowRoot.firstChild) return;
    const name = this.getAttribute("icon") || "";
    const key = "mdi" + name.slice(4).split("-").map((p) => p[0].toUpperCase() + p.slice(1)).join("");
    const inner = document.createElement("ha-svg-icon");
    this.shadowRoot.appendChild(inner);
    // The real element loads icons asynchronously too.
    setTimeout(() => { inner.path = window.MDI[key] || NO_STUB_DOT; }, 0);
  }
});

customElements.define("ha-card", class extends HTMLElement {
  connectedCallback() { this.style.display = "block"; this.style.borderRadius = "12px"; }
});
