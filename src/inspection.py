"""Inspect a user-selected release asset without installing or retaining it."""

from contextlib import closing
import hashlib
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

import tracking


MAX_DEB_SIZE = 512 * 1024 * 1024
MAX_CHECKSUM_SIZE = 1024 * 1024
DOWNLOAD_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


def allowed_download_url(url):
    try:
        parsed = urlparse(url)
        return (parsed.scheme == "https" and parsed.netloc.lower() in DOWNLOAD_HOSTS
                and not parsed.username and not parsed.password)
    except ValueError:
        return False


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_download_url(newurl):
            raise tracking.TrackingError("Download redirected to an untrusted host.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, destination, limit):
    if not allowed_download_url(url) or urlparse(url).netloc.lower() != "github.com":
        raise tracking.TrackingError("Invalid GitHub release asset URL.")
    request = Request(url, headers={"User-Agent": "Beacon", "Accept-Encoding": "identity"})
    digest = hashlib.sha256()
    size = 0
    try:
        with build_opener(SafeRedirect()).open(request, timeout=30) as response:
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    expected = int(length)
                except ValueError as exc:
                    raise tracking.TrackingError("Invalid download content length.") from exc
                if expected < 0 or expected > limit:
                    raise tracking.TrackingError("Download exceeds the allowed size.")
            else:
                expected = None
            with open(destination, "xb") as output:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > limit:
                        raise tracking.TrackingError("Download exceeds the allowed size.")
                    digest.update(chunk)
                    output.write(chunk)
            if expected is not None and size != expected:
                raise tracking.TrackingError("Download was incomplete.")
    except HTTPError as exc:
        detail = f"HTTP {exc.code}"
        exc.close()
        raise tracking.TrackingError(f"Unable to download release asset: {detail}") from exc
    except (OSError, URLError) as exc:
        raise tracking.TrackingError(f"Unable to download release asset: {exc}") from exc
    return digest.hexdigest()


def selected_assets(repository, filename):
    data = tracking.github_get("/repos/" + quote(repository, safe="/") + "/releases/latest")
    tag = data.get("tag_name")
    assets = data.get("assets")
    if (not isinstance(tag, str) or not tag or any(not c.isprintable() for c in tag)
            or not isinstance(assets, list)):
        raise tracking.TrackingError("GitHub returned invalid release metadata.")
    if (not filename.lower().endswith(".deb") or "/" in filename or "\\" in filename
            or any(not char.isprintable() for char in filename)):
        raise tracking.TrackingError("Specify the exact .deb asset filename from --check.")
    chosen = []
    checksum_files = []
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
            raise tracking.TrackingError("GitHub returned an invalid release asset.")
        if asset["name"] == filename:
            chosen.append(asset)
        if asset["name"] == "SHA256SUMS":
            checksum_files.append(asset)
    if len(chosen) != 1:
        raise tracking.TrackingError("The exact .deb asset was not found uniquely in the latest release.")
    if len(checksum_files) > 1:
        raise tracking.TrackingError("Multiple SHA256SUMS assets found; checksum is ambiguous.")

    def asset_url(asset):
        url = asset.get("browser_download_url")
        if not isinstance(url, str) or not allowed_download_url(url):
            raise tracking.TrackingError("GitHub returned an invalid asset URL.")
        parsed = urlparse(url)
        prefix = f"/{repository}/releases/download/"
        path = unquote(parsed.path)
        if (parsed.netloc.lower() != "github.com" or parsed.query or parsed.fragment
                or path[:len(prefix)].lower() != prefix.lower()
                or path[len(prefix):] != f"{tag}/{asset['name']}"):
            raise tracking.TrackingError("Asset URL does not match the confirmed repository and release.")
        return url

    return tag, asset_url(chosen[0]), asset_url(checksum_files[0]) if checksum_files else None


def expected_checksum(path, filename):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise tracking.TrackingError(f"Unable to read SHA256SUMS: {exc}") from exc
    matches = []
    for line in lines:
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
        if match and match.group(2) in (filename, "./" + filename):
            matches.append(match.group(1).lower())
    if not matches:
        return None
    if len(matches) != 1:
        raise tracking.TrackingError("Multiple checksum entries found for the asset.")
    return matches[0]


def inspect_fields(path):
    try:
        result = subprocess.run(
            ["dpkg-deb", "--show", "--showformat=${Package}\t${Architecture}\t${Version}\n", str(path)],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise tracking.TrackingError(f"Unable to inspect .deb metadata: {exc}") from exc
    if result.returncode:
        raise tracking.TrackingError(f"Unable to inspect .deb metadata: {result.stderr.strip() or 'dpkg-deb failed'}")
    fields = result.stdout.strip().split("\t")
    if (len(fields) != 3 or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", fields[0])
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", fields[1])
            or not fields[2] or any(not c.isprintable() for c in fields[2])):
        raise tracking.TrackingError("The .deb contains invalid or missing package metadata.")
    return fields


def version_relation(installed, candidate):
    try:
        for version in (installed, candidate):
            valid = subprocess.run(
                ["dpkg", "--validate-version", version],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if valid.returncode != 0:
                raise tracking.TrackingError(
                    f"Invalid Debian version; cannot compare: {valid.stderr.strip() or version}"
                )
        for operation, label in (("gt", "newer"), ("eq", "same"), ("lt", "older")):
            result = subprocess.run(
                ["dpkg", "--compare-versions", candidate, operation, installed],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if result.returncode == 0:
                return label
            if result.returncode != 1:
                raise tracking.TrackingError(f"Unable to compare Debian versions: {result.stderr.strip()}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise tracking.TrackingError(f"Unable to compare Debian versions: {exc}") from exc
    raise tracking.TrackingError("Unable to compare Debian versions.")


def inspect(package, filename):
    name, architecture, installed_version = tracking.installed_package(package)
    with closing(tracking.open_database()) as db:
        row = db.execute(
            "SELECT repository_name, repository_id FROM tracked_packages WHERE package_name=? AND architecture=?",
            (name, architecture),
        ).fetchone()
    if not row:
        raise tracking.TrackingError(f"No confirmed upstream for {name}:{architecture}.")
    repository, identifier = tracking.resolve_repository(row[0])
    if identifier != row[1]:
        raise tracking.TrackingError("GitHub repository identity changed; confirm the upstream again before inspection.")
    tag, url, checksum_url = selected_assets(repository, filename)
    print(f"Inspecting {filename} from {repository} release {tag}.")
    with tempfile.TemporaryDirectory(prefix="beacon-inspect-") as directory:
        deb = Path(directory) / "asset.deb"
        digest = download(url, deb, MAX_DEB_SIZE)
        print(f"SHA256: {digest}")
        if checksum_url:
            checksum_path = Path(directory) / "SHA256SUMS"
            download(checksum_url, checksum_path, MAX_CHECKSUM_SIZE)
            expected = expected_checksum(checksum_path, filename)
            if expected is None:
                print("Checksum: SHA256SUMS has no entry for this asset; integrity not verified.")
            elif digest != expected:
                raise tracking.TrackingError("SHA256 checksum mismatch; do not use this asset.")
            else:
                print("Checksum: matches release SHA256SUMS (not authenticated).")
        else:
            print("Checksum: no SHA256SUMS asset available; integrity not verified.")
        asset_name, asset_arch, asset_version = inspect_fields(deb)
        print(f"Installed package: {name}:{architecture} {installed_version}")
        print(f"Asset package: {asset_name}:{asset_arch} {asset_version}")
        if asset_name != name:
            raise tracking.TrackingError("Package name mismatch; this asset is not an update for the installed package.")
        if asset_arch not in (architecture, "all"):
            raise tracking.TrackingError("Package architecture mismatch; this asset is not suitable for this installation.")
        relation = version_relation(installed_version, asset_version)
        print(f"Debian version comparison: asset is {relation} than installed." if relation != "same"
              else "Debian version comparison: asset and installed versions are the same.")
        print("Metadata and checksum do not prove authenticity or dependency compatibility.")
        print("No package was installed; the temporary download was removed.")
