# Software Discovery Test Cases

These fixtures reflect APT and dpkg metadata inspected on 2026-11-07, a
user-provided Kubuntu 26.04.1 snapshot from 2026-11-08, available package
metadata and public release inspections from 2026-11-13/14 and 2026-11-15,
and an operator-reported Beacon v1.1.2 desktop summary on Kubuntu 26.04
(Beacon installed from the signed APT repository). Deterministic fixtures
exercise package parsing without requiring network access or packages to be
installed in the test environment. Dated live records (for example the
2026-11-10 Beacon/CloverEye workflows and 2026-11-13/15 lab notes) are
snapshots, not guarantees about future upstream releases. The Kubuntu
v1.1.2 section below is an undated operator-reported summary, not a dated
transcript.

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

On 2026-11-14 (UTC), read-only lookups through Beacon's GitHub release parser
validated the release-page and Debian-asset URLs for four public repositories:
Beacon `v1.0.0` (1 `.deb`), CloverEye `v0.1.1` (1), `sharkdp/bat` `v0.26.1`
(8), and `sharkdp/fd` `v10.5.2` (8). Each URL matched the exact repository,
tag, and asset filename. The `bat` and `fd` releases also list musl-named
assets. This confirms the current API URL shape only; no asset was downloaded,
and package identity, compatibility, integrity, and authenticity were not
checked.

The same `bat` release also offers `bat_0.26.1_arm64.deb`. On 2026-11-13,
temporary inspection found internal metadata `bat:arm64` version `0.26.1`
and SHA-256
`4a70c3f6236f2c621bd68357257e21b78c9497de4de1e803301ec0209f168653`.
Filename evidence correctly marked it as a likely candidate for `arm64` and
not suggested for `amd64`. This validates metadata inspection and filename
architecture filtering for one public archive; it does not certify Beacon
installation on arm64 or expand the supported platform matrix.

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
The live `bat` release also lists `bat-musl` assets; filename regressions keep
those unverified for the regular `bat` package even when the architecture
suffix matches.

Offline regression coverage uses these observed versions, names, homepage
and repository identities. It also explicitly **simulates installed
packages** and adds a synthetic competing name-search result to exercise
the installed-only CLI paths without changing the host. The fixtures verify
direct-homepage ranking, a warning when a distinct exact-name candidate
conflicts with the package homepage, and no association being saved;
conservative release comparisons; APT ownership blocking before release
selection/download; and `fd`/`fd-find` rejection with cleanup and preservation
of an unrelated prepared update. The simulated installed APT policy is not a
recorded host installation. These cases preserve the existing guards; they do
not expand version-tag support. Survey-documented packaging aliases for
`--suggest` (`git-delta`→`delta`, `du-dust`→`dust`, `fd-find`→`fd`) are covered
separately under offline suggestion regressions and remain evidence-only.

## Interrupted preparation and changed release inputs

The offline cases in `tests/test_updates.py` also qualify failure paths using
temporary tracking state and synthetic archive bytes:

| Injected condition | Required result |
| --- | --- |
| Download error or `KeyboardInterrupt` during archive or checksum download while re-preparing | Keep the prior prepared row and archive, remove the new partial files, and clean stale partial downloads |
| Storage error at directory synchronization after promoting a replacement archive | Remove the uncommitted replacement and retain the prior row and archive |
| Changed selected asset URL, removed checksum asset, or changed/missing checksum entry | Reject installation before transaction preview, user approval, or privileged handoff; preserve saved preparation |
| Modified retained archive bytes | Reject the changed digest before preview, approval, or privileged handoff; do not silently repair or approve the file |

These are deterministic fault-injection regressions, not live upstream
mutations, third-party installations, or a power-loss qualification. They
exercise the existing cleanup and revalidation behavior without weakening
the production guards. In particular, they do not establish crash atomicity
between filesystem writes and SQLite commits. A saved preparation rejected
as changed still requires a fresh `--prepare` and review; retaining its record
is not permission to install it.

