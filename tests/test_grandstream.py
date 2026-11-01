"""Grandstream GWN access points: Wi-Fi clients from the AP's own SNMP client table land under that AP."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from homeassistant.core import HomeAssistant

from custom_components.netorbit.snmp import GRANDSTREAM_OID_PREFIX, OID_GWN_CLIENT_IP, OID_GWN_CLIENT_MAC, ProbeResult, SnmpClient, is_grandstream, parse_mac

from .conftest import GATEWAY
from .test_integration import _entry, _node_states, _setup

GW_MAC = "00:00:5e:00:53:01"
AP_MAC = "00:00:5e:00:53:06"
PHONE_MAC = "00:00:5e:00:53:40"
LAPTOP_MAC = "00:00:5e:00:53:41"
AP_IP = "192.0.2.6"
GWN_PROBE = ProbeResult(descr="Grandstream GWN access point", name="ap-1", bridge=False, object_id=f"{GRANDSTREAM_OID_PREFIX}.1.1")


def _tuple(oid: str) -> tuple[int, ...]:
    return tuple(int(x) for x in oid.split("."))


def _mac_tuple(mac: str) -> tuple[int, ...]:
    return tuple(int(x, 16) for x in mac.split(":"))


class Octets:
    """Stands in for pysnmp's OctetString: only the raw bytes are needed."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def asOctets(self) -> bytes:  # noqa: N802
        return self._data


def _client(rows_by_base: dict[str, object]) -> SnmpClient:
    """A SnmpClient whose walks return canned rows: {base oid: [(oid tuple, value)] or an Exception}."""

    async def bulk_walk_cmd(_engine, _comm, _target, _ctx, _nr, _mr, objtype, lexicographicMode=False):  # noqa: N803
        base = objtype.base
        rows = rows_by_base.get(base, [])
        if isinstance(rows, Exception):
            raise rows
        if rows == "error":
            yield "timeout", 0, 0, []
            return
        yield None, 0, 0, list(rows)

    async def create(_addr, timeout=1.0, retries=0):  # noqa: ARG001
        return object()

    mod = SimpleNamespace(
        bulk_walk_cmd=bulk_walk_cmd,
        ObjectType=lambda ident: SimpleNamespace(base=ident),
        ObjectIdentity=lambda oid: oid,
        CommunityData=lambda *a, **k: None,
        ContextData=lambda: None,
        UdpTransportTarget=SimpleNamespace(create=create),
    )
    client = SnmpClient(hass=None)
    client._mod, client._engine = mod, object()
    return client


def _row(mac: str, value) -> tuple[tuple[int, ...], object]:
    return _tuple(OID_GWN_CLIENT_MAC) + _mac_tuple(mac), value


def test_parse_mac_forms() -> None:
    raw = bytes.fromhex("00005e005306")
    for value in (raw, bytearray(raw), Octets(raw), "00:00:5E:00:53:06", "00-00-5e-00-53-06", "00005e005306", "0x00005e005306",
                  "00:00:5e:00:53:06 ", Octets(b"00:00:5e:00:53:06")):
        assert parse_mac(value) == AP_MAC, value
    for bad in (None, b"", b"\x00\x01", "not a mac", "00:00:5e", 12, Octets(b"\xff\xfe\xfd\xfc\xfb\xfa\xf9")):
        assert parse_mac(bad) is None, bad


def test_is_grandstream() -> None:
    assert is_grandstream(f"{GRANDSTREAM_OID_PREFIX}.1.1")
    assert is_grandstream(f".{GRANDSTREAM_OID_PREFIX}")
    assert is_grandstream(None, "Grandstream GWN7660")
    assert not is_grandstream("1.3.6.1.4.1.423970.1")  # a different enterprise that merely starts with the digits
    assert not is_grandstream("1.3.6.1.4.1.41112.1.6", "UniFi AP")


async def test_walk_raw_bytes_and_text_macs() -> None:
    client = _client({OID_GWN_CLIENT_MAC: [
        _row(PHONE_MAC, Octets(bytes.fromhex("00005e005340"))),   # raw 6 bytes
        _row(LAPTOP_MAC, "00:00:5E:00:53:41"),                     # text
    ]})
    assert await client.wireless_clients(AP_IP, "public") == {PHONE_MAC, LAPTOP_MAC}


async def test_walk_takes_mac_from_the_row_index_when_the_value_is_unreadable() -> None:
    client = _client({OID_GWN_CLIENT_MAC: [_row(PHONE_MAC, Octets(b""))]})
    assert await client.wireless_clients(AP_IP, "public") == {PHONE_MAC}


