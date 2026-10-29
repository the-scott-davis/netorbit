# Releasing

1. Bump `version` in `custom_components/netorbit/manifest.json` and add a section to `CHANGELOG.md`.
2. Push and wait for the Validate workflow to pass: HACS action, hassfest, tests, secret scan. The HACS action must pass with nothing ignored.
3. Create a GitHub **release** (a tag alone isn't enough; the Marketplace and HACS read releases). Tag `vX.Y.Z` to match the manifest. Mark pre-releases as such.
4. The Release workflow checks the tag matches the manifest.

## Repository settings the Marketplace and HACS check

- Public repository with a description, issues enabled, and topics (for example `home-assistant`, `hacs`, `home-assistant-integration`, `network`, `network-map`, `snmp`).
- A license GitHub can identify (MIT).
- Brand icon at `custom_components/netorbit/brand/icon.png` (Home Assistant 2026.3 and newer show it; older versions show a generic icon).

## Getting into the default list

Anyone can add NetOrbit as a custom repository today. To show up when people search the Marketplace without adding it, it has to be in the default list: open a pull request to https://github.com/hacs/default adding `the-scott-davis/netorbit` to the `integration` file, in alphabetical order, from a personal account (the PR must be editable). Its checks repeat the list above plus "at least one release" and "the domain isn't used by a core integration".
