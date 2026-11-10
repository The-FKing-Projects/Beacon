# Beacon

Beacon aims to help keep standalone Debian packages up to date when they have
no configured repository or built-in updater. It investigates where an
installed package might have come from, helps users identify its upstream
project, and lets users review selected upstream packages before handing an
update to APT.

The initial focus is Debian and Ubuntu. Discovery, source classification,
GitHub upstream suggestions, manually confirmed release tracking, retained
update preparation, and an explicitly approved APT handoff are implemented.
The updater path has passed isolated real-transaction tests and package
qualification across the declared support matrix; Beacon's release process
will designate the first stable version.

## Compatibility and validation

Beacon targets Debian/Ubuntu systems with Python 3.10 or newer, APT, and dpkg.
Package CI builds and installs Beacon in pinned Debian 12/13 and Ubuntu
22.04/24.04/26.04 container targets, runs the deterministic regression suite
and isolated real APT/dpkg handoff tests, and exercises the installed CLI.
See the [Debian package workflow](.github/workflows/debian-package.yml) for
current results; a listed target is not a claim that every run passes.

These are Linux amd64 container checks, not full desktop, derivative
distribution, or other-architecture certification. Networked GitHub discovery
and release inspection have separate live examples in the
[discovery cases](docs/research/discovery-test-cases.md); CI does not depend
on live GitHub search results or install third-party updates. The APT tests use
local fixture packages inside bubblewrap and do not modify the host package
database.

## Current Features

- Package inspection
- Package version detection
- Package source detection with confidence evidence
- System inventory scanning (`--scan`)
- Repository inventory (`--repos`)
- Configuration-remains inventory (`--clean`)
- Local package inventory (`--local`)
- Read-only GitHub upstream suggestions (`--suggest`)
- Manually confirmed GitHub associations, release checks, and `.deb` asset suggestions
- Temporary inspection of a user-selected GitHub `.deb` asset (`--inspect`)
- Retained preparation of an exact user-selected release asset (`--prepare`)
- Reviewed APT transaction and installation of a prepared update (`--install`)
- Debian package build metadata for installing Beacon itself
- Automated SemVer tags and GitHub Releases for qualifying merged pull requests

## Track a GitHub upstream

After installing Beacon's Debian package, use the `beacon` command:

```bash
beacon --local
beacon <package>
beacon --suggest <package>
beacon --track <package> <owner/repository>
beacon --tracked
beacon --check <package>
beacon --inspect <package> <exact-asset-filename.deb>
beacon --prepare <package> <exact-asset-filename.deb>
beacon --install <package>
beacon --untrack <package>
```

Verify the repository is the package's upstream before confirming it. Beacon
does not determine that relationship for you. `--suggest` checks an exact
GitHub repository homepage when present and searches the first page of GitHub
repository names. Each candidate is labeled as a direct homepage match, exact
name match, similar name, or search-only result. If multiple repositories tie
for the strongest nonzero evidence, Beacon warns that no single upstream is
identified. It presents evidence, fork and archive status, and alternatives
without saving or approving a match. Search results may be incomplete or
unrelated; verify the project independently. The package must be installed;
specify `package:architecture` if more than one architecture is installed.
Associations are saved per user under `$XDG_STATE_HOME/beacon/tracking.sqlite3`
(default `~/.local/state/beacon/tracking.sqlite3`). Re-running `--track`
requires confirmation before replacing an association.
Package discovery, inventories, tracking, suggestions, release checks, and
asset inspection limit each system metadata query to 15 seconds. A timeout or
failed command is reported as an error instead of being presented as an
unknown package/source; saved associations remain unchanged and commands are
not retried automatically.

`--untrack` shows the saved association and requires confirmation before
removing it; any prepared update for that association is removed too. It works
offline and after the package has been uninstalled; it never uninstalls
software. If multiple architectures are tracked, specify
the exact `package:architecture` shown by `--tracked`. A missing association
or an association changed by another process during confirmation is reported
as an error rather than deleting a different entry.

Checks query the public GitHub API without authentication and show the latest
published stable release and its `.deb` assets. Beacon suggests likely assets
when the filename resembles the installed package name and specifies a
matching architecture (or `all`); it also shows other `.deb` assets for manual
review and flags multiple likely candidates. Filenames are only hints: this
check does not verify asset contents, compatibility, package identity, or integrity.
Network errors, interrupted API responses, rate limits, unavailable releases,
and changed repository identities are reported without replacing saved
associations. Failed requests are not retried automatically; retry the command
after connectivity recovers or the rate limit clears. Version comparison is limited to three-component
numeric versions with an optional `v` prefix. Installed versions may also have
a numeric Debian revision: `0.8.1-1` versus `v0.8.2` reports a newer upstream
release. These checks explicitly compare only the upstream version, not the
Debian revision or a release asset's package version; equal upstream versions
do not establish that the packages are identical or equally current. Epochs,
distro-specific revisions such as `-1ubuntu1`, prereleases, and other tag
formats are reported as unknown. Use `--inspect` for the selected asset's full
Debian version comparison.

