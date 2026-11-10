# Beacon

Beacon aims to help keep standalone Debian packages up to date when they have
no configured repository or built-in updater. It investigates where an
installed package might have come from, helps users identify its upstream
project, and aims to track upstream releases.

The initial focus is Debian and Ubuntu. Beacon is at an early stage: discovery,
source classification, GitHub upstream suggestions, and manually confirmed
release tracking work today. Beacon can inspect a user-selected release asset;
automatic upstream approval and installation are not implemented.

## Compatibility and validation

Beacon targets Debian/Ubuntu systems with Python 3.10 or newer, APT, and dpkg.
Package CI builds and installs Beacon in pinned Debian 12/13 and Ubuntu
22.04/24.04/26.04 container targets, runs the deterministic regression suite,
and exercises the installed CLI, discovery inventories, and offline tracking
removal. See the [Debian package workflow](.github/workflows/debian-package.yml)
for current results; a listed target is not a claim that every run passes.

These are Linux amd64 container checks, not full desktop, derivative
distribution, or other-architecture certification. Networked GitHub discovery
and release inspection have separate live examples in the
[discovery cases](docs/research/discovery-test-cases.md); CI does not depend
on live GitHub search results or install third-party updates. Privileged APT
safety experiments remain opt-in and are not part of this compatibility claim.

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
Tracking, suggestions, release checks, and asset inspection limit each
installed-package metadata query to 15 seconds. A timeout is reported as an
error without changing saved associations; Beacon does not retry automatically.

`--untrack` shows the saved association and requires confirmation before
removing it. It works offline and after the package has been uninstalled;
it never uninstalls software. If multiple architectures are tracked, specify
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

## Direction

The first end-to-end milestone is to:

1. Discover an installed package that may not be maintained by a configured
   repository, and show why it is a candidate.
2. Propose an upstream repository with supporting evidence and let the user
   confirm or correct it.
3. Store the confirmed association and check upstream releases against the
   installed version, reporting uncertainty when versions cannot be compared.
4. Present a suitable upstream download or release page for a real standalone
   `.deb`. The initial milestone does not automatically download or install
   updates.

Later, Beacon may help select and download an appropriate `.deb` and hand it
to APT for installation. Before any such handoff, the workflow must check the
upstream identity, package identity and architecture, and available
verification evidence; a confidence score alone is not proof of authenticity.
Details of download verification and installation approval remain to be
decided; see the [APT handoff safety design](docs/design/apt-handoff.md).
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
- Design safe update preparation and an APT handoff after tracking works.
