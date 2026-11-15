# Non-GitHub vendor download support (design / evaluation)

## Status

**Evaluation only — not started.** Beacon’s updater remains GitHub-only.
This note defines what a first non-GitHub “vendor download” provider would
need before any code, CLI flags, network download paths, or schema changes.
It does not authorize implementation.

Related evidence: Kubuntu and lab correct negatives for packages whose
homepage is a marketing site rather than a GitHub repository (see
[discovery test cases](../research/discovery-test-cases.md)).

## Problem

Some standalone `.deb` installs are not covered by a configured APT
repository or PPA, and also have no usable GitHub Releases updater path.
Their built-in checkers often open a vendor download page and leave install
to the user. Beacon already detects those packages as local candidates and
correctly refuses to invent a GitHub association. A future provider might
help only if source identity and verification are defined as carefully as
the GitHub path.

## 1. What counts as a vendor-download source identity

A vendor-download *source* is a user-confirmed identity Beacon would track —
analogous to today’s confirmed `owner/name` GitHub repository — not an
inferred marketing homepage.

### Candidate identity elements

| Element | Role | Constraint |
| --- | --- | --- |
| Publisher / product label | Human-readable identity shown at confirmation | Must be explicit text the user affirms; never inferred solely from package name |
| Canonical HTTPS origin | Stable origin for allowed download URLs | Exact host (and optional path prefix) allowlist; no free-form “any HTTPS” |
| Version discovery endpoint | How Beacon learns that a newer `.deb` exists | Must be documented per publisher; scraping unbounded HTML is out of scope for a first provider |
| Asset URL template or listing | Exact `.deb` locations | User still selects an exact filename/URL; Beacon never auto-picks |
| Redirect policy | How CDN / marketing redirects are handled | Follow only HTTPS redirects that stay within the confirmed origin allowlist (or an explicitly confirmed CDN host list); refuse open redirects and host changes outside that list |
| Homepage (optional evidence) | Package metadata or operator hint | A homepage such as `https://discord.com` is **evidence for evaluation**, not a trackable source by itself |

### What is *not* source identity

- Package name similarity to a brand (`discord-ptb` ↔ Discord)
- Weak GitHub search hits on a vendor product name
- An unsigned checksum file co-hosted with the `.deb`
- APT/`Origin` fields from unrelated repositories
- A one-off download URL pasted without a confirmed publisher + origin policy

### Working definition (decision gate)

A trackable vendor-download source is at least:

1. A **publisher label** the user confirms,
2. A **pinned HTTPS origin allowlist** (download host(s) + optional path prefix),
3. A **documented version/asset discovery method** for that publisher,
4. Stored separately from GitHub `provider="github"` associations so the two
   cannot be confused.

Until those four are specified for a concrete publisher, Beacon must keep
the current correct-negative behavior.

## 2. Integrity versus authenticity

Beacon already separates these for GitHub (API digest and optional
`SHA256SUMS` are integrity evidence only). A vendor path must keep the same
language and gates. See [APT handoff](apt-handoff.md).

| Mechanism | What it can show | What it must **not** claim |
| --- | --- | --- |
| SHA-256 (or similar) of downloaded bytes vs a published digest | Bytes match a stated digest (transport/storage integrity) | Publisher authenticity |
| Checksum file from the **same** vendor origin as the `.deb` | Consistency between two files from one origin | Independent authentication of that origin |
| Detached signature over the `.deb` or manifest | Authenticity **if** the verifying key is independently trusted | Anything when the key was fetched from the same unauthenticated download page |
| Pinned publisher key / certificate fingerprint (operator- or Beacon-configured) | Stronger authenticity relative to that pin | Universal trust without a documented trust, rotation, and revocation story |
| TLS to the download host | Confidentiality/integrity of the HTTP session to that host | That the host is the legitimate publisher |

### Required product rules (carry over from GitHub)

- Never describe a digest or unsigned checksum match as “verified publisher.”
- Mismatch or malformed digest evidence **blocks** prepare/install.
- Missing independent authenticity evidence may proceed only after a clear
  warning and **fresh** user approval — never silently.
- A first vendor provider should prefer publishers that offer either
  (a) a pinned key/signature story or (b) an explicit operator-accepted
  integrity-only path with stronger confirmation copy than GitHub’s
  familiar API digest case.

## 3. Mapping existing safety gates

Vendor downloads must reuse the GitHub workflow’s review boundaries, not
bypass them with “direct URL convenience.”

