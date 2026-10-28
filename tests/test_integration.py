"""End to end tests: setup, discovery, status, events, services, options."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.netorbit.const import DOMAIN

from .conftest import GATEWAY, MAC_A, MAC_B, MAC_C, SUBNET


def _entry(mode: str = "auto", **opts) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="NetOrbit",
        unique_id=SUBNET,
        data={"subnet": SUBNET, "gateway": GATEWAY},
        options={"mode": mode, "ping_interval": 60, "discovery_interval": 300, "stale_hours": 24, "ignore_random_mac": True, **opts},
    )


def _node_states(hass: HomeAssistant) -> dict[str, object]:
    out = {}
    for st in hass.states.async_all("sensor"):
        if st.attributes.get("netorbit") and st.attributes.get("kind") != "summary":
            out[st.attributes["label"]] = st
    return out


def _summary(hass: HomeAssistant):
    return next(s for s in hass.states.async_all("sensor") if s.attributes.get("kind") == "summary")


async def _advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    for _ in range(3):
        await hass.async_block_till_done(wait_background_tasks=True)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_user_flow(hass: HomeAssistant, fake_net) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"subnet": "192.0.2.0/24", "gateway": "203.0.113.1", "mode": "auto", "ping_interval": 60}
    )
    assert result["errors"] == {"gateway": "gateway_outside"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"subnet": "10.0.0.0/16", "gateway": "10.0.0.1", "mode": "auto", "ping_interval": 60}
    )
    assert result["errors"] == {"subnet": "subnet_too_large"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"subnet": "192.0.2.9/24", "gateway": GATEWAY, "mode": "manual", "ping_interval": 120}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"subnet": "192.0.2.0/24", "gateway": GATEWAY}
    assert result["options"]["mode"] == "manual"
    assert result["options"]["hubs"][0]["id"] == "gateway"
    await hass.async_block_till_done()

    dup = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    dup = await hass.config_entries.flow.async_configure(
        dup["flow_id"], {"subnet": "192.0.2.0/24", "gateway": GATEWAY, "mode": "auto", "ping_interval": 60}
    )
    assert dup["type"] is FlowResultType.ABORT


async def test_auto_mode_discovers_and_tracks(hass: HomeAssistant, fake_net) -> None:
    fake_net.alive = {GATEWAY, "192.0.2.10", "192.0.2.11", "192.0.2.12"}
    fake_net.arp = {GATEWAY: "00:00:5e:00:53:01", "192.0.2.10": MAC_A, "192.0.2.11": MAC_B, "192.0.2.12": MAC_C}
    events = async_capture_events(hass, "netorbit_new_device")
    await _setup(hass, _entry("auto"))

    nodes = _node_states(hass)
    # router hub + two real MACs; the randomized MAC is ignored, the gateway is not a device
    assert set(nodes) == {"Router", "Device 53:0B", "Device 53:0C"}
    assert all(s.state == "online" for s in nodes.values())
    assert nodes["Device 53:0B"].attributes["link"] == "hub:gateway"
    assert nodes["Router"].attributes["kind"] == "hub"
    assert nodes["Router"].attributes["link"] is None
    assert _summary(hass).state == "2"
    # the very first sweep fills the map quietly
    assert events == []


async def test_new_device_event_and_manual_mode(hass: HomeAssistant, fake_net, freezer: FrozenDateTimeFactory) -> None:
    fake_net.alive = {GATEWAY, "192.0.2.11"}
    fake_net.arp = {"192.0.2.11": MAC_B}
    events = async_capture_events(hass, "netorbit_new_device")
    entry = _entry("manual")
    await _setup(hass, entry)

    # manual mode: found but not tracked, listed as new
    assert set(_node_states(hass)) == {"Router"}
    new = _summary(hass).attributes["new_devices"]
    assert [d["mac"] for d in new] == [MAC_B.upper()]

    # a device joins later and the next sweep announces it
    fake_net.alive.add("192.0.2.12")
    fake_net.arp["192.0.2.12"] = MAC_C
    await _advance(hass, freezer, 301)
    assert [e.data["mac"] for e in events] == [MAC_C]

    # track one through the service, ignore the other
    await hass.services.async_call(DOMAIN, "track_device", {"mac": MAC_B, "name": "Kitchen Speaker", "sleepy": True}, blocking=True)
    await hass.services.async_call(DOMAIN, "ignore_device", {"mac": MAC_C}, blocking=True)
    await hass.async_block_till_done()
    nodes = _node_states(hass)
    assert "Kitchen Speaker" in nodes
    assert nodes["Kitchen Speaker"].attributes["sleepy"] is True
    assert nodes["Kitchen Speaker"].attributes["icon"] == "mdi:speaker"
    assert _summary(hass).attributes["new_devices"] == []
    assert entry.options["ignored"] == [MAC_C]


async def test_stale_and_recovered(hass: HomeAssistant, fake_net, freezer: FrozenDateTimeFactory) -> None:
    fake_net.alive = {GATEWAY, "192.0.2.11"}
    fake_net.arp = {"192.0.2.11": MAC_B}
    stale = async_capture_events(hass, "netorbit_device_stale")
    back = async_capture_events(hass, "netorbit_device_recovered")
    await _setup(hass, _entry("auto"))
    name = "Device 53:0B"

    fake_net.alive.discard("192.0.2.11")
    await _advance(hass, freezer, 61)
    assert _node_states(hass)[name].state == "recent"

    await _advance(hass, freezer, 25*3600)
    assert _node_states(hass)[name].state == "stale"
    assert [e.data["name"] for e in stale] == [name]

    fake_net.alive.add("192.0.2.11")
    await _advance(hass, freezer, 61)
    assert _node_states(hass)[name].state == "online"
    assert [e.data["name"] for e in back] == [name]


async def test_options_hubs_and_devices(hass: HomeAssistant, fake_net) -> None:
    fake_net.alive = {GATEWAY, "192.0.2.5", "192.0.2.11"}
    fake_net.arp = {"192.0.2.11": MAC_B}
    entry = _entry("auto")
    await _setup(hass, entry)

    # add an access point hub
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["type"] is FlowResultType.MENU
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "add_hub"})
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"name": "Hallway AP", "host": "192.0.2.5", "type": "access_point", "parent": "gateway"}
    )
    assert flow["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert [h["id"] for h in entry.options["hubs"]] == ["gateway", "hallway_ap"]

    # move the device under the AP and rename it
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "edit_device"})
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"device": MAC_B})
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"name": "Office Printer", "hub": "hallway_ap", "sleepy": False}
    )
    assert flow["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    nodes = _node_states(hass)
    assert nodes["Office Printer"].attributes["link"] == "hub:hallway_ap"
    assert nodes["Office Printer"].attributes["icon"] == "mdi:printer"
    assert nodes["Hallway AP"].attributes["link"] == "hub:gateway"
    assert nodes["Hallway AP"].state == "online"

    # a hub cannot become its own ancestor
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "edit_hub"})
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"hub": "gateway"})
    assert flow["step_id"] == "edit_hub_details"
    assert "parent" not in flow["data_schema"].schema

    # removing the hub moves its device back to the router
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "edit_hub"})
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"hub": "hallway_ap"})
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"name": "Hallway AP", "type": "access_point", "parent": "gateway", "remove": True}
    )
    await hass.async_block_till_done()
    nodes = _node_states(hass)
    assert "Hallway AP" not in nodes
    assert nodes["Office Printer"].attributes["link"] == "hub:gateway"


async def test_stop_tracking_removes_entity(hass: HomeAssistant, fake_net) -> None:
    fake_net.alive = {GATEWAY, "192.0.2.11"}
    fake_net.arp = {"192.0.2.11": MAC_B}
    entry = _entry("auto")
    await _setup(hass, entry)
    reg = er.async_get(hass)
    before = {e.entity_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)}

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "edit_device"})
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"device": MAC_B})
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"hub": "gateway", "sleepy": False, "stop_tracking": True})
    await hass.async_block_till_done()
    after = {e.entity_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
    assert len(after) == len(before) - 1
    assert "Device 53:0B" not in _node_states(hass)


async def test_diagnostics_redacts(hass: HomeAssistant, fake_net) -> None:
    from custom_components.netorbit.diagnostics import async_get_config_entry_diagnostics

    fake_net.alive = {GATEWAY, "192.0.2.11"}
    fake_net.arp = {"192.0.2.11": MAC_B}
    entry = _entry("auto")
    await _setup(hass, entry)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = repr(diag)
    assert "192.0.2" not in text
    assert MAC_B not in text.lower()
    assert diag["nodes"]


async def test_unload(hass: HomeAssistant, fake_net) -> None:
    entry = _entry("auto")
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
