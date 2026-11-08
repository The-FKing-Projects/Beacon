# Beacon

Beacon aims to help keep standalone Debian packages up to date when they have
no configured repository or built-in updater. It investigates where an
installed package might have come from, helps users identify its upstream
project, and aims to track upstream releases.

The initial focus is Debian and Ubuntu. Beacon is at an early stage: discovery
and source classification work today, while upstream matching, persistent
tracking, release checks, and update preparation are not implemented yet.

## Current Features

- Package inspection
- Package version detection
- Package source detection with confidence evidence
- System inventory scanning (`--scan`)
- Repository inventory (`--repos`)
- Configuration-remains inventory (`--clean`)
- Local package inventory (`--local`)
- Automated SemVer tags and GitHub Releases for qualifying merged pull requests

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
designed. Beacon should surface ambiguity instead of guessing.

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

- Implement upstream matching and explicit confirmation for standalone package
  candidates.
- Implement local tracking and release comparison for one supported upstream.
- Validate the end-to-end workflow against a real standalone `.deb`.
- Design safe update preparation and an APT handoff after tracking works.
