# Version comparison rules

Beacon uses two different version comparisons. Operators should know which
command uses which, and when `--check` prints
`Unknown: versions cannot be compared safely.`

This describes the **current** implementation in `tracking.compare_versions`
(used by `--check`) and `inspection.version_relation` (used by `--inspect` /
`--prepare`). It does not authorize broader tag formats beyond the narrow
exceptions below.

## `--check`: installed package vs release tag

`--check` compares the **installed Debian package version string** to the
**latest stable GitHub release tag**. It does **not** look at a selected
`.deb` asset's internal version. Asset selection and Debian-direction decisions
happen later with `--inspect` / `--prepare`.

Implementation: `src/tracking.py` (`VERSION_PATTERN`,
`DEBIAN_UPSTREAM_REPACK_SUFFIX`, `compare_versions`).

### What is comparable

Both sides must fit a narrow shape:

| Side | Accepted form |
| --- | --- |
| Release tag | Exactly three numeric components, optional leading `v`: `1.2.3` or `v1.2.3`. No leading zeros on a component except a lone `0`. No other prefixes/suffixes. |
| Installed version | The same three-component upstream form, optionally with a Debian repack marker `+ds`, `+dsN`, `+dfsg`, or `+dfsgN` on that upstream portion, **and/or** a single `-` plus a **purely numeric** Debian revision. Examples: `1.2.3`, `1.2.3-1`, `3.27.0+ds-1`, `1.2.3+dfsg2`. |

When a numeric Debian revision is present, Beacon compares **only** the
upstream triples (`1.2.3` vs the tag). It then appends that the installed
Debian revision was not compared. When a `+ds` / `+dfsg` (optional digits)
suffix was stripped from the installed upstream portion, Beacon appends that
that suffix was ignored for the comparison. Equal upstream triples print
`Upstream versions match.` when a revision or ignored repack suffix was
present, otherwise `Versions match.`

Examples that compare today:

| Installed | Tag | `--check` status (summary) |
| --- | --- | --- |
| `1.2.3` | `v1.2.4` | Newer upstream release available |
| `1.2.3` | `v1.2.3` | Versions match |
| `1.2.4` | `1.2.3` | Installed version is newer than the latest upstream release |
| `0.8.1-1` | `v0.8.2` | Newer upstream…; revision `1` not compared |
| `1.2.3-1` | `v1.2.3` | Upstream versions match…; revision `1` not compared |
| `3.27.0+ds-1` | `v3.29.0` | Newer upstream…; revision `1` not compared; `+ds` ignored |
| `1.2.3+dfsg2` | `v1.2.3` | Upstream versions match…; `+dfsg2` ignored |

### What stays unknown

If either side fails the rules above, `--check` reports
`Unknown: versions cannot be compared safely.` and does **not** guess.

| Kind | Examples | Why unknown |
| --- | --- | --- |
| Epoch on the installed version | `1:1.2.3-1`, `3:20240117-1ubuntu0.1` | Epoch/`:` is outside the upstream pattern |
| Distro or vendor revision text | `1.2.3-1ubuntu1`, `0.25.0-5ubuntu1`, `1.2.3-1~deb12u1`, `1.2.3-1+b1`, `3.27.0+ds-1ubuntu1` | Revision after the first `-` is not purely numeric |
| Other `+` suffixes on upstream | `1.2.3+git20200101`, `1.2.3+other-1` | Only lowercase `+ds` / `+dfsg` with optional digits are ignored |
| Build-suffixed installed versions | `3.7.1-build.50` (Kubuntu `github-desktop`) | Revision `build.50` is not purely numeric |
| Non-standard release tags | `release-3.4.13-linux1` (Kubuntu `github-desktop`), `20250605`, `v1.2.4-beta`, `v1.2.4-1` | Tag is not exactly optional `v` + three numeric components; no safe prefix/suffix mapping |
| Wrong component count | Installed `1.2`, tag `v1.2.3` | Must be exactly three components |
| Leading zeros on a component | `01.2.3-1` | Components use `(0\|[1-9][0-9]*)` |
| Extra hyphens in the revision | `1.2.3-1-2`, empty revision `1.2.3-` | Revision must be one run of digits |
| Prerelease-style installed strings | `1.2.3~rc1-1`, `1.2.3-beta-1` | Upstream or revision portion fails the pattern |

**Unknown is expected** for those shapes. It is not a crash and not permission
to invent a comparison. Use `--inspect` on an **exact** selected asset when
you need the asset's full Debian version direction.

### What “match” from `--check` does not mean

- Equal upstream triples do **not** prove the packages are identical, equally
  current, or safe to install.
- `--check` never compares the Debian revision, ignored `+ds`/`+dfsg` markers,
  or the selected asset's package version as install approval.
- Filename “likely” hints are separate from version comparison.

## `--inspect` / `--prepare`: full Debian version of the selected asset

After the user names an exact `.deb` asset, Beacon downloads it (inspect) or
retains it (prepare) and compares **installed Debian version** to the
**asset's internal Debian version** with `dpkg --compare-versions`
(`inspection.version_relation`). That path can report newer / same / older
for ordinary Debian version strings that `--check` would leave unknown.

Gates that still apply (unchanged by this document):

- Exact package-name match is required for both commands.
- Architecture: `--inspect` accepts the installed architecture **or** `all`;
  `--prepare` requires an **exact** architecture match and therefore blocks an
  `all` asset when the installation is architecture-specific.
- Downgrades are blocked at prepare/install; same-version still needs fresh
  approval.
- Digests and unsigned `SHA256SUMS` entries are integrity evidence, not
  publisher authenticity.

## Kubuntu v1.1.2 operator evidence

From the undated Kubuntu 26.04 operator-reported summary (not a dated
transcript):

| Package | Installed vs tag (as reported) | `--check` outcome |
| --- | --- | --- |
| `github-desktop` | `3.7.1-build.50` vs `release-3.4.13-linux1` | **Unknown** (build revision + non-standard tag; no safe mapping) |
| `spdx-licenses` | `3.27.0+ds-1` vs `v3.29.0` | **Comparable** after ignoring `+ds` (still no `.deb` assets upstream, so Beacon cannot prepare/install from GitHub) |
| Successful upgrades such as `clover-eye` / `moonfin` | Ordinary numeric triples (with or without numeric revisions) | Comparable when both sides fit the rules above |

Lab note: installed `3:20240117-1ubuntu0.1` vs tag `20250605` remains unknown
(epoch + `ubuntu` revision + non-`X.Y.Z` tag).

## Follow-up (not in this change)

Further tag or revision support remains backlog: add formats only with
unambiguous mappings and offline regressions. `release-…-linux*` tags,
`-build.*` revisions, epochs, and `ubuntu` revisions stay unknown until then.
Rely on `--inspect` for selected-asset Debian direction.

Related: [discovery test cases](../research/discovery-test-cases.md),
[APT handoff](apt-handoff.md).
