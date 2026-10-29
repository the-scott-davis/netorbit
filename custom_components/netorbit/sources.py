"""Read hub and placement hints that other Home Assistant integrations already have."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .detect import NETWORK_DOMAINS
from .logic import normalize_mac


@dataclass
class RegistryInfo:
    """What another integration says about a MAC."""

    name: str | None
    model: str | None
    manufacturer: str | None
    domain: str | None


def registry_by_mac(hass: HomeAssistant) -> dict[str, RegistryInfo]:
    """Every device in Home Assistant that has a MAC connection, keyed by MAC."""
    reg = dr.async_get(hass)
    out: dict[str, RegistryInfo] = {}
    for dev in reg.devices.values():
        macs = [normalize_mac(v) for k, v in dev.connections if k == dr.CONNECTION_NETWORK_MAC]
        macs = [m for m in macs if m]
        if not macs:
            continue
        domain = None
        for entry_id in dev.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry and entry.domain in NETWORK_DOMAINS:
                domain = entry.domain
                break
            if entry and domain is None and entry.domain != "netorbit":
                domain = entry.domain
        info = RegistryInfo(
            name=dev.name_by_user or dev.name, model=dev.model, manufacturer=dev.manufacturer, domain=domain
        )
        for mac in macs:
            # Prefer entries from network integrations when a MAC appears twice.
            if mac not in out or (domain in NETWORK_DOMAINS and out[mac].domain not in NETWORK_DOMAINS):
                out[mac] = info
    return out


def client_access_points(hass: HomeAssistant) -> dict[str, str]:
    """{client mac: AP mac} from integrations that know which AP each client uses.

    * Any device_tracker exposing ``mac`` and ``ap_mac`` attributes (UniFi does).
    * Netgear's per-device ``conn_ap_mac`` sensors (Orbi and other mesh routers).
    """
    out: dict[str, str] = {}
    for state in hass.states.async_all("device_tracker"):
        ap = normalize_mac(state.attributes.get("ap_mac"))
        mac = normalize_mac(state.attributes.get("mac"))
        if ap and mac and state.state == "home":
            out[mac] = ap

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    for entry in ent_reg.entities.values():
        if entry.domain != "sensor" or not (entry.unique_id or "").endswith("conn_ap_mac"):
            continue
        state = hass.states.get(entry.entity_id)
        ap = normalize_mac(state.state) if state else None
        if not ap or not entry.device_id:
            continue
        dev = dev_reg.async_get(entry.device_id)
        if not dev:
            continue
        for kind, value in dev.connections:
            mac = normalize_mac(value) if kind == dr.CONNECTION_NETWORK_MAC else None
            if mac:
                out[mac] = ap
    return out


async def ssdp_types_by_ip(hass: HomeAssistant) -> dict[str, list[str]]:
    """{ip: [device types]} for devices that announced themselves over UPnP."""
    if "ssdp" not in hass.config.components:
        return {}
    try:
        from homeassistant.components import ssdp  # noqa: PLC0415
        from urllib.parse import urlparse  # noqa: PLC0415
    except ImportError:
        return {}
    out: dict[str, list[str]] = {}
    for st in (
        "urn:schemas-upnp-org:device:WLANAccessPointDevice:1",
        "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
        "urn:schemas-upnp-org:device:InternetGatewayDevice:2",
    ):
        try:
            infos = await ssdp.async_get_discovery_info_by_st(hass, st)
        except Exception:  # noqa: BLE001
            continue
        for info in infos:
            host = urlparse(info.ssdp_location or "").hostname
            if host:
                out.setdefault(host, []).append(info.upnp.get("deviceType") or st)
    return out
