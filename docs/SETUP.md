# Getting the most automatic map

NetOrbit draws a map the moment you add it. How much of it is right on its own depends on what your network can tell it. This page covers the three things that do most of the work for you, and how to finish the rest by hand in a minute or two.

| You have | What to do | What you get |
| --- | --- | --- |
| UniFi | Add Home Assistant's UniFi Network integration | Every wireless client placed under its access point, with names |
| Managed switches | Turn on SNMP (below) | Every device placed under the switch, and the access point, it really connects through |
| Netgear or Orbi | Add the Netgear integration and turn on its "connected AP" sensors | Clients placed under the right satellite |
| eero, Google/Nest Wifi, Deco, Velop, an ISP router | Nothing to turn on, these don't share it | Use the quick manual steps at the bottom |

You can mix these. Anything you place by hand always wins over automatic placement.

## 1. Let your router or controller integration do it

If Home Assistant already has an integration for your router or Wi-Fi system, NetOrbit reads what it knows:

- **UniFi Network:** which access point each wireless client is on, plus the client names you see in UniFi. NetOrbit adds your UniFi access points as hubs automatically.
- **Netgear / Orbi:** the Netgear integration creates a "connected AP" sensor per device, turned off by default. Turn them on (Settings > Devices & services > Netgear > entities, show disabled, enable the ones you want) and NetOrbit uses them.
- **Fritz!Box, ASUS, OpenWrt, MikroTik, Keenetic and other router integrations:** these give NetOrbit device names, even when they don't say which access point a device is on.

## 2. Turn on SNMP on managed switches

SNMP lets a switch share its address table, the list of which device sits behind which port. With that, NetOrbit works out the whole wired picture by itself, including which access point every wireless device is on (because the access point sits on a switch port too).

NetOrbit only ever reads. It never changes a setting on your switch.

### Does my switch support it?

- **Yes:** most switches sold as "managed", "smart managed" or "business": UniFi (most models), TP-Link Omada/JetStream (for example TL-SG2008), Netgear Smart Pro and Insight, Cisco Business, MikroTik.
- **No:** unmanaged switches, and some budget "smart" lines with no SNMP at all, for example **TP-Link Easy Smart** (TL-SG105E, TL-SG108E) and **Netgear Plus** (GS105E, GS108E, GS308E). NetOrbit still works with these; place devices behind them by hand.
- **Not supported by UniFi:** USW Flex and USW Ultra switches.

### UniFi

1. In UniFi Network, open **Settings > CyberSecure > Traffic Logging**.
2. Scroll to **SNMP**, turn it on, choose **v1/v2c**, and set a community (see the tip below).
3. Click **Apply Changes**.

### TP-Link Omada (controller)

1. On the site, open **Network Config > SNMP**.
2. Turn on **SNMPv1/v2c** and set the community.
3. Click **Apply**. The controller pushes it to your Omada switches.

### Any other managed switch

Open the switch's web page and look for **SNMP** (often under Management, System or Monitoring). Turn on **SNMP v2c**, and set or keep a **read-only** community. You don't need traps, write access or SNMPv3.

### Then tell NetOrbit

Settings > Devices & services > NetOrbit > **Configure > Settings**, and enter the community under **SNMP community**. If you left it as the factory "public", there's nothing to enter.

NetOrbit asks each device on your network once an hour whether it speaks SNMP, and reads switch tables every few minutes. It's a tiny amount of traffic.

**Tips**

- Use a community made of **letters and numbers only**. Some switches accept symbols in their web page but quietly ignore a community containing `#` or `@`.
- Changing it from "public" is a good idea; treat it like a password. NetOrbit stores it with your Home Assistant config and leaves it out of diagnostics downloads.
- Read-only is all NetOrbit needs. If your switch has a read-write community you don't use, turn it off.

## 3. Finish the rest by hand (about a minute)

Whatever NetOrbit couldn't work out, you can place yourself. Three ways, use whichever is quickest:

**Drag and drop.** Tap **Edit layout**, drag a device onto the hub it connects through, tap **Done**.

![Dragging devices onto a hub](howto-drag.gif)

**Confirm a possible hub.** Devices with a spinning pink ring look like network gear. Tap one and choose **It's a hub** (or **Not a hub**). Then drag its devices onto it.

![Confirming a suggested hub](howto-confirm-hub.gif)

**On a phone,** tap a device in edit mode and pick its hub from the menu.

![Moving a device on a phone](howto-phone-move.gif)

**Paste a client list.** Most access point web pages and mesh apps list the devices connected to each unit. Copy that list, then in Home Assistant go to NetOrbit > **Configure > Paste a client list**, paste it, and pick the hub. Every device in it is placed at once.

**Ask an AI assistant.** If you use Home Assistant's MCP Server or Assist, an assistant can walk you through each piece of gear and do the placing. See [ASSISTANT.md](ASSISTANT.md).

## Better names

NetOrbit names devices from, in order: Home Assistant's own device list, router and controller integrations, Ping sensors you've set up, your router's local DNS, and the name a device announces over Bonjour. When none of those know a device, it shows the maker (for example "Apple 28:54").

To rename one, open its sensor in Home Assistant and change the name, or use **Configure > Track / edit a device**. Names stick to the device's MAC address, so they survive IP changes.
