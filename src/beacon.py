#!/usr/bin/env python3

VERSION = "0.9.4"

import os
import re
import subprocess
import sys
from urllib.parse import urlparse

import tracking
import suggestions
import inspection
import updates


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
    print("    --prepare <package> <asset.deb> Download and pin a selected update.")
    print("    --install <package>            Review and install a prepared update through APT.")
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


class DiscoveryError(Exception):
    pass


def _package_command(command, purpose, allowed_returncodes=(0,)):
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=15, check=False,
            env=tracking.command_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DiscoveryError(f"Unable to {purpose}: {exc}") from exc
    if result.returncode not in allowed_returncodes:
        detail = result.stderr.strip() or f"command exited with status {result.returncode}"
        raise DiscoveryError(f"Unable to {purpose}: {detail}")
    return result


# =================================
# PACKAGE FUNCTIONS
# =================================

def package_exists(package):
    result = _package_command(
        ["apt-cache", "policy", package],
        f"check package availability for {package}",
    )

    for line in (result.stdout or "").splitlines():
        if line.strip().lower().startswith("candidate:"):
            candidate = line.split(":", 1)[1].strip()
            return candidate != "(none)"

    return False


def package_state(package):
    result = _package_command(
        ["dpkg", "-l", package],
        f"inspect package state for {package}", allowed_returncodes=(0, 1),
    )

    requested_name, separator, requested_arch = package.partition(":")
    matching_states = []

    for line in (result.stdout or "").splitlines():
        parts = line.split()

        if len(parts) < 2:
            continue

        installed_name, arch_separator, installed_arch = parts[1].partition(":")
        package_architecture = parts[3] if len(parts) >= 4 else ""

        if installed_name != requested_name:
            continue

        if arch_separator and installed_arch != package_architecture:
            raise DiscoveryError("dpkg returned inconsistent package architecture metadata.")
        if separator and package_architecture != requested_arch:
            continue

        if parts[0] in ("ii", "rc"):
            matching_states.append((package_architecture, parts[0]))

    if len({architecture for architecture, _ in matching_states}) > 1:
        raise DiscoveryError(
            f"Multiple architectures are installed for {requested_name}; "
            "specify package:architecture."
        )
    if matching_states:
        state = matching_states[0][1]
        if state == "ii":
            return "Installed"
        if state == "rc":
            return "Config Remains"

    if package_exists(package):
        return "Available"

    return "Unknown"


def is_local_candidate(package):
    result = _package_command(
        ["apt", "list", "--installed"],
        "list installed packages",
    )

    requested_name, separator, requested_architecture = package.partition(":")
    for line in result.stdout.splitlines():
        if "[installed,local]" not in line:
            continue
        parts = line.split()
        if len(parts) < 3 or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", parts[2]):
            continue
        installed_package = parts[0].split("/", 1)[0].strip()
        installed_name, arch_separator, installed_architecture = installed_package.partition(":")
        if (installed_name == requested_name
                and (not separator or requested_architecture == parts[2])
                and (not arch_separator or installed_architecture == parts[2])):
            return True

    return False


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
    result = _package_command(
        ["apt-cache", "policy", package],
        f"inspect package provenance for {package}",
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
    origins = inspection.policy_origins_for_version(policy_output, selected_version)
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
    result = _package_command(
        ["apt-cache", "policy", package],
        f"inspect package version for {package}",
    )

    output = result.stdout
    candidate = None

    for line in output.splitlines():

        if line.strip().lower().startswith("installed:"):
            version = line.split(":", 1)[1].strip()

            if version != "(none)":
                return version

        if line.strip().lower().startswith("candidate:"):
            candidate = line.split(":", 1)[1].strip()

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
    result = _package_command(["dpkg", "-l"], "list installed packages")
    return sum(line.startswith("ii ") for line in result.stdout.splitlines())


def config_remains_count():
    return len(config_remains_packages())


def auto_installed_count():
    result = _package_command(["apt-mark", "showauto"], "list automatically installed packages")
    return sum(bool(line.strip()) for line in result.stdout.splitlines())


def manual_installed_count():
    return installed_count() - auto_installed_count()


def config_remains_packages():
    result = _package_command(["dpkg", "-l"], "list configuration-remains packages")

    packages = []

    for line in result.stdout.splitlines():

        parts = line.split()

        if line.startswith("rc ") and len(parts) >= 2:
            packages.append(parts[1])

    return sorted(packages)


def local_packages():
    result = _package_command(
        ["apt", "list", "--installed"],
        "list locally installed packages",
    )

    packages = []

    for line in result.stdout.splitlines():

        if "[installed,local]" in line:
            fields = line.split()
            if len(fields) >= 3 and re.fullmatch(r"[a-z0-9][a-z0-9-]*", fields[2]):
                package = fields[0].split("/", 1)[0]
                name = package.split(":", 1)[0]
                packages.append(f"{name}:{fields[2]}")

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

def _main():

    if len(sys.argv) > 1 and sys.argv[1] in (
        "--track", "--untrack", "--check", "--tracked", "--suggest",
        "--inspect", "--prepare", "--install",
    ):
        command = sys.argv[1]
        expected = {
            "--track": 4, "--untrack": 3, "--check": 3, "--tracked": 2,
            "--suggest": 3, "--inspect": 4, "--prepare": 4, "--install": 3,
        }[command]
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
            elif command == "--prepare":
                updates.prepare(sys.argv[2], sys.argv[3])
            elif command == "--install":
                updates.install(sys.argv[2])
            elif command == "--suggest":
                suggestions.suggest(sys.argv[2])
            elif command == "--check":
                tracking.check(sys.argv[2])
            else:
                tracking.list_tracked()
        except (tracking.TrackingError, tracking.sqlite3.Error, DiscoveryError, OSError) as exc:
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


def main():
    try:
        _main()
    except DiscoveryError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()