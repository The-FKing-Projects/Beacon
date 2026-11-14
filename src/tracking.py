"""Manual GitHub release tracking for installed Debian packages."""

import json
import fcntl
import os
from contextlib import closing
from http.client import HTTPException
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
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


def command_environment():
    environment = os.environ.copy()
    environment.update({"LC_ALL": "C", "LANG": "C"})
    return environment


def acquire_database_lock():
    path = database_path().parent
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        details = path.lstat()
        if not stat.S_ISDIR(details.st_mode) or details.st_uid != os.geteuid():
            raise TrackingError("Tracking storage directory is not owned by the current user.")
        if details.st_mode & 0o077:
            path.chmod(0o700)
        descriptor = os.open(
            path / ".updates.lock",
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        lock_details = os.fstat(descriptor)
        if (not stat.S_ISREG(lock_details.st_mode)
                or lock_details.st_uid != os.geteuid()
                or lock_details.st_mode & 0o077):
            os.close(descriptor)
            raise TrackingError("Tracking lock is not private and owned by the current user.")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return descriptor
    except (OSError, TrackingError) as exc:
        raise TrackingError(f"Unable to lock tracking state: {exc}") from exc


def release_database_lock(descriptor):
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


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
            [
                "dpkg-query", "-W",
                "-f", "${binary:Package}\t${Architecture}\t${db:Status-Status}\t${Version}\n",
                name,
            ],
            capture_output=True, text=True, timeout=15, check=False,
            env=command_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TrackingError(f"Unable to run dpkg-query: {exc}") from exc
    requested_name, _, requested_arch = name.partition(":")
    matches = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            raise TrackingError("Unexpected dpkg-query output; package was not recorded.")
        binary_name, architecture, state, version = parts
        installed_name, separator, installed_arch = binary_name.partition(":")
        if installed_name != requested_name:
            continue
        if separator and installed_arch != architecture:
            raise TrackingError("dpkg-query returned inconsistent package architecture metadata.")
        if state == "installed" and (not requested_arch or architecture == requested_arch):
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


TRACKED_COLUMNS = [
    ("package_name", "TEXT", 1, None, 1),
    ("architecture", "TEXT", 1, None, 2),
    ("repository_id", "INTEGER", 1, None, 0),
    ("repository_name", "TEXT", 1, None, 0),
]
PREPARED_COLUMNS = [
    ("package_name", "TEXT", 1, None, 1),
    ("architecture", "TEXT", 1, None, 2),
    ("repository_id", "INTEGER", 1, None, 0),
    ("repository_name", "TEXT", 1, None, 0),
    ("release_tag", "TEXT", 1, None, 0),
    ("asset_name", "TEXT", 1, None, 0),
    ("asset_url", "TEXT", 1, None, 0),
    ("checksum_asset_url", "TEXT", 0, None, 0),
    ("expected_sha256", "TEXT", 0, None, 0),
    ("sha256", "TEXT", 1, None, 0),
    ("checksum_status", "TEXT", 1, None, 0),
    ("asset_package_name", "TEXT", 1, None, 0),
    ("asset_architecture", "TEXT", 1, None, 0),
    ("asset_version", "TEXT", 1, None, 0),
    ("installed_version", "TEXT", 1, None, 0),
    ("artifact_path", "TEXT", 1, None, 0),
    ("prepared_at", "TEXT", 1, None, 0),
]


def _create_prepared_table(connection):
    connection.execute("""CREATE TABLE prepared_updates (
        package_name TEXT NOT NULL,
        architecture TEXT NOT NULL,
        repository_id INTEGER NOT NULL,
        repository_name TEXT NOT NULL,
        release_tag TEXT NOT NULL,
        asset_name TEXT NOT NULL,
        asset_url TEXT NOT NULL,
        checksum_asset_url TEXT,
        expected_sha256 TEXT,
        sha256 TEXT NOT NULL,
        checksum_status TEXT NOT NULL,
        asset_package_name TEXT NOT NULL,
        asset_architecture TEXT NOT NULL,
        asset_version TEXT NOT NULL,
        installed_version TEXT NOT NULL,
        artifact_path TEXT NOT NULL,
        prepared_at TEXT NOT NULL,
        PRIMARY KEY (package_name, architecture)
    )""")


def _backup_before_migration(connection, path):
    backup = path.with_name(path.name + ".v1.bak")
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.backup-", dir=path.parent,
        )
        os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        destination = sqlite3.connect(temporary)
        try:
            connection.backup(destination)
            destination.commit()
        finally:
            destination.close()
        with open(temporary, "rb") as source:
            os.fsync(source.fileno())
        os.link(temporary, backup)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError as exc:
        raise TrackingError(
            f"Migration backup already exists at {backup}; preserve and review it before retrying."
        ) from exc
    except (OSError, sqlite3.Error) as exc:
        raise TrackingError(f"Unable to preserve tracking database before migration: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _create_current_schema(connection):
    connection.execute("""CREATE TABLE tracked_packages (
        package_name TEXT NOT NULL,
        architecture TEXT NOT NULL,
        repository_id INTEGER NOT NULL,
        repository_name TEXT NOT NULL,
        PRIMARY KEY (package_name, architecture)
    )""")
    _create_prepared_table(connection)
    connection.execute("PRAGMA user_version = 2")


def open_database():
    path = database_path()
    connection = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys = ON")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        objects = connection.execute(
            "SELECT name, type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if version == 0 and not objects:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                _create_current_schema(connection)
            version = 2
            objects = [("tracked_packages", "table"), ("prepared_updates", "table")]
        if set(objects) != {("tracked_packages", "table")} and version == 1:
            raise TrackingError("Unsupported or unrecognized tracking database; no changes made.")
        if version not in (1, 2):
            raise TrackingError("Unsupported or unrecognized tracking database; no changes made.")
        columns = connection.execute("PRAGMA table_info(tracked_packages)").fetchall()
        if [tuple(column[1:]) for column in columns] != TRACKED_COLUMNS:
            raise TrackingError("Unrecognized tracking table structure; no changes made.")
        if version == 1:
            _backup_before_migration(connection, path)
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                _create_prepared_table(connection)
                connection.execute("PRAGMA user_version = 2")
            version = 2
            objects = [("tracked_packages", "table"), ("prepared_updates", "table")]
        if version == 2:
            if set(objects) != {("tracked_packages", "table"), ("prepared_updates", "table")}:
                raise TrackingError("Unsupported or unrecognized tracking database; no changes made.")
            columns = connection.execute("PRAGMA table_info(prepared_updates)").fetchall()
            if [tuple(column[1:]) for column in columns] != PREPARED_COLUMNS:
                raise TrackingError("Unrecognized prepared-update table structure; no changes made.")
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise TrackingError("Tracking database integrity check failed; no changes made.")
        rows = connection.execute(
            "SELECT package_name, architecture, repository_id, repository_name FROM tracked_packages"
        )
        for name, architecture, identifier, repository in rows:
            if (not isinstance(name, str) or not PACKAGE_PATTERN.fullmatch(name) or ":" in name
                    or not isinstance(architecture, str)
                    or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", architecture)
                    or not isinstance(identifier, int) or identifier <= 0
                    or not isinstance(repository, str)):
                raise TrackingError("Invalid saved tracking association; no changes made.")
            if repository_name(repository) != repository:
                raise TrackingError("Invalid saved tracking repository; no changes made.")
        prepared = connection.execute(
            "SELECT package_name, architecture, repository_id, repository_name, release_tag, "
            "asset_name, asset_url, checksum_asset_url, expected_sha256, sha256, checksum_status, "
            "asset_package_name, asset_architecture, asset_version, installed_version, artifact_path, "
            "prepared_at FROM prepared_updates"
        )
        for row in prepared:
            (
                name, architecture, identifier, repository, tag, asset_name, asset_url,
                checksum_url, expected_digest, digest, checksum_status, asset_package,
                asset_architecture, asset_version, installed_version, artifact_path, prepared_at,
            ) = row
            if (
                not isinstance(name, str) or not PACKAGE_PATTERN.fullmatch(name) or ":" in name
                or not isinstance(architecture, str)
                or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", architecture)
                or not isinstance(identifier, int) or identifier <= 0
                or not isinstance(repository, str) or repository_name(repository) != repository
                or not isinstance(tag, str) or not tag or any(not c.isprintable() for c in tag)
                or not isinstance(asset_name, str) or not asset_name or "/" in asset_name
                or "\\" in asset_name or any(not c.isprintable() for c in asset_name)
                or not isinstance(asset_url, str)
                or not _valid_release_asset_url(asset_url, repository, tag, asset_name)
                or (checksum_url is not None and (
                    not isinstance(checksum_url, str)
                    or not _valid_release_asset_url(checksum_url, repository, tag, "SHA256SUMS")
                ))
                or (expected_digest is not None and not re.fullmatch(r"[0-9a-f]{64}", str(expected_digest)))
                or not re.fullmatch(r"[0-9a-f]{64}", str(digest))
                or checksum_status not in ("matched-unauthenticated", "entry-missing", "asset-missing")
                or (checksum_status == "matched-unauthenticated" and (
                    expected_digest is None or expected_digest != digest or checksum_url is None
                ))
                or (checksum_status == "entry-missing" and (
                    expected_digest is not None or checksum_url is None
                ))
                or (checksum_status == "asset-missing" and (
                    expected_digest is not None or checksum_url is not None
                ))
                or not isinstance(asset_package, str) or asset_package != name
                or not isinstance(asset_architecture, str)
                or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", asset_architecture)
                or not isinstance(asset_version, str) or not asset_version
                or not isinstance(installed_version, str) or not installed_version
                or not isinstance(artifact_path, str) or not os.path.isabs(artifact_path)
                or not isinstance(prepared_at, str) or not prepared_at
            ):
                raise TrackingError("Invalid saved prepared update; no changes made.")
        return connection
    except (TrackingError, OSError, sqlite3.Error) as exc:
        if connection is not None:
            connection.close()
        raise TrackingError(
            f"Unable to open tracking database {path}: {exc} "
            "Preserve the database before attempting recovery; Beacon has not reset it."
        ) from exc


def _valid_release_asset_url(url, repository, tag, asset):
    try:
        parsed = urlparse(url)
        expected = (
            f"/{repository}/releases/download/{tag}/{asset}"
        )
        return (
            parsed.scheme == "https"
            and parsed.netloc.lower() == "github.com"
            and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment and not parsed.params
            and unquote(parsed.path) == expected
        )
    except ValueError:
        return False


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
    except (URLError, OSError, ValueError, HTTPException) as exc:
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
        if not _valid_release_asset_url(asset_url, name, tag, filename):
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


def _prepared_artifact_for_removal(db, package, architecture):
    row = db.execute(
        "SELECT artifact_path FROM prepared_updates WHERE package_name=? AND architecture=?",
        (package, architecture),
    ).fetchone()
    if not row:
        return None
    configured = os.environ.get("XDG_DATA_HOME")
    if configured:
        root = Path(configured)
        if not root.is_absolute():
            raise TrackingError("XDG_DATA_HOME must be an absolute path.")
    else:
        root = Path.home() / ".local" / "share"
    beacon_directory = root / "beacon"
    directory = beacon_directory / "updates"
    for path in (beacon_directory, directory):
        try:
            directory_details = path.lstat()
        except OSError as exc:
            raise TrackingError(f"Unable to inspect prepared-update storage: {exc}") from exc
        if (not stat.S_ISDIR(directory_details.st_mode)
                or directory_details.st_uid != os.geteuid()
                or stat.S_IMODE(directory_details.st_mode) & 0o077):
            raise TrackingError("Prepared-update storage is not private; refusing to remove it.")
    artifact = Path(row[0])
    expected = re.escape(f"{package}.{architecture}.") + r"[a-f0-9]{32}\.deb"
    if artifact.parent != directory or not re.fullmatch(expected, artifact.name):
        raise TrackingError("Prepared artifact path is invalid; refusing to remove the association.")
    try:
        details = artifact.lstat()
    except FileNotFoundError:
        return artifact
    except OSError as exc:
        raise TrackingError(f"Unable to inspect prepared artifact: {exc}") from exc
    if (not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid()
            or details.st_mode & 0o077):
        raise TrackingError("Prepared artifact is not private; refusing to remove the association.")
    return artifact


def _remove_prepared_artifact(artifact, context):
    if artifact is None:
        return
    try:
        artifact.unlink(missing_ok=True)
    except OSError as exc:
        raise TrackingError(
            f"{context}, but prepared artifact cleanup failed: {exc}"
        ) from exc


def compare_versions(installed, tag):
    upstream, separator, revision = installed.partition("-")
    if separator and not re.fullmatch(r"[0-9]+", revision):
        return "Unknown: versions cannot be compared safely."
    left = VERSION_PATTERN.fullmatch(upstream)
    right = VERSION_PATTERN.fullmatch(tag)
    if not left or not right:
        return "Unknown: versions cannot be compared safely."
    current = tuple(map(int, left.groups()))
    latest = tuple(map(int, right.groups()))
    if latest > current:
        status = "Newer upstream release available."
    elif latest == current:
        status = "Upstream versions match." if separator else "Versions match."
    else:
        status = "Installed version is newer than the latest upstream release."
    if separator:
        status += (
            f" Comparing upstream versions only; installed Debian revision {revision}"
            " is not compared."
        )
    return status


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
        lock = acquire_database_lock()
        prepared_artifact = None
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT repository_name, repository_id FROM tracked_packages WHERE package_name=? AND architecture=?",
                    (name, architecture),
                ).fetchone()
                if current != existing:
                    raise TrackingError("Association changed during confirmation; review it and try again.")
                if current != (canonical, identifier):
                    prepared_artifact = _prepared_artifact_for_removal(
                        db, name, architecture,
                    )
                    db.execute(
                        "DELETE FROM prepared_updates WHERE package_name=? AND architecture=?",
                        (name, architecture),
                    )
                db.execute("""INSERT INTO tracked_packages
                    (package_name, architecture, repository_id, repository_name) VALUES (?, ?, ?, ?)
                    ON CONFLICT(package_name, architecture) DO UPDATE SET
                        repository_id=excluded.repository_id, repository_name=excluded.repository_name""",
                    (name, architecture, identifier, canonical))
            _remove_prepared_artifact(
                prepared_artifact, "Confirmed upstream changed",
            )
        finally:
            release_database_lock(lock)
    print("Association saved.")


