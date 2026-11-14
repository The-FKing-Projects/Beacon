"""Retained release artifacts and explicitly reviewed APT installs."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess

import apt_handoff
import inspection
import tracking


PREPARED_COLUMNS = (
    "package_name, architecture, repository_id, repository_name, release_tag, asset_name, "
    "asset_url, checksum_asset_url, expected_sha256, sha256, checksum_status, "
    "asset_package_name, asset_architecture, asset_version, installed_version, artifact_path, "
    "prepared_at, github_api_sha256"
)


def _updates_directory():
    configured = os.environ.get("XDG_DATA_HOME")
    if configured:
        root = Path(configured)
        if not root.is_absolute():
            raise tracking.TrackingError("XDG_DATA_HOME must be an absolute path.")
    else:
        root = Path.home() / ".local" / "share"
    beacon = root / "beacon"
    updates = beacon / "updates"
    for path in (beacon, updates):
        try:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            details = path.lstat()
        except OSError as exc:
            raise tracking.TrackingError(f"Unable to create private update storage: {exc}") from exc
        if not stat.S_ISDIR(details.st_mode) or details.st_uid != os.geteuid():
            raise tracking.TrackingError(f"Update storage is not owned by the current user: {path}")
        if stat.S_IMODE(details.st_mode) & 0o077:
            try:
                path.chmod(0o700)
            except OSError as exc:
                raise tracking.TrackingError(f"Unable to protect update storage {path}: {exc}") from exc
    return updates


def _update_lock(directory):
    return tracking.acquire_database_lock()


def _unlock(descriptor):
    tracking.release_database_lock(descriptor)


def _clean_partial_files(directory):
    for path in directory.glob(".partial-*"):
        try:
            details = path.lstat()
            if stat.S_ISLNK(details.st_mode):
                path.unlink()
            elif stat.S_ISREG(details.st_mode) and details.st_uid == os.geteuid():
                path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise tracking.TrackingError(f"Unable to clean interrupted download {path}: {exc}") from exc


def _private_artifact_path(path, package, architecture, directory):
    artifact = Path(path)
    expected = re.escape(f"{package}.{architecture}.") + r"[a-f0-9]{32}\.deb"
    if artifact.parent != directory or not re.fullmatch(expected, artifact.name):
        raise tracking.TrackingError("Prepared artifact path has an invalid filename.")
    try:
        details = artifact.lstat()
    except FileNotFoundError as exc:
        raise tracking.TrackingError(
            "Prepared artifact is missing; prepare the update again."
        ) from exc
    if (not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid()
            or stat.S_IMODE(details.st_mode) & 0o077):
        raise tracking.TrackingError("Prepared artifact is not a private regular file.")
    return artifact


def _remove_artifact(path, package, architecture, directory):
    artifact = Path(path)
    expected = re.escape(f"{package}.{architecture}.") + r"[a-f0-9]{32}\.deb"
    if artifact.parent != directory or not re.fullmatch(expected, artifact.name):
        raise tracking.TrackingError("Refusing to remove an artifact outside private Beacon storage.")
    try:
        details = artifact.lstat()
    except FileNotFoundError:
        return
    if (not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid()):
        raise tracking.TrackingError("Refusing to remove an unrecognized prepared artifact.")
    artifact.unlink()


def _association(package, architecture):
    with closing(tracking.open_database()) as db:
        tracked = db.execute(
            "SELECT repository_name, repository_id FROM tracked_packages "
            "WHERE package_name=? AND architecture=?",
            (package, architecture),
        ).fetchone()
    if not tracked:
        raise tracking.TrackingError(
            f"No confirmed upstream for {package}:{architecture}."
        )
    return tracked


def _resolve_tracked_repository(repository, identifier):
    canonical, actual_id = tracking.resolve_repository(repository)
    if actual_id != identifier:
        raise tracking.TrackingError(
            "GitHub repository identity changed; confirm the upstream again before updating."
        )
    if canonical != repository:
        raise tracking.TrackingError(
            "GitHub repository name changed; run --check and confirm the upstream again."
        )
    return canonical


def _prepared_row(package, architecture):
    with closing(tracking.open_database()) as db:
        row = db.execute(
            f"SELECT {PREPARED_COLUMNS} FROM prepared_updates "
            "WHERE package_name=? AND architecture=?",
            (package, architecture),
        ).fetchone()
    return row


def _download_checksum(url, filename, directory):
    if not url:
        return None
    temporary = directory / f".partial-{secrets.token_hex(16)}"
    try:
        inspection.download(url, temporary, inspection.MAX_CHECKSUM_SIZE)
        temporary.chmod(0o600)
        return inspection.expected_checksum(temporary, filename)
    finally:
        temporary.unlink(missing_ok=True)


def _checksum_evidence(status):
    return {
        "matched-unauthenticated": "matches release SHA256SUMS (not authenticated)",
        "entry-missing": "release SHA256SUMS has no entry for the selected asset",
        "asset-missing": "release has no SHA256SUMS asset",
    }[status]


def _api_digest_evidence(api_digest):
    return (
        "matches GitHub's upload-time digest (not publisher authentication)"
        if api_digest is not None else "unavailable"
    )


def prepare(package, filename):
    directory = _updates_directory()
    lock = _update_lock(directory)
    try:
        _clean_partial_files(directory)
        name, installed_architecture, installed_version = tracking.installed_package(package)
        repository, identifier = _association(name, installed_architecture)
        repository = _resolve_tracked_repository(repository, identifier)
        apt_handoff.assert_not_managed_by_apt(name, installed_architecture)
        tag, asset_url, checksum_url, api_digest = inspection.selected_assets(repository, filename)
        print(f"Preparing {name}:{installed_architecture} from {repository} release {tag}.")
        print(f"Selected asset: {filename}")
        temporary = directory / f".partial-{secrets.token_hex(16)}"
        checksum_temporary = directory / f".partial-{secrets.token_hex(16)}"
        final_artifact = None
        stored = False
        try:
            digest = inspection.download(asset_url, temporary, inspection.MAX_DEB_SIZE)
            temporary.chmod(0o600)
            if api_digest is not None and digest != api_digest:
                raise tracking.TrackingError(
                    "GitHub API SHA-256 digest mismatch; the selected asset cannot be prepared."
                )
            expected = None
            checksum_status = "asset-missing"
            if checksum_url:
                inspection.download(checksum_url, checksum_temporary, inspection.MAX_CHECKSUM_SIZE)
                checksum_temporary.chmod(0o600)
                expected = inspection.expected_checksum(checksum_temporary, filename)
                checksum_status = "entry-missing" if expected is None else "matched-unauthenticated"
                if expected is not None and digest != expected:
                    raise tracking.TrackingError(
                        "SHA256 checksum mismatch; the selected asset cannot be prepared."
                    )

            asset_package, asset_architecture, asset_version = inspection.inspect_fields(temporary)
            if asset_package != name:
                raise tracking.TrackingError(
                    "Package name mismatch; this asset is not an update for the tracked package."
                )
            if asset_architecture != installed_architecture:
                raise tracking.TrackingError(
                    "Package architecture mismatch; this asset is not suitable for this installation."
                )
            relation = inspection.version_relation(installed_version, asset_version)
            if relation == "older":
                raise tracking.TrackingError(
                    "The selected asset is older than the installed package; downgrades are blocked."
                )
            if relation == "same":
                print("Warning: asset and installed versions are the same; installation requires approval.")
            final_artifact = directory / (
                f"{name}.{installed_architecture}.{secrets.token_hex(16)}.deb"
            )
            os.replace(temporary, final_artifact)
            final_artifact.chmod(0o600)
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

            with closing(tracking.open_database()) as db:
                previous = db.execute(
                    "SELECT artifact_path FROM prepared_updates "
                    "WHERE package_name=? AND architecture=?",
                    (name, installed_architecture),
                ).fetchone()
                with db:
                    db.execute(
                        f"""INSERT INTO prepared_updates ({PREPARED_COLUMNS})
                        VALUES ({",".join("?" for _ in range(18))})
                        ON CONFLICT(package_name, architecture) DO UPDATE SET
                            repository_id=excluded.repository_id,
                            repository_name=excluded.repository_name,
                            release_tag=excluded.release_tag,
                            asset_name=excluded.asset_name,
                            asset_url=excluded.asset_url,
                            checksum_asset_url=excluded.checksum_asset_url,
                            expected_sha256=excluded.expected_sha256,
                            sha256=excluded.sha256,
                            checksum_status=excluded.checksum_status,
                            asset_package_name=excluded.asset_package_name,
                            asset_architecture=excluded.asset_architecture,
                            asset_version=excluded.asset_version,
                            installed_version=excluded.installed_version,
                            artifact_path=excluded.artifact_path,
                            prepared_at=excluded.prepared_at,
                            github_api_sha256=excluded.github_api_sha256""",
                        (
                            name, installed_architecture, identifier, repository, tag,
                            filename, asset_url, checksum_url, expected, digest,
                            checksum_status, asset_package, asset_architecture, asset_version,
                            installed_version, str(final_artifact),
                            datetime.now(timezone.utc).isoformat(),
                            api_digest,
                        ),
                    )
            stored = True
            if previous and previous[0] != str(final_artifact):
                _remove_artifact(previous[0], name, installed_architecture, directory)
        except BaseException:
            if final_artifact is not None and not stored:
                final_artifact.unlink(missing_ok=True)
            raise
        finally:
            temporary.unlink(missing_ok=True)
            checksum_temporary.unlink(missing_ok=True)
        print(f"SHA256: {digest}")
        print(f"Checksum evidence: {_checksum_evidence(checksum_status)}.")
        print(f"GitHub API SHA-256 digest evidence: {_api_digest_evidence(api_digest)}.")
        print("Publisher authenticity is not independently verified.")
        print(f"Asset package: {asset_package}:{asset_architecture} {asset_version}")
        print(f"Installed package: {name}:{installed_architecture} {installed_version}")
        print(f"Prepared artifact: {final_artifact}")
        print("No package was installed. Use --install to review and approve an APT transaction.")
    finally:
        _unlock(lock)


def _verify_prepared_release(row, directory):
    (
        name, installed_architecture, identifier, repository, tag, asset_name, asset_url,
        checksum_url, expected, digest, checksum_status, asset_package, asset_architecture,
        asset_version, installed_version, artifact_path, _, api_digest,
    ) = row
    resolved = _resolve_tracked_repository(repository, identifier)
    apt_handoff.assert_not_managed_by_apt(name, installed_architecture)
    (
        current_tag, current_url, current_checksum_url, current_api_digest,
    ) = inspection.selected_release_assets(resolved, tag, asset_name)
    if current_tag != tag or current_url != asset_url or current_checksum_url != checksum_url:
        raise tracking.TrackingError(
            "The prepared release asset identity changed; prepare the update again."
        )
    artifact = _private_artifact_path(
        artifact_path, name, installed_architecture, directory,
    )
    actual_digest = apt_handoff._hash_file(artifact, digest)
    if api_digest is not None and current_api_digest != api_digest:
        raise tracking.TrackingError(
            "The GitHub API asset digest changed; prepare the update again."
        )
    if current_api_digest is not None and current_api_digest != actual_digest:
        raise tracking.TrackingError(
            "The GitHub API digest does not match the prepared artifact."
        )
    metadata = inspection.inspect_fields(artifact)
    if metadata != [asset_package, asset_architecture, asset_version]:
        raise tracking.TrackingError("Prepared package metadata changed; prepare it again.")
    current_checksum = _download_checksum(checksum_url, asset_name, directory)
    if checksum_status == "matched-unauthenticated":
        if current_checksum != expected or current_checksum != actual_digest:
            raise tracking.TrackingError(
                "The release checksum changed or no longer matches the prepared artifact."
            )
    elif checksum_status == "entry-missing" and current_checksum is not None:
        raise tracking.TrackingError(
            "Release checksum evidence changed; prepare the update again."
        )
    elif checksum_status == "asset-missing" and current_checksum_url is not None:
        raise tracking.TrackingError(
            "Release checksum evidence changed; prepare the update again."
        )
    return artifact, current_api_digest


def _sudo_install(artifact, digest, payload):
    sudo = shutil.which("sudo")
    helper = Path("/usr/lib/beacon/apt_handoff.py")
    if not sudo:
        raise tracking.TrackingError("sudo is required for the reviewed APT installation.")
    try:
        details = helper.lstat()
    except OSError as exc:
        raise tracking.TrackingError(
            "The packaged APT installation helper is missing; install Beacon's Debian package."
        ) from exc
    if (not stat.S_ISREG(details.st_mode) or details.st_uid != 0
            or stat.S_IMODE(details.st_mode) & 0o022):
        raise tracking.TrackingError("The packaged APT installation helper is not trusted.")
    plan_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(plan_json.encode("utf-8")) > apt_handoff.MAX_PLAN_SIZE:
        raise tracking.TrackingError("APT review plan is too large; refusing installation.")
    try:
        result = subprocess.run(
            [
                sudo, "--", "/usr/bin/python3", str(helper),
                "--privileged-install", str(artifact), digest, plan_json,
            ],
            check=False,
            env=tracking.command_environment(),
        )
    except OSError as exc:
        raise tracking.TrackingError(f"Unable to request privileged APT installation: {exc}") from exc
    if result.returncode:
        raise tracking.TrackingError(
            f"Privileged APT installation helper failed with status {result.returncode}."
        )


def install(package):
    directory = _updates_directory()
    lock = _update_lock(directory)
    try:
        _clean_partial_files(directory)
        name, installed_architecture, installed_version = tracking.installed_package(package)
        row = _prepared_row(name, installed_architecture)
        if not row:
            raise tracking.TrackingError(
                f"No prepared update for {name}:{installed_architecture}; run --prepare first."
            )
        (
            saved_name, saved_architecture, repository_id, repository, tag, asset_name, asset_url,
            checksum_url, expected, digest, checksum_status, asset_package, asset_architecture,
            asset_version, prepared_from_version, artifact_path, _, _,
        ) = row
        tracked_repository, tracked_id = _association(saved_name, saved_architecture)
        if (tracked_repository != repository or tracked_id != repository_id
                or saved_name != name or saved_architecture != installed_architecture):
            raise tracking.TrackingError(
                "The confirmed upstream changed since preparation; prepare the update again."
            )
        if installed_version != prepared_from_version:
            raise tracking.TrackingError(
                "Installed package state changed since preparation; prepare the update again."
            )
        artifact, current_api_digest = _verify_prepared_release(row, directory)
        relation = inspection.version_relation(installed_version, asset_version)
        if relation == "older":
            raise tracking.TrackingError("Downgrades are blocked.")
        plan, _ = apt_handoff.simulate_install(artifact)
        print(f"Package: {name}:{installed_architecture}")
        print(f"Confirmed upstream: https://github.com/{repository} (repository ID {repository_id})")
        print(f"Release: {tag}")
        print(f"Asset: {asset_name}")
        print(f"Asset URL: {asset_url}")
        print(f"SHA256: {digest}")
        print(f"Checksum evidence: {_checksum_evidence(checksum_status)}.")
        print(
            "GitHub API SHA-256 digest evidence: "
            f"{_api_digest_evidence(current_api_digest)}."
        )
        print("Publisher authenticity is not independently verified.")
        print(f"Version change: {installed_version} -> {asset_version} ({relation})")
        print("APT transaction:")
        for line in apt_handoff.review_plan(plan):
            print(line)
        if any(item["action"] == "remove" for item in plan):
            raise tracking.TrackingError(
                "APT proposed removing installed packages; installation is blocked."
            )
        if any(
            item["old_version"] != "-"
            and apt_handoff._version_order(item["old_version"], item["new_version"]) > 0
            for item in plan
        ):
            raise tracking.TrackingError("APT proposed a package downgrade; installation is blocked.")
        selected = [
            item for item in plan
            if item["package"] == name
            and item["architecture"] == asset_architecture
            and item["new_version"] == asset_version
        ]
        if len(selected) != 1 or selected[0]["old_version"] != installed_version:
            raise tracking.TrackingError(
                "APT did not plan the selected package version from the reviewed installed state."
            )
        if selected[0]["old_architecture"] != installed_architecture:
            raise tracking.TrackingError(
                "APT proposed changing package architecture; installation is blocked."
            )
        if relation == "same":
            print("Warning: this is a same-version reinstall; review the full APT transaction.")
        print("APT may execute package maintainer scripts with root privileges.")
        print("Only the reviewed actions will be allowed; removals and downgrades are blocked.")
        try:
            answer = input("Install this exact APT transaction? [y/N] ").strip().lower()
        except EOFError as exc:
            raise tracking.TrackingError(
                "Confirmation required; no privileged installation was started."
            ) from exc
        if answer not in ("y", "yes"):
            print("Installation not started.")
            return
        payload = {
            "_package": name,
            "_architecture": asset_architecture,
            "_installed_architecture": installed_architecture,
            "_installed_version": installed_version,
            "_repository": repository,
            "_repository_id": repository_id,
            "_release_tag": tag,
            "_asset_name": asset_name,
            "_asset_url": asset_url,
            "_version": asset_version,
            "_plan": plan,
        }
        _sudo_install(artifact, digest, payload)
        confirmed_name, confirmed_architecture, confirmed_version = tracking.installed_package(
            f"{name}:{installed_architecture}",
        )
        if (confirmed_name != name or confirmed_architecture != installed_architecture
                or confirmed_version != asset_version):
            raise tracking.TrackingError(
                "APT returned success but the installed package state does not match the selected update."
            )
        print(f"Installation confirmed: {name}:{installed_architecture} {confirmed_version}.")
    finally:
        _unlock(lock)
