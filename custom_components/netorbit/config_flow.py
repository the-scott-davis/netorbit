"""Config and options flows for NetOrbit."""

from __future__ import annotations

import ipaddress
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector as sel

from .const import (
    CONF_DEVICES,
    CONF_DISCOVERY_INTERVAL,
    CONF_GATEWAY,
    CONF_HUBS,
    CONF_IGNORE_RANDOM_MAC,
    CONF_IGNORED,
    CONF_MODE,
    CONF_PING_INTERVAL,
    CONF_STALE_HOURS,
    CONF_SUBNET,
    DEFAULT_DISCOVERY_INTERVAL,
    DEFAULT_IGNORE_RANDOM_MAC,
    DEFAULT_MODE,
    DEFAULT_PING_INTERVAL,
    DEFAULT_STALE_HOURS,
    DOMAIN,
    HUB_ROUTER,
    HUB_TYPES,
    MAX_HOSTS,
    MIN_PING_INTERVAL,
    MODES,
    ROOT_HUB_ID,
)
from .coordinator import options_with_defaults
from .logic import slugify_id, validate_subnet

NONE_VALUE = "__none__"


async def _default_subnet(hass) -> tuple[str, str]:
    """Best guess at the LAN subnet and gateway from Home Assistant's network settings."""
    try:
        from homeassistant.components import network  # noqa: PLC0415

        for adapter in await network.async_get_adapters(hass):
            if not adapter["enabled"]:
                continue
            for ip in adapter["ipv4"]:
                net = ipaddress.ip_network(f"{ip['address']}/{ip['network_prefix']}", strict=False)
                if net.is_private and not net.is_loopback:
                    return str(net), str(next(net.hosts()))
    except Exception:  # noqa: BLE001
        pass
    return "192.168.0.0/24", "192.168.0.1"


def _int_box(minimum: int, maximum: int, unit: str) -> sel.NumberSelector:
    return sel.NumberSelector(
        sel.NumberSelectorConfig(min=minimum, max=maximum, step=1, mode=sel.NumberSelectorMode.BOX, unit_of_measurement=unit)
    )


def _select(options: list[str] | list[dict[str, str]], key: str | None = None, multiple: bool = False) -> sel.SelectSelector:
    config = sel.SelectSelectorConfig(options=options, multiple=multiple, mode=sel.SelectSelectorMode.DROPDOWN)
    if key:
        config["translation_key"] = key
    return sel.SelectSelector(config)


class NetOrbitConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup: which network to watch."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        default_subnet, default_gw = await _default_subnet(self.hass)
        if user_input is not None:
            try:
                subnet = validate_subnet(user_input[CONF_SUBNET], MAX_HOSTS)
            except ValueError as err:
                errors[CONF_SUBNET] = "subnet_too_large" if str(err) == "too_large" else "invalid_subnet"
            else:
                gateway = user_input[CONF_GATEWAY].strip()
                try:
                    if ipaddress.ip_address(gateway) not in ipaddress.ip_network(subnet):
                        errors[CONF_GATEWAY] = "gateway_outside"
                except ValueError:
                    errors[CONF_GATEWAY] = "invalid_ip"
                if not errors:
                    await self.async_set_unique_id(subnet)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="NetOrbit",
                        data={CONF_SUBNET: subnet, CONF_GATEWAY: gateway},
                        options={
                            CONF_MODE: user_input[CONF_MODE],
                            CONF_PING_INTERVAL: int(user_input[CONF_PING_INTERVAL]),
                            CONF_DISCOVERY_INTERVAL: DEFAULT_DISCOVERY_INTERVAL,
                            CONF_STALE_HOURS: DEFAULT_STALE_HOURS,
                            CONF_IGNORE_RANDOM_MAC: DEFAULT_IGNORE_RANDOM_MAC,
                            CONF_HUBS: [
                                {"id": ROOT_HUB_ID, "name": "Router", "host": gateway, "type": HUB_ROUTER, "parent": None}
                            ],
                            CONF_DEVICES: {},
                            CONF_IGNORED: [],
                        },
                    )
        schema = vol.Schema(
            {
                vol.Required(CONF_SUBNET, default=default_subnet): str,
                vol.Required(CONF_GATEWAY, default=default_gw): str,
                vol.Required(CONF_MODE, default=DEFAULT_MODE): _select(MODES, "mode"),
                vol.Required(CONF_PING_INTERVAL, default=DEFAULT_PING_INTERVAL): _int_box(MIN_PING_INTERVAL, 3600, "s"),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> NetOrbitOptionsFlow:
        return NetOrbitOptionsFlow()


class NetOrbitOptionsFlow(OptionsFlow):
    """Settings, hubs and devices."""

    def __init__(self) -> None:
        self._opts: dict[str, Any] | None = None
        self._hub_id: str | None = None
        self._device_key: str | None = None

    @property
    def opts(self) -> dict[str, Any]:
        if self._opts is None:
            self._opts = options_with_defaults(self.config_entry)
            self._opts[CONF_HUBS] = [dict(h) for h in self._opts[CONF_HUBS]]
            self._opts[CONF_DEVICES] = {k: dict(v) for k, v in self._opts[CONF_DEVICES].items()}
            self._opts[CONF_IGNORED] = list(self._opts[CONF_IGNORED])
        return self._opts

    def _coordinator(self):
        return getattr(self.config_entry, "runtime_data", None)

    def _save(self) -> ConfigFlowResult:
        return self.async_create_entry(data=self.opts)

    def _hub_choices(self, exclude: str | None = None) -> list[dict[str, str]]:
        return [
            {"value": h["id"], "label": h.get("name") or h["id"]}
            for h in self.opts[CONF_HUBS]
            if h["id"] != exclude
        ]

    def _tracked_choices(self) -> list[dict[str, str]]:
        coord = self._coordinator()
        if not coord or not coord.data:
            return []
        out = []
        for key, node in sorted(coord.data.nodes.items(), key=lambda kv: kv[1].name.lower()):
            if node.kind == "device":
                out.append({"value": key, "label": f"{node.name} ({node.ip or 'no IP'})"})
        return out

    def _untracked_choices(self) -> list[dict[str, str]]:
        coord = self._coordinator()
        if not coord or not coord.data:
            return []
        tracked = set(coord.data.nodes)
        out = []
        for key, rec in sorted(coord._seen.items(), key=lambda kv: kv[1].get("ip") or ""):  # noqa: SLF001
            if key.startswith("hub:") or key in tracked or not rec.get("discovered"):
                continue
            label = coord._discovered_name(key, rec)  # noqa: SLF001
            out.append({"value": key, "label": f"{label} ({rec.get('ip') or 'no IP'})"})
        return out

    # ----- menu ------------------------------------------------------------------

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        menu = ["settings", "add_hub", "edit_hub", "add_device", "edit_device"]
        if self._untracked_choices():
            menu.append("review_new")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self.opts.update(
                {
                    CONF_MODE: user_input[CONF_MODE],
                    CONF_PING_INTERVAL: int(user_input[CONF_PING_INTERVAL]),
                    CONF_DISCOVERY_INTERVAL: int(user_input[CONF_DISCOVERY_INTERVAL]),
                    CONF_STALE_HOURS: int(user_input[CONF_STALE_HOURS]),
                    CONF_IGNORE_RANDOM_MAC: user_input[CONF_IGNORE_RANDOM_MAC],
                }
            )
            return self._save()
        o = self.opts
        schema = vol.Schema(
            {
                vol.Required(CONF_MODE, default=o[CONF_MODE]): _select(MODES, "mode"),
                vol.Required(CONF_PING_INTERVAL, default=o[CONF_PING_INTERVAL]): _int_box(MIN_PING_INTERVAL, 3600, "s"),
                vol.Required(CONF_DISCOVERY_INTERVAL, default=o[CONF_DISCOVERY_INTERVAL]): _int_box(60, 86400, "s"),
                vol.Required(CONF_STALE_HOURS, default=o[CONF_STALE_HOURS]): _int_box(1, 720, "h"),
                vol.Required(CONF_IGNORE_RANDOM_MAC, default=o[CONF_IGNORE_RANDOM_MAC]): bool,
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)

    # ----- hubs ------------------------------------------------------------------

    def _hub_schema(self, hub: dict[str, Any], exclude: str | None, root: bool) -> vol.Schema:
        fields: dict[Any, Any] = {
            vol.Required("name", default=hub.get("name", "")): str,
            vol.Optional("host", description={"suggested_value": hub.get("host")}): str,
            vol.Required("type", default=hub.get("type", "access_point")): _select(HUB_TYPES, "hub_type"),
        }
        if not root:
            fields[vol.Required("parent", default=hub.get("parent") or ROOT_HUB_ID)] = _select(self._hub_choices(exclude))
        return vol.Schema(fields)

    async def async_step_add_hub(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = (user_input.get("host") or "").strip() or None
            if host and not _valid_ip(host):
                errors["host"] = "invalid_ip"
            else:
                base = slugify_id(user_input["name"])
                ids = {h["id"] for h in self.opts[CONF_HUBS]}
                hub_id, n = base, 2
                while hub_id in ids:
                    hub_id, n = f"{base}_{n}", n + 1
                self.opts[CONF_HUBS].append(
                    {"id": hub_id, "name": user_input["name"], "host": host, "type": user_input["type"], "parent": user_input["parent"]}
                )
                return self._save()
        return self.async_show_form(step_id="add_hub", data_schema=self._hub_schema({}, None, False), errors=errors)

    async def async_step_edit_hub(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._hub_id = user_input["hub"]
            return await self.async_step_edit_hub_details()
        return self.async_show_form(
            step_id="edit_hub", data_schema=vol.Schema({vol.Required("hub"): _select(self._hub_choices())})
        )

    async def async_step_edit_hub_details(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        hub = next(h for h in self.opts[CONF_HUBS] if h["id"] == self._hub_id)
        root = hub["id"] == ROOT_HUB_ID
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get("remove") and not root:
                self.opts[CONF_HUBS] = [h for h in self.opts[CONF_HUBS] if h["id"] != hub["id"]]
                for h in self.opts[CONF_HUBS]:
                    if h.get("parent") == hub["id"]:
                        h["parent"] = hub.get("parent") or ROOT_HUB_ID
                for cfg in self.opts[CONF_DEVICES].values():
                    if cfg.get("hub") == hub["id"]:
                        cfg["hub"] = hub.get("parent") or ROOT_HUB_ID
                return self._save()
            host = (user_input.get("host") or "").strip() or None
            if host and not _valid_ip(host):
                errors["host"] = "invalid_ip"
            elif not root and _creates_cycle(self.opts[CONF_HUBS], hub["id"], user_input["parent"]):
                errors["parent"] = "hub_cycle"
            else:
                hub.update({"name": user_input["name"], "host": host, "type": user_input["type"]})
                if not root:
                    hub["parent"] = user_input["parent"]
                return self._save()
        schema = self._hub_schema(hub, hub["id"], root)
        if not root:
            schema = schema.extend({vol.Optional("remove", default=False): bool})
        return self.async_show_form(
            step_id="edit_hub_details", data_schema=schema, errors=errors,
            description_placeholders={"hub": hub.get("name") or hub["id"]},
        )

    # ----- devices ---------------------------------------------------------------

    def _device_fields(self, cfg: dict[str, Any]) -> dict[Any, Any]:
        return {
            vol.Optional("name", description={"suggested_value": cfg.get("name")}): str,
            vol.Optional("icon", description={"suggested_value": cfg.get("icon")}): sel.IconSelector(),
            vol.Required("hub", default=cfg.get("hub") or ROOT_HUB_ID): _select(self._hub_choices()),
            vol.Required("sleepy", default=bool(cfg.get("sleepy", False))): bool,
        }

    async def async_step_add_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            picked = user_input.get("device")
            host = (user_input.get("host") or "").strip() or None
            if picked and picked != NONE_VALUE:
                key = picked
            elif host and _valid_ip(host):
                coord = self._coordinator()
                key = (coord.find_key(ip=host) if coord else None) or f"ip:{host}"
            else:
                errors["base"] = "pick_or_ip"
                key = None
            if key:
                cfg = self.opts[CONF_DEVICES].setdefault(key, {})
                cfg.update(_clean_device(user_input))
                cfg["tracked"] = True
                if host:
                    cfg["host"] = host
                if key in self.opts[CONF_IGNORED]:
                    self.opts[CONF_IGNORED].remove(key)
                return self._save()
        choices = [{"value": NONE_VALUE, "label": "Enter an IP address instead"}, *self._untracked_choices()]
        schema = vol.Schema(
            {
                vol.Optional("device", default=NONE_VALUE): _select(choices),
                vol.Optional("host"): str,
                **self._device_fields({}),
            }
        )
        return self.async_show_form(step_id="add_device", data_schema=schema, errors=errors)

    async def async_step_edit_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        choices = self._tracked_choices()
        if not choices:
            return self.async_abort(reason="no_devices")
        if user_input is not None:
            self._device_key = user_input["device"]
            return await self.async_step_edit_device_details()
        return self.async_show_form(
            step_id="edit_device", data_schema=vol.Schema({vol.Required("device"): _select(choices)})
        )

    async def async_step_edit_device_details(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        key = self._device_key
        cfg = dict(self.opts[CONF_DEVICES].get(key, {}))
        coord = self._coordinator()
        node = coord.data.nodes.get(key) if coord and coord.data else None
        if user_input is not None:
            if user_input.get("stop_tracking"):
                self.opts[CONF_DEVICES].pop(key, None)
                if key not in self.opts[CONF_IGNORED]:
                    self.opts[CONF_IGNORED].append(key)
                return self._save()
            new_cfg = self.opts[CONF_DEVICES].setdefault(key, {})
            new_cfg.update(_clean_device(user_input))
            for field in ("name", "icon"):
                if not user_input.get(field):
                    new_cfg.pop(field, None)
            new_cfg["tracked"] = True
            return self._save()
        if node:
            cfg.setdefault("hub", node.link or ROOT_HUB_ID)
        schema = vol.Schema({**self._device_fields(cfg), vol.Optional("stop_tracking", default=False): bool})
        return self.async_show_form(
            step_id="edit_device_details", data_schema=schema,
            description_placeholders={"device": node.name if node else key, "ip": (node.ip if node else None) or "unknown"},
        )

    async def async_step_review_new(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        choices = self._untracked_choices()
        if not choices:
            return self.async_abort(reason="no_new_devices")
        if user_input is not None:
            for key in user_input.get("track", []):
                self.opts[CONF_DEVICES].setdefault(key, {})["tracked"] = True
            for key in user_input.get("ignore", []):
                if key not in user_input.get("track", []) and key not in self.opts[CONF_IGNORED]:
                    self.opts[CONF_IGNORED].append(key)
            return self._save()
        schema = vol.Schema(
            {
                vol.Optional("track", default=[]): _select(choices, multiple=True),
                vol.Optional("ignore", default=[]): _select(choices, multiple=True),
            }
        )
        return self.async_show_form(step_id="review_new", data_schema=schema)


def _clean_device(user_input: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"hub": user_input.get("hub") or ROOT_HUB_ID, "sleepy": bool(user_input.get("sleepy"))}
    if user_input.get("name"):
        out["name"] = user_input["name"].strip()
    if user_input.get("icon"):
        out["icon"] = user_input["icon"]
    return out


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _creates_cycle(hubs: list[dict[str, Any]], hub_id: str, new_parent: str) -> bool:
    parents = {h["id"]: h.get("parent") for h in hubs}
    parents[hub_id] = new_parent
    seen = set()
    cur: str | None = hub_id
    while cur:
        if cur in seen:
            return True
        seen.add(cur)
        cur = parents.get(cur)
    return False
