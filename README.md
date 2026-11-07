# Beacon

Beacon discovers software installed outside traditional package
repositories and helps users identify, track, and update software
from upstream sources.

## Current Features

- Package inspection
- Package version detection
- Package source detection
- System inventory scanning
- Repository inventory reporting
- Repository classification

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

## Roadmap

### v0.1.2

- Configuration-remains inventory (`--clean`)

### v0.1.3

- Local package detection (`--local`)
- Detect packages installed outside repository management

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
