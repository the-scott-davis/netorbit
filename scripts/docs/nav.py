"""Draw the README's section navigation as a little NetOrbit map: docs/nav/*.svg

Eight sections orbit a NetOrbit hub. Each tile is its own image (GitHub only lets a whole
image be a link), with a dashed line pointing at the hub so the grid reads as one map.

Icons are Material Design Icons (Apache 2.0) read from scripts/preview/mdi.js:
  npm i @mdi/js@7.4.47 && cp node_modules/@mdi/js/mdi.js scripts/preview/
Run: python scripts/docs/nav.py
"""

from __future__ import annotations

import pathlib
import re
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "nav"
W, H = 250, 96

# (file, label, subtitle, icon, ring color, direction toward the hub)
TILES = [
    ("install", "Install", "Marketplace or HACS", "mdiDownloadCircleOutline", "#34d399", "se"),
    ("features", "What it does", "the short version", "mdiOrbit", "#60a5fa", "s"),
    ("gallery", "See it", "hundreds of networks", "mdiImageMultipleOutline", "#c084fc", "sw"),
    ("place", "Place devices", "drag, paste or ask", "mdiCursorMove", "#f472b6", "e"),
    ("setup", "Setup guide", "SNMP and integrations", "mdiTuneVariant", "#fbbf24", "w"),
    ("settings", "Settings", "card and integration", "mdiCogOutline", "#60a5fa", "ne"),
    ("services", "Automations", "entities, events, services", "mdiRobotOutline", "#34d399", "n"),
    ("limits", "Limits & privacy", "what to expect", "mdiShieldCheckOutline", "#f87171", "nw"),
]

# Where the tile's node sits and where its link line heads (toward the hub tile).
NODE = {"se": (52, 40), "s": (52, 40), "sw": (198, 40), "e": (52, 48), "w": (198, 48),
        "ne": (52, 56), "n": (52, 56), "nw": (198, 56)}
LINK_END = {"se": (W, H), "s": (125, H), "sw": (0, H), "e": (W, 48), "w": (0, 48),
            "ne": (W, 0), "n": (125, 0), "nw": (0, 0)}


def mdi_paths() -> dict[str, str]:
    src = (ROOT / "scripts" / "preview" / "mdi.js").read_text()
    return dict(re.findall(r'export var (mdi\w+) = "([^"]+)"', src))


def tile(label: str, sub: str, path: str, color: str, direction: str) -> str:
    nx, ny = NODE[direction]
    ex, ey = LINK_END[direction]
    left = direction in ("se", "s", "e", "ne", "n")
    tx = 84 if left else 166
    anchor = "start" if left else "end"
    label, sub = escape(label), escape(sub)
    text = (f'<text x="{tx}" y="{ny - 3}" text-anchor="{anchor}" class="l">{label}</text>'
            f'<text x="{tx}" y="{ny + 15}" text-anchor="{anchor}" class="s">{sub}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>.l{{font:600 16px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;fill:#e2e8f0}}.s{{font:12px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;fill:#94a3b8}}</style>
<rect width="{W}" height="{H}" rx="14" fill="#0b1220"/>
<line x1="{nx}" y1="{ny}" x2="{ex}" y2="{ey}" stroke="{color}" stroke-opacity=".55" stroke-width="2" stroke-dasharray="5 6"/>
<circle cx="{nx}" cy="{ny}" r="27" fill="{color}" fill-opacity=".14"/>
<circle cx="{nx}" cy="{ny}" r="20" fill="#0f1a2e" stroke="{color}" stroke-width="2.5"/>
<g transform="translate({nx - 12} {ny - 12})"><path d="{path}" fill="{color}"/></g>
{text}
</svg>
'''


def hub(path: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>.l{{font:700 18px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;fill:#f1f5f9}}.s{{font:12px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;fill:#94a3b8}}</style>
<defs><radialGradient id="g" cx=".5" cy=".5" r=".6"><stop offset="0" stop-color="#13213a"/><stop offset="1" stop-color="#0b1220"/></radialGradient></defs>
<rect width="{W}" height="{H}" rx="14" fill="url(#g)"/>
<g stroke="#60a5fa" stroke-opacity=".35" stroke-width="2" stroke-dasharray="5 6">
<line x1="0" y1="0" x2="62" y2="48"/><line x1="125" y1="0" x2="62" y2="48"/><line x1="{W}" y1="0" x2="62" y2="48"/>
<line x1="0" y1="{H}" x2="62" y2="48"/><line x1="125" y1="{H}" x2="62" y2="48"/><line x1="{W}" y1="{H}" x2="62" y2="48"/>
<line x1="0" y1="48" x2="62" y2="48"/><line x1="{W}" y1="48" x2="200" y2="48"/>
</g>
<circle cx="62" cy="48" r="34" fill="#34d399" fill-opacity=".12"/>
<circle cx="62" cy="48" r="26" fill="#0f1a2e" stroke="#34d399" stroke-width="3"/>
<g transform="translate(46 32) scale(1.333)"><path d="{path}" fill="#34d399"/></g>
<text x="102" y="45" class="l">NetOrbit</text>
<text x="102" y="63" class="s">back to the top</text>
</svg>
'''


def main() -> None:
    paths = mdi_paths()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, label, sub, icon, color, direction in TILES:
        (OUT / f"{name}.svg").write_text(tile(label, sub, paths[icon], color, direction))
    (OUT / "hub.svg").write_text(hub(paths["mdiRouterNetwork"]))
    print(f"wrote {len(TILES) + 1} tiles to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
