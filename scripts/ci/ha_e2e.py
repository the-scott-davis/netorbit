#!/usr/bin/env python3
"""End-to-end check of NetOrbit inside a real Home Assistant.

CI runs this from .github/workflows/e2e.yml against the official Home Assistant container. It onboards a fresh
instance with a throwaway user, adds NetOrbit through the config flow, tracks a few made-up devices, puts the card
on a dashboard, opens it in Chromium and WebKit (the Safari engine) and then checks Home Assistant's log.

To run it on your own machine (use a throwaway instance, never your real one):

    pip install -r scripts/ci/requirements_e2e.txt
    python -m playwright install --with-deps chromium webkit
    mkdir -p /tmp/ha-e2e
    docker run -d --name ha-e2e -p 8123:8123 -v /tmp/ha-e2e:/config \\
        -v "$PWD/custom_components/netorbit:/config/custom_components/netorbit:ro" \\
        ghcr.io/home-assistant/home-assistant:$(python scripts/ci/ha_e2e.py pinned-version)
    python scripts/ci/ha_e2e.py run --url http://localhost:8123 --out /tmp/ha-e2e-out
    python scripts/ci/ha_e2e.py check-log /tmp/ha-e2e/home-assistant.log
    docker rm -f ha-e2e

`run` saves a screenshot per browser into --out. Every failed check is printed as a GitHub `::error::` line, so
it shows up as an annotation on the run.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import math
import os
import pathlib
import re
import secrets
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "custom_components" / "netorbit" / "manifest.json"
DASHBOARD = "netorbit-ci"
VIEW = "map"
IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"

failures: list[tuple[str, str]] = []
summary: list[str] = []  # one line per check that ran, shown as a notice at the end


def log(msg: str) -> None:
    print(msg, flush=True)


def fail(title: str, msg: str) -> None:
    """Record a failed check. It's printed as an annotation right away and counted at the end."""
    failures.append((title, msg))
    # Annotations are one line: keep newlines as the encoded form GitHub understands.
    body = msg.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::error title={title}::{body}", flush=True)


def warn(title: str, msg: str) -> None:
    body = msg.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::warning title={title}::{body}", flush=True)


def report(title: str) -> None:
    """Print what ran as a notice, and add it to the job summary when running in Actions."""
    text = "; ".join(summary)
    print(f"::notice title={title}::{text}", flush=True)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(f"### {title}\n\n" + "".join(f"- {line}\n" for line in summary) + "\n")


# ---------------------------------------------------------------- pinned version


def pinned_version() -> str:
    """The Home Assistant release the unit tests run against.

    requirements_test.txt pulls in pytest-homeassistant-custom-component, and each release of that package pins
    one exact homeassistant version. Download the wheel pip would pick (no dependencies) and read the pin from it.
    """
    req = next(
        line.strip()
        for line in (ROOT / "requirements_test.txt").read_text().splitlines()
        if line.strip().startswith("pytest-homeassistant-custom-component")
    )
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [sys.executable, "-m", "pip", "download", "--quiet", "--no-deps", "--only-binary", ":all:", "-d", tmp, req],
            check=True,
        )
        wheel = next(pathlib.Path(tmp).glob("*.whl"))
        with zipfile.ZipFile(wheel) as zf:
            meta = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
            text = zf.read(meta).decode()
    m = re.search(r"^Requires-Dist: homeassistant\s*==\s*([0-9][^\s;,]*)", text, re.M)
    if not m:
        raise SystemExit(f"No homeassistant pin found in {wheel.name}")
    return m.group(1)


# ---------------------------------------------------------------- Home Assistant over HTTP