APT ownership regression tests also cover the case where the installed version
appears as the candidate from dpkg status while an older version remains
available from a configured repository. Any repository version now blocks
Beacon preparation before release selection or download; a locally installed
newer version no longer hides APT's ability to manage the package.

## Kubuntu 26.04: Beacon v1.1.2 operator-reported summary

**Auditability note:** this is an operator-reported summary from a Kubuntu
26.04 desktop running Beacon **v1.1.2** (signed APT install). It does **not**
yet meet the dated live-case checklist below (observation date, per-package
architecture, full command transcripts, and explicit verification limits are
not recorded here). Treat outcomes as directional evidence for backlog
prioritization, not as a fully auditable qualification transcript. A later
pass can promote rows to dated records when those fields are captured.

Packages below were described as standalone local `.deb` candidates (no
configured APT/PPA origin for the installed version) unless noted. The
operator reported the full local workflow:

`beacon` → `--suggest` → `--track` → `--check` → `--inspect` → `--prepare` →
`--install`

Prepared artifacts were retained under `~/.local/share/beacon/updates/`.
Installations used the reviewed APT handoff after the v1.1.2 packaged-helper
fix for `/run` `noexec` staging (packaged helper under `/usr`; staging under
`/run/beacon/` — see [isolated APT suite](../design/isolated-apt-suite.md) and
[APT handoff](../design/apt-handoff.md)). Digests and checksum matches below are
integrity evidence only; they do **not** prove publisher authenticity.

### Successful upgrades

| Package | From → to | Notes |
| --- | --- | --- |
| `stopgrade` | `17.6.1` → `17.16.0` | First real third-party upgrade on this host; exposed the `/run` `noexec` helper bug fixed in v1.1.2 |
| `clover-eye` | `0.1.1` → `0.1.3` | Clean install with large dependency transaction; exact `SHA256SUMS` entry and GitHub API digest both verified |
| `moonfin` | `3.0.0` → `3.1.0` | Operator report: `Moonfin_Linux_v3.1.0.deb` was not marked likely under older heuristics; exact selection, inspect, prepare, and install still succeeded. Current matching treats that Linux+version pattern as likely for **amd64 only** (unit-tested); exact selection remains required |

### Tracked without upgrade (or not upgradable via Beacon)

| Package | Observed check | Notes |
| --- | --- | --- |
| `caprine` | Current `2.61.0` | Homepage included a `#readme` fragment; at the time of the operator report that missed the “very high” direct-homepage tier (name search still found the repo). Fragment stripping is now covered by unit tests so `#readme` ranks as a direct homepage match without auto-confirm |
| `feishin` | Current `1.17.0` | Operator report left `Feishin-linux-amd64.deb` unverified; current matching treats product-`linux`-arch as likely when the product token matches the package name (unit-tested); exact selection remains required |
| `github-desktop` | Unknown comparison | Installed `3.7.1-build.50` versus tag `release-3.4.13-linux1`; release-tag comparison refused; assets not marked likely |
| `spdx-licenses` | No `.deb` assets; version now comparable | Installed `3.27.0+ds-1` versus tag `v3.29.0`: `--check` can compare after ignoring `+ds` (see [version comparison](../design/version-comparison.md)); upstream still ships XML, not a Debian package, so Beacon cannot prepare/install |
| `discord-ptb` | No usable upstream | Homepage `discord.com`; weak name-only search matches; correct negative — Beacon did not invent a GitHub updater path |

### Confirmed working on this host

- Local `.deb` candidate detection for standalone installs
- GitHub homepage resolution (when the URL is an exact repository page), name search, and match ranking
- Manual `--track` confirmation and persisted associations
- `--check` reporting newer, matching, or explicitly unknown version comparisons
- `--inspect` with GitHub API digest checks and optional exact `SHA256SUMS` entries
- `--prepare` retention under `~/.local/share/beacon/updates/`
- Reviewed APT transaction handoff and successful `--install` after the v1.1.2 helper fix

