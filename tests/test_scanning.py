"""Setup finishes before the first network scan, and the summary sensor shows the scan's progress."""

from __future__ import annotations

import asyncio

from freezegun.api import FrozenDateTimeFactory

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .test_auto_and_tools import _network
from .test_dhcp_helpers import advance
from .test_integration import _entry, _node_states, _setup, _summary


def _hold_sweeps(fake_net) -> asyncio.Event:
    """Make every subnet sweep wait until the returned event is set. Ping rounds still answer."""
    gate = asyncio.Event()
    real = fake_net.multiping

    async def held(addresses, **kwargs):
        if len(addresses) > 20:  # a subnet sweep, not the ping round of known devices
            await gate.wait()
        return await real(addresses, **kwargs)

    fake_net.multiping = held
    return gate


def _record_summary(hass: HomeAssistant) -> list[dict]:
    """Every summary state written from now on (attributes only)."""
    seen: list[dict] = []

    @callback  # runs in order, in the event loop
    def on_change(event) -> None:
        new = event.data.get("new_state")
        if new is not None and new.attributes.get("kind") == "summary":
            seen.append(dict(new.attributes))

    hass.bus.async_listen("state_changed", on_change)
    return seen


async def test_setup_does_not_wait_for_the_first_scan(hass: HomeAssistant, fake_net) -> None:
    _network(fake_net)
    gate = _hold_sweeps(fake_net)
    written = _record_summary(hass)
    entry = _entry("auto")
    entry.add_to_hass(hass)

    # The sweep can't finish, yet setup does.
    assert await asyncio.wait_for(hass.config_entries.async_setup(entry.entry_id), timeout=5)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    summary = _summary(hass).attributes
    assert summary["scanning"] is True
    assert summary["first_scan_done"] is False
    assert summary["scan_phase"] == "ping"
    assert summary["found"] == 0
    # Nothing found yet: only the router is on the map.
    assert set(_node_states(hass)) == {"Router"}

    gate.set()
    await hass.async_block_till_done(wait_background_tasks=True)

    summary = _summary(hass).attributes
    assert summary["scanning"] is False
    assert summary["first_scan_done"] is True
    assert summary["scan_phase"] is None
    assert summary["scan_progress"] == 100
    assert summary["found"] == 5  # everything that answered, apart from the router
    nodes = _node_states(hass)
    assert {"living-room-tv", "nas", "core-switch", "u6-lite-hall"} <= set(nodes)
    assert nodes["living-room-tv"].attributes["link"] == "hub:u6_lite_hall"

    # The phases went by in order, with only a handful of updates for the whole scan.
    phases = [a["scan_phase"] for a in written if a["scanning"]]
    assert [p for i, p in enumerate(phases) if i == 0 or p != phases[i - 1]] == ["starting", "ping", "arp", "names", "snmp", "layout"]
    progress = [a["scan_progress"] for a in written if a["scanning"]]
    assert progress == sorted(progress)
    assert len(written) <= 12, len(written)
    # The first finished state already carries the devices.
    done = next(a for a in written if not a["scanning"])
    assert done["first_scan_done"] is True and done["counts"]["online"] >= 3


async def test_first_scan_done_survives_a_reload(hass: HomeAssistant, fake_net) -> None:
    _network(fake_net)
    entry = _entry("auto")
    await _setup(hass, entry)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    before = {k: s.attributes["link"] for k, s in _node_states(hass).items()}
    assert before["u6-lite-hall"] == "hub:core_switch"
    assert _summary(hass).attributes["first_scan_done"] is True

    gate = _hold_sweeps(fake_net)
    assert await asyncio.wait_for(hass.config_entries.async_reload(entry.entry_id), timeout=5)
    await hass.async_block_till_done()

    # While the new scan runs, the map is drawn from what was saved: same devices, same tree.
    summary = _summary(hass).attributes
    assert summary["first_scan_done"] is True
    assert summary["scanning"] is True
    during = {k: s.attributes["link"] for k, s in _node_states(hass).items()}
    assert during == before
    assert _node_states(hass)["living-room-tv"].state == "online"  # the ping round ran

    gate.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _summary(hass).attributes["scanning"] is False
    assert {k: s.attributes["link"] for k, s in _node_states(hass).items()} == before


async def test_periodic_scans_show_progress(hass: HomeAssistant, fake_net, freezer: FrozenDateTimeFactory) -> None:
    _network(fake_net)
    entry = _entry("auto")
    await _setup(hass, entry)
    written = _record_summary(hass)

    # A ping round on its own is not a scan.
    await advance(hass, freezer, 61)
    assert not any(a["scanning"] for a in written)

    written.clear()
    await advance(hass, freezer, 301)
    assert [a["scan_phase"] for a in written if a["scanning"]][:1] == ["ping"]
    assert written[-1]["scanning"] is False and written[-1]["scan_progress"] == 100


async def test_a_failed_scan_does_not_stay_scanning(hass: HomeAssistant, fake_net) -> None:
    _network(fake_net)

    async def broken(addresses, **kwargs):
        if len(addresses) > 20:
            raise OSError("network is unreachable")
        return []

    fake_net.multiping = broken
    entry = _entry("auto")
    await _setup(hass, entry)
    summary = _summary(hass).attributes
    assert summary["scanning"] is False
    assert summary["first_scan_done"] is False