class HA:
    def __init__(self, session, url: str) -> None:
        self.s = session
        self.url = url.rstrip("/")
        self.client_id = self.url + "/"
        self.token: str | None = None
        self.tokens: dict = {}

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def get(self, path: str):
        async with self.s.get(self.url + path, headers=self._headers()) as r:
            body = await r.text()
            if r.status >= 400:
                raise RuntimeError(f"GET {path} returned {r.status}: {body[:500]}")
            return json.loads(body) if body else None

    async def post(self, path: str, payload: dict | None = None, form: dict | None = None):
        kw = {"data": form} if form is not None else {"json": payload or {}}
        async with self.s.post(self.url + path, headers=self._headers(), **kw) as r:
            body = await r.text()
            if r.status >= 400:
                raise RuntimeError(f"POST {path} returned {r.status}: {body[:500]}")
            return json.loads(body) if body else None

    async def wait_up(self, timeout: float) -> list:
        """Wait until the onboarding API answers (the frontend and http are up by then)."""
        deadline = time.monotonic() + timeout
        last = "no answer yet"
        while time.monotonic() < deadline:
            try:
                async with self.s.get(self.url + "/api/onboarding") as r:
                    if r.status == 200:
                        return await r.json()
                    last = f"HTTP {r.status}"
            except Exception as err:  # noqa: BLE001 - still starting
                last = f"{type(err).__name__}: {err}"
            await asyncio.sleep(2)
        raise RuntimeError(f"Home Assistant didn't come up within {timeout:.0f}s ({last})")

    async def onboard(self) -> None:
        steps = await self.wait_up(300)
        if any(s.get("step") == "user" and s.get("done") for s in steps):
            raise RuntimeError("This instance is already onboarded. The e2e check needs a fresh config directory.")
        # Throwaway credentials, made up for this run only. Nothing else ever uses them.
        username = "ci-" + secrets.token_hex(4)
        password = secrets.token_urlsafe(24)
        if IN_ACTIONS:
            print(f"::add-mask::{password}", flush=True)
        res = await self.post(
            "/api/onboarding/users",
            {"client_id": self.client_id, "name": "CI", "username": username, "password": password, "language": "en"},
        )
        self.tokens = await self.post(
            "/auth/token",
            form={"grant_type": "authorization_code", "code": res["auth_code"], "client_id": self.client_id},
        )
        self.token = self.tokens["access_token"]
        if IN_ACTIONS:
            print(f"::add-mask::{self.token}", flush=True)
            print(f"::add-mask::{self.tokens['refresh_token']}", flush=True)
        await self.post("/api/onboarding/core_config", {})
        await self.post("/api/onboarding/analytics", {})
        await self.post(
            "/api/onboarding/integration",
            {"client_id": self.client_id, "redirect_uri": self.client_id + "?auth_callback=1"},
        )
        log(f"Onboarded as {username}")

    async def ws(self, *messages: dict) -> list:
        """Send messages over the websocket API and return each result (raising on the first failure)."""
        out = []
        async with self.s.ws_connect(self.url + "/api/websocket") as ws:
            await ws.receive_json()  # auth_required
            await ws.send_json({"type": "auth", "access_token": self.token})
            hello = await ws.receive_json()
            if hello.get("type") != "auth_ok":
                raise RuntimeError(f"Websocket auth failed: {hello}")
            for i, msg in enumerate(messages, 1):
                await ws.send_json({"id": i, **msg})
                while True:
                    res = await ws.receive_json()
                    if res.get("id") == i and res.get("type") == "result":
                        break
                if not res.get("success"):
                    raise RuntimeError(f"{msg['type']} failed: {res.get('error')}")
                out.append(res.get("result"))
        return out


class SummaryWatch:
    """Records every state of NetOrbit's summary sensor from the websocket event stream.

    Started before NetOrbit is added, so the check sees the very first state the sensor gets, however quickly the
    first network scan finishes afterwards.
    """

    def __init__(self, ha: HA) -> None:
        self.ha = ha
        self.states: list[dict] = []  # (attributes plus "_t", seconds since start) in the order they happened
        self._ready = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._t0 = time.monotonic()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._listen())
        await asyncio.wait_for(self._ready.wait(), timeout=30)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def _listen(self) -> None:
        async with self.ha.s.ws_connect(self.ha.url + "/api/websocket") as ws:
            await ws.receive_json()  # auth_required
            await ws.send_json({"type": "auth", "access_token": self.ha.token})
            if (await ws.receive_json()).get("type") != "auth_ok":
                raise RuntimeError("Websocket auth failed")
            await ws.send_json({"id": 1, "type": "subscribe_events", "event_type": "state_changed"})
            while True:
                msg = await ws.receive_json()
                if msg.get("type") == "result" and msg.get("id") == 1:
                    if not msg.get("success"):
                        raise RuntimeError(f"subscribe_events failed: {msg.get('error')}")
                    self._ready.set()
                elif msg.get("type") == "event":
                    new = (msg.get("event") or {}).get("data", {}).get("new_state") or {}
                    attrs = new.get("attributes") or {}
                    if attrs.get("netorbit") is True and attrs.get("kind") == "summary":
                        self.states.append({**attrs, "_t": round(time.monotonic() - self._t0, 1)})


