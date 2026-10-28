"""Constants for NetOrbit."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "netorbit"
VERSION: Final = "0.1.0"

# Config entry data
CONF_SUBNET: Final = "subnet"
CONF_GATEWAY: Final = "gateway"

# Options
CONF_MODE: Final = "mode"
CONF_PING_INTERVAL: Final = "ping_interval"
CONF_DISCOVERY_INTERVAL: Final = "discovery_interval"
CONF_STALE_HOURS: Final = "stale_hours"
CONF_IGNORE_RANDOM_MAC: Final = "ignore_random_mac"
CONF_HUBS: Final = "hubs"
CONF_DEVICES: Final = "devices"
CONF_IGNORED: Final = "ignored"

MODE_AUTO: Final = "auto"
MODE_MANUAL: Final = "manual"
MODES: Final = [MODE_AUTO, MODE_MANUAL]

DEFAULT_MODE: Final = MODE_AUTO
DEFAULT_PING_INTERVAL: Final = 60
DEFAULT_DISCOVERY_INTERVAL: Final = 300
DEFAULT_STALE_HOURS: Final = 24
DEFAULT_IGNORE_RANDOM_MAC: Final = True

MIN_PING_INTERVAL: Final = 10
MAX_HOSTS: Final = 1024

# Hub types
HUB_ROUTER: Final = "router"
HUB_SWITCH: Final = "switch"
HUB_AP: Final = "access_point"
HUB_MESH: Final = "mesh_node"
HUB_OTHER: Final = "other"
HUB_TYPES: Final = [HUB_ROUTER, HUB_SWITCH, HUB_AP, HUB_MESH, HUB_OTHER]
HUB_ICONS: Final = {
    HUB_ROUTER: "mdi:router-network",
    HUB_SWITCH: "mdi:switch",
    HUB_AP: "mdi:access-point",
    HUB_MESH: "mdi:access-point-network",
    HUB_OTHER: "mdi:lan",
}
ROOT_HUB_ID: Final = "gateway"

# Status values
STATUS_ONLINE: Final = "online"
STATUS_RECENT: Final = "recent"
STATUS_STALE: Final = "stale"
STATUSES: Final = [STATUS_ONLINE, STATUS_RECENT, STATUS_STALE]

# Events
EVENT_NEW_DEVICE: Final = f"{DOMAIN}_new_device"
EVENT_DEVICE_STALE: Final = f"{DOMAIN}_device_stale"
EVENT_DEVICE_RECOVERED: Final = f"{DOMAIN}_device_recovered"

# Services
SERVICE_TRACK: Final = "track_device"
SERVICE_IGNORE: Final = "ignore_device"
SERVICE_SCAN: Final = "scan_now"

# Frontend
CARD_URL: Final = f"/{DOMAIN}/netorbit-card.js"
CARD_FILENAME: Final = "netorbit-card.js"

STORAGE_VERSION: Final = 1
