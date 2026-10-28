"""Discovery, ping and status tracking for NetOrbit."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import logging
import socket
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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
    EVENT_DEVICE_RECOVERED,
    EVENT_DEVICE_STALE,
    EVENT_NEW_DEVICE,
    HUB_ICONS,
    HUB_OTHER,
    HUB_ROUTER,
    MODE_AUTO,
    ROOT_HUB_ID,
    STATUS_ONLINE,
    STATUS_STALE,
    STORAGE_VERSION,
)
from .logic import (
    compute_status,
    fallback_name,
    guess_icon,
    is_random_mac,
    normalize_mac,
    parse_proc_arp,
    short_hostname,
    subnet_hosts,
)

_LOGGER = logging.getLogger(__name__)

PING_COUNT = 2
PING_TIMEOUT = 1.5
SWEEP_TIMEOUT = 1.0
DNS_TIMEOUT = 2.0
DNS_REFRESH = timedelta(hours=12)


@dataclass
class Node:
    """A hub or device shown on the map."""

    key: str
    kind: str  # "hub" or "device"
    name: str
    ip: str | None = None
    mac: str | None = None
    icon: str = "mdi:lan-connect"
    link: str | None = None  # parent hub id
    sleepy: bool = False
    status: str = "recent"
    last_seen: str | None = None
    first_seen: str | None = None
    hostname: str | None = None
    source: str = "discovered"  # discovered | manual | hub
    hub_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Dict form for diagnostics and the card."""
        return asdict(self)


@dataclass
class NetOrbitData:
    """Everything the entities need after one update."""

    nodes: dict[str, Node] = field(default_factory=dict)
    new_devices: list[dict[str, Any]] = field(default_factory=list)
    last_scan: str | None = None
    scanning_supported: bool = True


def options_with_defaults(entry: ConfigEntry) -> dict[str, Any]:
    """Merge options over defaults so older entries keep working."""
    opts = dict(entry.options)
    opts.setdefault(CONF_MODE, DEFAULT_MODE)
    opts.setdefault(CONF_PING_INTERVAL, DEFAULT_PING_INTERVAL)
    opts.setdefault(CONF_DISCOVERY_INTERVAL, DEFAULT_DISCOVERY_INTERVAL)
    opts.setdefault(CONF_STALE_HOURS, DEFAULT_STALE_HOURS)
    opts.setdefault(CONF_IGNORE_RANDOM_MAC, DEFAULT_IGNORE_RANDOM_MAC)
    opts.setdefault(CONF_HUBS, [])
    opts.setdefault(CONF_DEVICES, {})
    opts.setdefault(CONF_IGNORED, [])
    if not any(h.get("id") == ROOT_HUB_ID for h in opts[CONF_HUBS]):
        opts[CONF_HUBS] = [
            {"id": ROOT_HUB_ID, "name": "Router", "host": entry.data[CONF_GATEWAY], "type": HUB_ROUTER, "parent": None},
            *opts[CONF_HUBS],
        ]
    return opts


