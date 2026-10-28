"""Shared fixtures. All addresses use the 192.0.2.0/24 documentation range."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

SUBNET = "192.0.2.0/24"
GATEWAY = "192.0.2.1"
MAC_A = "02:00:5e:00:00:0a"  # randomized style (locally administered)
MAC_B = "00:00:5e:00:53:0b"  # IANA documentation range
MAC_C = "00:00:5e:00:53:0c"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/netorbit."""
    return


@dataclass
class FakeHost:
    address: str
    is_alive: bool


class FakeNet:
    """Stands in for the network: who answers pings and what the ARP table holds."""

    def __init__(self) -> None:
        self.alive: set[str] = set()
        self.arp: dict[str, str] = {}

    async def multiping(self, addresses, **kwargs):
        return [FakeHost(a, a in self.alive) for a in addresses]

    async def ping(self, *args, **kwargs):
        return FakeHost("127.0.0.1", True)


@pytest.fixture
def fake_net():
    net = FakeNet()
    with (
        patch("icmplib.async_multiping", side_effect=net.multiping),
        patch("icmplib.async_ping", side_effect=net.ping),
        patch("custom_components.netorbit.coordinator._read_arp", side_effect=lambda: dict(net.arp)),
        patch("custom_components.netorbit.coordinator._reverse_dns", return_value=None),
    ):
        yield net
