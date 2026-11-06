# Database Design

## Purpose

This document contains database design notes for Beacon.

No implementation decisions have been made yet.

---

## Proposed Entities

### Software

Stores discovered software.

Possible fields:

```text
Name
Version
Description
Homepage
Maintainer
```

---

### Source

Stores software origin information.

Possible fields:

```text
Type
Repository URL
Confidence
```

---

### Discovery Record

Stores discovery results.

Possible fields:

```text
State
Classification
Discovery Date
```

---

## Status

Research Phase

No schema has been finalized.

---

## Related Issues

- #4 Design local tracking database
