# Software Discovery Test Cases

These fixtures reflect APT and dpkg metadata inspected on 2026-11-07, a
user-provided Kubuntu 26.04.1 snapshot from 2026-11-08, and the available
package metadata and public release inspections from 2026-11-13 below, along
with explicit synthetic cases for source and package-state edge conditions. They exercise
package parsing without requiring network access or packages to be installed
in the test environment.

| Package | Observed evidence | Expected result |
| --- | --- | --- |
| `bash` | Installed version listed at `us.archive.ubuntu.com` | Ubuntu Repository, High |
| `steam` | Candidate from `repo.steampowered.com`; an older version is also listed in Ubuntu | Vendor Repository, High |
| `floorp` | Installed version listed at `ppa.floorp.app` | PPA, High |
| `clover-eye` | Installed version only in dpkg status; APT marks it local | Local .deb Candidate, Medium |
| `discord-ptb` | Installed version only in dpkg status; APT marks it local | Local .deb Candidate, Medium |
| `code-insiders` | Installed version `1.146.0-1794014368` listed at `packages.microsoft.com/repos/code` | Vendor Repository, High |
| `tailscale` | Installed version `1.104.5` listed at `pkgs.tailscale.com` | Vendor Repository, High |
| `beekeeper-studio` | Installed version `6.2.2` listed at `deb.beekeeperstudio.io` | Vendor Repository, High |
| `heroic` | dpkg status abbreviation is `rc` | Config Remains |
| `microsoft-edge-stable` | Not installed; APT cannot locate package in current cache | Unknown, Low |
| `brave-browser` | Not installed; APT cannot locate package in current cache | Unknown, Low |
| `orphan-candidate` | Synthetic installed/local policy fixture; no configured repository origin | Local .deb Candidate, Medium; not proven orphaned |

The `steam` result differs from the original candidate note in issue #9: the
selected candidate is provided by Steam's repository, while an older package
version is available from Ubuntu. Beacon should report the source of the
selected version, not any source listed for another version.

The user-provided snapshot contains three additional real vendor-repository
examples: Code Insiders, Tailscale, and Beekeeper Studio. In each case, the
installed version is present in current APT policy at the listed host.
`tailscale` and `beekeeper-studio` appear as `unknown` in `apt list --installed`
release labels, but their policy output still identifies the installed
version's repository; Beacon's source classification uses that version
origin, not the release label.

`microsoft-edge-stable` and `brave-browser` were not installed and APT could
not locate either package in the current cache. Their explicit tests assert
`Unknown`, not a positive vendor result. Synthetic fixtures separately verify
that representative Microsoft and Brave repository URLs classify as vendor
sources when such origins are actually present; they do not claim those
repositories or versions were observed on the user's system.

The `orphan-candidate` fixture represents an installed version available only
from dpkg status and marked `[installed,local]` by APT. This evidence supports
`Local .deb Candidate`, but does not prove the package is orphaned: the
original repository may have been removed, the package may have been
installed from a local archive, or the source may otherwise be unavailable.
By contrast, `heroic` has dpkg state `rc` and is classified as configuration
remaining, not installed software. A reproducible positive case for an
orphaned package, in the historical sense of an installed package formerly
provided by a now-removed repository, cannot be established from current
APT/dpkg metadata alone.

Run the deterministic fixtures with:

```sh
python3 -m unittest discover -s tests -v
```

## Real standalone-package workflow

On 2026-11-10 (UTC), the installed `beacon:all` package provided an end-to-end
case without installing or upgrading anything. Commands ran from the source
checkout as `python3 src/beacon.py`; the table uses the installed command's
`beacon` spelling for readability.

| Step | Observed result |
| --- | --- |
| `beacon beacon` | Installed `0.8.1-1`; Local .deb Candidate, Medium (65/100), based on APT's local marker and no installed-version repository origin |
| `beacon --suggest beacon` | No package homepage; first-page name search returned multiple strongest matches and warned that no single upstream was identified |
| `beacon --track beacon The-FKing-Projects/Beacon` | Explicitly confirmed the known project repository, rather than accepting an unrelated search result |
| `beacon --tracked` in a separate process | The association persisted as `beacon:all` pointing to the confirmed repository |
| `beacon --check beacon` | Found stable release `v0.8.2` and suggested `beacon_0.8.2-1_all.deb` by filename |
| `beacon --inspect beacon beacon_0.8.2-1_all.deb` | Package name and `all` architecture matched; full Debian comparison found asset version `0.8.2-1` newer than installed `0.8.1-1` |

