# Changelog

## 0.2.1

### Fixed
- Hub labels no longer overlap each other on busy maps.
- After an update, browsers load the new card right away instead of a cached copy.
- Uses the current Home Assistant field for a device's integration (the old one is deprecated and logged a warning on 2026.10).

## 0.2.0

First public release.

### Added
- Ready for the Home Assistant Marketplace (2026.11 and newer) as well as HACS: brand icon shipped with the integration, Marketplace categories, install docs for both.
- Hub detection: obvious network gear is added for you, likely gear is suggested with a one-tap confirm or dismiss.
- SNMP: reads managed switch MAC address tables to place wired and wireless devices automatically. Community is configurable and redacted from diagnostics.
- Controller placement from UniFi and Netgear/Orbi "connected AP" data.
- Three ways to place devices by hand: drag and drop on the card, paste a client list, or an AI assistant through Home Assistant's MCP Server and Assist.
- DHCP handling: everything is keyed by MAC, hubs follow their MAC to new IPs, devices added by IP switch to their MAC, IP change counts with DHCP reservation tips on the card.
- `netorbit.export_config` and `netorbit.import_config` to back up and restore your setup.
- Large networks fold quiet devices into "+N more" bubbles (`max_devices`, default 80). Problem devices and possible hubs always stay on the map.
- Devices are grouped by type until NetOrbit knows where they connect, using the name or, failing that, the maker.
- Names come from Home Assistant's device list (skipping entries that are just a MAC), device trackers, Ping sensors you already set up, the router's local DNS, and Bonjour.
- Possible hubs have their own color (pink), so they never look like "seen recently".
- Network simulator and browser tests covering hundreds of generated home networks.

### Changed
- Needs Home Assistant 2026.2 or newer.

## 0.1.0

- Initial version: ping sweep, ARP, radial card, events and blueprints.
