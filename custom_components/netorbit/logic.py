"""Pure helpers for NetOrbit. No Home Assistant imports so they are easy to test."""

from __future__ import annotations

from datetime import datetime, timedelta
import ipaddress
import re

from .const import STATUS_ONLINE, STATUS_RECENT, STATUS_STALE

_MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")

# Keyword -> icon. First match wins, checked against the lowercased name.
_ICON_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("iphone", "android", "pixel", "galaxy", "phone"), "mdi:cellphone"),
    (("ipad", "tablet"), "mdi:tablet"),
    (("macbook", "laptop", "notebook", "thinkpad"), "mdi:laptop"),
    (("imac", "desktop", "pc", "workstation", "studio"), "mdi:monitor"),
    (("appletv", "apple-tv", "apple tv", "roku", "firetv", "fire-tv", "chromecast", "shield", "streamer"), "mdi:television-play"),
    (("tv", "television", "bravia", "lgwebos", "tizen"), "mdi:television"),
    (("speaker", "homepod", "echo", "nest-audio", "soundbar"), "mdi:speaker"),
    (("cam", "camera", "doorbell", "ring", "wyze", "reolink"), "mdi:cctv"),
    (("printer", "print", "hp", "epson", "brother", "canon"), "mdi:printer"),
    (("thermostat",), "mdi:thermostat"),
    (("vacuum", "roomba", "roborock", "deebot"), "mdi:robot-vacuum"),
    (("playstation", "ps4", "ps5", "xbox", "nintendo", "switch-console", "steamdeck"), "mdi:gamepad-variant"),
    (("homeassistant", "home-assistant", "hass"), "mdi:home-assistant"),
    (("nas", "synology", "qnap", "unraid", "truenas", "server"), "mdi:server"),
    (("esp", "shelly", "tasmota", "tuya", "plug", "bulb", "light"), "mdi:chip"),
    (("garage",), "mdi:garage"),
    (("watch",), "mdi:watch"),
]


def normalize_mac(mac: str | None) -> str | None:
    """Return a lowercase colon separated MAC, or None if it is not a MAC."""
    if not mac:
        return None
    raw = re.sub(r"[^0-9a-fA-F]", "", mac).lower()
    if len(raw) != 12:
        return None
    out = ":".join(raw[i : i + 2] for i in range(0, 12, 2))
    if out in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
        return None
    return out if _MAC_RE.match(out) else None


def is_random_mac(mac: str | None) -> bool:
    """True when the MAC is locally administered (phones and laptops randomize these)."""
    mac = normalize_mac(mac)
    return bool(mac) and mac[1] in "26ae"


def compute_status(
    online: bool,
    last_seen: datetime | None,
    first_seen: datetime | None,
    now: datetime,
    stale_after: timedelta,
) -> str:
    """Online now, seen within the window, or not seen for longer than the window."""
    if online:
        return STATUS_ONLINE
    ref = last_seen or first_seen
    if ref is None or now - ref < stale_after:
        return STATUS_RECENT
    return STATUS_STALE


def guess_icon(name: str | None, default: str = "mdi:lan-connect") -> str:
    """Pick a sensible icon from a device name or hostname."""
    if not name:
        return default
    low = name.lower()
    tokens = set(re.split(r"[^a-z0-9]+", low))
    for words, icon in _ICON_HINTS:
        # Short words must match a whole token so "hp" does not match "iphone".
        if any((w in tokens) if len(w) < 5 else (w in low) for w in words):
            return icon
    return default


def short_hostname(name: str | None) -> str | None:
    """Strip the domain from a reverse DNS name and ignore names that are just an IP."""
    if not name:
        return None
    name = name.strip().rstrip(".")
    try:
        ipaddress.ip_address(name)
        return None
    except ValueError:
        pass
    host = name.split(".")[0]
    if not host or re.fullmatch(r"[0-9-]+", host):
        return None
    return host


def fallback_name(mac: str | None, ip: str | None) -> str:
    """Name for a device we know nothing about."""
    if mac:
        return "Device " + mac[-5:].upper()
    return "Device " + (ip or "unknown")


def parse_proc_arp(text: str) -> dict[str, str]:
    """Parse /proc/net/arp into {ip: mac} for complete entries."""
    out: dict[str, str] = {}
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        ip, _hw, flags, mac = parts[0], parts[1], parts[2], parts[3]
        try:
            complete = int(flags, 16) & 0x2
        except ValueError:
            continue
        mac = normalize_mac(mac)
        if complete and mac:
            out[ip] = mac
    return out


def subnet_hosts(subnet: str) -> list[str]:
    """All usable host addresses in a subnet."""
    net = ipaddress.ip_network(subnet, strict=False)
    return [str(h) for h in net.hosts()]


def validate_subnet(subnet: str, max_hosts: int) -> str:
    """Return the canonical subnet string or raise ValueError."""
    net = ipaddress.ip_network(subnet.strip(), strict=False)
    if net.version != 4:
        raise ValueError("ipv4_only")
    if net.num_addresses - 2 > max_hosts:
        raise ValueError("too_large")
    return str(net)


def slugify_id(text: str) -> str:
    """Simple id slug: lowercase letters, digits and underscores."""
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "item"
