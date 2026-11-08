"""Manual GitHub release tracking for installed Debian packages."""

import json
import os
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


PACKAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9+.-]*(?::[a-z0-9][a-z0-9-]*)?$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]+$")
VERSION_PATTERN = re.compile(r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
ASSET_ARCHITECTURES = {
    "amd64": "amd64", "x86_64": "amd64", "x64": "amd64",
    "arm64": "arm64", "aarch64": "arm64",
    "i386": "i386", "i686": "i386", "x86": "i386",
    "armhf": "armhf", "armel": "armel", "all": "all",
}


class TrackingError(Exception):
    pass


def repository_name(value):
    if value.startswith("https://"):
        parsed = urlparse(value)
        if (parsed.netloc.lower() != "github.com" or parsed.query or parsed.fragment
                or parsed.params):
            raise TrackingError("Use owner/repository or an HTTPS github.com repository URL.")
        value = parsed.path.strip("/")
    if (not REPOSITORY_PATTERN.fullmatch(value) or value.endswith(".git")
            or value.split("/")[-1] in (".", "..")):
        raise TrackingError("Use owner/repository or an HTTPS github.com repository URL.")
    return value


def installed_package(name):
    if not PACKAGE_PATTERN.fullmatch(name):
        raise TrackingError("Invalid Debian package name.")
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f", "${binary:Package}\t${Architecture}\t${db:Status-Status}\t${Version}\n", name],
            capture_output=True, text=True, check=False,
        )
    except OSError as exc:
        raise TrackingError(f"Unable to run dpkg-query: {exc}") from exc
    requested_name, _, requested_arch = name.partition(":")
    matches = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            raise TrackingError("Unexpected dpkg-query output; package was not recorded.")
        binary_name, architecture, state, version = parts
        if (binary_name.split(":", 1)[0] == requested_name and state == "installed"
                and (not requested_arch or architecture == requested_arch)):
            matches.append((requested_name, architecture, version))
    if result.returncode != 0:
        raise TrackingError(f"Unable to inspect installed package {name}: {result.stderr.strip() or 'not found'}")
    if len(matches) != 1:
        raise TrackingError(f"Expected one installed instance of {name}; specify its architecture if ambiguous.")
    return matches[0]


def database_path():
    state = os.environ.get("XDG_STATE_HOME")
    if state:
        root = Path(state)
        if not root.is_absolute():
            raise TrackingError("XDG_STATE_HOME must be an absolute path.")
    else:
        root = Path.home() / ".local" / "state"
    return root / "beacon" / "tracking.sqlite3"


def open_database():
    path = database_path()
    connection = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys = ON")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if version == 0 and not tables:
            with connection:
                connection.execute("""CREATE TABLE tracked_packages (
                    package_name TEXT NOT NULL,
                    architecture TEXT NOT NULL,
                    repository_id INTEGER NOT NULL,
                    repository_name TEXT NOT NULL,
                    PRIMARY KEY (package_name, architecture)
                )""")
                connection.execute("PRAGMA user_version = 1")
        elif version != 1 or {row[0] for row in tables} != {"tracked_packages"}:
            connection.close()
            raise TrackingError("Unsupported or unrecognized tracking database; no changes made.")
        return connection
    except (OSError, sqlite3.Error) as exc:
        if connection is not None:
            connection.close()
        raise TrackingError(f"Unable to open tracking database {path}: {exc}") from exc


