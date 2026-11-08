# Source Classification Research

## Purpose

Define how Beacon should describe the available evidence about an installed
Debian package's source without overstating what APT and dpkg can prove.

## Evidence Model

`apt-cache policy <package>` reports installed and candidate versions and the
versions available in APT's current package cache. Beacon should compare the
installed version when one exists, otherwise the candidate version. A
repository that offers a different version is not evidence for the selected
version's source.

The policy output is current-cache evidence, not an installation receipt.
APT's documentation notes that when the same version is available from more
than one configured source, source ordering can determine which copy is
downloaded. The installed package database does not record a definitive
repository URL. Therefore, a matching policy URL supports “this exact version
is available from this source,” not proof that this repository supplied the
installed artifact.

## Classification Rules

| Evidence for the selected version | Beacon source | Current score | Interpretation |
| --- | --- | ---: | --- |
| URL host matches a PPA heuristic | PPA | 90 | A PPA-like host supplies the exact version in current APT metadata. |
| URL host is `ubuntu.com` or a subdomain | Ubuntu Repository | 90 | An Ubuntu-domain repository supplies the exact version. |
| URL host is `debian.org` or a subdomain | Debian Repository | 90 | A Debian-domain repository supplies the exact version. |
| Other repository URL | Vendor Repository | 90 | A non-Ubuntu, non-Debian, non-PPA repository supplies the exact version. |
| Exact installed version has different repository types | Multiple Sources | 45 | Conflicting source categories exist; Beacon does not select one. |
| No repository URL; APT marks installed version `[installed,local]` | Local .deb Candidate | 65 | The installed version is not available in current configured sources. |
| No repository URL; installed version appears in dpkg status only | Local .deb Candidate | 55 | dpkg records the installed version, but APT has no repository origin for it. |
| No repository or local-install signal | Unknown | 0 | Evidence is insufficient to classify the source. |

The scores are evidence grades, not probabilities. “Candidate” is intentional:
APT cannot establish that an unavailable installed version came from a
downloaded `.deb` rather than a repository that has since been removed, a
repository version that has since changed, or another installation route.

## Repository Host Heuristics

- Hosts beginning with `ppa.` are treated as PPA-like, including the observed
  `ppa.floorp.app` host. This is a naming heuristic, not cryptographic
  verification of a Launchpad PPA.
- Launchpad domains (`launchpad.net` and its subdomains, including
  `launchpadcontent.net`) are treated as PPA-related.
- Ubuntu and Debian matches require the exact domain or a dot-delimited
  subdomain. Text that merely contains `ubuntu.com` or `debian.org` is not
  enough.
- Other repository hosts are classified as Vendor Repository. This category
  includes non-vendor mirrors and private repositories because APT metadata
  alone does not establish who operates a host.

Repository configuration, package `Homepage` and `Maintainer` fields, and
binary names can be useful corroborating signals, but none proves the source
of an already installed artifact. They should be retained separately from the
version-origin evidence rather than silently used to override it.

## Conflicts and Missing Evidence

- When the selected version is listed under multiple repository types, report
  `Multiple Sources`, list the observed types, and lower confidence. Do not
  choose the host with the highest priority or most familiar name as the
  package's origin.
- Multiple URLs of the same type can be shown as evidence, but do not prove
  which repository supplied the package.
- If a repository was removed or its package index no longer contains the
  installed version, its historical origin cannot be recovered from
  `apt-cache policy` alone. Report the local-candidate signal or `Unknown`;
  do not infer a vendor from stale package metadata.
- APT pin priorities affect candidate selection, not historical package
  provenance. A candidate from a repository must not be used to attribute a
  different installed version.
- A failed or unavailable APT query is not equivalent to an empty cache. It
  should be surfaced as an inspection error, not converted into `Unknown`.

## Observed Validation Cases

The deterministic cases in
[`discovery-test-cases.md`](discovery-test-cases.md) exercise:

- `bash`: installed version listed in an Ubuntu repository.
- `steam`: candidate version in Steam's repository while an older version is
  in Ubuntu; source follows the candidate version.
- `floorp`: installed version listed at `ppa.floorp.app`.
- `clover-eye` and `discord-ptb`: installed versions marked local.
- A package with same-version origins from multiple source types.
- No package origin evidence.

Edge and Brave had no APT policy records on the inspected machine, so no
positive source result is asserted for them. The host checks are application
heuristics and should be expanded with fixtures when new repository families
are observed.

## References

- [`apt-cache(8)`](https://manpages.debian.org/bookworm/apt/apt-cache.8.en.html):
  `policy` reports source priorities and helps debug APT version selection.
- [`apt_preferences(5)`](https://manpages.debian.org/bookworm/apt/apt_preferences.5.en.html):
  describes version priorities and source ordering when identical versions
  are available from multiple sources.
- [Beacon confidence scoring design](../design/confidence-scoring.md)
- [Beacon discovery test cases](discovery-test-cases.md)

## Related Issues

- #11 Research source classification heuristics
- #8 Design confidence scoring system