### Observed limitations (do not weaken gates)

- Release-tag version comparison remains narrow (see rules below)
- Filename heuristics stay conservative: product-`linux`-arch, amd64-only product-`Linux`-version, LocalSend-style `x86-64`/`arm-64`, and `gh`-style underscore version_linux names can mark likely; musl/wrong-arch/wrong-product names stay unverified; exact selection is still required
- Homepage query strings, `/releases`-style paths, and non-repository marketing URLs still miss the direct homepage tier; fragments such as `#readme` are ignored for matching (further normalize deferred — see [homepage URL normalize](../design/homepage-url-normalize.md))
- `--check-all` summarizes every tracked association read-only; it never prepares or installs
- Tracking does not auto-update associations when upstreams rename or move

These desktop installs are distinct from CI and from temporary-state lab
cases. They still do not authorize unattended installation, non-GitHub
providers, or treating digests as authenticity proofs.

### Version comparison pointer

Canonical operator rules for when `--check` compares versus when it prints
unknown — including Kubuntu `github-desktop` / `spdx-licenses` examples and
the `--inspect` vs `--prepare` architecture difference — are in
[version comparison](../design/version-comparison.md). Expanding the
supported tag set remains backlog and needs unambiguous mappings plus offline
regressions before any code change.

## Supporting lab observations (2026-11-14)

Read-only / temporary-state checks on an Ubuntu 24.04 amd64 lab host (no
third-party package installations; temporary `XDG_STATE_HOME` only):

| Case | Result |
| --- | --- |
| Installed `iputils-ping` with homepage `https://github.com/iputils/iputils/` | `--suggest` ranked the homepage repository **very high**; association saved only after explicit confirm in temp state; `--check` found tag `20250605` with **no** `.deb` assets and **unknown** version comparison for epoch/`ubuntu` installed version `3:20240117-1ubuntu0.1`; `--prepare` blocked because APT owns the package |
| Installed `gh` (homepage `https://cli.github.com/`) | Homepage not a direct GitHub repository URL; name search returned many exact-name ties and warned that no single upstream was identified (official `cli/cli` not established by package-name search alone) |
| Stale APT cache before `apt-get update` | Several Ubuntu packages briefly appeared as Local `.deb` Candidate; after refreshing lists they correctly classified as Ubuntu Repository — discovery depends on current policy metadata |
| `sharkdp/bat` `v0.26.1` competing assets | `bat_0.26.1_amd64.deb` likely for `bat:amd64`; `bat-musl_0.26.1_musl-linux-amd64.deb` unverified by filename and inspects as internal package `bat-musl` / arch `musl-linux-amd64` |
| `sindresorhus/caprine` `v2.61.0` | Temporary download: internal `caprine:amd64` `2.61.0`, no `SHA256SUMS`, GitHub API digest matched downloaded bytes; digest is not publisher authentication |
| `The-FKing-Projects/Beacon` `v1.1.2` | Asset `beacon_1.1.2-1_all.deb` inspects as `beacon:all` `1.1.2-1`; release-tag compare treats `1.1.2-1` vs `v1.1.2` as matching upstream versions while ignoring the Debian revision; full Debian compare still sees `1.1.2-1` ≠ bare `1.1.2` |
| Vendor download evaluation | `steam-installer` homepage points at Steam's site; no Discord GitHub release updater path found — keeps non-GitHub providers at evaluation only |

## Post-v1 qualification status

v1.1.x turned several original backlog rows into offline regressions and
dated live observations plus the undated Kubuntu 26.04 v1.1.2
operator-reported summary above. Fixture coverage and one host's upgrades
still do not generalize to every project; keep expanding cases rather than
weakening confirmation or integrity gates.

