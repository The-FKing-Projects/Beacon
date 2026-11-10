"""APT preview and transaction enforcement for pinned local packages."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

import tracking
import inspection


APT_BINARY = "/usr/bin/apt-get"
DPKG_BINARY = "/usr/bin/dpkg"
DPKG_DEB_BINARY = "/usr/bin/dpkg-deb"
STAGING_ROOT = Path("/run/beacon")
PACKAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
ARCHITECTURE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MAX_PLAN_SIZE = 64 * 1024
MAX_PROTOCOL_SIZE = 8 * 1024 * 1024
MAX_ARTIFACT_SIZE = inspection.MAX_DEB_SIZE


def _environment():
    return {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "LANG": "C"}


def _run(command, purpose, timeout=30):
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False,
            env=_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise tracking.TrackingError(f"Unable to {purpose}: {exc}") from exc
    if result.returncode:
        detail = result.stderr.strip() or f"command exited with status {result.returncode}"
        raise tracking.TrackingError(f"Unable to {purpose}: {detail}")
    return result


def _version_order(left, right):
    if left == "-":
        _validate_version(right)
        return -1
    _validate_version(left)
    _validate_version(right)
    for operation, order in (("lt", -1), ("eq", 0), ("gt", 1)):
        try:
            result = subprocess.run(
                [DPKG_BINARY, "--compare-versions", left, operation, right],
                capture_output=True, text=True, timeout=10, check=False,
                env=_environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise tracking.TrackingError(f"Unable to compare Debian versions: {exc}") from exc
        if result.returncode == 0:
            return order
        if result.returncode != 1:
            raise tracking.TrackingError(
                f"Unable to compare Debian versions: {result.stderr.strip() or left}"
            )
    raise tracking.TrackingError("Unable to compare Debian versions.")


def _validate_version(version):
    if not isinstance(version, str) or not version or version == "-":
        raise tracking.TrackingError("APT transaction contains an invalid Debian version.")
    _run(
        [DPKG_BINARY, "--validate-version", version],
        "validate Debian package version",
        timeout=10,
    )


def _installed_architectures():
    result = _run(
        [
            "dpkg-query", "-W",
            "-f=${binary:Package}\t${Architecture}\t${Version}\t${db:Status-Status}\n",
        ],
        "read installed package identities",
    )
    records = []
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 4 or fields[3] != "installed":
            continue
        binary_name, architecture, version, _ = fields
        name, separator, qualified_architecture = binary_name.partition(":")
        if separator and qualified_architecture != architecture:
            continue
        records.append((name, architecture, version))
    return records


def _identity_from_preview(name, architecture=None, old_version="-"):
    package_name, separator, qualified_architecture = name.partition(":")
    if not PACKAGE_PATTERN.fullmatch(package_name):
        raise tracking.TrackingError("APT preview contains an invalid package name.")
    if separator:
        if architecture and architecture != qualified_architecture:
            raise tracking.TrackingError("APT preview package architecture is inconsistent.")
        architecture = qualified_architecture
    if architecture is None:
        matches = {
            item_arch
            for item_name, item_arch, item_version in _installed_architectures()
            if item_name == package_name
            and (old_version == "-" or item_version == old_version)
        }
        if len(matches) != 1:
            raise tracking.TrackingError(
                f"APT preview architecture for {package_name} is ambiguous."
            )
        architecture = matches.pop()
    if not ARCHITECTURE_PATTERN.fullmatch(architecture):
        raise tracking.TrackingError("APT preview contains an invalid architecture.")
    return package_name, architecture


def parse_preview(output):
    """Parse all package changes from an apt-get simulation or fail closed."""
    plan = []
    configure_lines = []
    for line in output.splitlines():
        if line.startswith("Inst "):
            match = re.fullmatch(
                r"Inst (\S+)(?: \[([^\]]+)\])? \((\S+).* \[([a-z0-9][a-z0-9-]*)\]\)",
                line,
            )
            if not match:
                raise tracking.TrackingError(
                    "APT preview contained an unrecognized install action; refusing to continue."
                )
            name, old_version, new_version, architecture = match.groups()
            package_name, architecture = _identity_from_preview(name, architecture, old_version or "-")
            old_architecture = "-"
            if old_version:
                old_architecture = _old_architecture(name, old_version)
                if old_architecture != architecture:
                    raise tracking.TrackingError(
                        f"APT preview changes architecture for {package_name}; refusing to continue."
                    )
            plan.append({
                "package": package_name,
                "architecture": architecture,
                "old_architecture": old_architecture,
                "old_version": old_version or "-",
                "new_version": new_version,
                "action": "install",
            })
        elif line.startswith("Remv "):
            match = re.fullmatch(r"Remv (\S+)(?: \[([^\]]+)\])?(?: .*)?", line)
            if not match:
                raise tracking.TrackingError(
                    "APT preview contained an unrecognized removal action; refusing to continue."
                )
            name, old_version = match.groups()
            package_name, architecture = _identity_from_preview(
                name, old_version=old_version or "-",
            )
            plan.append({
                "package": package_name,
                "architecture": architecture,
                "old_architecture": architecture,
                "old_version": old_version or "-",
                "new_version": "-",
                "action": "remove",
            })
        elif line.startswith("Conf "):
            configure_lines.append(line)
    for line in configure_lines:
        match = re.fullmatch(r"Conf (\S+) \((\S+)(?: .*)?\)", line)
        if not match:
            raise tracking.TrackingError(
                "APT preview contained an unrecognized configuration action; refusing to continue."
            )
        name, version = match.groups()
        package_name, separator, requested_architecture = name.partition(":")
        planned = [
            item for item in plan
            if item["action"] == "install"
            and item["package"] == package_name
            and item["new_version"] == version
            and (not separator or item["architecture"] == requested_architecture)
        ]
        if len(planned) != 1:
            raise tracking.TrackingError(
                f"APT preview also configures {name} outside the package changes Beacon can review."
            )
    identities = [
        (item["package"], item["architecture"])
        for item in plan
    ]
    if len(identities) != len(set(identities)):
        raise tracking.TrackingError("APT preview contained duplicate package actions.")
    return sorted(plan, key=lambda item: (item["package"], item["architecture"]))


def _old_architecture(name, old_version):
    package_name, separator, requested_architecture = name.partition(":")
    matches = {
        architecture
        for installed_name, architecture, installed_version in _installed_architectures()
        if installed_name == package_name
        and installed_version == old_version
        and (not separator or requested_architecture == architecture)
    }
    if len(matches) != 1:
        raise tracking.TrackingError(
            f"APT preview old architecture for {package_name} is ambiguous."
        )
    return matches.pop()


def simulate_install(artifact):
    result = _run(
        [
            APT_BINARY, "--simulate", "-o", "APT::Color=0",
            "-o", "Dpkg::Use-Pty=0", "install", str(artifact),
        ],
        "simulate APT dependency resolution",
        timeout=120,
    )
    return parse_preview(result.stdout), result.stdout


def assert_not_managed_by_apt(package, architecture):
    result = _run(
        ["/usr/bin/apt-cache", "policy", f"{package}:{architecture}"],
        f"inspect APT ownership for {package}:{architecture}",
    )
    installed = candidate = None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith("installed:"):
            installed = stripped.split(":", 1)[1].strip()
        elif lowered.startswith("candidate:"):
            candidate = stripped.split(":", 1)[1].strip()
    if installed is None or candidate is None:
        raise tracking.TrackingError(
            "APT ownership is uncertain; refusing to prepare or install this package."
        )
    if candidate != "(none)":
        origins = inspection.policy_origins_for_version(result.stdout, candidate)
        if any("://" in origin for origin in origins):
            raise tracking.TrackingError(
                f"APT has a repository candidate for {package}:{architecture}; "
                "use the configured APT source rather than Beacon."
            )
        if not origins:
            raise tracking.TrackingError(
                "APT candidate origin is uncertain; refusing to override it with Beacon."
            )
    return {
        "installed": installed,
        "candidate": candidate,
        "evidence": "no configured APT repository candidate was found",
    }


def review_plan(plan):
    lines = []
    for item in plan:
        name = f"{item['package']}:{item['architecture']}"
        if item["action"] == "remove":
            lines.append(f"  REMOVE {name} {item['old_version']} (blocked)")
            continue
        old_version = item["old_version"]
        new_version = item["new_version"]
        if old_version == "-":
            lines.append(f"  INSTALL {name} {new_version}")
        elif _version_order(old_version, new_version) > 0:
            lines.append(f"  DOWNGRADE {name} {old_version} -> {new_version} (blocked)")
        elif old_version == new_version:
            lines.append(f"  REINSTALL {name} {old_version}")
        else:
            lines.append(f"  UPGRADE {name} {old_version} -> {new_version}")
    return lines


def _validate_plan(plan):
    if not isinstance(plan, list) or not plan:
        raise tracking.TrackingError("Approved APT plan is empty or invalid.")
    normalized = []
    for item in plan:
        if not isinstance(item, dict) or set(item) != {
            "package", "architecture", "old_architecture", "old_version",
            "new_version", "action",
        }:
            raise tracking.TrackingError("Approved APT plan has invalid fields.")
        package = item["package"]
        architecture = item["architecture"]
        old_architecture = item["old_architecture"]
        old_version = item["old_version"]
        new_version = item["new_version"]
        if (not isinstance(package, str) or not PACKAGE_PATTERN.fullmatch(package)
                or not isinstance(architecture, str)
                or not ARCHITECTURE_PATTERN.fullmatch(architecture)
                or not isinstance(old_architecture, str)
                or not isinstance(old_version, str) or not old_version
                or not isinstance(new_version, str) or not new_version
                or item["action"] != "install"):
            raise tracking.TrackingError("Approved APT plan has invalid package actions.")
        if old_version == "-" and new_version == "-":
            raise tracking.TrackingError("Approved APT plan contains an empty package action.")
        if new_version != "-":
            _validate_version(new_version)
        if ((old_version == "-" and old_architecture != "-")
                or (old_version != "-" and not ARCHITECTURE_PATTERN.fullmatch(old_architecture))):
            raise tracking.TrackingError("Approved APT plan has invalid old package architecture.")
        if new_version == "-" or (
            old_version != "-" and _version_order(old_version, new_version) > 0
        ):
            raise tracking.TrackingError("Approved APT plan contains a removal or downgrade.")
        normalized.append({
            "package": package,
            "architecture": architecture,
            "old_architecture": old_architecture,
            "old_version": old_version,
            "new_version": new_version,
            "action": "install",
        })
    keys = [(item["package"], item["architecture"]) for item in normalized]
    if len(keys) != len(set(keys)):
        raise tracking.TrackingError("Approved APT plan contains duplicate package actions.")
    return sorted(normalized, key=lambda item: (item["package"], item["architecture"]))


def _validate_manifest(manifest):
    expected_keys = {
        "sha256", "artifact", "package", "architecture", "installed_architecture",
        "installed_version", "repository", "repository_id", "release_tag", "asset_name",
        "asset_url", "version", "plan",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_keys:
        raise tracking.TrackingError("APT handoff manifest is invalid.")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest["sha256"])):
        raise tracking.TrackingError("APT handoff digest is invalid.")
    if (not isinstance(manifest["artifact"], str)
            or not Path(manifest["artifact"]).is_absolute()
            or not isinstance(manifest["package"], str)
            or not PACKAGE_PATTERN.fullmatch(manifest["package"])
            or not isinstance(manifest["architecture"], str)
            or not ARCHITECTURE_PATTERN.fullmatch(manifest["architecture"])
            or not isinstance(manifest["installed_architecture"], str)
            or not ARCHITECTURE_PATTERN.fullmatch(manifest["installed_architecture"])
            or not isinstance(manifest["installed_version"], str)
            or not manifest["installed_version"]
            or not isinstance(manifest["repository"], str)
            or tracking.repository_name(manifest["repository"]) != manifest["repository"]
            or not isinstance(manifest["repository_id"], int)
            or isinstance(manifest["repository_id"], bool)
            or manifest["repository_id"] <= 0
            or not isinstance(manifest["release_tag"], str)
            or not manifest["release_tag"]
            or any(not char.isprintable() for char in manifest["release_tag"])
            or not isinstance(manifest["asset_name"], str)
            or not manifest["asset_name"].lower().endswith(".deb")
            or "/" in manifest["asset_name"] or "\\" in manifest["asset_name"]
            or any(not char.isprintable() for char in manifest["asset_name"])
            or not isinstance(manifest["asset_url"], str)
            or not tracking._valid_release_asset_url(
                manifest["asset_url"], manifest["repository"],
                manifest["release_tag"], manifest["asset_name"],
            )
            or not isinstance(manifest["version"], str) or not manifest["version"]):
        raise tracking.TrackingError("APT handoff package identity is invalid.")
    manifest["plan"] = _validate_plan(manifest["plan"])
    if not any(
        action["package"] == manifest["package"]
        and action["architecture"] == manifest["architecture"]
        and action["old_version"] == manifest["installed_version"]
        and action["new_version"] == manifest["version"]
        for action in manifest["plan"]
    ):
        raise tracking.TrackingError("APT plan does not include the selected package version.")
    return manifest


def _hash_file(path, expected=None, require_root_private=False):
    digest = hashlib.sha256()
    size = 0
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise tracking.TrackingError(f"Unable to open pinned package artifact: {exc}") from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise tracking.TrackingError("Pinned package artifact is not a regular file.")
        if require_root_private and (
            details.st_uid != 0
            or stat.S_IMODE(details.st_mode) & 0o077
            or stat.S_IMODE(details.st_mode) & 0o222
        ):
            raise tracking.TrackingError("Pinned package artifact is not root-owned and immutable to users.")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ARTIFACT_SIZE:
                raise tracking.TrackingError("Pinned package artifact exceeds the size limit.")
            digest.update(chunk)
    finally:
        os.close(descriptor)
    value = digest.hexdigest()
    if expected is not None and value != expected:
        raise tracking.TrackingError("Pinned package digest changed; refusing APT handoff.")
    return value


def _metadata(path):
    try:
        result = subprocess.run(
            [
                DPKG_DEB_BINARY, "--show",
                "--showformat=${Package}\t${Architecture}\t${Version}\n", str(path),
            ],
            capture_output=True, text=True, timeout=30, check=False,
            env=_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise tracking.TrackingError(f"Unable to inspect staged package: {exc}") from exc
    if result.returncode:
        raise tracking.TrackingError(
            f"Unable to inspect staged package: {result.stderr.strip() or 'dpkg-deb failed'}"
        )
    fields = result.stdout.rstrip("\n").split("\t")
    if (len(fields) != 3 or not PACKAGE_PATTERN.fullmatch(fields[0])
            or not ARCHITECTURE_PATTERN.fullmatch(fields[1]) or not fields[2]):
        raise tracking.TrackingError("Staged package contains invalid metadata.")
    _validate_version(fields[2])
    return fields


def validate_hook_protocol(data, manifest):
    """Reject transaction actions that differ from approval or violate policy."""
    manifest = _validate_manifest(dict(manifest))
    lines = data.splitlines()
    if not lines or lines[0] != "VERSION 3":
        raise tracking.TrackingError("APT did not provide the required transaction protocol v3.")
    try:
        boundary = lines.index("")
    except ValueError as exc:
        raise tracking.TrackingError("APT transaction protocol is incomplete.") from exc
    actual = []
    selected_archive_seen = False
    for line in lines[boundary + 1:]:
        fields = line.split()
        if len(fields) != 9:
            raise tracking.TrackingError("APT transaction contains an invalid action record.")
        (package, old_version, old_arch, old_multiarch, direction, new_version,
         new_arch, new_multiarch, action) = fields
        if (not PACKAGE_PATTERN.fullmatch(package)
                or old_multiarch not in {"same", "foreign", "allowed", "none", "no"}
                or new_multiarch not in {"same", "foreign", "allowed", "none", "no"}
                or direction not in {"<", "=", ">"}
                or (old_arch != "-" and not ARCHITECTURE_PATTERN.fullmatch(old_arch))
                or (new_arch != "-" and not ARCHITECTURE_PATTERN.fullmatch(new_arch))):
            raise tracking.TrackingError("APT transaction contains invalid package metadata.")
        if action == "**CONFIGURE**":
            configured = [
                item for item in manifest["plan"]
                if item["package"] == package
                and item["architecture"] == new_arch
            ]
            if len(configured) != 1:
                raise tracking.TrackingError(
                    "APT transaction configures a package outside the reviewed plan."
                )
            planned = configured[0]
            if (old_arch != planned["old_architecture"]
                    or old_version != planned["old_version"]
                    or new_version != planned["new_version"]):
                raise tracking.TrackingError(
                    "APT configuration action differs from the reviewed package plan."
                )
            continue
        if action == "**REMOVE**":
            raise tracking.TrackingError("APT transaction proposes removing a package.")
        if action.startswith("**") or not Path(action).is_absolute():
            raise tracking.TrackingError("APT transaction contains an unsupported package action.")
        if new_version == "-" or new_arch == "-":
            raise tracking.TrackingError("APT transaction action is missing its new package identity.")
        _validate_version(new_version)
        if old_version == "-":
            if direction != "<":
                raise tracking.TrackingError("APT transaction direction is inconsistent.")
        else:
            if old_arch == "-" or _version_order(old_version, new_version) > 0:
                raise tracking.TrackingError("APT transaction proposes a downgrade.")
            expected_direction = {
                -1: "<", 0: "=", 1: ">",
            }[_version_order(old_version, new_version)]
            if direction != expected_direction:
                raise tracking.TrackingError("APT transaction direction is inconsistent.")
        actual.append({
            "package": package,
            "architecture": new_arch,
            "old_architecture": old_arch,
            "old_version": old_version,
            "new_version": new_version,
            "action": "install",
        })
        if os.path.abspath(action) == manifest["artifact"]:
            selected_archive_seen = True
            if package != manifest["package"] or new_arch != manifest["architecture"]:
                raise tracking.TrackingError("APT selected a different package identity.")
            if new_version != manifest["version"]:
                raise tracking.TrackingError("APT selected a different package version.")
            _hash_file(action, manifest["sha256"], require_root_private=True)
            if _metadata(action) != [
                manifest["package"], manifest["architecture"], manifest["version"],
            ]:
                raise tracking.TrackingError("APT package metadata changed after approval.")
    expected = manifest["plan"]
    key = lambda item: (
        item["package"], item["architecture"], item["old_architecture"],
        item["old_version"], item["new_version"],
    )
    actual_keys = [key(item) for item in actual]
    expected_keys = [key(item) for item in expected]
    if len(actual_keys) != len(set(actual_keys)) or sorted(actual_keys) != sorted(expected_keys):
        raise tracking.TrackingError("APT transaction differs from the reviewed plan.")
    if not selected_archive_seen:
        raise tracking.TrackingError("APT transaction omitted the selected pinned artifact.")
    return True


def _secure_directory(path):
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        details = path.lstat()
    except OSError as exc:
        raise tracking.TrackingError(f"Unable to create private APT staging area: {exc}") from exc
    if (not stat.S_ISDIR(details.st_mode) or details.st_uid != 0
            or stat.S_IMODE(details.st_mode) & 0o700 != 0o700
            or stat.S_IMODE(details.st_mode) & 0o077):
        raise tracking.TrackingError("APT staging directory is not private and root-owned.")


def _acquire_staging_lock():
    path = STAGING_ROOT / ".lock"
    descriptor = None
    try:
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        details = os.fstat(descriptor)
        if (not stat.S_ISREG(details.st_mode) or details.st_uid != 0
                or stat.S_IMODE(details.st_mode) & 0o077):
            raise tracking.TrackingError("APT staging lock is not private and root-owned.")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return descriptor
    except (OSError, tracking.TrackingError) as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise tracking.TrackingError(f"Unable to lock APT staging: {exc}") from exc


def _clean_stale_transactions():
    for path in STAGING_ROOT.iterdir():
        if not path.name.startswith("transaction-"):
            continue
        try:
            details = path.lstat()
        except OSError as exc:
            raise tracking.TrackingError(f"Unable to inspect stale APT staging data: {exc}") from exc
        if (not stat.S_ISDIR(details.st_mode) or details.st_uid != 0
                or stat.S_IMODE(details.st_mode) & 0o077):
            raise tracking.TrackingError(
                f"Refusing to remove unrecognized APT staging data at {path}."
            )
        try:
            shutil.rmtree(path)
        except OSError as exc:
            raise tracking.TrackingError(
                f"Unable to remove stale APT staging data at {path}: {exc}"
            ) from exc


def _copy_pinned_artifact(source, destination, expected_digest):
    source_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    target_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        source_fd = os.open(source, source_flags)
    except OSError as exc:
        raise tracking.TrackingError(f"Unable to read prepared package artifact: {exc}") from exc
    try:
        target_fd = os.open(destination, target_flags, 0o400)
    except OSError as exc:
        os.close(source_fd)
        raise tracking.TrackingError(f"Unable to stage pinned package artifact: {exc}") from exc
    digest = hashlib.sha256()
    size = 0
    try:
        source_details = os.fstat(source_fd)
        if not stat.S_ISREG(source_details.st_mode):
            raise tracking.TrackingError("Prepared artifact is not a regular file.")
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ARTIFACT_SIZE:
                raise tracking.TrackingError("Prepared artifact exceeds the size limit.")
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(target_fd, view)
                view = view[written:]
        os.fsync(target_fd)
    finally:
        os.close(source_fd)
        os.close(target_fd)
    if digest.hexdigest() != expected_digest:
        raise tracking.TrackingError("Prepared artifact changed; refusing APT handoff.")


def _write_private_file(path, content, mode=0o400):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    except OSError as exc:
        raise tracking.TrackingError(f"Unable to write private APT handoff data: {exc}") from exc


def _installed_version(package, architecture):
    try:
        result = subprocess.run(
            [
                "dpkg-query", "-W",
                "-f=${Package}\t${Architecture}\t${db:Status-Status}\t${Version}\n",
                f"{package}:{architecture}",
            ],
            capture_output=True, text=True, timeout=15, check=False,
            env=_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise tracking.TrackingError(
            f"Unable to verify installed state for {package}:{architecture}: {exc}"
        ) from exc
    matches = [
        line.split("\t")
        for line in result.stdout.splitlines()
        if len(line.split("\t")) == 4
        and line.split("\t")[1] == architecture
        and line.split("\t")[2] == "installed"
    ]
    if result.returncode and not matches:
        return None
    if len(matches) != 1:
        return None
    return matches[0][3]


def privileged_install(source, manifest):
    if os.geteuid() != 0:
        raise tracking.TrackingError("APT installation helper must run through sudo.")
    manifest = _validate_manifest(dict(manifest))
    source = Path(source)
    _hash_file(source, manifest["sha256"])
    if _metadata(source) != [
        manifest["package"], manifest["architecture"], manifest["version"],
    ]:
        raise tracking.TrackingError("Prepared artifact metadata changed; refusing APT handoff.")
    selected = next(
        action for action in manifest["plan"]
        if action["package"] == manifest["package"]
        and action["architecture"] == manifest["architecture"]
    )
    expected_current = (
        None if manifest["installed_version"] == "-" else manifest["installed_version"]
    )
    _secure_directory(STAGING_ROOT)
    lock = _acquire_staging_lock()
    transaction = None
    try:
        _clean_stale_transactions()
        assert_not_managed_by_apt(manifest["package"], manifest["installed_architecture"])
        current_version = _installed_version(
            manifest["package"], manifest["installed_architecture"],
        )
        if current_version != expected_current or selected["old_version"] != manifest["installed_version"]:
            raise tracking.TrackingError("Installed package state changed after review.")

        transaction = Path(tempfile.mkdtemp(prefix="transaction-", dir=STAGING_ROOT))
        os.chmod(transaction, 0o700)
        staged = transaction / "selected.deb"
        _copy_pinned_artifact(source, staged, manifest["sha256"])
        staged_manifest = dict(manifest, artifact=str(staged))
        if _metadata(staged) != [
            manifest["package"], manifest["architecture"], manifest["version"],
        ]:
            raise tracking.TrackingError("Staged package metadata changed.")
        manifest_path = transaction / "manifest.json"
        _write_private_file(
            manifest_path,
            json.dumps(staged_manifest, sort_keys=True, separators=(",", ":")),
        )
        hook_path = transaction / "apt-hook"
        hook_code = (
            "#!/usr/bin/python3\n"
            "import sys\n"
            f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
            "from apt_handoff import hook_main\n"
            f"raise SystemExit(hook_main({str(manifest_path)!r}))\n"
        )
        _write_private_file(hook_path, hook_code, 0o500)
        os.chmod(hook_path, 0o500)
        command = str(hook_path)
        result = subprocess.run(
            [
                APT_BINARY,
                "-o", f"DPkg::Pre-Install-Pkgs::={command}",
                "-o", f"DPkg::Tools::options::{command}::Version=3",
                "--no-remove", "install", str(staged),
            ],
            check=False,
            env=_environment(),
        )
        final_version = _installed_version(
            manifest["package"], manifest["installed_architecture"],
        )
        if result.returncode:
            raise tracking.TrackingError(
                f"APT installation failed with status {result.returncode}; "
                f"installed package version is {final_version or 'not installed'}. "
                "APT may have left partial system changes; no rollback is promised."
            )
        if final_version != manifest["version"]:
            raise tracking.TrackingError(
                "APT returned success but the selected installed version could not be confirmed; "
                f"observed {final_version or 'not installed'}."
            )
    finally:
        try:
            if transaction is not None:
                shutil.rmtree(transaction)
        except OSError as exc:
            raise tracking.TrackingError(
                f"Unable to remove private APT staging data at {transaction}: {exc}"
            ) from exc
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)


def hook_main(manifest_path):
    try:
        path = Path(manifest_path)
        details = path.lstat()
        if (not stat.S_ISREG(details.st_mode) or details.st_uid != 0
                or stat.S_IMODE(details.st_mode) & 0o077 or details.st_size > MAX_PLAN_SIZE):
            raise tracking.TrackingError("APT handoff manifest is not private and root-owned.")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        protocol = sys.stdin.read(MAX_PROTOCOL_SIZE + 1)
        if len(protocol) > MAX_PROTOCOL_SIZE:
            raise tracking.TrackingError("APT transaction protocol exceeds the size limit.")
        validate_hook_protocol(protocol, manifest)
    except (OSError, ValueError, tracking.TrackingError) as exc:
        print(f"Beacon APT policy check failed: {exc}", file=sys.stderr)
        return 1
    return 0


def privileged_main(arguments):
    if len(arguments) != 4 or arguments[0] != "--privileged-install":
        print("Invalid internal APT helper invocation.", file=sys.stderr)
        return 2
    source, expected_digest, plan_json = arguments[1:]
    if len(plan_json.encode("utf-8")) > MAX_PLAN_SIZE:
        print("APT review plan is too large; refusing installation.", file=sys.stderr)
        return 1
    try:
        plan = json.loads(plan_json)
        if not isinstance(plan, dict):
            raise tracking.TrackingError("APT review plan is invalid.")
        manifest = _validate_manifest({
            "sha256": expected_digest,
            "artifact": os.path.abspath(source),
            "package": plan.pop("_package"),
            "architecture": plan.pop("_architecture"),
            "installed_architecture": plan.pop("_installed_architecture"),
            "installed_version": plan.pop("_installed_version"),
            "repository": plan.pop("_repository"),
            "repository_id": plan.pop("_repository_id"),
            "release_tag": plan.pop("_release_tag"),
            "asset_name": plan.pop("_asset_name"),
            "asset_url": plan.pop("_asset_url"),
            "version": plan.pop("_version"),
            "plan": plan.pop("_plan"),
        })
        if plan:
            raise tracking.TrackingError("APT review plan contains unexpected data.")
        privileged_install(source, manifest)
    except (ValueError, KeyError, tracking.TrackingError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(privileged_main(sys.argv[1:]))