class NetOrbitCoordinator(DataUpdateCoordinator[NetOrbitData]):
    """Pings tracked hosts every interval and sweeps the subnet for new ones."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.opts = options_with_defaults(entry)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=self.opts[CONF_PING_INTERVAL]),
        )
        self.subnet: str = entry.data[CONF_SUBNET]
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._seen: dict[str, dict[str, Any]] = {}
        self._initialized = False
        self._last_sweep: datetime | None = None
        self._prev_status: dict[str, str] = {}
        self._force_sweep = False
        self._privileged: bool | None = None
        self._sweep_lock = asyncio.Lock()

    # ----- lifecycle -------------------------------------------------------

    async def async_load(self) -> None:
        """Load persisted state and work out how we are allowed to ping."""
        data = await self._store.async_load() or {}
        self._seen = data.get("seen", {})
        self._initialized = data.get("initialized", False)
        self._privileged = await self._detect_privileges()

    async def _detect_privileges(self) -> bool | None:
        from icmplib import SocketPermissionError, async_ping  # noqa: PLC0415

        for privileged in (True, False):
            try:
                await async_ping("127.0.0.1", count=0, timeout=0, privileged=privileged)
            except SocketPermissionError:
                continue
            except Exception:  # noqa: BLE001
                return privileged
            return privileged
        _LOGGER.error("NetOrbit cannot open an ICMP socket; ping based presence is unavailable")
        return None

    @callback
    def apply_options(self, entry: ConfigEntry) -> None:
        """Use new options without reloading the entry."""
        self.opts = options_with_defaults(entry)
        self.update_interval = timedelta(seconds=self.opts[CONF_PING_INTERVAL])
        self._force_sweep = False

    def request_sweep(self) -> None:
        """Run a discovery sweep on the next update."""
        self._force_sweep = True

    def _save(self) -> None:
        self._store.async_delay_save(lambda: {"seen": self._seen, "initialized": self._initialized}, 10)

    # ----- update ------------------------------------------------------------

    async def _async_update_data(self) -> NetOrbitData:
        now = dt_util.utcnow()
        sweep_due = (
            self._force_sweep
            or self._last_sweep is None
            or now - self._last_sweep >= timedelta(seconds=self.opts[CONF_DISCOVERY_INTERVAL])
        )
        if self._privileged is None:
            raise UpdateFailed("ICMP sockets are not permitted on this system")
        try:
            if sweep_due:
                await self._sweep(now)
            alive = await self._ping_tracked()
        except OSError as err:
            raise UpdateFailed(f"Network error: {err}") from err

        for key, ip in alive:
            rec = self._seen.setdefault(key, {"first_seen": now.isoformat()})
            rec["last_seen"] = now.isoformat()
            if ip:
                rec["ip"] = ip
        self._save()
        data = self._build(now, {k for k, _ in alive})
        self._fire_transitions(data)
        return data

    async def _sweep(self, now: datetime) -> None:
        """Ping every address once, then read the ARP table to learn MACs."""
        from icmplib import async_multiping  # noqa: PLC0415

        async with self._sweep_lock:
            self._force_sweep = False
            hosts = subnet_hosts(self.subnet)
            results = await async_multiping(
                hosts, count=1, timeout=SWEEP_TIMEOUT, concurrent_tasks=128, privileged=self._privileged
            )
            replied = {h.address for h in results if h.is_alive}
            arp = await self.hass.async_add_executor_job(_read_arp)
            hub_ips = {h.get("host") for h in self.opts[CONF_HUBS]}
            ignored = set(self.opts[CONF_IGNORED])
            first_run = not self._initialized
            fresh: list[str] = []

            for ip in sorted(set(arp) | replied, key=_ip_sort):
                if ip in hub_ips or ip not in self._subnet_set(hosts):
                    continue
                mac = arp.get(ip)
                if mac is None:
                    continue  # answered ping but no MAC yet; picked up next sweep
                if self.opts[CONF_IGNORE_RANDOM_MAC] and is_random_mac(mac):
                    continue
                key = mac
                rec = self._seen.get(key)
                if rec is None:
                    rec = self._seen[key] = {"first_seen": now.isoformat(), "discovered": True}
                    if key not in ignored:
                        fresh.append(key)
                rec["mac"] = mac
                rec["ip"] = ip
                if ip in replied:
                    rec["last_seen"] = now.isoformat()

            await self._resolve_names(now)
            self._last_sweep = now
            self._initialized = True
            self._save()

            if not first_run:
                for key in fresh:
                    rec = self._seen[key]
                    self.hass.bus.async_fire(
                        EVENT_NEW_DEVICE,
                        {"mac": rec.get("mac"), "ip": rec.get("ip"), "name": self._discovered_name(key, rec)},
                    )

    def _subnet_set(self, hosts: list[str]) -> set[str]:
        cached = getattr(self, "_hosts_cache", None)
        if cached is None or cached[0] != self.subnet:
            cached = (self.subnet, set(hosts))
            self._hosts_cache = cached
        return cached[1]

    async def _resolve_names(self, now: datetime) -> None:
        """Reverse DNS for devices we have no recent hostname for."""
        todo = []
        for key, rec in self._seen.items():
            ip = rec.get("ip")
            checked = rec.get("dns_checked")
            if not ip:
                continue
            if checked and now - datetime.fromisoformat(checked) < DNS_REFRESH:
                continue
            todo.append((key, ip))
        sem = asyncio.Semaphore(16)

        async def one(key: str, ip: str) -> None:
            async with sem:
                try:
                    name = await asyncio.wait_for(
                        self.hass.async_add_executor_job(_reverse_dns, ip), DNS_TIMEOUT
                    )
                except (TimeoutError, asyncio.TimeoutError):
                    name = None
                rec = self._seen[key]
                rec["dns_checked"] = now.isoformat()
                host = short_hostname(name)
                if host:
                    rec["hostname"] = host

        await asyncio.gather(*(one(k, ip) for k, ip in todo))

    async def _ping_tracked(self) -> list[tuple[str, str | None]]:
        """Ping hubs and tracked devices. Returns [(key, ip)] that answered."""
        from icmplib import async_multiping  # noqa: PLC0415

        targets: dict[str, str] = {}
        for hub in self.opts[CONF_HUBS]:
            if hub.get("host"):
                targets[f"hub:{hub['id']}"] = hub["host"]
        for key, ip in self._tracked_targets().items():
            if ip:
                targets[key] = ip
        if not targets:
            return []
        by_ip: dict[str, list[str]] = {}
        for key, ip in targets.items():
            by_ip.setdefault(ip, []).append(key)
        results = await async_multiping(
            list(by_ip), count=PING_COUNT, interval=0.3, timeout=PING_TIMEOUT,
            concurrent_tasks=64, privileged=self._privileged,
        )
        alive: list[tuple[str, str | None]] = []
        for host in results:
            if host.is_alive:
                for key in by_ip.get(host.address, []):
                    alive.append((key, host.address))
        return alive

    # ----- model ---------------------------------------------------------------

    def _tracked_targets(self) -> dict[str, str | None]:
        """Keys of devices being tracked and the IP to ping for each."""
        out: dict[str, str | None] = {}
        devices = self.opts[CONF_DEVICES]
        ignored = set(self.opts[CONF_IGNORED])
        if self.opts[CONF_MODE] == MODE_AUTO:
            for key, rec in self._seen.items():
                if rec.get("discovered") and key not in ignored:
                    if self.opts[CONF_IGNORE_RANDOM_MAC] and is_random_mac(rec.get("mac")):
                        continue
                    out[key] = rec.get("ip")
        for key, cfg in devices.items():
            if key in ignored or not cfg.get("tracked", True):
                out.pop(key, None)
                continue
            out[key] = (self._seen.get(key) or {}).get("ip") or cfg.get("host")
        return out

    def _discovered_name(self, key: str, rec: dict[str, Any]) -> str:
        mac = rec.get("mac")
        if mac:
            dev = dr.async_get(self.hass).async_get_device(connections={(dr.CONNECTION_NETWORK_MAC, mac)})
            if dev and (dev.name_by_user or dev.name):
                return dev.name_by_user or dev.name
        return rec.get("hostname") or fallback_name(mac, rec.get("ip"))

    def _build(self, now: datetime, alive_keys: set[str]) -> NetOrbitData:
        stale_after = timedelta(hours=self.opts[CONF_STALE_HOURS])
        hub_ids = {h["id"] for h in self.opts[CONF_HUBS]}
        nodes: dict[str, Node] = {}

        for hub in self.opts[CONF_HUBS]:
            key = f"hub:{hub['id']}"
            rec = self._seen.get(key, {})
            parent = hub.get("parent")
            if hub["id"] == ROOT_HUB_ID:
                parent = None
            elif parent not in hub_ids:
                parent = ROOT_HUB_ID
            nodes[key] = Node(
                key=key, kind="hub", name=hub.get("name") or hub["id"], ip=hub.get("host"),
                icon=hub.get("icon") or HUB_ICONS.get(hub.get("type", HUB_OTHER), "mdi:lan"),
                link=parent, status=self._status(key in alive_keys, rec, now, stale_after),
                last_seen=rec.get("last_seen"), first_seen=rec.get("first_seen"),
                source="hub", hub_type=hub.get("type", HUB_OTHER),
            )

        devices = self.opts[CONF_DEVICES]
        for key, ip in self._tracked_targets().items():
            rec = self._seen.get(key, {})
            cfg = devices.get(key, {})
            name = cfg.get("name") or self._discovered_name(key, rec)
            hub = cfg.get("hub") if cfg.get("hub") in hub_ids else ROOT_HUB_ID
            nodes[key] = Node(
                key=key, kind="device", name=name, ip=ip, mac=rec.get("mac") or cfg.get("mac"),
                icon=cfg.get("icon") or guess_icon(f"{name} {rec.get('hostname') or ''}"),
                link=hub, sleepy=bool(cfg.get("sleepy", False)),
                status=self._status(key in alive_keys, rec, now, stale_after),
                last_seen=rec.get("last_seen"), first_seen=rec.get("first_seen"),
                hostname=rec.get("hostname"), source="manual" if key in devices else "discovered",
            )

        new_devices = []
        if self.opts[CONF_MODE] != MODE_AUTO:
            ignored = set(self.opts[CONF_IGNORED])
            for key, rec in self._seen.items():
                if not rec.get("discovered") or key in nodes or key in ignored:
                    continue
                if self.opts[CONF_IGNORE_RANDOM_MAC] and is_random_mac(rec.get("mac")):
                    continue
                new_devices.append({
                    "key": key, "mac": rec.get("mac"), "ip": rec.get("ip"),
                    "name": self._discovered_name(key, rec), "first_seen": rec.get("first_seen"),
                    "last_seen": rec.get("last_seen"),
                })
            new_devices.sort(key=lambda d: d.get("first_seen") or "", reverse=True)

        return NetOrbitData(
            nodes=nodes, new_devices=new_devices,
            last_scan=self._last_sweep.isoformat() if self._last_sweep else None,
        )

    @staticmethod
    def _status(online: bool, rec: dict[str, Any], now: datetime, stale_after: timedelta) -> str:
        last = rec.get("last_seen")
        first = rec.get("first_seen")
        return compute_status(
            online,
            datetime.fromisoformat(last) if last else None,
            datetime.fromisoformat(first) if first else now,
            now,
            stale_after,
        )

    def _fire_transitions(self, data: NetOrbitData) -> None:
        for key, node in data.nodes.items():
            prev = self._prev_status.get(key)
            if prev is not None and prev != node.status:
                payload = {"name": node.name, "ip": node.ip, "mac": node.mac, "kind": node.kind, "last_seen": node.last_seen}
                if node.status == STATUS_STALE and not node.sleepy:
                    self.hass.bus.async_fire(EVENT_DEVICE_STALE, payload)
                elif prev == STATUS_STALE and node.status == STATUS_ONLINE:
                    self.hass.bus.async_fire(EVENT_DEVICE_RECOVERED, payload)
            self._prev_status[key] = node.status

    # ----- helpers used by config flow and services --------------------------

    def known_device(self, key: str) -> dict[str, Any] | None:
        """Raw record for a device the scanner has seen."""
        return self._seen.get(key)

    def find_key(self, mac: str | None = None, ip: str | None = None) -> str | None:
        """Find a device key by MAC or IP."""
        mac = normalize_mac(mac)
        if mac and mac in self._seen:
            return mac
        if ip:
            for key, rec in self._seen.items():
                if rec.get("ip") == ip and not key.startswith("hub:"):
                    return key
        return mac


def _read_arp() -> dict[str, str]:
    try:
        with open("/proc/net/arp", encoding="ascii") as fh:
            return parse_proc_arp(fh.read())
    except OSError:
        return {}


def _reverse_dns(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (OSError, UnicodeError):
        return None


def _ip_sort(ip: str) -> tuple[int, ...]:
    return tuple(int(p) for p in ip.split("."))
