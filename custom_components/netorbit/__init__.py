"""NetOrbit: a live radial map of your home network."""

from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType

from .const import (
    CARD_FILENAME,
    CARD_URL,
    CONF_DEVICES,
    CONF_IGNORED,
    DOMAIN,
    SERVICE_IGNORE,
    SERVICE_SCAN,
    SERVICE_TRACK,
    VERSION,
)
from .coordinator import NetOrbitCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type NetOrbitConfigEntry = ConfigEntry[NetOrbitCoordinator]

_TARGET = {
    vol.Optional("mac"): cv.string,
    vol.Optional("ip"): cv.string,
    vol.Optional("config_entry_id"): cv.string,
}
TRACK_SCHEMA = vol.Schema(
    {
        **_TARGET,
        vol.Optional("name"): cv.string,
        vol.Optional("icon"): cv.icon,
        vol.Optional("hub"): cv.string,
        vol.Optional("sleepy"): cv.boolean,
    }
)
IGNORE_SCHEMA = vol.Schema(_TARGET)
SCAN_SCHEMA = vol.Schema({vol.Optional("config_entry_id"): cv.string})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the card and the services once."""
    await _register_card(hass)

    async def _track(call: ServiceCall) -> None:
        entry, coord = _resolve(hass, call)
        key = coord.find_key(call.data.get("mac"), call.data.get("ip"))
        if key is None:
            if not call.data.get("ip"):
                raise ServiceValidationError("Give a MAC or IP address")
            key = f"ip:{call.data['ip']}"
        devices = dict(entry.options.get(CONF_DEVICES, {}))
        cfg = dict(devices.get(key, {}))
        cfg["tracked"] = True
        if call.data.get("ip"):
            cfg["host"] = call.data["ip"]
        for field in ("name", "icon", "hub", "sleepy"):
            if field in call.data:
                cfg[field] = call.data[field]
        devices[key] = cfg
        ignored = [k for k in entry.options.get(CONF_IGNORED, []) if k != key]
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_DEVICES: devices, CONF_IGNORED: ignored}
        )

    async def _ignore(call: ServiceCall) -> None:
        entry, coord = _resolve(hass, call)
        key = coord.find_key(call.data.get("mac"), call.data.get("ip"))
        if key is None:
            raise ServiceValidationError("Device not found")
        ignored = list(dict.fromkeys([*entry.options.get(CONF_IGNORED, []), key]))
        devices = {k: v for k, v in entry.options.get(CONF_DEVICES, {}).items() if k != key}
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_DEVICES: devices, CONF_IGNORED: ignored}
        )

    async def _scan(call: ServiceCall) -> None:
        _entry, coord = _resolve(hass, call)
        coord.request_sweep()
        await coord.async_request_refresh()

    async_register_admin_service(hass, DOMAIN, SERVICE_TRACK, _track, TRACK_SCHEMA)
    async_register_admin_service(hass, DOMAIN, SERVICE_IGNORE, _ignore, IGNORE_SCHEMA)
    async_register_admin_service(hass, DOMAIN, SERVICE_SCAN, _scan, SCAN_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NetOrbitConfigEntry) -> bool:
    """Set up NetOrbit from a config entry."""
    coordinator = NetOrbitCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NetOrbitConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _options_updated(hass: HomeAssistant, entry: NetOrbitConfigEntry) -> None:
    coordinator = entry.runtime_data
    coordinator.apply_options(entry)
    await coordinator.async_refresh()


def _resolve(hass: HomeAssistant, call: ServiceCall) -> tuple[NetOrbitConfigEntry, NetOrbitCoordinator]:
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    wanted = call.data.get("config_entry_id")
    if wanted:
        entries = [e for e in entries if e.entry_id == wanted]
    if not entries:
        raise ServiceValidationError("No loaded NetOrbit entry found")
    if len(entries) > 1 and not wanted:
        raise ServiceValidationError("More than one NetOrbit entry; pass config_entry_id")
    return entries[0], entries[0].runtime_data


async def _register_card(hass: HomeAssistant) -> None:
    """Serve the bundled card and load it on every dashboard."""
    if hass.http is None:
        return
    path = Path(__file__).parent / "frontend" / CARD_FILENAME
    from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(path), True)])
    if "frontend" not in hass.config.components:
        return
    from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415

    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