`--inspect` downloads the exact named asset from the tracked repository's
latest stable release into a temporary directory, compares its package name,
architecture, and Debian version to the installed package, and then removes the
download. Downloads are limited to 512 MiB. If the release has a `SHA256SUMS`
asset, Beacon checks an exact filename entry; a missing entry or checksum file
is reported, and a mismatch stops inspection. The checksum is not authenticated
and does not prove authenticity: someone able to replace both the asset and
the manifest can make them match. Only a file named `SHA256SUMS` with a
supported exact-filename entry is checked; other checksum formats are not.
The command does not check dependencies or
execute package maintainer scripts, and never installs a package.

`--prepare` downloads and retains the exact selected asset under
`$XDG_DATA_HOME/beacon/updates` (default `~/.local/share/beacon/updates`).
It records the release, asset URL, package metadata, digest, checksum evidence,
and installed version. A failed checksum, package identity mismatch, or
architecture mismatch blocks preparation. An unsigned checksum published
alongside the asset is not independent publisher authentication.

`--install` revalidates the prepared artifact and confirmed upstream, shows
the APT dependency transaction, blocks removals and downgrades, and asks for
fresh approval before invoking the packaged privileged helper through `sudo`.
The helper stages a root-owned copy and enforces the reviewed transaction
through APT's protocol-v3 pre-install hook. Package maintainer scripts run as
root. Beacon trusts the administrator and root-run APT hooks; it does not
protect against a malicious administrator or guarantee rollback. A failed
APT operation can leave partial package state, which Beacon reports.
Re-run `--check`, select and `--prepare` the desired asset, then review it
again with `--install`; do not assume a failed installation was rolled back.
The [APT handoff design](docs/design/apt-handoff.md) documents the trust
boundary, safety mechanism, and remaining qualification requirements.

### Tracking-store errors and recovery

Beacon checks the tracking database's schema, integrity, and saved association
fields before using it. Unknown versions, incompatible tables, unexpected
schema objects, corrupt files, and invalid records produce an error showing
the database path. Beacon does not reset or automatically repair that data.

If opening the store fails, stop other Beacon processes and preserve a copy
of the database and any adjacent `-wal`/`-shm` files before attempting recovery.
Check the reported path, permissions, and whether a newer Beacon version
created the store. Restore a known-good backup only after preserving the
failed store. Without a usable backup, keep the original and move it aside
explicitly before starting a fresh store; associations must then be reviewed
and confirmed again. Do not edit the schema version merely to bypass an error.

## Build the Debian package

The package installs Beacon's CLI and Python modules; it does not install or
update other software, add APT sources, or activate APT hooks. Build it on a
Debian- or Ubuntu-based system with the Debian packaging tools:

```bash
sudo apt install debhelper dpkg-dev
dpkg-buildpackage -us -uc -b
```

The `.deb` is written to the parent directory. Inspect its metadata and file
list before installing it:

```bash
PACKAGE="../beacon_$(dpkg-parsechangelog -SVersion)_all.deb"
dpkg-deb --info "$PACKAGE"
dpkg-deb --contents "$PACKAGE"
```

The package version in `debian/changelog` is synchronized with Beacon's
automated release version. A Debian package build does not verify upstream
release assets or make installing those assets safe.

The release workflow builds, checks, and uploads a matching `.deb` for every
automated release. To add or refresh the package for an existing release, run
the **Publish Debian package** workflow with that release's tag.

Releases can also be published to the project's self-hosted, GPG-signed aptly
repository. See [APT publishing setup](docs/research/release-automation.md#self-hosted-apt-publishing)
for runner requirements, enablement, and retry instructions.

## Direction

The first end-to-end milestone is to:

1. Discover an installed package that may not be maintained by a configured
   repository, and show why it is a candidate.
2. Propose an upstream repository with supporting evidence and let the user
   confirm or correct it.
3. Store the confirmed association and check upstream releases against the
   installed version, reporting uncertainty when versions cannot be compared.
4. Prepare a pinned, user-selected `.deb`, show APT's proposed dependency
   changes, require fresh approval, install through APT, and verify the
   installed result. See the [APT handoff safety design](docs/design/apt-handoff.md)
   for its trust boundary, qualification record, and limitations.
Beacon should surface ambiguity instead of guessing.

An APT local or dpkg-only signal is a **candidate**, not proof that a package
was originally installed from a standalone `.deb`: its repository may have
been removed or its installed version may no longer be present in the cache.
Not every package will have an identifiable upstream or suitable release.

## Non-Goals

- Replacing APT
- Replacing Flatpak
- Replacing Topgrade
- Creating another Linux package manager
- Silently installing packages or treating a confidence score as proof of trust

APT remains responsible for package installation and dependency handling.
RPM- and Arch-based discovery, along with other installation formats, are
future considerations rather than current support.

## Releases

Merged `feat:` pull requests trigger a minor release; `fix:` and `perf:`
trigger patch releases. A `!` marker or `BREAKING CHANGE:` footer triggers a
major release. Documentation, tests, and other non-feature changes do not
release by default. See [automated release details](docs/research/release-automation.md)
for the required repository settings. Direct pushes do not automatically
release; the **Release** workflow also supports a manual run on `main` with
an explicit version bump and release title.

## Next steps

- Improve upstream suggestions with additional evidence and real-world cases.
- Validate the end-to-end workflow against real standalone `.deb` packages and
  expand version comparison only where it is reliable.
- Designate and publish the first stable updater version through the normal
  project release process.
