"""DHCP: things keep their identity when their IP changes, and settings can be exported and restored."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.netorbit.const import DOMAIN

from .conftest import GATEWAY
from .test_dhcp_helpers import advance
from .test_integration import _entry, _node_states, _setup

AP = "00:00:5f:00:53:04"
TV = "00:00:5e:00:53:10"
NEW = "00:00:5e:00:53:30"


async def test_device_keeps_name_and_hub_when_ip_changes(hass: HomeAssistant, fake_net, freezer) -> None:
    fake_net.alive = {GATEWAY, "192.0.2.6", "192.0.2.10"}
    fake_net.arp = {"192.0.2.6": AP, "192.0.2.10": TV}
    entry = _entry("auto")
    await _setup(hass, entry)
    await hass.services.async_call(DOMAIN, "confirm_hub", {"device": "192.0.2.6", "name": "Hall AP"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_device", {"device": "192.0.2.10", "hub": "Hall AP"}, blocking=True)
    await hass.services.async_call(DOMAIN, "track_device", {"mac": TV, "name": "Living Room TV"}, blocking=True)

    # DHCP hands the TV and the AP new addresses; the old ARP entries linger.
    fake_net.alive = {GATEWAY, "192.0.2.66", "192.0.2.77"}
    fake_net.arp = {"192.0.2.6": AP, "192.0.2.66": AP, "192.0.2.10": TV, "192.0.2.77": TV}
    await advance(hass, freezer, 301)

    nodes = _node_states(hass)
    tv = nodes["Living Room TV"].attributes
    assert tv["ip"] == "192.0.2.77" and tv["link"] == "hub:hall_ap" and tv["ip_changes"] == 1
    assert nodes["Living Room TV"].state == "online"
    hall = nodes["Hall AP"].attributes
    assert hall["ip"] == "192.0.2.66" and hall["ip_changes"] == 1
    assert nodes["Hall AP"].state == "online"
    assert next(h for h in entry.options["hubs"] if h["id"] == "hall_ap")["host"] == "192.0.2.66"


async def test_device_added_by_ip_switches_to_its_mac(hass: HomeAssistant, fake_net, freezer) -> None:
    fake_net.alive = {GATEWAY}
    fake_net.arp = {}
    entry = _entry("manual")
    await _setup(hass, entry)
    await hass.services.async_call(DOMAIN, "track_device", {"ip": "192.0.2.40", "name": "Garden Cam", "sleepy": True}, blocking=True)
    assert "ip:192.0.2.40" in entry.options["devices"]

    fake_net.alive.add("192.0.2.40")
    fake_net.arp = {"192.0.2.40": NEW}
    await advance(hass, freezer, 301)
    assert "ip:192.0.2.40" not in entry.options["devices"]
    assert entry.options["devices"][NEW]["name"] == "Garden Cam"

    # Now DHCP moves it, and it is still the same device.
    fake_net.alive = {GATEWAY, "192.0.2.41"}
    fake_net.arp = {"192.0.2.41": NEW}
    await advance(hass, freezer, 301)
    cams = [s for s in _node_states(hass).values() if s.attributes["label"] == "Garden Cam"]
    assert len(cams) == 1
    cam = cams[0]
    assert cam.attributes["ip"] == "192.0.2.41" and cam.attributes["sleepy"] is True and cam.state == "online"


async def test_export_and_import(hass: HomeAssistant, fake_net) -> None:
    fake_net.alive = {GATEWAY, "192.0.2.6", "192.0.2.10"}
    fake_net.arp = {"192.0.2.6": AP, "192.0.2.10": TV}
    entry = _entry("auto")
    await _setup(hass, entry)
    await hass.services.async_call(DOMAIN, "confirm_hub", {"device": "192.0.2.6", "name": "Hall AP"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_device", {"device": TV, "hub": "Hall AP"}, blocking=True)
    await hass.services.async_call(DOMAIN, "track_device", {"mac": TV, "name": "Living Room TV", "icon": "mdi:television"}, blocking=True)
    exported = await hass.services.async_call(DOMAIN, "export_config", {}, blocking=True, return_response=True)
    assert exported["devices"][TV]["name"] == "Living Room TV"
    assert "192.0.2" not in str(exported["devices"])  # devices are keyed by MAC, not IP

    # Wipe everything back to defaults, then restore.
    await hass.services.async_call(DOMAIN, "remove_hub", {"hub": "Hall AP"}, blocking=True)
    await hass.services.async_call(DOMAIN, "reset_placement", {"device": TV}, blocking=True)
    res = await hass.services.async_call(DOMAIN, "import_config", {"data": exported}, blocking=True, return_response=True)
    assert res["hubs"] == 2
    tv = _node_states(hass)["Living Room TV"].attributes
    assert tv["link"] == "hub:hall_ap" and tv["icon"] == "mdi:television"

    bad = await hass.services.async_call(DOMAIN, "export_config", {}, blocking=True, return_response=True)
    bad["netorbit_export"] = 99
    import pytest  # noqa: PLC0415
    from homeassistant.exceptions import ServiceValidationError  # noqa: PLC0415

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "import_config", {"data": bad}, blocking=True)
