# Beacon

Beacon aims to help keep standalone Debian packages up to date when they have
no configured repository or built-in updater. It investigates where an
installed package might have come from, helps users identify its upstream
project, and aims to track upstream releases.

The initial focus is Debian and Ubuntu. Beacon is at an early stage: discovery,
source classification, GitHub upstream suggestions, and manually confirmed
release tracking work today. Beacon can inspect a user-selected release asset;
automatic upstream approval and installation are not implemented.

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

```bash
python3 src/beacon.py --local
python3 src/beacon.py <package>
python3 src/beacon.py --suggest <package>
python3 src/beacon.py --track <package> <owner/repository>
python3 src/beacon.py --tracked
python3 src/beacon.py --check <package>
python3 src/beacon.py --inspect <package> <exact-asset-filename.deb>
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

Checks query the public GitHub API without authentication and show the latest
published stable release and its `.deb` assets. Beacon suggests likely assets
when the filename resembles the installed package name and specifies a
matching architecture (or `all`); it also shows other `.deb` assets for manual
review and flags multiple likely candidates. Filenames are only hints: this
check does not verify asset contents, compatibility, package identity, or integrity.
Network errors, rate limits, unavailable releases, and changed repository
identities are reported. Version comparison is limited to three-component
numeric versions with an optional `v` prefix; Debian revisions and other tags
are reported as unknown.

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
for the required repository settings.

## Next steps

- Improve upstream suggestions with additional evidence and real-world cases.
- Validate the end-to-end workflow against real standalone `.deb` packages and
  expand version comparison only where it is reliable.
- Design safe update preparation and an APT handoff after tracking works.