async def check_first_scan(watch: SummaryWatch, timeout: float = 240) -> None:
    """Setup finishes before the first network scan: the summary sensor first shows a scan in progress (or not
    done yet), and later shows it finished."""
    deadline = time.monotonic() + timeout
    done = None
    while time.monotonic() < deadline:
        done = next((a for a in watch.states if a.get("first_scan_done") is True and a.get("scanning") is False), None)
        if done:
            break
        await asyncio.sleep(1)
    if not watch.states:
        fail("No summary states", "The summary sensor never showed up on the websocket event stream")
        return
    first = watch.states[0]
    if not (first.get("scanning") is True or first.get("first_scan_done") is False):
        fail("Setup waited for the scan",
             "The summary sensor's first state should show the first network scan still running "
             f"(scanning true or first_scan_done false), got scanning={first.get('scanning')!r} "
             f"first_scan_done={first.get('first_scan_done')!r}")
    phases = []
    for a in watch.states:
        if a.get("scanning") and (not phases or phases[-1] != a.get("scan_phase")):
            phases.append(a.get("scan_phase"))
    if not done:
        last = {k: watch.states[-1].get(k) for k in ("scanning", "scan_phase", "scan_progress", "first_scan_done", "found")}
        fail("First scan never finished", f"After {timeout:.0f}s the summary sensor still shows {last}")
        return
    log(f"First scan: first state scanning={first.get('scanning')} first_scan_done={first.get('first_scan_done')}, "
        f"phases {phases}, done after {done['_t']}s with {done.get('found')} found, last_scan {done.get('last_scan')}")
    summary.append(f"setup finished before the first scan (phases {', '.join(map(str, phases))}); "
                   f"scan done in {done['_t']}s, {done.get('found')} found")
    if not done.get("last_scan"):
        fail("No last_scan after the first scan", f"first_scan_done is true but last_scan is {done.get('last_scan')!r}")


def _narrow(subnet: str, gateway: str) -> str:
    """NetOrbit refuses huge subnets; docker hands out /16s. Watch the /24 around the gateway instead."""
    net = ipaddress.ip_network(subnet, strict=False)
    if net.num_addresses > 256:
        net = ipaddress.ip_network(f"{gateway}/24", strict=False)
    return str(net)


async def add_netorbit(ha: HA, subnet: str | None, gateway: str | None) -> str:
    flow = await ha.post("/api/config/config_entries/flow", {"handler": "netorbit", "show_advanced_options": False})
    if flow.get("type") != "form":
        raise RuntimeError(f"Config flow didn't show its form: {flow}")
    defaults = {f["name"]: f.get("default") for f in flow.get("data_schema", [])}
    gateway = gateway or defaults["gateway"]
    subnet = _narrow(subnet or defaults["subnet"], gateway)
    user_input = {**{k: v for k, v in defaults.items() if v is not None}, "subnet": subnet, "gateway": gateway}
    log(f"Adding NetOrbit for the container network {subnet} (gateway {gateway})")
    res = await ha.post(f"/api/config/config_entries/flow/{flow['flow_id']}", user_input)
    if res.get("type") != "create_entry":
        raise RuntimeError(f"Config flow didn't create an entry: {json.dumps(res)[:800]}")
    entry_id = (res.get("result") or {}).get("entry_id")

    deadline = time.monotonic() + 60
    state = reason = None
    while time.monotonic() < deadline:
        entries = await ha.get("/api/config/config_entries/entry?domain=netorbit")
        entry = next((e for e in entries if not entry_id or e["entry_id"] == entry_id), None)
        if entry:
            state, reason = entry.get("state"), entry.get("reason")
            entry_id = entry["entry_id"]
            if state in ("loaded", "setup_error", "migration_error", "failed_unload"):
                break
        await asyncio.sleep(1)
    if state != "loaded":
        fail("Config entry did not load", f"NetOrbit config entry state is {state!r} (reason: {reason}), expected 'loaded'")
    else:
        log(f"Config entry {entry_id} is loaded")
        summary.append(f"config entry for {subnet} is loaded")
    return gateway


