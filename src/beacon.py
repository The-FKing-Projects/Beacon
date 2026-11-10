#!/usr/bin/env python3

VERSION = "0.9.0"

import os
import subprocess
import sys
from urllib.parse import urlparse

import tracking
import suggestions
import inspection


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
    print("    beacon <package>")
    print()
    print("Options:")
    print("    --help       Show this help menu.")
    print("    --version    Show Beacon version.")
    print("    --scan       Show system summary.")
    print("    --repos      Show repository inventory.")
    print("    --clean      Show configuration remains.")
    print("    --local      Show locally installed packages.")
    print("    --track <package> <owner/repo>  Confirm a GitHub upstream.")
    print("    --untrack <package>            Remove a confirmed association.")
    print("    --suggest <package>            Suggest GitHub upstreams.")
    print("    --check <package>              Check its latest GitHub release.")
    print("    --inspect <package> <asset.deb> Inspect a selected release asset.")
    print("    --tracked                      List confirmed associations.")
    print()
    print("Examples:")
    print("    beacon floorp")
    print("    beacon steam")
    print("    beacon clover-eye")
    print("    beacon --scan")
    print("    beacon --repos")
    print("    beacon --clean")
    print("    beacon --local")


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

    for line in (result.stdout or "").splitlines():
        if line.strip().lower().startswith("candidate:"):
            candidate = line.split(":", 1)[1].strip()
            return candidate != "(none)"

    return False


def package_state(package):
    result = subprocess.run(
        ["dpkg", "-l", package],
        capture_output=True,
        text=True,
    )

    requested_name, separator, requested_arch = package.partition(":")

    for line in (result.stdout or "").splitlines():
        parts = line.split()

        if len(parts) < 2:
            continue

        installed_name, arch_separator, installed_arch = parts[1].partition(":")

        if installed_name != requested_name:
            continue

        if separator and (
            not arch_separator or installed_arch != requested_arch
        ):
            continue

        if parts[0] == "ii":
            return "Installed"

        if parts[0] == "rc":
            return "Config Remains"

    if package_exists(package):
        return "Available"

    return "Unknown"


def is_local_candidate(package):
    result = subprocess.run(
        ["apt", "list", "--installed"],
        capture_output=True,
        text=True,
    )

    for line in result.stdout.splitlines():
        if "[installed,local]" not in line:
            continue

        installed_package = line.split("/")[0].strip()

        if installed_package == package:
            return True

    return False


def _policy_origins_for_version(output, selected_version):
    origins = []
    current_version = None
    in_version_table = False

    for line in output.splitlines():
        stripped = line.strip()

        if stripped.lower().startswith("version table:"):
            in_version_table = True
            continue

        if not in_version_table:
            continue

        version_line = stripped[3:].strip() if stripped.startswith("***") else stripped
        parts = version_line.split()

        if len(parts) >= 2 and parts[1].isdigit():
            current_version = parts[0]
            continue

        if current_version == selected_version and (
            "://" in stripped or "/var/lib/dpkg/status" in stripped
        ):
            origins.append(stripped)

    return origins


def _source_for_repository_url(url):
    host = (urlparse(url).hostname or "").lower()

    if (
        host.startswith("ppa.")
        or host == "launchpad.net"
        or host.endswith((".launchpad.net", ".launchpadcontent.net"))
    ):
        return "PPA"

    if host == "ubuntu.com" or host.endswith(".ubuntu.com"):
        return "Ubuntu Repository"

    if host == "debian.org" or host.endswith(".debian.org"):
        return "Debian Repository"

    return "Vendor Repository"


def _confidence_label(score):
    if score >= 75:
        return "High"

    if score >= 40:
        return "Medium"

    return "Low"


def package_provenance(package):
    result = subprocess.run(
        ["apt-cache", "policy", package],
        capture_output=True,
        text=True,
    )
    policy_output = result.stdout or ""
    installed_version = None
    candidate_version = None

    for line in policy_output.splitlines():
        if line.strip().lower().startswith("installed:"):
            installed_version = line.split(":", 1)[1].strip()
        elif line.strip().lower().startswith("candidate:"):
            candidate_version = line.split(":", 1)[1].strip()

    is_installed = installed_version and installed_version != "(none)"
    selected_version = installed_version if is_installed else candidate_version
    origins = _policy_origins_for_version(policy_output, selected_version)
    repository_urls = []
    has_dpkg_status_origin = False

    for origin in origins:
        if "/var/lib/dpkg/status" in origin:
            has_dpkg_status_origin = True

        for token in origin.split():
            if token.startswith(("http://", "https://")):
                repository_urls.append(token.rstrip("),"))

    repository_urls = sorted(set(repository_urls))

    if repository_urls:
        source_types = {
            _source_for_repository_url(url) for url in repository_urls
        }

        if len(source_types) > 1:
            source = "Multiple Sources"
            score = 45
            evidence = [
                "The selected package version is listed in repositories of "
                f"multiple types: {', '.join(sorted(source_types))}."
            ]
        else:
            source = next(iter(source_types))
            score = 90
            version_kind = "installed" if is_installed else "candidate"
            evidence = [
                f"The selected {version_kind} version is listed at {url}."
                for url in repository_urls
            ]
    elif is_installed and is_local_candidate(package):
        source = "Local .deb Candidate"
        score = 65
        evidence = [
            "APT marks the installed package as local, with no repository "
            "origin for its installed version."
        ]
    elif is_installed and has_dpkg_status_origin:
        source = "Local .deb Candidate"
        score = 55
        evidence = [
            "The installed version appears only in dpkg status metadata; "
            "no repository origin was found."
        ]
    else:
        source = "Unknown"
        score = 0
        evidence = ["No repository origin or local-install signal was found."]

    return {
        "source": source,
        "score": score,
        "confidence": _confidence_label(score),
        "evidence": evidence,
    }


def package_source(package):
    return package_provenance(package)["source"]


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


def package_confidence(package):
    return package_provenance(package)["confidence"]


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

    if len(sys.argv) > 1 and sys.argv[1] in ("--track", "--untrack", "--check", "--tracked", "--suggest", "--inspect"):
        command = sys.argv[1]
        expected = {"--track": 4, "--untrack": 3, "--check": 3, "--tracked": 2, "--suggest": 3, "--inspect": 4}[command]
        if len(sys.argv) != expected:
            print(f"Invalid arguments for {command}; see --help.", file=sys.stderr)
            sys.exit(1)
        try:
            if command == "--track":
                tracking.track(sys.argv[2], sys.argv[3])
            elif command == "--untrack":
                tracking.untrack(sys.argv[2])
            elif command == "--inspect":
                inspection.inspect(sys.argv[2], sys.argv[3])
            elif command == "--suggest":
                suggestions.suggest(sys.argv[2])
            elif command == "--check":
                tracking.check(sys.argv[2])
            else:
                tracking.list_tracked()
        except (tracking.TrackingError, tracking.sqlite3.Error, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    if len(sys.argv) != 2:
        print("Usage: beacon <package>")
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
    provenance = package_provenance(package)
    version = package_version(package)
    icon = state_icon(state)

    print_banner()

    print(f"[{icon}] {package}")
    print()

    print(f"    State      : {state}")
    print(f"    Source     : {provenance['source']}")
    print(f"    Version    : {version}")
    print(
        f"    Confidence : {provenance['confidence']} "
        f"({provenance['score']}/100)"
    )
    print(f"    Evidence   : {'; '.join(provenance['evidence'])}")


if __name__ == "__main__":
    main()