| Gate | GitHub today | Vendor-download mapping |
| --- | --- | --- |
| Source confirmation | User confirms `owner/name` (and optional repo ID) before tracking | User confirms publisher label + origin allowlist + discovery method; no auto-track from homepage alone |
| Exact asset selection | Exact release asset filename; no auto-select from “likely” hints | Exact HTTPS URL or exact filename from a listed set; filename heuristics remain hints only |
| Inspect | Download selected asset; check internal name/arch/version; digests | Same package-metadata checks; digests from vendor manifest/API if any; redirect must stay in allowlist |
| Prepare | Retain artifact + identity + digests under user storage | Same retention shape with `provider` ≠ `github`; revalidation must include origin allowlist |
| Install / APT handoff | Fresh transaction preview; `--no-remove`; block removals/downgrades; APT ownership block; post-install verify | **Identical** APT policy; vendor origin must not weaken handoff |
| Remove / downgrade blocks | Block removing other packages; block older-than-installed assets | Unchanged |
| APT/PPA ownership | Refuse packages managed by configured repositories | Unchanged — vendor provider must not take over APT/PPA packages |

Discovery (`--suggest`) stays out of scope for inventing vendor sources from
name search. Any future “suggest vendor publisher” flow would need its own
design and still require explicit confirmation.

## 4. Non-goals for a first provider

- No silent or unattended install; no auto-prepare; no cron/daemon updater.
- No taking over packages that APT/PPA already manage.
- No scraping arbitrary marketing HTML as a generic discovery engine.
- No accepting arbitrary user-pasted URLs without a confirmed publisher
  identity and origin policy.
- No treating CDN cookies, login walls, or DRM-ish download gates as in-scope.
- No claiming digests, TLS, or same-origin checksums prove authenticity.
- No Flatpak/Snap/AppImage/vendor `.rpm` support in this track.
- No CLI flags, network download code, or schema migrations in this
  evaluation — documentation only until the decision gate passes.

## 5. Open questions / decision gate (before any code)

Resolve these explicitly; prefer false negatives over a vague provider:

1. **Identity schema.** How is a vendor source keyed in storage
   (`provider`, publisher id, origin allowlist JSON)? How do renames and CDN
   host changes migrate without silent retargeting?
2. **Version discovery.** Per-publisher API, static latest-URL with
   Content-Disposition, or operator-supplied version field? Generic HTML
   scrape is rejected for v1-of-vendor.
3. **Redirect allowlist.** Exact hosts only, or suffix rules? Who confirms
   CDN aliases when the marketing site and download CDN differ?
4. **Authenticity bar.** Is integrity-only + warning acceptable for a first
   publisher, or is a pinned signature mandatory?
5. **Channel / channel packages.** How do PTB/canary/stable product channels
   map to Debian package names without cross-channel upgrades?
6. **Architecture and filename hints.** Reuse GitHub `asset_match` ideas only
   as hints; what is the listing source for exact selection?
7. **Threat model copy.** Operator-facing text that never overclaims digests;
   alignment with [APT handoff](apt-handoff.md) wording.
8. **Qualification.** At least one offline fixture publisher and one
   operator-observed live case recorded before merging implementation.

**Gate:** Do not start implementation until (1)–(4) and (7)–(8) have written
answers for a *specific* first publisher, reviewed against the non-goals
above.

## 6. Evaluation examples (not implementation targets)

These are qualification-shaped examples from existing evidence. They
illustrate why a design is needed; they are **not** commitments to support
these apps.

### `discord-ptb` (correct negative today)

- Installed as a local `.deb` candidate; homepage points at `discord.com`.
- GitHub name search is weak / non-authoritative; Beacon correctly does not
  invent a Releases updater path.
- A future vendor source would need a confirmed Discord/publisher identity,
  HTTPS download origin(s) for PTB `.deb` assets, a channel-aware version
  discovery method, and an integrity/authenticity story that does not treat
  a co-hosted checksum as proof of publisher authenticity.
- Risk highlights: marketing-site vs CDN host mismatch, PTB vs stable channel
  confusion, and login or geo-gated download URLs.

### Steam-style vendor homepage (`steam-installer` / Steam site)

- Homepage evidence points at Valve/Steam’s site rather than a GitHub
  repository with `.deb` release assets.
- Useful as an evaluation reminder that “vendor download” and “vendor APT
  repository” are different: if a machine already has Steam’s APT source
  configured, Beacon must refuse takeover (existing APT ownership gate).
- A first provider should prefer cases that remain true standalone local
  `.deb` installs, not packages already served by a vendor repository.

## Relationship to the post-v1 roadmap

README item **“Other standalone `.deb` sources”** stays **Not started /
evaluation**. Completing this design note does not move that item to
partial implementation. Expanding tag comparison, suggestions, or filename
hints on the GitHub path remains separate work.