async def test_walk_falls_back_to_the_ip_column() -> None:
    """If the MAC column is hidden (index only), the IP column's row index carries the MAC."""
    client = _client({
        OID_GWN_CLIENT_MAC: [],
        OID_GWN_CLIENT_IP: [(_tuple(OID_GWN_CLIENT_IP) + _mac_tuple(PHONE_MAC), "192.0.2.40")],
    })
    assert await client.wireless_clients(AP_IP, "public") == {PHONE_MAC}


async def test_empty_table_is_an_empty_set_not_an_error() -> None:
    assert await _client({}).wireless_clients(AP_IP, "public") == set()


async def test_ignores_rows_outside_the_table() -> None:
    client = _client({OID_GWN_CLIENT_MAC: [((1, 3, 6, 1, 2, 1, 1, 1, 0), "other"), _row(PHONE_MAC, "00:00:5e:00:53:40")]})
    assert await client.wireless_clients(AP_IP, "public") == {PHONE_MAC}


async def test_walk_error_and_timeout_do_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    assert await _client({OID_GWN_CLIENT_MAC: "error"}).wireless_clients(AP_IP, "public") is None
    assert await _client({OID_GWN_CLIENT_MAC: TimeoutError("no answer")}).wireless_clients(AP_IP, "public") is None
    assert await _client({OID_GWN_CLIENT_MAC: OSError("unreachable")}).wireless_clients(AP_IP, "public") is None


async def test_unavailable_pysnmp_returns_none() -> None:
    client = SnmpClient(hass=None)

    async def no(): return False  # noqa: E704
    client._ensure = no  # type: ignore[method-assign]
    assert await client.wireless_clients(AP_IP, "public") is None


def _network(fake_net) -> None:
    """Router .1 and a Grandstream AP .6 (no switch tables). A phone and a laptop are on its Wi-Fi."""
    fake_net.alive = {GATEWAY, AP_IP, "192.0.2.40", "192.0.2.41"}
    fake_net.arp = {GATEWAY: GW_MAC, AP_IP: AP_MAC, "192.0.2.40": PHONE_MAC, "192.0.2.41": LAPTOP_MAC}
    fake_net.dns = {AP_IP: "ap-1.lan", "192.0.2.40": "phone.lan", "192.0.2.41": "laptop.lan"}
    fake_net.vendors = {"00:00:5E": "Grandstream Networks"}
    fake_net.snmp = {AP_IP: ("public", GWN_PROBE)}


async def test_wifi_clients_land_under_the_grandstream_ap(hass: HomeAssistant, fake_net) -> None:
    _network(fake_net)
    fake_net.wifi = {AP_IP: {PHONE_MAC}}
    entry = _entry("auto")
    await _setup(hass, entry)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    hubs = {h["name"]: h for h in entry.options["hubs"]}
    assert "ap-1" in hubs and hubs["ap-1"]["type"] == "access_point", hubs
    nodes = _node_states(hass)
    assert nodes["phone"].attributes["link"] == f"hub:{hubs['ap-1']['id']}"
    assert nodes["phone"].attributes["placement"] == "snmp"
    # The laptop is not in the AP's client list, so nothing places it.
    assert nodes["laptop"].attributes["link"] == "hub:gateway"
    assert nodes["laptop"].attributes["placement"] == "none"


async def test_manual_placement_beats_the_ap_client_list(hass: HomeAssistant, fake_net) -> None:
    _network(fake_net)
    fake_net.wifi = {AP_IP: {PHONE_MAC}}
    entry = _entry("auto")
    await _setup(hass, entry)
    await entry.runtime_data.async_refresh()
    await hass.services.async_call("netorbit", "assign_device", {"device": ["phone"], "hub": "Router"}, blocking=True, return_response=True)
    phone = _node_states(hass)["phone"]
    assert phone.attributes["link"] == "hub:gateway" and phone.attributes["placement"] == "manual"


async def test_unreadable_client_table_does_not_break_the_map(hass: HomeAssistant, fake_net) -> None:
    _network(fake_net)
    fake_net.wifi = {AP_IP: None}  # walk failed
    entry = _entry("auto")
    await _setup(hass, entry)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    nodes = _node_states(hass)
    assert nodes["phone"].attributes["link"] == "hub:gateway" and nodes["phone"].attributes["placement"] == "none"


async def test_other_vendors_are_not_asked_for_a_client_table(hass: HomeAssistant, fake_net) -> None:
    _network(fake_net)
    fake_net.snmp = {AP_IP: ("public", ProbeResult(descr="Some other AP", name="ap-1", bridge=False, object_id="1.3.6.1.4.1.41112.1.6"))}
    fake_net.wifi = {AP_IP: {PHONE_MAC}}
    entry = _entry("auto")
    await _setup(hass, entry)
    await entry.runtime_data.async_refresh()
    assert _node_states(hass)["phone"].attributes["placement"] == "none"
