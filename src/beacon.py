#!/usr/bin/env python3

import subprocess
import sys

def package_source(package):
    result = subprocess.run(
        ["apt-cache", "policy", package],
        capture_output=True,
        text=True,
    )

    output = result.stdout.lower()

    if "ppa.launchpadcontent.net" in output or "ppa." in output:
        return "PPA"

    if "archive.ubuntu.com" in output:
        return "Ubuntu Repository"

    if "security.ubuntu.com" in output:
        return "Ubuntu Repository"

    if "packages.microsoft.com" in output:
        return "Vendor Repository"

    return "Unknown"

def package_state(package):
    result = subprocess.run(
        ["dpkg", "-l", package],
        capture_output=True,
        text=True,
    )

    output = result.stdout

    if f"ii  {package}" in output:
        return "Installed"

    if f"rc  {package}" in output:
        return "Config Remains"

    return "Unknown"

def state_icon(state):
    icons = {
        "Installed": "✓",
        "Config Remains": "!",
        "Unknown": "?",
    }
    return icons.get(state, "?")

def main():
    if len(sys.argv) != 2:
        print("Usage: beacon.py <package>")
        sys.exit(1)

    package = sys.argv[1]

    state = package_state(package)
    source = package_source(package)
    icon = state_icon(state)

    print("=================================")
    print(" Beacon Discovery Engine")
    print("=================================")
    print()

    print(f"[{icon}] {package}")
    print()
    print(f"    State  : {state}")
    print(f"    Source : {source}")


if __name__ == "__main__":
    main()