| Case | Offline / fixture coverage | Live observation | Still needed |
| --- | --- | --- | --- |
| Package with a direct GitHub homepage | Simulated installed `--suggest` coverage is for `fd-find` (homepage outranks a synthetic exact-name search hit; no auto-save), Caprine-style `#readme` fragment stripping, and survey aliases (`git-delta`/`du-dust` low-tier only). `bat` offline coverage is available-package provenance, release-tag/asset comparison, and filename matching — not a simulated installed suggestion flow | Kubuntu standalone workflow; lab `iputils-ping` very-high homepage rank; Caprine `#readme` was an operator miss before fragment stripping | Query-string homepages remain unsupported; confirm ranking without auto-save; do not broaden undocumented aliases |
| Installed version also managed by APT | APT ownership blocks preparation when any policy version comes from a repository, including a newer local candidate over an older repo version | Lab `iputils-ping` prepare refused; `bat`/`fd-find`/`gh` Ubuntu Repository after fresh apt lists | Repeat handoff refusal on more APT-managed desktop packages |
| Ambiguous or renamed package/asset | `fd` vs `fd-find` rejection, musl filename non-matches, arm64-vs-amd64 filtering, Feishin product-`linux`-arch, Moonfin Linux+version amd64, LocalSend `x86-64`/`arm-64`, and `gh` underscore version_linux heuristics | CloverEye hyphen/name mismatch; bat/bottom musl; operator Moonfin/Feishin; 2026-11-15 `git-delta`/`du-dust` name separation | Keep exact user selection; do not promote hints to provenance |
| Unsupported upstream tag/version | Epochs, `ubuntu1` and other distro suffixes, prereleases, and malformed tags stay unknown; numeric Debian revisions compare upstream-only; installed `+ds`/`+dfsg` upstream markers are ignored for `--check` | `github-desktop` build/tag mismatch still unknown; `spdx-licenses` `+ds` now comparable for the tag check only; lab epoch/`ubuntu` unknown; LocalSend `+64` and Helix `25.07.1` correctly unknown | Broader comparison only with unambiguous mappings and regressions |
| Interrupted or changed preparation | Deterministic fault injection in `tests/test_updates.py` for interrupted downloads, storage failures, changed URLs/checksums, and modified bytes | None required for CI; live mutation of third-party releases is out of scope | Retain regressions; do not claim crash atomicity between filesystem writes and SQLite commits |
| Full reviewed install path | Isolated APT suite and packaging gates | Operator-reported Kubuntu upgrades for `stopgrade`, `clover-eye`, and `moonfin` after v1.1.2 helper fix (summary; not a dated transcript) | Capture dated auditable records; never unattended installs |

## Follow-up backlog (docs only; not authorized work)

Suggested product directions from the Kubuntu qualification. Recorded here so
later PRs can pick them up deliberately; **do not** implement them solely
because they appear in this list:

| Direction | Motivation from cases | Constraint |
| --- | --- | --- |
| Broader release-tag version comparison | `github-desktop` still unknown; `spdx-licenses` `+ds` handled; epoch/`ubuntu` unknowns remain | **Design note** for Desktop-style tags in [github-desktop-tag-comparison](../design/github-desktop-tag-comparison.md); no parser expansion until that decision gate passes; keep unsupported tags unknown |
| Optional `--check-all` | Multiple tracked packages on one host | **Done** as read-only summary with per-package soft failures; never auto-prepare or auto-install |
| Slightly more flexible filename matching, or mark likely after successful inspect | Moonfin title-case / Feishin channel-style names; LocalSend `x86-64`/`arm-64`; `gh` underscores | **Done** for product-`linux`-arch, amd64-only product-`Linux`-version, LocalSend hyphenated arch aliases, and post-`linux` version peel; post-inspect auto-likely and broader aliases remain out of scope; exact selection still mandatory |
| Document version-comparison rules more prominently for operators | Operators need to know when `--check` says unknown vs when `--inspect` decides direction | **Done** for current behavior in [version comparison](../design/version-comparison.md); broader formats still backlog |
| Homepage URL normalization (strip fragments such as `#readme`) | Caprine direct-homepage tier missed | **Done** for fragments only (`homepage_repository`); query/`/releases` further normalize **decision-deferred** in [homepage URL normalize](../design/homepage-url-normalize.md) — no dated package case; still no auto-confirm |
| Non-GitHub vendor download providers | `discord-ptb` correct negative; Steam-style vendor homepages | **Decision recorded** in [vendor download](../design/vendor-download.md): stay GitHub-only; no first publisher clears the gate; still no provider implementation until Dennis approves a named unlock |