def untrack(package):
    if not PACKAGE_PATTERN.fullmatch(package):
        raise TrackingError("Invalid Debian package name.")
    name, _, architecture = package.partition(":")
    with closing(open_database()) as db:
        rows = db.execute(
            "SELECT architecture, repository_name, repository_id FROM tracked_packages "
            "WHERE package_name=? ORDER BY architecture",
            (name,),
        ).fetchall()
        if architecture:
            rows = [row for row in rows if row[0] == architecture]
        if not rows:
            raise TrackingError(f"No confirmed upstream for {package}.")
        if len(rows) != 1:
            raise TrackingError(
                f"Multiple tracked architectures for {name}; specify package:architecture "
                "from --tracked."
            )
        architecture, repository, identifier = rows[0]
        print(f"Package: {name}:{architecture}")
        print(f"Current association: https://github.com/{repository}")
        print("Only the saved association will be removed; no package will be uninstalled.")
        try:
            answer = input("Remove this association? [y/N] ").strip().lower()
        except EOFError as exc:
            raise TrackingError("Confirmation required; association was not removed.") from exc
        if answer not in ("y", "yes"):
            print("Association not removed.")
            return
        lock = acquire_database_lock()
        prepared_artifact = None
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                prepared_artifact = _prepared_artifact_for_removal(
                    db, name, architecture,
                )
                result = db.execute(
                    "DELETE FROM tracked_packages WHERE package_name=? AND architecture=? "
                    "AND repository_name=? AND repository_id=?",
                    (name, architecture, repository, identifier),
                )
                if result.rowcount != 1:
                    raise TrackingError("Association changed during confirmation; review it and try again.")
                db.execute(
                    "DELETE FROM prepared_updates WHERE package_name=? AND architecture=?",
                    (name, architecture),
                )
            _remove_prepared_artifact(
                prepared_artifact, "Association was removed",
            )
        finally:
            release_database_lock(lock)
    print("Association removed.")


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
            lock = acquire_database_lock()
            try:
                result = db.execute(
                    "UPDATE tracked_packages SET repository_name=? WHERE package_name=? AND architecture=? "
                    "AND repository_name=? AND repository_id=?",
                    (repository, name, architecture, row[0], identifier),
                )
                if result.rowcount != 1:
                    raise TrackingError("Association changed during the release check; try again.")
            finally:
                release_database_lock(lock)
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
