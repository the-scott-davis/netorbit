# NetOrbit

A live, radial map of your home network for Home Assistant. Every device orbits the router, switch, access point or mesh node it connects through, colored by whether it's answering right now, was seen recently, or has gone quiet.

Install it, click Submit, and NetOrbit draws the best map your network can tell it about. Then fix anything it couldn't work out by dragging devices around, pasting a client list, or asking an AI assistant to do it for you.

![NetOrbit card](docs/full.png)

## What it does

- **Finds every device.** Sweeps your subnet, learns MAC addresses from the ARP table, and names devices from Home Assistant's device list, their network hostname, or their maker.
- **Finds your network gear.** Spots routers, switches, access points and mesh nodes from who made them, what they call themselves, what they announce on the network, and what other integrations already know. Obvious ones are added for you. Likely ones show up with a spinning yellow ring and a one-tap "It's a hub / Not a hub".
- **Works out where each device connects, when your network will say:**
  - **Managed switches with SNMP:** NetOrbit reads their MAC address tables and works out which switch port, and so which access point, every device is behind. No port mapping needed.
  - **UniFi**, and other integrations that report which access point each client uses (Netgear/Orbi's per-device "connected AP" sensors, for example).
- **Lets you place the rest, three ways:**
  1. **Drag and drop on the card.** Tap *Edit layout*, drag a device onto its hub, or tap it for *Move to*, *Make it a hub* and *Automatic*.
  2. **Paste a client list.** Copy the client list from an access point's web page or a mesh app, paste it into NetOrbit, pick the hub. Done.
  3. **Ask an AI assistant.** NetOrbit exposes tools to Claude, ChatGPT and other assistants through Home Assistant's MCP Server, and to Assist. The assistant walks you through each piece of gear and does the placing. See [docs/ASSISTANT.md](docs/ASSISTANT.md).
- **Looks good even when it knows nothing.** If no source reports the layout, devices are grouped by type (TV and media, computers and phones, cameras, smart home) until you place them.
- **Remembers when it last saw each device.** Green = answering, yellow = seen within your window (24 h by default), red = gone longer than that. Survives restarts.
- **Events for automations,** plus ready-made notification blueprints.
- **Lightweight.** One ping round per interval (default 60 s), one subnet sweep every 5 minutes, one SNMP question per device per hour. A few kilobits per second.

| Wired with access points | Mesh system | Mesh with nothing reporting placement |
| --- | --- | --- |
| ![](docs/full.png) | ![](docs/mesh.png) | ![](docs/novice.png) |

| Editing on the card |
| --- |
| ![](docs/edit.png) |

## What your network can tell NetOrbit

| Your setup | Hubs found | Devices placed under the right hub |
| --- | --- | --- |
| UniFi with the UniFi integration | Automatically | Automatically (wireless clients) |
| Managed switches with SNMP on | Automatically | Automatically (wired and wireless, through the switch port) |
| Netgear/Orbi with the Netgear integration | Suggested | Automatically, once you enable its "connected AP" sensors |
| eero, Google/Nest Wifi, Deco, Velop, ISP routers | Suggested | By you: drag and drop, paste a list, or an AI assistant |

Placement you choose always wins over automatic placement. Each device shows how it was placed, and *Automatic* hands it back to NetOrbit.

## Install

### HACS

1. In HACS, open the menu, choose **Custom repositories**, add `https://github.com/the-scott-davis/netorbit` with type **Integration**.
2. Install **NetOrbit** and restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration > NetOrbit**. The subnet and router are filled in for you.

### Manual

Copy `custom_components/netorbit` into your Home Assistant `config/custom_components` folder and restart.

### Add the card

```yaml
type: custom:netorbit-card
title: Home Network
```

It's also in the card picker as **NetOrbit**.

## Settings

Under the integration's **Configure** menu:

| Option | What it does |
| --- | --- |
| Review suggested hubs | Confirm or dismiss everything NetOrbit thinks might be network gear. |
| Paste a client list | Paste a client list from an access point, app or switch, pick the hub, and every device in it is placed there. |
| Add / edit a hub | Add gear NetOrbit can't see, rename hubs, change what they connect to. |
| Track / edit a device | Name, icon, hub (or *Automatic*), "allowed to sleep", stop tracking. |
| Review new devices | In manual mode, choose which newly found devices to track. |
| Settings | Tracking mode, ping and scan intervals, the "not seen" window, randomized MACs, automatic hubs, grouping by type, SNMP on/off and SNMP community. |

**Tracking mode:** *Automatic* tracks everything it finds. *Manual* only tracks devices you add, and lists the rest under "New devices".

**Allowed to sleep** is for TVs, consoles and anything else that's off a lot. They still show their status but never fire the stale event.

### DHCP, MAC addresses and keeping your setup

Most homes hand out addresses with DHCP, so a device's IP can change at any time. NetOrbit is built for that:

- **Everything is keyed by MAC address.** Names, icons, hub placement, "allowed to sleep" and history all follow the device's MAC, so a new IP changes nothing. When a device's IP changes, NetOrbit just pings the new one.
- **Hubs follow their MAC too.** If an access point gets a new IP, NetOrbit notices on the next sweep and updates it.
- **Devices added by IP switch to their MAC** as soon as NetOrbit sees them on the network, so they survive the next DHCP change as well.
- **Renaming works either way.** Rename in NetOrbit's settings, from an AI assistant, or in Home Assistant's own entity settings; the map uses whichever name you set.
- **Back up your setup.** `netorbit.export_config` returns every name, icon, hub and placement, keyed by MAC. `netorbit.import_config` restores it (merging by default), for example after reinstalling.

Tips for the tidiest map:

- **Give network gear a DHCP reservation** (sometimes called a static lease or address reservation) in your router: switches, access points and mesh nodes. NetOrbit copes without it, but reserved addresses keep everything else that talks to them happy too. Hovering a hub whose IP has changed shows this tip.
- **Reserve addresses for devices other things depend on**, like printers, NAS boxes, cameras and Home Assistant itself. Hovering a device whose IP keeps changing shows a reminder.
- **Phones and laptops** usually use a private (randomized) MAC address per network. NetOrbit hides those by default. Turn off *Ignore randomized MAC addresses* if you want them: on current phones the private address normally stays the same for your network unless the phone is set to rotate it.

### SNMP

SNMP is how managed switches share their MAC address tables. NetOrbit only ever reads (it never changes anything), and it asks each device on your network once an hour whether it speaks SNMP.

- If your switches still use the factory read-only community, there's nothing to do.
- If you changed it (good idea), enter it under **Settings > SNMP community**. Letters and numbers only work best; some switches silently ignore communities with symbols.
- Consumer routers and mesh systems don't support SNMP. That's normal.

## Card options

| Option | Default | Description |
| --- | --- | --- |
| `title` | `Network` | Card title. |
| `height` | `900` | Maximum height in pixels. |
| `show_ip` | `false` | Show hub IPs under their names instead of the hub type. Off by default so screenshots are safe to share. |
| `show_legend` | `true` | Show the legend at the bottom. |
| `group_by_type` | `true` | Group unplaced devices by type. |
| `hide_sleepy_offline` | `false` | Hide sleep-allowed devices while they're offline. |
| `max_devices` | `80` | Above this many devices, each hub shows its problem devices first and folds the rest into a "+N more" bubble. |
| `device_id` | | Only show one NetOrbit entry when you have several. |

Hover a device for details, tap it for its history. Admins get an **Edit layout** button.

## Entities, events and services

- One sensor per hub and tracked device. State is `online`, `recent` or `stale`. Attributes include `ip`, `mac`, `vendor`, `link` (the hub), `placement` (`manual`, `controller`, `snmp` or `none`), `last_seen`, `hostname` and `sleepy`.
- `sensor.netorbit_devices_online` counts online devices and lists `new_devices` and `suggested_hubs`.

| Event | Data |
| --- | --- |
| `netorbit_new_device` | `name`, `ip`, `mac` |
| `netorbit_device_stale` | `name`, `ip`, `mac`, `kind`, `last_seen` |
| `netorbit_device_recovered` | `name`, `ip`, `mac`, `kind`, `last_seen` |

Every service returns a response describing what it did. Devices can be given by name, IP or MAC; hubs by name or id.

| Service | Fields |
| --- | --- |
| `netorbit.assign_device` | `device` (one or a list), `hub` |
| `netorbit.reset_placement` | `device` |
| `netorbit.import_client_list` | `hub`, `text`, `add_missing` |
| `netorbit.add_hub` | `name` or `device`, `type`, `parent`, `ip`, `mac` |
| `netorbit.update_hub` | `hub`, `name`, `type`, `parent` |
| `netorbit.remove_hub` | `hub` |
| `netorbit.confirm_hub` | `device`, `type`, `name` |
| `netorbit.dismiss_hub` | `device` |
| `netorbit.track_device` | `mac` or `ip`, `name`, `icon`, `hub`, `sleepy` |
| `netorbit.export_config` | none (returns your settings, keyed by MAC) |
| `netorbit.import_config` | `data` (an export), `replace` |
| `netorbit.ignore_device` | `device` or `mac` or `ip` |
| `netorbit.scan_now` | none |

### Blueprints

- [Notify when a device goes offline](blueprints/automation/netorbit/device_offline_notify.yaml)
- [Notify when a new device joins](blueprints/automation/netorbit/new_device_notify.yaml)

Import either from **Settings > Automations & scenes > Blueprints > Import blueprint** using the file's GitHub URL.

## Requirements and limits

- Home Assistant needs to be on the same network as your devices, with host networking. Home Assistant OS and supervised installs are. Docker installs need `network_mode: host`.
- Presence is based on ping. Devices that block ping show as not seen even when connected. Mark them as allowed to sleep, or ignore them.
- Phones and laptops often use a private MAC address per network. Those are ignored by default since they can change, and they roam between access points anyway.
- If an access point and wired devices share one switch port through an unmanaged switch, the switch can't tell them apart, so those wired devices may be drawn under the access point. Move them by hand if it matters to you.
- Placements from pasted lists are a snapshot. TVs, cameras and smart home gear stay put, so that's fine for them.
- IPv4 only, up to 1024 hosts per entry. Add one entry per subnet if you have several.

## Privacy

NetOrbit runs entirely on your network and never contacts anything outside it. Maker names come from a list bundled with Home Assistant. Diagnostics downloads replace every IP, MAC and name with placeholders, so they're safe to attach to an issue. The card hides IPs by default.

## Roadmap

- Omada placement through the Omada controller.
- ARP based presence for devices that block ping.
- A visual card editor.

## Contributing

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
node --test tests/card.test.js
```

Preview the card with fake data: `npm i @mdi/js@7.4.47` and copy `node_modules/@mdi/js/mdi.js` to `scripts/preview/`, serve the repo root (`python -m http.server 8766`), and open `http://localhost:8766/scripts/preview/index.html?s=full` (or `mesh`, `flat`, `novice`). `scripts/preview/interact.js` drives edit mode in a real browser with Playwright.

### The network simulator

`tests/test_simulation.py` generates hundreds of home networks with a known true layout (flat routers, mesh with nothing reporting, UniFi, one or several managed switches, unmanaged switches in between, routers that speak SNMP, odd gateways, randomized MACs, devices that ignore ping, DHCP churn, aged-out MAC table entries, wrong SNMP communities, duplicate and non-ASCII names, up to several hundred devices) and runs the real integration against each one. It fails on crashes, duplicates, loops, devices placed on the wrong branch, manual placement not winning, state lost on restart, or real addresses in diagnostics. `pytest -s -k simulation` prints a report of how much it found and placed.

To draw every simulated map in a browser and check for errors and overlaps: `NETORBIT_DUMP=scripts/preview/_simstates pytest -k simulation`, serve the repo root, then `node scripts/preview/fuzz.js`.

## License

MIT