The test used an isolated temporary `XDG_STATE_HOME` across separate CLI
processes, then removed it; the user's tracking database was not changed.
The supplied repository is Beacon's own project, not an automatically
verified match. Search results and latest releases are time-sensitive.

The initial release check reported an unknown version comparison for
`0.8.1-1` versus `v0.8.2`. Numeric Debian revision support now compares the
upstream portions and explicitly states that revision `1` is not compared.
The deterministic tracking tests cover this case and retain unknown results
for epochs, distro suffixes, prereleases, and unsupported release tags.

The inspected asset's SHA-256 was
`ab172d6374efe788741b828ea9a17c3d2a49b76a4697fdc4bb2ed7837838e421`.
No `SHA256SUMS` asset was available, and Beacon reported integrity as
unverified. This digest records the observed download, not independent
authenticity evidence. Inspection removed its temporary download and did
not check dependencies, run maintainer scripts, or install a package.

## Independent project: CloverEye

On 2026-11-10 (UTC), the source checkout also exercised the workflow against
the installed third-party package `clover-eye:amd64` version `0.1.1`.
Discovery reported Local .deb Candidate, Medium (65/100), based on APT's
local marker and no repository origin for the installed version.

The package had no homepage metadata. `--suggest clover-eye` returned
`MiguelCarino/CloverEye` as a low-confidence similar-name candidate, along
with unrelated search-only alternatives. Removing a separator was not
treated as an exact identity match. The repository's README independently
described the same unofficial desktop client as the installed package's
description, and its release listed a Debian download. This supported
selecting it for the test; it did not authenticate the installed artifact
or prove its historical origin.

Using a fresh temporary `XDG_STATE_HOME`, separate CLI processes ran:

```sh
beacon --track clover-eye MiguelCarino/CloverEye
beacon --tracked
beacon --check clover-eye
beacon --inspect clover-eye clovereye_0.1.1_amd64.deb
beacon --tracked
```

