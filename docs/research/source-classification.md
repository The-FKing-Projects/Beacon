# Source Classification Research

## Purpose

Determine how Beacon classifies software origins.

---

## Proposed Categories

```text
Repository
PPA
Vendor Repository
Local .deb
Unknown
```

---

## Classification Rules

### Repository

Evidence:

```text
Repository URL present
```

Example:

```text
Steam
```

Result:

```text
Repository Managed
```

---

### PPA

Evidence:

```text
PPA URL present
```

Example:

```text
Floorp
```

Result:

```text
PPA Managed
```

---

### Local .deb Candidate

Evidence:

```text
Only /var/lib/dpkg/status visible
```

Examples:

```text
Discord PTB
CloverEye
```

Result:

```text
Local .deb Candidate
```

---

### Unknown

Evidence:

```text
Insufficient information
```

Result:

```text
Unknown
```

---

## Open Questions

- What differentiates a vendor repository from a PPA?
- What evidence is required before classifying a package as Local .deb?
- How should conflicting evidence be handled?

---

## Related Issues

- #11 Research source classification heuristics
