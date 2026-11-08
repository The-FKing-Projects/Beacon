# Beacon

Beacon discovers software installed outside traditional package
repositories and helps users identify, track, and update software
from upstream sources.

## Current Features

- Package inspection
- Package version detection
- Package source detection with confidence evidence
- System inventory scanning (`--scan`)
- Repository inventory (`--repos`)
- Configuration-remains inventory (`--clean`)
- Local package inventory (`--local`)
- Automated SemVer tags and GitHub Releases for qualifying merged pull requests

## Goals

- Discover unmanaged software
- Identify upstream repositories
- Track releases
- Integrate with existing update workflows

## Non-Goals

- Replacing APT
- Replacing Flatpak
- Replacing Topgrade
- Creating another Linux package manager

## Releases

Merged `feat:` pull requests trigger a minor release; `fix:` and `perf:`
trigger patch releases. A `!` marker or `BREAKING CHANGE:` footer triggers a
major release. Documentation, tests, and other non-feature changes do not
release by default. See [automated release details](docs/research/release-automation.md)
for the required repository settings.

## Roadmap

### v0.1.2

- Configuration-remains inventory (`--clean`)

### v0.1.3

- Refine provenance confidence scoring with real-world package test cases

### v0.2

- System audit engine (`--audit`)
- Repository health checks

### v0.3

- GitHub release tracking
- Upstream version monitoring

### v0.4

- Application inventory management
- Mixed source tracking (APT, GitHub, local .deb)

### v1.0

- Topgrade integration
- Obtainium-style application tracking
