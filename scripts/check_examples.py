"""Fail if any file in the repo contains a real-looking network address.

Examples, tests and docs must only use the ranges set aside for documentation, so
nobody's real network can end up in the repo by accident:

  IPv4:  192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24  (RFC 5737)
  MAC:   00:00:5e:00:53:xx                               (RFC 7042)

A value that has to be outside those ranges (a randomized-MAC test, a subnet bigger
than /24) can stay if its line carries an `example-ok` comment saying why.

Run: python scripts/check_examples.py   (CI runs it on every push)
"""

from __future__ import annotations

import ipaddress
import pathlib
import re
import subprocess
import sys

DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
# Addresses that are fine to mention: loopback, "any", broadcast, and well known public resolvers.
ALLOWED_IPS = {"127.0.0.1", "0.0.0.0", "255.255.255.255", "224.0.0.251", "1.1.1.1", "8.8.8.8"}
# Subnets that appear only as config examples ("for example 10.0.0.0/24").
ALLOWED_TEXT = ("10.0.0.0/24",)
DOC_MAC_PREFIX = "00005e0053"
ALLOWED_MACS = {"000000000000", "ffffffffffff"}

IP_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?:/\d{1,2})?(?![\w.]*\d)")
MAC_RE = re.compile(r"(?<![0-9A-Fa-f:-])((?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2})(?![0-9A-Fa-f:-])")
BARE_MAC_RE = re.compile(r"(?<![0-9A-Fa-f])([0-9A-Fa-f]{12})(?![0-9A-Fa-f])")
SKIP_SUFFIXES = {".png", ".gif", ".jpg", ".ico", ".svg", ".zip"}
SKIP_FILES = {"scripts/preview/mdi.js", "scripts/check_examples.py"}


def problems_in(path: str, text: str) -> list[str]:
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if "example-ok" in line:  # a deliberately synthetic value, marked on purpose
            continue
        if any(a in line for a in ALLOWED_TEXT):
            line = line.replace("10.0.0.0/24", "")
        for m in IP_RE.finditer(line):
            ip = m.group(1)
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue  # version numbers and the like
            if ip in ALLOWED_IPS or any(addr in n for n in DOC_NETS):
                continue
            if addr.is_private or addr.is_link_local or addr.is_global:
                out.append(f"{path}:{lineno}: IP {ip} (use 192.0.2.x)")
        for m in MAC_RE.finditer(line):
            raw = re.sub(r"[:-]", "", m.group(1)).lower()
            if raw in ALLOWED_MACS or raw.startswith(DOC_MAC_PREFIX):
                continue
            out.append(f"{path}:{lineno}: MAC {m.group(1)} (use 00:00:5e:00:53:xx)")
        for m in BARE_MAC_RE.finditer(line):
            raw = m.group(1).lower()
            # Only flag bare 12-hex strings that look like a MAC: mixed digits and letters,
            # not a commit hash fragment or a long number.
            if raw in ALLOWED_MACS or raw.startswith(DOC_MAC_PREFIX) or raw.isdigit() or raw.isalpha():
                continue
            if re.search(r"(?i)\b(sha|commit|hash|ref|id)\b", line):
                continue
            out.append(f"{path}:{lineno}: MAC-like {m.group(1)} (use 00005E0053xx)")
    return out


def main() -> int:
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    found: list[str] = []
    for f in files:
        if f in SKIP_FILES or pathlib.Path(f).suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = pathlib.Path(f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        found += problems_in(f, text)
    for p in found:
        print(p)
    if found:
        print(f"\n{len(found)} real-looking address(es). Use documentation ranges in examples and tests.")
        return 1
    print("No real-looking addresses.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