def github_get(path):
    request = Request(
        "https://api.github.com" + path,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Beacon"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            final_url = urlparse(response.geturl())
            if final_url.scheme != "https" or final_url.netloc.lower() != "api.github.com":
                raise TrackingError("GitHub redirected to an unexpected host.")
            data = json.load(response)
    except HTTPError as exc:
        detail = f"GitHub request failed (HTTP {exc.code})"
        if exc.code in (403, 429):
            detail += "; check rate limits and retry later"
        exc.close()
        raise TrackingError(detail + ".") from exc
    except (URLError, OSError, ValueError) as exc:
        raise TrackingError(f"GitHub request failed: {exc}") from exc
    if not isinstance(data, dict):
        raise TrackingError("Unexpected GitHub response.")
    return data


def resolve_repository(name):
    name = repository_name(name)
    data = github_get("/repos/" + quote(name, safe="/"))
    canonical = data.get("full_name")
    identifier = data.get("id")
    if not isinstance(canonical, str):
        raise TrackingError("GitHub returned an invalid repository name.")
    try:
        repository_name(canonical)
    except TrackingError as exc:
        raise TrackingError("GitHub returned an invalid repository name.") from exc
    if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0:
        raise TrackingError("GitHub returned an invalid repository identity.")
    return canonical, identifier


def latest_release(name):
    try:
        data = github_get("/repos/" + quote(name, safe="/") + "/releases/latest")
    except TrackingError as exc:
        if isinstance(exc.__cause__, HTTPError) and exc.__cause__.code == 404:
            raise TrackingError("No published stable GitHub release found (or repository is inaccessible).") from exc
        raise
    tag = data.get("tag_name")
    url = data.get("html_url")
    if not isinstance(tag, str) or not tag or not isinstance(url, str):
        raise TrackingError("GitHub returned an invalid release.")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise TrackingError("GitHub returned an invalid release URL.")
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise TrackingError("GitHub returned invalid or missing release assets.")
    deb_assets = []
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
            raise TrackingError("GitHub returned an invalid release asset.")
        filename = asset["name"]
        if not filename.lower().endswith(".deb"):
            continue
        asset_url = asset.get("browser_download_url")
        if (not filename or any(ord(char) < 32 or ord(char) == 127 for char in filename)
                or not isinstance(asset_url, str)
                or any(ord(char) < 32 or ord(char) == 127 for char in asset_url)):
            raise TrackingError("GitHub returned an invalid Debian release asset.")
        parsed_asset = urlparse(asset_url)
        if parsed_asset.scheme != "https" or parsed_asset.netloc.lower() != "github.com":
            raise TrackingError("GitHub returned an invalid Debian asset URL.")
        deb_assets.append((filename, asset_url))
    return tag, url, deb_assets


def asset_match(filename, package, architecture):
    """Return filename evidence, not a guarantee of package compatibility."""
    stem = filename[:-4].lower()
    arch_match = re.search(
        r"[_-](x86_64|aarch64|amd64|arm64|armhf|armel|i386|i686|x64|x86|all)$",
        stem,
    )
    if not arch_match:
        return "Unverified: architecture not recognized in filename"
    asset_arch = ASSET_ARCHITECTURES[arch_match.group(1)]
    if asset_arch != architecture and asset_arch != "all":
        return f"Not suggested: filename indicates {asset_arch}, not {architecture}"
    name_part = stem[:arch_match.start()]
    # Remove a version only when it starts with a digit (or v followed by one).
    name_part = re.sub(r"[_-]v?\d[^_]*$", "", name_part)
    normalize = lambda value: re.sub(r"[-_.]", "", value.lower())
    if normalize(name_part) != normalize(package):
        return "Unverified: filename does not match the installed package name"
    return f"Likely candidate: filename matches package name and {asset_arch} architecture"


def print_deb_assets(assets, package, architecture):
    if not assets:
        print("Debian assets: none found in this release.")
        return
    print("Debian assets (filename-based suggestions, not verified packages):")
    matches = 0
    for filename, url in assets:
        result = asset_match(filename, package, architecture)
        if result.startswith("Likely candidate:"):
            matches += 1
        print(f"  {filename}: {result}")
        print(f"    {url}")
    if matches == 0:
        print("No likely candidates found; review unverified assets manually.")
    elif matches > 1:
        print("Multiple likely candidates found; review them manually.")
    print("Package identity, contents, compatibility, and integrity have not been verified.")


def compare_versions(installed, tag):
    left = VERSION_PATTERN.fullmatch(installed)
    right = VERSION_PATTERN.fullmatch(tag)
    if not left or not right:
        return "Unknown: versions cannot be compared safely."
    current = tuple(map(int, left.groups()))
    latest = tuple(map(int, right.groups()))
    if latest > current:
        return "Newer upstream release available."
    if latest == current:
        return "Versions match."
    return "Installed version is newer than the latest upstream release."


def track(package, repository):
    name, architecture, version = installed_package(package)
    canonical, identifier = resolve_repository(repository)
    with closing(open_database()) as db:
        existing = db.execute(
            "SELECT repository_name, repository_id FROM tracked_packages WHERE package_name=? AND architecture=?",
            (name, architecture),
        ).fetchone()
        print(f"Package: {name}:{architecture} ({version})")
        print(f"GitHub repository: https://github.com/{canonical}")
        if existing:
            print(f"Current association: https://github.com/{existing[0]}")
        print("Confirm only if you have verified this is the package's upstream.")
        try:
            answer = input("Save this association? [y/N] ").strip().lower()
        except EOFError as exc:
            raise TrackingError("Confirmation required; association was not saved.") from exc
        if answer not in ("y", "yes"):
            print("Association not saved.")
            return
        with db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT repository_name, repository_id FROM tracked_packages WHERE package_name=? AND architecture=?",
                (name, architecture),
            ).fetchone()
            if current != existing:
                raise TrackingError("Association changed during confirmation; review it and try again.")
            db.execute("""INSERT INTO tracked_packages
                (package_name, architecture, repository_id, repository_name) VALUES (?, ?, ?, ?)
                ON CONFLICT(package_name, architecture) DO UPDATE SET
                    repository_id=excluded.repository_id, repository_name=excluded.repository_name""",
                (name, architecture, identifier, canonical))
    print("Association saved.")


def check(package):
    name, architecture, version = installed_package(package)
    with closing(open_database()) as db:
        row = db.execute(
            "SELECT repository_name, repository_id FROM tracked_packages WHERE package_name=? AND architecture=?",
            (name, architecture),
        ).fetchone()
    if not row:
        raise TrackingError(f"No confirmed upstream for {name}:{architecture}.")
    repository, identifier = resolve_repository(row[0])
    if identifier != row[1]:
        raise TrackingError("GitHub repository identity changed; confirm the upstream again before tracking.")
    tag, url, assets = latest_release(repository)
    if repository != row[0]:
        with closing(open_database()) as db, db:
            result = db.execute(
                "UPDATE tracked_packages SET repository_name=? WHERE package_name=? AND architecture=? "
                "AND repository_name=? AND repository_id=?",
                (repository, name, architecture, row[0], identifier),
            )
            if result.rowcount != 1:
                raise TrackingError("Association changed during the release check; try again.")
    print(f"Package: {name}:{architecture}")
    print(f"Installed version: {version}")
    print(f"GitHub repository: https://github.com/{repository}")
    print(f"Latest stable release: {tag}")
    print(f"Release URL: {url}")
    print(f"Status: {compare_versions(version, tag)}")
    print_deb_assets(assets, name, architecture)


def list_tracked():
    with closing(open_database()) as db:
        rows = db.execute(
            "SELECT package_name, architecture, repository_name FROM tracked_packages ORDER BY package_name, architecture"
        ).fetchall()
    if not rows:
        print("No confirmed upstream associations.")
    for name, architecture, repository in rows:
        print(f"{name}:{architecture}  https://github.com/{repository}")