### Post-v1.3.0 GitHub-path cross-check

After [v1.3.0](https://github.com/The-FKing-Projects/Beacon/releases/tag/v1.3.0),
this file was re-checked against `--suggest` / `homepage_repository`,
`asset_match`, and the offline suggestion and filename fixtures. Evidence-backed
GitHub-path polish from the Kubuntu and lab cases above (homepage `#fragment`
stripping, installed `+ds`/`+dfsg` tag comparison, read-only `--check-all`,
and Feishin/Moonfin-style likely filename hints) is already shipped. The
2026-11-15 public-release survey justified the narrow LocalSend `x86-64`/`arm-64`
and `gh`-style post-`linux` version peel filename fixes (v1.2.1) and the
documented packaging aliases `git-delta`→`delta`, `du-dust`→`dust`,
`fd-find`→`fd` (v1.3.0; low-tier evidence only, never auto-track). No further
safe GitHub-path product change remains without Dennis: query-string
homepages and `/releases` path stripping remain **decision-deferred** (no
observed package case; see [homepage URL normalize](../design/homepage-url-normalize.md));
`github-desktop` tag shapes and vendor-download providers stay design-only;
LocalSend `+64`, Helix leading-zero tags, undocumented aliases, and broader
arch aliases stay correctly refused. Confirmation, exact asset selection,
integrity≠authenticity, APT ownership gates, and isolation rules are unchanged.

## Public GitHub `.deb` survey (2026-11-15)

Read-only GitHub Releases API lookups plus temporary `dpkg-deb -f` inspection
of selected public assets (no host installs; digests are download integrity
only). Observation date: **2026-11-15 (UTC)**. These expand roadmap item 1
with realistic filename, package-identity, and `--check` comparison shapes
not already covered by Beacon/CloverEye/bat/fd/Feishin/Moonfin/github-desktop.

| Upstream | Latest tag observed | Selected `.deb` asset(s) | Internal `Package` / `Version` / `Architecture` | Filename `asset_match` (amd64 unless noted) | `--check` if installed matched that shape |
| --- | --- | --- | --- | --- | --- |
| [`localsend/localsend`](https://github.com/localsend/localsend/releases/tag/v1.18.2) | `v1.18.2` | `LocalSend-1.18.2-linux-x86-64.deb`, `LocalSend-1.18.2-linux-arm-64.deb` | `localsend` / `1.18.2+64` / `amd64` (x86-64 asset inspected) | After the narrow alias fix: **likely** for matching arch; before the fix, `x86-64` was misread as `x86`→i386 (`Not suggested`) and `arm-64` stayed unrecognized | Installed `1.18.2+64` vs `v1.18.2` → **unknown** (`+64` is not `+ds`/`+dfsg`; do not broaden repack ignoring). Plain `1.18.1` vs `v1.18.2` would compare |
| [`cli/cli`](https://github.com/cli/cli/releases/tag/v2.104.0) | `v2.104.0` | `gh_2.104.0_linux_amd64.deb` (also arm64/386/armv6) | `gh` / `2.104.0` / `amd64` | Underscore `name_VERSION_linux_ARCH`: **likely** after peeling version again post-`linux`; previously unverified. Package name is `gh`, not `cli` | Comparable (`2.100.0` vs `v2.104.0` → newer). Lab note still applies: homepage `cli.github.com` is not a direct repository URL |
| [`helix-editor/helix`](https://github.com/helix-editor/helix/releases/tag/25.07.1) | `25.07.1` | `helix_25.7.1-1_amd64.deb` | `helix` / `25.7.1-1` / `amd64` | **Likely** (`helix` + amd64) | Tag `25.07.1` has a leading-zero component → **unknown** even though the asset version is `25.7.1-1`. Correct refusal; no parser change |
| [`dandavison/delta`](https://github.com/dandavison/delta/releases/tag/0.20.1) | `0.20.1` (no `v`) | `git-delta_0.20.1_amd64.deb`; also `git-delta-musl_*` | `git-delta` / `0.20.1` / `amd64` | **Likely** only for package `git-delta`; `delta` and musl filenames stay **unverified**. `--suggest` may also search alias `delta` and rank it **Low** (never auto-track) | Tag without `v` still comparable (`0.19.0` vs `0.20.1` → newer) |
| [`bootandy/dust`](https://github.com/bootandy/dust/releases/tag/v1.2.7) | `v1.2.7` | `du-dust_1.2.7-1_amd64.deb` | `du-dust` / `1.2.7-1` / `amd64` | **Likely** for `du-dust`; package name `dust` is a **correct negative** (filename product token is `du-dust`). `--suggest` may search alias `dust` at **Low** tier only; reverse `dust`→`du-dust` stays non-evidence | `1.2.0-1` vs `v1.2.7` → newer upstream (revision ignored) |
| [`ClementTsang/bottom`](https://github.com/ClementTsang/bottom/releases/tag/0.15.0) | `0.15.0` | `bottom_0.15.0-1_amd64.deb` vs `bottom-musl_0.15.0-1_amd64.deb` | `bottom` / `0.15.0-1` / `amd64` (glibc asset) | glibc asset **likely**; musl filename **unverified** (same bat-class guard). Package/repo names already match for `--suggest` (no alias needed) | No-`v` tag comparable with numeric Debian revision |

Supporting positives already matching current heuristics (no new code needed;
recorded for breadth):

| Upstream | Tag | Asset note |
| --- | --- | --- |
| [`rclone/rclone`](https://github.com/rclone/rclone/releases/tag/v1.76.0) | `v1.76.0` | `rclone-v1.76.0-linux-amd64.deb` already **likely**; release ships `SHA256SUMS` (plus MD5/SHA1). `linux-386` stays unrecognized (no `386` arch alias — prefer false negative) |
| [`topgrade-rs/topgrade`](https://github.com/topgrade-rs/topgrade/releases/tag/v17.16.0) | `v17.16.0` | `topgrade_17.16.0_amd64.deb` **likely** for package `topgrade`; Kubuntu operator package `stopgrade` remains a distinct identity (filename does not fold to `stopgrade`) |
| [`BurntSushi/ripgrep`](https://github.com/BurntSushi/ripgrep/releases/tag/15.2.0) | `15.2.0` | `ripgrep_15.2.0-1_amd64.deb` → internal `ripgrep` / `15.2.0-1` / `amd64`; per-asset `.sha256` files, not a shared `SHA256SUMS` |
| [`ajeetdsouza/zoxide`](https://github.com/ajeetdsouza/zoxide/releases/tag/v0.10.0) | `v0.10.0` | Classic `name_ver-rev_arch.deb`; comparable with numeric revision |

Correct limitations reinforced by this survey (still **not** authorized work):

- Do **not** treat arbitrary `+` suffixes (LocalSend `+64`) like `+ds`/`+dfsg`.
- Do **not** strip leading zeros in release tags (Helix `25.07.1`) to force a compare.
- Do **not** implement `github-desktop` `release-`/`-build` parsers or vendor-download providers from these cases.
- Exact asset selection, integrity≠authenticity, and APT ownership gates unchanged.

Observed download digests (integrity only; not publisher authentication):

- `LocalSend-1.18.2-linux-x86-64.deb`: `cc42a4f3eacdcb25ec31f0016b1272acb003145ab30484db8965450e20c72cd2`
- `gh_2.104.0_linux_amd64.deb`: `f90d578cbc4c3b067dfc4a1a540cef41faef64eebfb280b548ab32455977a21f`
- `helix_25.7.1-1_amd64.deb`: `c9ff7ee3113f039c21c3ff31e8e2b71d1cc51a2c3e6c39face36e3cf25fe8788`
- `git-delta_0.20.1_amd64.deb`: `0683067a4cbbcc19b9fd2841253131d1b37ccfa724725098d811d4d0d9fcc25b`
- `du-dust_1.2.7-1_amd64.deb`: `84217d34c4ef92ced959781d16bda64344c2795fad735267378be1652d0a019f`
- `bottom_0.15.0-1_amd64.deb`: `02aabca9cd9dd41d3fbf3642e96b5a7b266027fd0ba9eb78a96e4c5eeabcd8c8`

Offline regressions for the LocalSend and `gh` filename shapes live in
`tests/filename_match_fixtures.py` / `tests/test_tracking.py`. Offline
`--suggest` regressions for the documented packaging aliases live in
`tests/test_suggestions.py`.

## Remaining live qualification sketches

Cases still useful to expand later. Sketches already exercised on Kubuntu or
in lab notes above are marked accordingly; they are not implementation
commitments and do not authorize new providers or automatic upstream
confirmation.

| Proposed case | Status | Guardrails |
| --- | --- | --- |
| Third-party installed local `.deb` with a direct GitHub homepage | **Exercised** on Kubuntu (Beacon workflow + several tracked apps) and lab `iputils-ping` | Temporary or explicit user state; no auto-confirm |
| Competing glibc vs musl or multi-arch `.deb` assets | **Exercised** in lab for `bat` musl vs glibc; earlier arm64 notes retained | Exact selection; reject identity/architecture mismatches |
| Upstream tag with prerelease or non-numeric Debian revision | **Exercised** via `github-desktop`, `spdx-licenses`, lab epoch/`ubuntu` | No new parser without unambiguous mapping + regression |
| Same upstream version, different Debian revision or rebuild | **Exercised** via Beacon `1.1.2-1` vs tag `v1.1.2` metadata | Tag match ≠ package identity or install approval |
| Vendor download-only updater (no GitHub release asset) | **Exercised** as correct negatives (`discord-ptb`; Steam-style evaluation); first-publisher gate closed negative in [vendor download](../design/vendor-download.md) | Stay GitHub-only; no provider implementation until a named publisher unlock is approved |
| Caprine-style same-version asset without `SHA256SUMS` | **Exercised** (Kubuntu current `2.61.0`; lab digest-only download) | Unsigned digests are not publisher authentication |
| Homepage fragment / non-repository marketing URL | **Exercised**; `#readme` fragment stripping covered by unit tests; `gh` → `cli.github.com` remains non-direct | Query strings, `/releases` paths, and marketing sites still unsupported (further normalize deferred); no auto-confirm |

For each new live case, record the observation date, package and architecture,
command results, and what was and was not verified. Use temporary Beacon state
and artifact directories so exploratory tracking does not alter normal user
associations unless the operator intentionally uses their real profile. Do not
copy private metadata into fixtures; retain only the minimal public or
synthetic inputs needed to reproduce the behavior.

Live inspection may download an explicitly selected public asset, but is not
permission to install third-party packages on a developer's host. The Kubuntu
installs above were the package owner's reviewed upgrades. Exercise
installation failure and transaction cases with locally built fixture packages
inside the existing isolated APT suite. Keep that evidence distinct from
real-project metadata inspection and from the declared distro matrix.
