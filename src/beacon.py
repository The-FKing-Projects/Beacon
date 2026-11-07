#!/usr/bin/env python3

import subprocess
import sys


def package_state(package):
    result = subprocess.run(
        ["dpkg", "-s", package],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return "Unknown"

    if "install ok installed" in result.stdout:
        return "Installed"

    return "Unknown"


def main():
    package = sys.argv[1]

    print(f"Package: {package}")
    print(f"State: {package_state(package)}")


if __name__ == "__main__":
    main()