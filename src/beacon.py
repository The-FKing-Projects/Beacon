#!/usr/bin/env python3

import subprocess
import sys


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


def main():
    if len(sys.argv) != 2:
        print("Usage: beacon.py <package>")
        sys.exit(1)

    package = sys.argv[1]

    print(f"Package: {package}")
    print(f"State: {package_state(package)}")


if __name__ == "__main__":
    main()