async def check_sensors(ha: HA, gateway: str) -> None:
    deadline = time.monotonic() + 60
    ours: list = []
    while time.monotonic() < deadline:
        ours = [s for s in await ha.get("/api/states") if (s.get("attributes") or {}).get("netorbit") is True]
        summary_sensor = [s for s in ours if s["attributes"].get("kind") == "summary"]
        hub = [s for s in ours if s["attributes"].get("kind") == "hub" and s["attributes"].get("ip") == gateway]
        if summary_sensor and hub:
            log(f"NetOrbit sensors: {len(ours)} ({summary_sensor[0]['entity_id']}, gateway hub {hub[0]['entity_id']})")
            summary.append(f"{len(ours)} NetOrbit sensors including the summary and the gateway hub")
            return
        await asyncio.sleep(2)
    found = ", ".join(f"{s['entity_id']} ({s['attributes'].get('kind')})" for s in ours) or "none"
    fail("NetOrbit sensors missing", f"Expected a summary sensor and a hub sensor for the gateway {gateway}. Found: {found}")


# A few made-up devices so the map has more than the gateway on it. Documentation-range MACs only (RFC 7042).
SAMPLE_DEVICES = [
    {"mac": "00:00:5e:00:53:01", "name": "CI TV", "icon": "mdi:television"},
    {"mac": "00:00:5e:00:53:02", "name": "CI Phone", "icon": "mdi:cellphone"},
    {"mac": "00:00:5e:00:53:03", "name": "CI Printer", "icon": "mdi:printer"},
]


async def add_sample_devices(ha: HA) -> None:
    """Track a few devices and add an access point through NetOrbit's own actions."""
    # Over the websocket API, so a refused call comes back with NetOrbit's own error message.
    calls = [{"service": "add_hub", "service_data": {"name": "CI access point", "type": "access_point"}}]
    calls += [{"service": "track_device", "service_data": dev} for dev in SAMPLE_DEVICES]
    await ha.ws(*({"type": "call_service", "domain": "netorbit", **c} for c in calls))
    want = {d["name"] for d in SAMPLE_DEVICES} | {"CI access point"}
    deadline = time.monotonic() + 30
    labels: set = set()
    while time.monotonic() < deadline:
        labels = {
            (s.get("attributes") or {}).get("label")
            for s in await ha.get("/api/states")
            if (s.get("attributes") or {}).get("netorbit") is True
        }
        if want <= labels:
            summary.append(f"netorbit.add_hub and netorbit.track_device added {len(want)} nodes")
            return
        await asyncio.sleep(1)
    fail("Sample devices missing", f"After add_hub and track_device, these never got a sensor: {sorted(want - labels)}")


async def make_dashboard(ha: HA) -> None:
    await ha.ws(
        {
            "type": "lovelace/dashboards/create",
            "url_path": DASHBOARD,
            "title": "NetOrbit CI",
            "icon": "mdi:lan",
            "mode": "storage",
            "show_in_sidebar": True,
            "require_admin": False,
        },
        {
            "type": "lovelace/config/save",
            "url_path": DASHBOARD,
            "config": {"title": "NetOrbit CI", "views": [{"title": "Map", "path": VIEW, "cards": [{"type": "custom:netorbit-card"}]}]},
        },
    )
    log(f"Dashboard /{DASHBOARD}/{VIEW} saved with a netorbit-card")


# ---------------------------------------------------------------- the card in real browsers

# Looks inside the card's shadow root. Playwright's locator already pierces the shadow roots of HA's own elements.
CARD_STATE_JS = """(card) => {
  const root = card.shadowRoot;
  const svg = root && root.querySelector("svg.map");
  if (!svg) return { map: false };
  const icons = [...svg.querySelectorAll("g.ic")];
  const drawn = icons.filter((g) => { const p = g.querySelector("path"); return p && (p.getAttribute("d") || "").trim().length > 0; });
  return {
    map: true,
    icons: icons.length,
    drawn: drawn.length,
    foreignObjects: svg.querySelectorAll("foreignObject").length,
    missing: icons.filter((g) => !drawn.includes(g)).map((g) => g.dataset.icon),
  };
}"""