The association was explicitly confirmed in test state, persisted across
processes, and remained unchanged after inspection. The release check found
[`v0.1.1`](https://github.com/MiguelCarino/CloverEye/releases/tag/v0.1.1),
reported matching versions, and suggested `clovereye_0.1.1_amd64.deb`.
Although its filename omits the package name's hyphen, inspection found
the exact internal package identity `clover-eye:amd64` version `0.1.1`.
Full Debian version comparison correctly reported the same version, not
an available upgrade.

The asset's SHA-256 was
`64d4ea8f65383ea568bce32cc862eb608bf50f0575b315f27179abe1769082e9`
and matched the release's `SHA256SUMS` entry. Beacon explicitly described
that match as unauthenticated: publishing the checksum alongside the asset
does not independently prove authenticity or dependency compatibility.
The temporary download and test tracking state were removed; the user's
tracking database and installed packages were unchanged.

Together, the Beacon and CloverEye cases cover a newer available version,
an already-current upstream version, ambiguous generic-name search, a
separator-only name suggestion, and releases with and without a supported
checksum manifest. They do not establish support for all projects, release
formats, or Debian/Ubuntu versions.

## Available distro packages: bat and fd-find

On 2026-11-13 (UTC), read-only APT metadata queries and temporary public
archive inspection expanded the evidence to two additional projects. Neither
package was installed. These observations compare **available Ubuntu
candidates**, not installed standalone packages; they are not a full
`--track`/`--prepare`/`--install` qualification.

| APT package | Observed Ubuntu candidate | Package homepage | Selected upstream archive | Internal archive metadata |
| --- | --- | --- | --- | --- |
| `bat` | `0.25.0-5ubuntu1` | `https://github.com/sharkdp/bat` | [`bat_0.26.1_amd64.deb`](https://github.com/sharkdp/bat/releases/tag/v0.26.1) | `bat:amd64` version `0.26.1` |
| `fd-find` | `10.3.0-2ubuntu1` | `https://github.com/sharkdp/fd` | [`fd_10.5.2_amd64.deb`](https://github.com/sharkdp/fd/releases/tag/v10.5.2) | `fd:amd64` version `10.5.2` |

Both APT candidates were listed at
`http://us.archive.ubuntu.com/ubuntu resolute/universe`, so discovery reported
Ubuntu Repository rather than Local .deb Candidate. Both homepages were
exact HTTPS GitHub repository URLs; `homepage_repository` recognized them.
This tests public homepage metadata, not `package_homepage` against an
installed package. No real GitHub name-search ranking was measured.

The selected assets were fetched using `selected_release_assets` and
`download`, inspected with `inspect_fields`, and removed with their temporary
directory. No payload or maintainer script was executed. Neither release
provided the supported `SHA256SUMS` asset. Observed SHA-256 values were:

- `bat_0.26.1_amd64.deb`: `ad59954aa1540e526f97267f60557ea5ef4c7dcf91a0811254134537cb353a3c`
- `fd_10.5.2_amd64.deb`: `342a9d1618c4340668cb7ad96d353064bf226ac403add80e587103975d5fa49c`

These digests record the downloads; they are not independent authenticity
evidence. The full Debian comparison found each selected archive's version
newer than its corresponding distro candidate. The release-tag comparison
correctly remained unknown for the `ubuntu1` revisions.

The `fd-find` case demonstrates why upstream identity and package identity
must remain separate: its homepage identifies `sharkdp/fd`, but the upstream
archive is a package named `fd`, not `fd-find`. A newer version and a valid
upstream association must not turn it into an update for `fd-find`.
Filename matching left this asset unverified, while the `bat` filename was
only a likely candidate, not an approved update.

Offline regression coverage uses these observed versions, names, homepage
and repository identities. It also explicitly **simulates installed
packages** and adds a synthetic competing name-search result to exercise
the installed-only CLI paths without changing the host. The fixtures verify
direct-homepage ranking without saving an association, conservative release
comparisons, APT ownership blocking before release selection/download, and
`fd`/`fd-find` rejection with cleanup and preservation of an unrelated prepared
update. The simulated installed APT policy is not a recorded host installation.
These cases preserve the existing guards; they do not enable package-name
aliases or expand version-tag support.

## Post-v1 qualification backlog

The next qualification work should expand the observed cases rather than
assume that successful self-updating or one third-party inspection generalizes.
These are planned cases, not completed live validations:

| Case | Evidence to record | Required behavior |
| --- | --- | --- |
| Package with a direct GitHub homepage | Installed metadata, repository identity, alternatives, and conflicting evidence | Prefer the direct-homepage evidence without automatically confirming the association |
| Installed version also managed by APT | Exact installed-version origins and available APT candidate | Report APT ownership and preserve the existing handoff policy |
| Ambiguous or renamed package/asset | Internal package identity, filename hints, architecture, and competing assets | Require exact user selection; reject internal identity or architecture mismatches |
| Unsupported upstream tag/version | Installed Debian version, exact release tag, and selected asset version | Report unknown release comparison unless a supported mapping is established; use full Debian comparison for the selected asset |
| Interrupted or changed preparation | Pinned release/asset identity, digest, persisted association, and artifact state | Report the failure, preserve valid state, and reject stale or changed installation inputs |

For each new live case, record the observation date, package and architecture,
command results, and what was and was not verified. Use temporary Beacon state
and artifact directories so exploratory tracking does not alter normal user
associations. Do not copy private metadata into fixtures; retain only the
minimal public or synthetic inputs needed to reproduce the behavior.

Live inspection may download an explicitly selected public asset, but is not
permission to install third-party packages on a developer's host. Exercise
installation failure and transaction cases with locally built fixture packages
inside the existing isolated APT suite. Keep that evidence distinct from
real-project metadata inspection and from the declared distro matrix.
