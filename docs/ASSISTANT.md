# Setting up NetOrbit with an AI assistant

Most home networks don't tell Home Assistant which access point or mesh node each device uses. An AI assistant can fill that in with you in a few minutes: it reads NetOrbit's map, asks what gear you have, helps you find each device list, and places everything.

There are two ways to do it.

## Option 1: Let the assistant make the changes (recommended)

NetOrbit gives assistants a set of tools: read the map, place devices, add or rename hubs, confirm suggested hubs, import pasted client lists. They work with:

- **Claude, ChatGPT and other MCP clients,** through Home Assistant's **Model Context Protocol Server** integration.
- **Assist,** when it uses an AI conversation agent such as the OpenAI or Anthropic integration.

### Connect it

1. In Home Assistant, add the **Model Context Protocol Server** integration (Settings > Devices & services > Add integration).
2. When it asks which APIs to expose, include **NetOrbit network map** alongside Assist. If you already have it set up without NetOrbit, remove the integration and add it again with NetOrbit ticked.
3. Connect your assistant to Home Assistant's MCP server as described in the [Model Context Protocol Server documentation](https://www.home-assistant.io/integrations/mcp_server/).

For Assist: open your voice assistant's conversation agent settings and include **NetOrbit network map** in its Home Assistant API control.

### Then say something like

> Help me set up my NetOrbit network map.

The assistant gets NetOrbit's own instructions, so you don't need a special prompt. It will:

1. Read the map and summarize it in plain words.
2. Ask what network gear you have, and offer to confirm or dismiss any suggested hubs.
3. For each access point or mesh node, ask you to open its device list (in the phone app or web page) and copy, paste or screenshot it.
4. Place the devices it finds, tell you what matched and what didn't, and ask before every change.

## Option 2: Any chat assistant, no setup

If you'd rather not connect anything, any chat assistant can still guide you while NetOrbit does the matching. Paste this into Claude, ChatGPT or similar:

```text
I'm mapping my home network in a Home Assistant integration called NetOrbit.
It needs to know which access point, mesh node or switch each device connects through.
My network gear is: [describe it, e.g. "an eero router plus two eero nodes in the
living room and upstairs" or "a Netgear router and two Ubiquiti access points"].

For each access point or mesh node, tell me exactly where to find the list of devices
connected to it (in the phone app or web admin page for my brand), one at a time.
When I paste or screenshot the list, tell me which hub name to choose and remind me to
paste the list into NetOrbit under Configure > "Paste a client list".
Keep it short and don't assume I know networking terms.
```

NetOrbit's **Paste a client list** screen pulls the MAC and IP addresses out of whatever you paste (a table, a screen of text, a CSV) and places every matching device under the hub you pick.

## Good to know

- **Phones and laptops** move between access points and often use private addresses, so placing them is optional.
- **TVs, cameras, speakers and smart home gear** stay put, so placing them once is enough.
- Anything you place yourself, by hand or through an assistant, stays where you put it. To hand a device back to NetOrbit, choose **Automatic** for it.
- Assistants only see what NetOrbit's tools return: hub and device names, IPs, MACs and status. Nothing leaves your network unless your assistant is a cloud service, in which case that information goes to it.