async def check_browser(pw, engine: str, ha: HA, version: str, out: pathlib.Path) -> None:
    title = f"{engine}:"
    browser = await getattr(pw, engine).launch()
    try:
        context = await browser.new_context(viewport={"width": 1280, "height": 1100})
        tokens = {
            "access_token": ha.token,
            "token_type": "Bearer",
            "expires_in": ha.tokens.get("expires_in", 1800),
            "refresh_token": ha.tokens.get("refresh_token"),
            "expires": int(time.time() * 1000) + int(ha.tokens.get("expires_in", 1800)) * 1000,
            "hassUrl": ha.url,
            "clientId": ha.client_id,
        }
        # Log the browser in the same way the frontend remembers a login: tokens in localStorage.
        await context.add_init_script(f"window.localStorage.setItem('hassTokens', {json.dumps(json.dumps(tokens))});")
        page = await context.new_page()
        console: list[tuple[str, str]] = []
        page_errors: list[str] = []
        page.on("console", lambda m: console.append((m.type, m.text)))
        page.on("pageerror", lambda e: page_errors.append(f"{e.name}: {e.message}\n{e.stack or ''}"))

        await page.goto(f"{ha.url}/{DASHBOARD}/{VIEW}", wait_until="domcontentloaded")
        try:
            await page.wait_for_function("() => !!window.customElements.get('netorbit-card')", timeout=20000)
        except Exception:  # noqa: BLE001
            fail(f"{title} card not defined", "customElements.get('netorbit-card') was still undefined after 20s. "
                 "The card's JS didn't load or threw before defining the element.")

        card = page.locator("netorbit-card").first
        state: dict = {"map": False}
        attached = False
        try:
            await card.wait_for(state="attached", timeout=20000)
            attached = True
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                state = await card.evaluate(CARD_STATE_JS)
                if state.get("map") and state["icons"] and state["drawn"] >= math.ceil(state["icons"] * 0.8):
                    break
                await page.wait_for_timeout(500)
        except Exception as err:  # noqa: BLE001
            fail(f"{title} card not on the dashboard", f"No netorbit-card element appeared on /{DASHBOARD}/{VIEW}: {err}")

        if attached:
            if not state.get("map"):
                fail(f"{title} no map", "The card's shadow root has no svg.map")
            else:
                log(f"{engine}: map has {state['icons']} icons, {state['drawn']} drawn as paths")
                summary.append(f"{engine}: {state['drawn']}/{state['icons']} map icons drawn as paths")
                if not state["icons"]:
                    fail(f"{title} no icons", "svg.map has no g.ic icon groups")
                elif state["drawn"] < math.ceil(state["icons"] * 0.8):
                    fail(f"{title} icons not drawn",
                         f"Only {state['drawn']} of {state['icons']} map icons got an SVG path. Still empty: {state['missing']}")
                if state["foreignObjects"]:
                    fail(f"{title} foreignObject in map", f"svg.map has {state['foreignObjects']} foreignObject element(s)")

        await page.wait_for_timeout(1000)
        out.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(out / f"{engine}.png"))

        banners = [text for _, text in console if "NETORBIT" in text]
        if not banners:
            fail(f"{title} no banner", f"The console never showed the NETORBIT banner (expected version {version})")
        elif not any(re.search(rf"NETORBIT\b.*?(?<![\d.]){re.escape(version)}(?![\d.])", b) for b in banners):
            fail(f"{title} banner version", f"Console banner {banners[0]!r} doesn't match the manifest version {version}")
        else:
            log(f"{engine}: banner {banners[0].split('color')[0].strip()!r}")
            summary.append(f"{engine}: console banner shows {version}")

        for err in page_errors:
            if "netorbit" in err.lower():
                fail(f"{title} page error", err[:1500])
        for kind, text in console:
            if kind == "error" and "netorbit" in text.lower():
                fail(f"{title} console error", text[:1500])
        other = [e.splitlines()[0] for e in page_errors if "netorbit" not in e.lower()]
        if other:
            log(f"{engine}: {len(other)} page error(s) not about NetOrbit (ignored): {other[:5]}")
    finally:
        await browser.close()


# ---------------------------------------------------------------- main commands


async def run(args) -> int:
    import aiohttp  # noqa: PLC0415
    from playwright.async_api import async_playwright  # noqa: PLC0415

    version = json.loads(MANIFEST.read_text())["version"]
    out = pathlib.Path(args.out)
    timeout = aiohttp.ClientTimeout(total=600)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        ha = HA(session, args.url)
        try:
            await ha.onboard()
            config = await ha.get("/api/config")
            summary.append(f"Home Assistant {config.get('version')}, NetOrbit {version}")
            watch = SummaryWatch(ha)
            await watch.start()
            try:
                gateway = await add_netorbit(ha, args.subnet, args.gateway)
                await check_sensors(ha, gateway)
                await check_first_scan(watch)
            finally:
                await watch.stop()
            await add_sample_devices(ha)
            await make_dashboard(ha)
        except Exception as err:  # noqa: BLE001
            fail("Home Assistant setup failed", f"{type(err).__name__}: {err}")
            report("E2E failed")
            return 1
        async with async_playwright() as pw:
            for engine in args.browsers.split(","):
                try:
                    await check_browser(pw, engine.strip(), ha, version, out)
                except Exception as err:  # noqa: BLE001
                    fail(f"{engine}: browser check crashed", f"{type(err).__name__}: {err}")
    report("E2E failed" if failures else "E2E passed")
    if failures:
        log(f"\n{len(failures)} check(s) failed")
        return 1
    log("\nAll checks passed")
    return 0


