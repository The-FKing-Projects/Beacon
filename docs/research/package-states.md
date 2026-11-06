# Package States Research

## Purpose

This document tracks package states observed during Beacon research.

Package state detection is one of the first steps performed by the Discovery Engine.

---

## Observed States

### Installed

Example:

```text
ii steam-launcher
```

Meaning:

```text
Package is installed.
```

---

### Removed, Configuration Remains

Example:

```text
rc steam-installer
```

Meaning:

```text
Package removed.
Configuration files remain.
```

---

## dpkg Status

Example:

```text
Status: install ok installed
```

Current interpretation:

```text
Installed
```

---

## Proposed Beacon States

```text
Installed
Removed
Config Remains
Unknown
```

---

## Open Questions

- Which dpkg states exist beyond ii and rc?
- Should Beacon expose raw dpkg states?
- Should Beacon simplify multiple package manager states into common Beacon states?

---

## Related Issues

- #6 Investigate package state detection
- #7 Define package installation states
