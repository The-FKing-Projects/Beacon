# Beacon

Beacon helps keep standalone Debian packages up to date when no configured
APT repository or PPA provides them. An application may have its own update
checker; Beacon can still help when that checker only points to a download and
leaves installing the update to the user. Beacon investigates where an
installed package might have come from, helps users identify its upstream
project, and lets users review a selected release asset before handing the
update to APT.

The v1 updater currently tracks confirmed GitHub repositories and GitHub
release assets. Direct vendor download URLs and other release providers are
not yet supported.

The initial focus is Debian and Ubuntu. Beacon
[v1.0.0](https://github.com/The-FKing-Projects/Beacon/releases/tag/v1.0.0)
is the first stable CLI updater release, available as a GitHub Release Debian
package and through the project's signed APT repository. Discovery, source
classification, GitHub upstream suggestions, manually confirmed release
tracking, retained update preparation, and an explicitly approved APT handoff
are implemented.
The updater path has passed isolated real-transaction tests and package
qualification across the declared support matrix.

## Install Beacon

Use the stable Debian package; building from source is not required.
Installing Beacon adds its CLI, Python modules, and privileged APT handoff
helper. It does not update other software, add APT sources, or activate
persistent APT hooks.

### Signed APT repository (recommended)

Use the repository to receive Beacon updates through your normal APT upgrades.
The following setup is for an amd64 Debian or Ubuntu system. The repository
currently publishes `all` and `amd64` packages; other architectures have not
been qualified.

If you already configured this repository, keep your existing source entry
and skip to the install/upgrade commands below instead of adding a duplicate.

First, install the prerequisites and download the public signing key:

```bash
sudo apt update
sudo apt install ca-certificates curl gnupg
curl --fail --show-error --location --output fkingprojects.asc \
  https://repo.fkingprojects.org/repo.asc
gpg --show-keys --with-fingerprint ./fkingprojects.asc
```

Confirm that the **primary key fingerprint** matches:

```text
CC3A F6FC 9E04 3D34 9F4E  EE9A FCDE 9316 8DE0 563A
```

Stop if the download fails or the fingerprint differs. Otherwise, install the
key and add the repository. `Signed-By` restricts this source to that key;
it does not add the key to APT's global trusted keyring.

```bash
sudo install -d -m 0755 /etc/apt/keyrings
sudo install -m 0644 ./fkingprojects.asc /etc/apt/keyrings/fkingprojects.asc
sudo tee /etc/apt/sources.list.d/fkingprojects.sources >/dev/null <<'EOF'
Types: deb
URIs: https://repo.fkingprojects.org
Suites: stable
Components: main
Architectures: amd64
Signed-By: /etc/apt/keyrings/fkingprojects.asc
EOF
```

Then install or upgrade Beacon:

```bash
sudo apt update
sudo apt install beacon
beacon --version
```

Review APT's proposed transaction before confirming. Repository setup is an
explicit system configuration change; installing Beacon alone does not add
this source.

### Download the stable .deb (alternative)

Download the `.deb` from the
[latest stable release](https://github.com/The-FKing-Projects/Beacon/releases/latest).
For v1.0.0, the file is `beacon_1.0.0-1_all.deb`. Open a terminal in the
directory containing the downloaded file and run:

```bash
sudo apt install ./beacon_1.0.0-1_all.deb
beacon --version
```

For a newer release, substitute the actual downloaded filename. APT resolves
the package's dependencies; review its proposed transaction before confirming.
Installing a downloaded `.deb` does not configure automatic updates for Beacon.

## Compatibility and validation

Beacon targets Debian/Ubuntu systems with Python 3.10 or newer, APT, and dpkg.
Package CI builds and installs Beacon in pinned Debian 12/13 and Ubuntu
22.04/24.04/26.04 container targets, runs the deterministic regression suite
and exercises the installed CLI. The isolated real APT/dpkg handoff suite runs
separately on a native Ubuntu 24.04 GitHub-hosted VM because the distro matrix
containers do not permit Bubblewrap's unprivileged user namespaces. See the
[Debian package workflow](.github/workflows/debian-package.yml) for current
results; a listed target is not a claim that every run passes.

These are Linux amd64 container checks, not full desktop, derivative
distribution, or other-architecture certification. Networked GitHub discovery
and release inspection have separate live examples in the
[discovery cases](docs/research/discovery-test-cases.md); CI does not depend
on live GitHub search results or install third-party updates. The APT tests
use local fixture packages inside bubblewrap and do not modify the runner's
package database.

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
identified. If an exact package-name match conflicts with the package
homepage, Beacon flags that disagreement. It presents evidence, fork and
archive status, and alternatives without saving or approving a match. Search
results may be incomplete or unrelated; verify the project independently.
The package must be installed;
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
the manifest can make them match. When GitHub supplies an asset SHA-256 digest,
Beacon also checks the downloaded bytes against it; if both sources are
available, both must match. A GitHub API digest is GitHub-generated integrity
metadata, not publisher authentication. A malformed digest or mismatch stops
inspection. Only a file named `SHA256SUMS` with a supported exact-filename
entry is checked; other checksum formats are not. The command does not check
dependencies or execute package maintainer scripts, and never installs a
package.

`--prepare` downloads and retains the exact selected asset under
`$XDG_DATA_HOME/beacon/updates` (default `~/.local/share/beacon/updates`).
It records the release, asset URL, package metadata, downloaded digest,
checksum evidence, any GitHub API digest, and installed version. A failed
checksum or API digest, package identity mismatch, or architecture mismatch
blocks preparation. Neither an unsigned checksum published alongside the
asset nor a GitHub API digest independently authenticates the publisher.

`--install` revalidates the prepared artifact, any GitHub API digest, and the
confirmed upstream; shows the APT dependency transaction; blocks removals and
downgrades; and asks for fresh approval before invoking the packaged
privileged helper through `sudo`.
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

## Stable updater workflow

The v1 CLI implements the following end-to-end workflow:

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

- Replacing APT, Flatpak, Snap, or another package manager
- Duplicating package updates already handled by their package manager or
  [Topgrade](https://github.com/topgrade-rs/topgrade)
- Managing AppImage updates already handled by
  [Gear Lever](https://github.com/mijorus/gearlever)
- Creating another Linux package manager
- Silently installing packages or treating a confidence score as proof of trust

Beacon covers standalone local `.deb` packages that are not available from a
configured APT repository or PPA, whether or not an application includes its
own update checker. A checker that only directs the user to a download does
not itself update the installed package; Beacon can help turn that release
asset into a reviewed APT transaction. This does not extend to AppImages:
[Gear Lever](https://github.com/mijorus/gearlever) manages AppImage updates
using embedded update information or a source configured by the user, such as
GitHub. APT, PPAs, Flatpak, and Snap remain useful and supported parts of the
desktop ecosystem; their existing package managers and
[Topgrade](https://github.com/topgrade-rs/topgrade) should handle the update
workflows they already provide. Beacon hands installation and dependency
resolution to APT for its explicitly reviewed `.deb` updates. Arch support
is not currently on the roadmap because pacman and the AUR already cover that
ecosystem's package workflows. RPM support is a possible future evaluation,
not a commitment: supporting the Red Hat and SUSE branches would require
separate compatibility and maintenance decisions. Neither is currently
supported.

## Releases

Merged `feat:` pull requests trigger a minor release; `fix:` and `perf:`
trigger patch releases. A `!` marker or `BREAKING CHANGE:` footer triggers a
major release. Documentation, tests, and other non-feature changes do not
release by default. See [automated release details](docs/research/release-automation.md)
for the required repository settings. Direct pushes do not automatically
release; the **Release** workflow also supports a manual run on `main` with
an explicit version bump and release title.

The release workflow builds, checks, and uploads a matching `.deb` for every
automated release. To add or refresh the package for an existing release, run
the **Publish Debian package** workflow with that release's tag.

Releases can also be published to the project's self-hosted, GPG-signed aptly
repository. See [APT publishing setup](docs/research/release-automation.md#self-hosted-apt-publishing)
for runner requirements, enablement, and retry instructions. This is maintainer
documentation, not client-side APT source setup.

## For contributors

<details>
<summary>Build the Debian package from source</summary>

From the root of a Beacon checkout on a Debian- or Ubuntu-based system,
install the build tools and build the package:

```bash
sudo apt install debhelper dpkg-dev
dpkg-buildpackage -us -uc -b
```

The `.deb` is written to the checkout's parent directory. Inspect its metadata
and file list before installing it:

```bash
PACKAGE="../beacon_$(dpkg-parsechangelog -SVersion)_all.deb"
dpkg-deb --info "$PACKAGE"
dpkg-deb --contents "$PACKAGE"
```

The package version in `debian/changelog` is synchronized with Beacon's
automated release version. A Debian package build does not verify upstream
release assets or make installing those assets safe.

</details>

## Post-v1 roadmap

The proposed v1.1 focus is real-world discovery and update reliability. These
are planned acceptance criteria, not claims of implemented support:

1. **Broader real-world evidence.** Expand the
   [discovery cases](docs/research/discovery-test-cases.md#post-v1-qualification-backlog)
   beyond Beacon and CloverEye. Record expected identity, source evidence,
   version comparison, asset selection, and verification limits. Turn useful
   metadata cases into offline regression fixtures; keep live GitHub checks
   separate from deterministic CI.
2. **Better upstream suggestions.** Use those cases to identify which
   additional evidence actually improves matches. Show conflicting evidence
   and preserve explicit user confirmation; do not promote filename or
   name similarity into proof of package provenance.
3. **Reliable update comparisons.** Add version-format support only where
   upstream tag interpretation is unambiguous and backed by regression cases.
   Unsupported formats must remain explicitly unknown; use the selected
   asset's full Debian version for installation decisions.
4. **Preserved installation safety.** Exercise reviewed preparation and
   installation with local fixtures in the isolated APT suite. Retain the
   existing source confirmation, exact asset selection, fresh transaction
   approval, removal/downgrade blocking, and post-install verification gates.
5. **Other standalone `.deb` sources.** Evaluate packages whose built-in
   checker only points users to a vendor download, but whose update is not
   available from APT or a PPA. The current updater is GitHub-only; any
   additional provider needs an explicit design for version discovery, source
   identity, redirects, and artifact verification before implementation.

Any future Topgrade integration should focus only on the standalone `.deb`
gap, avoid duplicating its existing package-manager support, and preserve
Beacon's explicit review and approval gates. It is not needed to reimplement
Flatpak, Snap, or repository updates. Direct Nala support and a GUI remain
deferred. This roadmap does not add unattended installation or broaden the
declared platform support.