# "2026-01-31 12:00:00.123 WARNING (...)", newer releases add the UTC offset: "12:00:00.123+00:00 WARNING".
LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})? (DEBUG|INFO|WARNING|ERROR|CRITICAL) ")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def read_entries(path: str) -> list[tuple[str, str]]:
    """Split a log into (level, text) entries, with tracebacks kept on the entry they belong to."""
    entries: list[tuple[str, str]] = []
    for raw in pathlib.Path(path).read_text(errors="replace").splitlines():
        line = ANSI_RE.sub("", raw)
        m = LINE_RE.match(line)
        if m:
            entries.append((m.group(1), line))
        elif entries:
            entries[-1] = (entries[-1][0], entries[-1][1] + "\n" + line)
    return entries


def short(text: str) -> str:
    """An annotation-sized version of a log entry: the message and the end of its traceback."""
    lines = text.splitlines()
    if len(lines) > 12:
        lines = lines[:3] + [f"... ({len(lines) - 9} lines, full text in the uploaded log) ..."] + lines[-6:]
    return "\n".join(lines)[:3000]


def check_log(paths: list[str]) -> int:
    """Fail on log entries about NetOrbit that point at a real problem.

    Every file given is read (home-assistant.log and the container's output carry the same lines, so repeats are
    dropped). Home Assistant always warns that netorbit is a custom integration. If that line isn't found, the
    log is missing or its format changed, and a check that can't see anything shouldn't pass.
    """
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    files: list[str] = []
    for path in paths:
        if not os.path.isfile(path):
            files.append(f"{path}: not there")
            continue
        found = read_entries(path)
        head = pathlib.Path(path).read_text(errors="replace").splitlines()[:3]
        files.append(f"{path}: {os.path.getsize(path)} bytes, {len(found)} entries, starts with {head}")
        for level, text in found:
            if text not in seen:
                seen.add(text)
                entries.append((level, text))
    if not any("custom integration netorbit" in text.lower() for _, text in entries):
        fail("Log not readable", "Didn't find Home Assistant's custom integration warning for netorbit. The log is "
             "missing or its line format changed, so the log check can't see anything.\n" + "\n".join(files))
        report("Log check failed")
        return 1

    bad = 0
    other_errors = []
    for level, text in entries:
        low = text.lower()
        ours = "netorbit" in low
        if level in ("ERROR", "CRITICAL") and ours:
            fail("NetOrbit error in the log", short(text))
            bad += 1
        elif ours and ("detected blocking call" in low or "deprecat" in low or "detected that custom integration" in low):
            fail("NetOrbit warning in the log", short(text))
            bad += 1
        elif level in ("ERROR", "CRITICAL"):
            other_errors.append(text.splitlines()[0])
    for text in other_errors[:10]:
        warn("Home Assistant error (not NetOrbit)", text[:1000])
    for line in files:
        log(line)
    summary.append(f"{len(entries)} log entries, {bad} NetOrbit problem(s), {len(other_errors)} error(s) from other integrations")
    report("Log check failed" if bad else "Log check passed")
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pinned-version", help="print the Home Assistant version the unit tests use")
    r = sub.add_parser("run", help="onboard, add NetOrbit and check the card in real browsers")
    r.add_argument("--url", default="http://localhost:8123")
    r.add_argument("--out", default="e2e-artifacts", help="where screenshots go")
    r.add_argument("--browsers", default="chromium,webkit")
    r.add_argument("--subnet", help="network to watch (default: what the config flow suggests, narrowed to a /24)")
    r.add_argument("--gateway", help="gateway address (default: what the config flow suggests)")
    c = sub.add_parser("check-log", help="fail on NetOrbit errors, blocking calls or deprecations in the log")
    c.add_argument("paths", nargs="+", help="log files to read (missing ones are skipped)")
    args = parser.parse_args()

    if args.cmd == "pinned-version":
        print(pinned_version())
        return 0
    if args.cmd == "check-log":
        return check_log(args.paths)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
