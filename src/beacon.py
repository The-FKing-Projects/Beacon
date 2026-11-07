#!/usr/bin/env python3

VERSION = "0.1.2"

import os
import subprocess
import sys


# =================================
# UI FUNCTIONS
# =================================

def print_banner():
    print("=================================")
    print(" Beacon Discovery Engine")
    print("=================================")
    print()


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
    print("    --repos      Show repository inventory.")
    print("    --clean      Show configuration remains.")
    print("    --local      Show locally installed packages.")
    print()
    print("Examples:")
    print("    beacon.py floorp")
    print("    beacon.py steam")
    print("    beacon.py clover-eye")
    print("    beacon.py --scan")
    print("    beacon.py --repos")
    print("    beacon.py --clean")
    print("    beacon.py --local")


def state_icon(state):
    icons = {
        "Installed": "✓",
        "Config Remains": "!",
        "Available": "↓",
        "Unknown": "?",
    }

    return icons.get(state, "?")

# =================================
# PACKAGE FUNCTIONS
# =================================

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


# =================================
# REPOSITORY FUNCTIONS
# =================================

def active_repository_files():
    path = "/etc/apt/sources.list.d"

    files = []

    for entry in os.listdir(path):

        full_path = os.path.join(path, entry)

        if os.path.isfile(full_path):

            if entry.endswith(".sources") or entry.endswith(".list"):
                files.append(full_path)

    return files


def repository_file_count():
    return len(active_repository_files())


def ppa_repository_count():

    count = 0

    for repo_file in active_repository_files():

        try:

            with open(repo_file, "r") as file:

                content = file.read().lower()

                if "ppa.launchpadcontent.net" in content:
                    count += 1

        except Exception:
            pass

    return count


def ubuntu_repository_count():

    count = 0

    for repo_file in active_repository_files():

        try:

            with open(repo_file, "r") as file:

                content = file.read().lower()

                if (
                    "archive.ubuntu.com" in content
                    or "security.ubuntu.com" in content
                    or "ubuntu.com" in content
                ):
                    count += 1

        except Exception:
            pass

    return count


def vendor_repository_count():

    count = 0

    for repo_file in active_repository_files():

        try:

            with open(repo_file, "r") as file:

                content = file.read().lower()

                if "ppa.launchpadcontent.net" in content:
                    continue

                if (
                    "archive.ubuntu.com" in content
                    or "security.ubuntu.com" in content
                    or "ubuntu.com" in content
                ):
                    continue

                count += 1

        except Exception:
            pass

    return count


def repository_names():

    names = []

    for repo_file in active_repository_files():

        names.append(os.path.basename(repo_file))

    return sorted(names)

# =================================
# SCAN FUNCTIONS
# =================================

def installed_count():
    result = subprocess.run(
        "dpkg -l | grep '^ii' | wc -l",
        shell=True,
        capture_output=True,
        text=True,
    )

    return int(result.stdout.strip())


def config_remains_count():
    result = subprocess.run(
        "dpkg -l | grep '^rc' | wc -l",
        shell=True,
        capture_output=True,
        text=True,
    )

    return int(result.stdout.strip())


def auto_installed_count():
    result = subprocess.run(
        "apt-mark showauto | wc -l",
        shell=True,
        capture_output=True,
        text=True,
    )

    return int(result.stdout.strip())


def manual_installed_count():
    return installed_count() - auto_installed_count()


def config_remains_packages():
    result = subprocess.run(
        "dpkg -l | grep '^rc'",
        shell=True,
        capture_output=True,
        text=True,
    )

    packages = []

    for line in result.stdout.splitlines():

        parts = line.split()

        if len(parts) >= 2:
            packages.append(parts[1])

    return sorted(packages)


def local_packages():
    result = subprocess.run(
        ["apt", "list", "--installed"],
        capture_output=True,
        text=True,
    )

    packages = []

    for line in result.stdout.splitlines():

        if "[installed,local]" in line:

            package = line.split("/")[0]

            packages.append(package)

    return sorted(packages)


def scan_summary():
    print_banner()

    print("System Summary")
    print()

    print(f"Total Packages          : {installed_count()}")
    print(f"Manually Installed      : {manual_installed_count()}")
    print(f"Automatically Installed : {auto_installed_count()}")
    print(f"Configuration Remains   : {config_remains_count()}")
    print()

    print(f"Repository Files        : {repository_file_count()}")
    print(f"PPA Repositories        : {ppa_repository_count()}")
    print(f"Vendor Repositories     : {vendor_repository_count()}")
    print(f"Ubuntu Repositories     : {ubuntu_repository_count()}")


def repository_summary():
    print_banner()

    print("Repository Inventory")
    print()

    for repo in repository_names():
        print(f"  - {repo}")


def clean_summary():
    print_banner()

    print("Configuration Remains")
    print()

    packages = config_remains_packages()

    for package in packages:
        print(f"  - {package}")

    print()

    print(f"Total Packages : {len(packages)}")


def local_summary():
    print_banner()

    print("Local Packages")
    print()

    packages = local_packages()

    for package in packages:
        print(f"  - {package}")

    print()

    print(f"Total Local Packages : {len(packages)}")

# =================================
# MAIN
# =================================

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

    if sys.argv[1] == "--repos":
        repository_summary()
        sys.exit(0)

    if sys.argv[1] == "--clean":
        clean_summary()
        sys.exit(0)

    if sys.argv[1] == "--local":
        local_summary()
        sys.exit(0)

    package = sys.argv[1]

    state = package_state(package)
    source = package_source(package)
    version = package_version(package)
    icon = state_icon(state)

    print_banner()

    print(f"[{icon}] {package}")
    print()

    print(f"    State   : {state}")
    print(f"    Source  : {source}")
    print(f"    Version : {version}")


if __name__ == "__main__":
    main()