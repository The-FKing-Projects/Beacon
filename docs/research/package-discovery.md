# Package Discovery Research

## Purpose

This document captures research related to software discovery on Debian and Ubuntu systems.

The goal is to determine how Beacon can identify installed software, determine its state, and classify its source.

---

## Research Goals

Beacon should answer:

1. Is the software installed?
2. Was the software removed?
3. Where did the software come from?
4. Can the software be updated automatically?
5. How confident is Beacon in its conclusions?

---

## Findings

### apt-cache policy

Observed behavior:

Repository URL present:

```text
Steam
→ http://repo.steampowered.com/steam
```

Classification:

```text
Repository Managed
```

---

PPA URL present:

```text
Floorp
→ https://ppa.floorp.app/amd64
```

Classification:

```text
PPA Managed
```

---

Only dpkg status present:

```text
100 /var/lib/dpkg/status
```

Examples:

```text
Discord PTB
CloverEye
```

Classification:

```text
Local .deb Candidate
```

---

### apt history

Searches performed:

```bash
grep "steam-launcher" /var/log/apt/history.log
grep "discord-ptb" /var/log/apt/history.log
grep "clover-eye" /var/log/apt/history.log
```

Result:

```text
No matches found.
```

Current conclusion:

APT history should be considered supplementary evidence rather than a primary source of package origin information.

---

## Open Questions

- Can Beacon reliably distinguish local .deb files from all other unmanaged software?
- Can multiple repositories provide the same package?
- Can package origin be determined after repositories are removed?
- What information survives package removal?

---

## Related Issues

- #2 Research package discovery methods on Debian and Ubuntu
- #6 Investigate package state detection
- #11 Research source classification heuristics

## Additional Findings

### Ubuntu Repository Packages

Examples:

```text
git
firefox
vlc
```

Repository URLs observed:

```text
http://us.archive.ubuntu.com/ubuntu
http://security.ubuntu.com/ubuntu
```

Classification:

```text
Repository Managed
```

Confidence:

```text
High
```

---

### Local .deb Candidates

Examples:

```text
discord-ptb
clover-eye
```

Observed pattern:

```text
Only /var/lib/dpkg/status present
```

Classification:

```text
Local .deb Candidate
```

Confidence:

```text
Medium-High
```
