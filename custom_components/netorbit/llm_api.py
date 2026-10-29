"""NetOrbit tools for AI assistants.

Registered as an LLM API, so it shows up:
* in Home Assistant's MCP Server integration (for Claude Desktop, ChatGPT and other MCP clients),
* in conversation agents such as the OpenAI and Anthropic integrations.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, llm
from homeassistant.util.json import JsonObjectType

from . import actions
from .const import DOMAIN, HUB_TYPES
from .manage import ManageError

API_ID = DOMAIN
API_NAME = "NetOrbit network map"

PROMPT = """You are helping someone build a map of their home network in NetOrbit, a Home Assistant integration.

How the map works:
- Hubs are routers, switches, access points (APs) and mesh nodes. Devices hang off the hub they connect through.
- NetOrbit finds devices and many hubs by itself. Placements come from: "manual" (a person chose it, always wins),
  "controller" (a UniFi or similar integration), "snmp" (a managed switch's MAC table) or "none" (shown under the router).
- Suggested hubs are devices NetOrbit thinks are network gear but is not sure about.

How to help:
1. Call netorbit_get_map first and summarize it in plain words: hubs found, how many devices sit under each, how many are
   still under the router with placed_by "none", and any suggested hubs. Avoid jargon. Never show MAC addresses unless asked.
2. Ask what network gear they have (router brand, mesh system or separate access points, any switches). Offer to confirm
   or dismiss suggested hubs and to add missing hubs.
3. For each AP or mesh node, ask them to open its client list and copy or screenshot it:
   - mesh systems (eero, Google/Nest Wifi, Deco, Orbi, Velop): the device or client list in the brand's phone app,
   - standalone APs and prosumer gear: the "Clients" or "Wireless clients" page in its web admin,
   - managed switches: the MAC address table page.
   Brand menus change often; describe where such lists usually live and let them find it.
4. Read the MAC and IP addresses out of what they paste or show you and call netorbit_import_client_list with the hub
   and the text, or netorbit_assign_devices with names, IPs or MACs. Report what matched and what did not.
5. Phones and laptops roam between APs and often use private addresses, so placing them is optional. TVs, cameras,
   speakers and smart home gear stay put and are worth placing.
6. Before any change, say what you are about to do in one sentence and get a yes. Batch changes where you can.
"""


def _entry_coord(hass: HomeAssistant):
    from . import resolve_entry  # noqa: PLC0415

    try:
        return resolve_entry(hass, None)
    except Exception as err:  # noqa: BLE001
        raise HomeAssistantError(str(err)) from err


class _Tool(llm.Tool):
    def __init__(self, name: str, description: str, parameters: vol.Schema, fn) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self._fn = fn

    async def async_call(self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext) -> JsonObjectType:
        entry, coord = _entry_coord(hass)
        try:
            result = await self._fn(hass, entry, coord, tool_input.tool_args)
        except ManageError as err:
            return {"error": str(err)}
        return result


def _tools() -> list[llm.Tool]:
    hub_type = vol.In(HUB_TYPES)
    return [
        _Tool(
            "netorbit_get_map",
            "Get the current network map: hubs, every device with the hub it connects through and how it was placed, "
            "new devices waiting to be tracked, and suggested hubs.",
            vol.Schema({}),
            lambda h, e, c, a: _sync(actions.network_map(c)),
        ),
        _Tool(
            "netorbit_assign_devices",
            "Place one or more devices under a hub. Devices can be given by name, IP or MAC. Manual placement overrides "
            "anything automatic.",
            vol.Schema({vol.Required("devices"): [cv.string], vol.Required("hub"): cv.string}),
            lambda h, e, c, a: actions.assign(h, e, c, a["devices"], a["hub"]),
        ),
        _Tool(
            "netorbit_import_client_list",
            "Place every device whose MAC or IP appears in pasted text (an AP's client table, an app's device list, a switch "
            "MAC table) under one hub. Unknown MACs are added as new devices.",
            vol.Schema({vol.Required("hub"): cv.string, vol.Required("text"): cv.string}),
            lambda h, e, c, a: actions.import_list(h, e, c, a["hub"], a["text"]),
        ),
        _Tool(
            "netorbit_reset_placement",
            "Undo manual placement so NetOrbit places these devices automatically again.",
            vol.Schema({vol.Required("devices"): [cv.string]}),
            lambda h, e, c, a: actions.reset(h, e, c, a["devices"]),
        ),
        _Tool(
            "netorbit_add_hub",
            "Add a hub (router, switch, access_point, mesh_node or other). Give an existing device to turn it into a hub, "
            "or a name with an optional IP/MAC. parent is the hub it connects to (defaults to the router).",
            vol.Schema({
                vol.Optional("device"): cv.string, vol.Optional("name"): cv.string,
                vol.Optional("type", default="access_point"): hub_type, vol.Optional("parent"): cv.string,
                vol.Optional("ip"): cv.string, vol.Optional("mac"): cv.string,
            }),
            lambda h, e, c, a: actions.add_hub(h, e, c, a.get("name"), a.get("type", "access_point"), a.get("parent"), a.get("ip"), a.get("mac"), a.get("device")),
        ),
        _Tool(
            "netorbit_update_hub",
            "Rename a hub, change its type, or change which hub it connects to.",
            vol.Schema({vol.Required("hub"): cv.string, vol.Optional("name"): cv.string,
                        vol.Optional("type"): hub_type, vol.Optional("parent"): cv.string}),
            lambda h, e, c, a: actions.update_hub(h, e, c, a["hub"], name=a.get("name"), type=a.get("type"), parent=a.get("parent")),
        ),
        _Tool(
            "netorbit_remove_hub",
            "Remove a hub. Its devices move to the hub it connected to.",
            vol.Schema({vol.Required("hub"): cv.string}),
            lambda h, e, c, a: actions.remove_hub(h, e, c, a["hub"]),
        ),
        _Tool(
            "netorbit_confirm_hub",
            "Accept a suggested hub (or mark any device as a hub). Optionally set its type and name.",
            vol.Schema({vol.Required("device"): cv.string, vol.Optional("type"): hub_type, vol.Optional("name"): cv.string}),
            lambda h, e, c, a: actions.confirm_hub(h, e, c, a["device"], a.get("type"), a.get("name")),
        ),
        _Tool(
            "netorbit_dismiss_hub",
            "Reject a suggested hub so it is not suggested again.",
            vol.Schema({vol.Required("device"): cv.string}),
            lambda h, e, c, a: actions.dismiss_hub(h, e, c, a["device"]),
        ),
        _Tool(
            "netorbit_update_device",
            "Rename a device, set its icon (mdi:...), or mark it as allowed to sleep (no offline alerts).",
            vol.Schema({vol.Required("device"): cv.string, vol.Optional("name"): cv.string,
                        vol.Optional("icon"): cv.string, vol.Optional("allowed_to_sleep"): cv.boolean}),
            lambda h, e, c, a: actions.update_device(h, e, c, a["device"], a.get("name"), a.get("icon"), a.get("allowed_to_sleep")),
        ),
        _Tool(
            "netorbit_ignore_device",
            "Stop tracking a device and hide it from the map.",
            vol.Schema({vol.Required("device"): cv.string}),
            lambda h, e, c, a: actions.ignore(h, e, c, device=a["device"]),
        ),
        _Tool(
            "netorbit_scan_now",
            "Sweep the network for new devices and hubs right away.",
            vol.Schema({}),
            lambda h, e, c, a: _scan(c),
        ),
    ]


async def _sync(value: Any) -> Any:
    return value


async def _scan(coord) -> dict[str, Any]:
    coord.request_sweep(probe=True)
    await coord.async_refresh()
    return {"done": True, "devices": len(coord.data.nodes) if coord.data else 0}


class NetOrbitAPI(llm.API):
    """The API registered with Home Assistant."""

    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        return llm.APIInstance(api=self, api_prompt=PROMPT, llm_context=llm_context, tools=_tools())


@callback
def async_register_llm_api(hass: HomeAssistant) -> None:
    """Register once per Home Assistant instance."""
    if any(api.id == API_ID for api in llm.async_get_apis(hass)):
        return
    llm.async_register_api(hass, NetOrbitAPI(hass=hass, id=API_ID, name=API_NAME))
