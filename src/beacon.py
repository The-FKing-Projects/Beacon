#!/usr/bin/env python3

VERSION = "0.1.1"

import subprocess
import sys

def help_menu():
    print("Beacon Discovery Engine")
    print()
    print("Usage:")
    print("    beacon.py <package>")
    print()
    print("Options:")
    print("    --help       Show this help menu.")
    print("    --version    Show Beacon version.")
    print("    --scan       Show system summary.")
    print()
    print("Examples:")
    print("    beacon.py floorp")
    print("    beacon.py steam")
    print("    beacon.py clovereye")
    print("    beacon.py --scan")

def package_exists(package):
    result = subprocess.run(
        ["apt-cache", "policy", package],
        capture_output=True,
        text=True,
    )

    output = result.stdout
    error = result.stderr

    if "Unable to locate package" in error:
        return False

    if "Candidate:" in output:
        return True

    return False


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

    if package_exists(package):
        return "Available"

    return "Unknown"

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

def package_version(package):
    result = subprocess.run(
        ["apt-cache", "policy", package],
        capture_output=True,
        text=True,
    )

    output = result.stdout
    candidate = None

    for line in output.splitlines():

        if "Installed:" in line:
            version = line.split("Installed:")[1].strip()

            if version != "(none)":
                return version

        if "Candidate:" in line:
            candidate = line.split("Candidate:")[1].strip()

    return candidate if candidate and candidate != "(none)" else "Unknown"

def installed_count():
    result = subprocess.run(
        "dpkg -l | grep '^ii' | wc -l",
        shell=True,
        capture_output=True,
        text=True,
    )

    return result.stdout.strip()

def config_remains_count():
    result = subprocess.run(
        "dpkg -l | grep '^rc' | wc -l",
        shell=True,
        capture_output=True,
        text=True,
    )

    return result.stdout.strip()  

def print_banner():
    print("=================================")
    print(" Beacon Discovery Engine")
    print("=================================")
    print()

def scan_summary():
    print_banner()
    print("System Summary")
    print()
    print(f"Installed Packages : {installed_count()}")
    print(f"Config Remains     : {config_remains_count()}")

def state_icon(state):
    icons = {
        "Installed": "✓",
        "Config Remains": "!",
        "Available": "↓",
        "Unknown": "?",
    }

    return icons.get(state, "?")

def main():

    if len(sys.argv) != 2:
        print("Usage: beacon.py <package>")
        sys.exit(1)

    if sys.argv[1] == "--version":
        print(f"Beacon v{VERSION}")
        sys.exit(0)

    if sys.argv[1] == "--help":
        help_menu()
        sys.exit(0)

    if sys.argv[1] == "--scan":
        scan_summary()
        sys.exit(0)

    package = sys.argv[1]

    state = package_state(package)
    source = package_source(package)
    version = package_version(package)
    icon = state_icon(state)

    print_banner()
    print()
    print(f"[{icon}] {package}")
    print()

    print(f"    State   : {state}")
    print(f"    Source  : {source}")
    print(f"    Version : {version}")

if __name__ == "__main__":
    main()