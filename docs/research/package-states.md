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

### Installed, No Current Repository Origin

An installed package whose version appears only in `/var/lib/dpkg/status` may
be marked `[installed,local]` by APT. This is a useful unmanaged-package
candidate signal, but it does not prove the package is orphaned or establish
how it was installed. Its former repository may have been removed, or it may
have been installed from a local `.deb`.

This state is distinct from `rc` / `Config Remains`: an `rc` package is no
longer installed, even though dpkg retains its configuration-file record.
Current APT and dpkg metadata alone cannot reliably recover the historical
repository of an installed package.

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
