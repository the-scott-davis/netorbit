"""Automatic hubs from SNMP and vendors, controller placement, manual tools and the AI tool set."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from custom_components.netorbit.const import DOMAIN
from custom_components.netorbit.snmp import ProbeResult

from .conftest import GATEWAY
from .test_integration import _entry, _node_states, _setup, _summary

GW_MAC = "00:00:5e:00:53:01"
SW_MAC = "00:00:5e:00:53:02"
AP_MAC = "00:00:5f:00:53:04"  # example-ok: synthetic test value
TV_MAC = "00:00:5e:00:53:10"
NAS_MAC = "00:00:5e:00:53:12"
MAYBE_MAC = "00:00:5f:00:53:20"  # example-ok: synthetic test value


def _network(fake_net, community: str = "public") -> None:
    """Router .1, managed switch .2 (SNMP), access point .6, TV behind the AP, NAS wired to the switch."""
    fake_net.alive = {GATEWAY, "192.0.2.2", "192.0.2.6", "192.0.2.10", "192.0.2.12", "192.0.2.20"}
    fake_net.arp = {
        GATEWAY: GW_MAC, "192.0.2.2": SW_MAC, "192.0.2.6": AP_MAC,
        "192.0.2.10": TV_MAC, "192.0.2.12": NAS_MAC, "192.0.2.20": MAYBE_MAC,
    }
    fake_net.dns = {"192.0.2.6": "u6-lite-hall.lan", "192.0.2.10": "living-room-tv.lan", "192.0.2.12": "nas.lan"}
    fake_net.vendors = {"00:00:5F": "Ubiquiti Inc"}
    fake_net.snmp = {"192.0.2.2": (community, ProbeResult(descr="8-port PoE managed switch", name="core-switch", bridge=True))}
    fake_net.tables = {"192.0.2.2": {GW_MAC: 1, AP_MAC: 6, TV_MAC: 6, NAS_MAC: 3, MAYBE_MAC: 4}}


async def test_snmp_builds_the_layout(hass: HomeAssistant, fake_net) -> None:
    _network(fake_net)
    entry = _entry("auto")
    await _setup(hass, entry)
    # Hubs were added on the first sweep; the next refresh lays devices out under them.
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    hubs = {h["name"]: h for h in entry.options["hubs"]}
    assert set(hubs) == {"Router", "core-switch", "u6-lite-hall"}
    assert hubs["core-switch"]["type"] == "switch" and hubs["core-switch"]["source"] == "snmp"
    assert hubs["u6-lite-hall"]["type"] == "access_point"

    nodes = _node_states(hass)
    assert nodes["u6-lite-hall"].attributes["link"] == "hub:core_switch"
    assert nodes["core-switch"].attributes["link"] == "hub:gateway"
    assert nodes["living-room-tv"].attributes["link"] == "hub:u6_lite_hall"
    assert nodes["living-room-tv"].attributes["placement"] == "snmp"
    assert nodes["nas"].attributes["link"] == "hub:core_switch"
    # Hubs are not listed as devices as well.
    assert not any(n.attributes["kind"] == "device" and n.attributes["mac"] == AP_MAC.upper() for n in nodes.values())

    # A Ubiquiti device with no other clues is only suggested.
    suggested = _summary(hass).attributes["suggested_hubs"]
    assert [s["key"] for s in suggested] == [MAYBE_MAC]
    assert "snmp" in _summary(hass).attributes["sources"]


async def test_custom_community(hass: HomeAssistant, fake_net) -> None:
    _network(fake_net, community="s3cretRO")
    entry = _entry("auto")
    await _setup(hass, entry)
    assert "core-switch" not in {h["name"] for h in entry.options["hubs"]}

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "settings"})
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {"mode": "auto", "ping_interval": 60, "discovery_interval": 300, "stale_hours": 24,
         "ignore_random_mac": True, "auto_hubs": True, "group_by_type": True,
         "snmp_enabled": True, "snmp_community": "s3cretRO"},
    )
    await hass.async_block_till_done()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert "core-switch" in {h["name"] for h in entry.options["hubs"]}


async def test_suggestions_confirm_and_dismiss(hass: HomeAssistant, fake_net) -> None:
    _network(fake_net)
    fake_net.alive.add("192.0.2.21")
    fake_net.arp["192.0.2.21"] = "00:00:5f:00:53:21"  # example-ok: synthetic test value
    entry = _entry("auto")
    await _setup(hass, entry)
    keys = {s["key"] for s in _summary(hass).attributes["suggested_hubs"]}
    assert keys == {MAYBE_MAC, "00:00:5f:00:53:21"}  # example-ok: synthetic test value

    res = await hass.services.async_call(
        DOMAIN, "confirm_hub", {"device": MAYBE_MAC, "type": "mesh_node", "name": "Den Node"}, blocking=True, return_response=True
    )
    assert res["name"] == "Den Node"
    await hass.services.async_call(DOMAIN, "dismiss_hub", {"device": "192.0.2.21"}, blocking=True)
    await hass.async_block_till_done()
    assert _summary(hass).attributes["suggested_hubs"] == []
    assert any(h["name"] == "Den Node" and h["type"] == "mesh_node" for h in entry.options["hubs"])
    assert "00:00:5f:00:53:21" in entry.options["dismissed_hubs"]  # example-ok: synthetic test value


async def test_manual_beats_automatic_and_reset(hass: HomeAssistant, fake_net) -> None:
    _network(fake_net)
    entry = _entry("auto")
    await _setup(hass, entry)
    await entry.runtime_data.async_refresh()

    res = await hass.services.async_call(
        DOMAIN, "assign_device", {"device": ["living-room-tv"], "hub": "Router"}, blocking=True, return_response=True
    )
    assert res["assigned"] == ["living-room-tv"]
    tv = _node_states(hass)["living-room-tv"]
    assert tv.attributes["link"] == "hub:gateway" and tv.attributes["placement"] == "manual"

    await hass.services.async_call(DOMAIN, "reset_placement", {"device": "192.0.2.10"}, blocking=True)
    tv = _node_states(hass)["living-room-tv"]
    assert tv.attributes["link"] == "hub:u6_lite_hall" and tv.attributes["placement"] == "snmp"


async def test_import_client_list(hass: HomeAssistant, fake_net) -> None:
    fake_net.alive = {GATEWAY, "192.0.2.10", "192.0.2.12"}
    fake_net.arp = {"192.0.2.10": TV_MAC, "192.0.2.12": NAS_MAC}
    entry = _entry("auto")
    await _setup(hass, entry)
    await hass.services.async_call(DOMAIN, "add_hub", {"name": "Upstairs Node", "type": "mesh_node"}, blocking=True)

    pasted = f"""Connected devices (3)
    Living room TV   {TV_MAC.upper().replace(':', '-')}   5 GHz
    nas              192.0.2.12
    Unknown thing    00:00:5E:00:53:77
    """
    res = await hass.services.async_call(
        DOMAIN, "import_client_list", {"hub": "upstairs node", "text": pasted}, blocking=True, return_response=True
    )
    assert res["hub"] == "upstairs_node"
    assert len(res["assigned"]) == 3
    assert res["added_new"] == ["00:00:5E:00:53:77"]
    links = {n.attributes["mac"]: n.attributes["link"] for n in _node_states(hass).values() if n.attributes["kind"] == "device"}
    assert links[TV_MAC.upper()] == "hub:upstairs_node"
    assert links[NAS_MAC.upper()] == "hub:upstairs_node"


async def test_controller_placement(hass: HomeAssistant, fake_net) -> None:
    fake_net.alive = {GATEWAY, "192.0.2.6", "192.0.2.10"}
    fake_net.arp = {"192.0.2.6": AP_MAC, "192.0.2.10": TV_MAC}
    entry = _entry("auto")
    await _setup(hass, entry)
    await hass.services.async_call(DOMAIN, "confirm_hub", {"device": "192.0.2.6", "type": "access_point", "name": "Hall AP"}, blocking=True)
    # A UniFi style tracker reports the TV on the AP's radio MAC (one byte off).
    hass.states.async_set("device_tracker.tv", "home", {"mac": TV_MAC, "ap_mac": "00:00:5f:00:53:05"})  # example-ok: synthetic test value
    await entry.runtime_data.async_refresh()
    tv = next(n for n in _node_states(hass).values() if n.attributes["mac"] == TV_MAC.upper())
    assert tv.attributes["link"] == "hub:hall_ap"
    assert tv.attributes["placement"] == "controller"


async def test_llm_tools(hass: HomeAssistant, fake_net) -> None:
    _network(fake_net)
    entry = _entry("auto")
    await _setup(hass, entry)
    await entry.runtime_data.async_refresh()

    assert any(api.id == DOMAIN for api in llm.async_get_apis(hass))
    ctx = llm.LLMContext(platform="test", context=None, language="en", assistant=None, device_id=None)
    api = await llm.async_get_api(hass, DOMAIN, ctx)
    assert "netorbit_get_map" in {t.name for t in api.tools}
    assert "Before any change" in api.api_prompt

    result = await api.async_call_tool(llm.ToolInput("netorbit_get_map", {}))
    assert {h["name"] for h in result["hubs"]} >= {"Router", "core-switch"}
    assert any(d["name"] == "living-room-tv" and d["placed_by"] == "snmp" for d in result["devices"])

    result = await api.async_call_tool(llm.ToolInput("netorbit_add_hub", {"name": "Attic AP", "type": "access_point", "parent": "core-switch"}))
    assert result["hub"] == "attic_ap"
    result = await api.async_call_tool(llm.ToolInput("netorbit_assign_devices", {"devices": ["nas", "nope"], "hub": "attic ap"}))
    assert result["assigned"] == ["nas"] and result["not_found"] == ["nope"]
    result = await api.async_call_tool(llm.ToolInput("netorbit_assign_devices", {"devices": ["nas"], "hub": "basement"}))
    assert "error" in result and "Hubs:" in result["error"]
    result = await api.async_call_tool(llm.ToolInput("netorbit_update_device", {"device": "nas", "name": "Backup NAS", "allowed_to_sleep": True}))
    assert result["device"] == "Backup NAS"
    nas = _node_states(hass)["Backup NAS"]
    assert nas.attributes["sleepy"] is True and nas.attributes["link"] == "hub:attic_ap"
    garage = _node_states(hass)["Attic AP"]
    assert garage.attributes["link"] == "hub:core_switch"
