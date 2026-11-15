# Non-GitHub vendor download support (design / evaluation)

## Status

**Decision recorded (2026-11-15): stay GitHub-only.** Beacon’s updater
remains GitHub Releases–only. No first non-GitHub “vendor download” publisher
clears the identity and authenticity bars documented below. This note is the
written decision gate for that call. It does **not** authorize implementation:
no CLI flags, download paths, schema, network code, or provider modules until
Dennis approves a *specific* future publisher that meets the unlock criteria.

Related evidence: Kubuntu and lab correct negatives for packages whose
homepage is a marketing site rather than a GitHub repository (see
[discovery test cases](../research/discovery-test-cases.md)).

## Decision (first-publisher gate)

**Product stance:** Prefer false negatives. Keep the current correct-negative
behavior for marketing homepages and non-GitHub download pages. Do not ship a
generic “paste a URL” or “follow the homepage” provider.

**Verdict:** No observed standalone publisher is ready as Beacon’s first
vendor-download provider. Discord PTB and Steam-style cases are counterexamples
that illustrate the gaps; they are not implementation targets.

### Why no first publisher clears the bars yet

A trackable vendor source requires all four identity elements in §1, plus an
integrity/authenticity story that matches [APT handoff](apt-handoff.md)
language (digest ≠ publisher authenticity). Against that bar:

| Observed case | Identity | Discovery | Integrity / authenticity | Gate outcome |
| --- | --- | --- | --- | --- |
| `discord-ptb` | Package name and `discord.com` homepage are **not** a confirmed publisher + pinned origin allowlist | No documented machine-readable version/asset listing suitable for a first provider; unbounded HTML scrape is a non-goal | At best same-origin checksums (integrity only); no independently pinned key story in evidence | Correct negative — Beacon must not invent a GitHub updater path, and must **not** add a vendor path |
| Steam-style (`steam-installer` / Steam site) | Homepage points at Valve/Steam, not a GitHub Releases `.deb` | Often overlaps **vendor APT repository** territory (`repo.steampowered.com`); when that source is configured, APT ownership already blocks Beacon takeover | Same integrity≠authenticity rules as GitHub; does not create a standalone vendor-download need | Prefer APT/PPA path when present; do not invent a parallel download provider for APT-managed packages |

Additional Discord-specific risks that would remain even after a draft identity
sketch: marketing host vs CDN host mismatch, PTB/stable/canary channel
confusion mapped to Debian package names, and login or geo-gated download URLs
(out of scope per §4).

Steam-style cases reinforce a sharper product split: **vendor APT repository**
(already classified; Beacon must not take over) versus **vendor direct `.deb`
download** (still unevaluated as a safe first provider). Conflating the two
would weaken the APT ownership gate.

### Answers to the prior open questions (gate items)

Written answers for the *absence* of a first publisher. When a future
publisher is proposed, re-answer (1)–(4) and (7)–(8) for that publisher
specifically before any code.

1. **Identity schema.** Not defined for any concrete vendor provider.
   Storage shape (`provider`, publisher id, origin allowlist JSON, rename/CDN
   migration) stays deferred. Until a publisher is approved, there is no
   schema migration and no `provider` value other than today’s GitHub path.
2. **Version discovery.** No per-publisher API, static latest-URL contract, or
   operator-supplied version field is documented for an observed standalone
   case. Generic HTML scrape remains rejected.
3. **Redirect allowlist.** No confirmed download-host / CDN-host list exists
   for an observed first publisher. Exact-host confirmation (not open suffix
   rules) remains the required direction when one is proposed.
4. **Authenticity bar.** Integrity-only may be acceptable **only** with
   stronger confirmation copy than GitHub’s familiar API-digest case, and only
   for a publisher that otherwise clears identity + discovery + redirect pins.
   No observed publisher reaches that combined bar today. A pinned signature
   with an independently trusted key would strengthen a future proposal but is
   not available in current evidence for Discord PTB or Steam-style downloads.
5. **Channel / channel packages.** Unresolved for Discord PTB/canary/stable;
   unresolved channel mapping is itself a reason to refuse Discord as first
   publisher.
6. **Architecture and filename hints.** Unchanged: exact selection only;
   heuristics remain hints. No vendor listing source is approved.
7. **Threat model copy.** Carry forward APT handoff wording: never describe a
   digest, TLS session, or same-origin checksum as “verified publisher.” Any
   future integrity-only vendor path must warn more explicitly than GitHub’s
   digest case and require fresh approval.
8. **Qualification.** No offline fixture publisher and no operator-observed
   live vendor-download success path is recorded, because no publisher is
   approved. Correct negatives (`discord-ptb`; Steam-style evaluation) remain
   the qualification evidence for *refusing* a provider.

**Gate result:** Implementation stays blocked. Completing this decision does
not move README roadmap item 5 to partial implementation.

### What would unlock a future publisher

Dennis (or a follow-up design PR he accepts) must name **one** concrete
publisher and supply written answers that satisfy all of:

1. **Publisher label** users confirm (not inferred from package name alone).
2. **Pinned HTTPS origin allowlist** for download hosts (and CDN aliases if
   distinct), with an explicit redirect policy (HTTPS only; refuse open
   redirects and hosts outside the list).
3. **Documented version/asset discovery** that is not unbounded HTML scraping
   (API, stable listing contract, or another operator-reviewed method).
4. **Channel mapping** when product channels exist (e.g. PTB vs stable), so
   Beacon cannot cross-upgrade Debian packages.
5. **Integrity / authenticity story** aligned with APT handoff: mismatch
   blocks; missing independent authenticity proceeds only after stronger
   confirmation copy and fresh approval; no “verified publisher” wording for
   digests or same-origin checksums.
6. **Qualification plan:** at least one offline fixture and one
   operator-observed live case before merging any provider code.
7. **Non-goals review:** still no silent install, no APT/PPA takeover, no
   arbitrary pasted URLs, no Flatpak/Snap/AppImage/`.rpm` in this track.

Until those land for a named publisher, agents must not add vendor provider
code, CLI surface, network download paths, or schema.

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
- No CLI flags, network download code, or schema migrations until Dennis
  approves a named publisher that meets the unlock criteria above.

## 5. Open questions (deferred until a named publisher)

Items (1)–(4) and (7)–(8) are answered for the *no first publisher* decision
in the Decision section. The following remain open **only** when proposing a
future concrete publisher; prefer false negatives over a vague provider:

1. **Identity schema** for that publisher (storage key, origin allowlist JSON,
   rename/CDN migration without silent retargeting).
2. **Version discovery** method for that publisher (API, static contract, or
   operator-reviewed alternative — not generic HTML scrape).
3. **Redirect allowlist** (exact hosts; who confirms CDN aliases).
4. **Authenticity bar** for that publisher (integrity-only + stronger copy vs
   pinned signature mandatory).
5. **Channel / channel packages** mapping to Debian names without
   cross-channel upgrades.
6. **Architecture and filename hints** listing source for exact selection.
7. **Threat model copy** operator-facing text aligned with
   [APT handoff](apt-handoff.md).
8. **Qualification** offline fixture + operator-observed live case before
   merging implementation.

**Implementation gate:** Do not start provider code until (1)–(4) and (7)–(8)
have written answers for a *specific* first publisher, reviewed against the
non-goals above, and Dennis has approved that publisher.

## 6. Evaluation examples (counterexamples, not implementation targets)

These are qualification-shaped examples from existing evidence. They
illustrate why the first-publisher gate stays closed; they are **not**
commitments to support these apps.

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
- **Decision impact:** fails the first-publisher gate on identity, discovery,
  redirects/CDN, and channel mapping; do not use as an implementation target.

### Steam-style vendor homepage (`steam-installer` / Steam site)

- Homepage evidence points at Valve/Steam’s site rather than a GitHub
  repository with `.deb` release assets.
- Useful as an evaluation reminder that “vendor download” and “vendor APT
  repository” are different: if a machine already has Steam’s APT source
  configured, Beacon must refuse takeover (existing APT ownership gate).
- A first provider should prefer cases that remain true standalone local
  `.deb` installs, not packages already served by a vendor repository.
- **Decision impact:** does not clear a standalone vendor-download identity;
  prefer existing APT classification and ownership rules.

## Appendix: candidate when approved

**None at this time.** No observed publisher clears enough of the unlock
criteria to list even as an optional “candidate when approved” with pinned
origins + integrity-only + stronger confirmation copy. Discord PTB and
Steam-style cases fail as documented above. Do not invent a speculative
publisher here; add an appendix entry only when a concrete product has written
answers for identity, discovery, redirects, authenticity copy, channels (if
any), and a qualification plan — still **no provider code** until Dennis
approves that entry and implementation is explicitly authorized.

## Relationship to the post-v1 roadmap

README item **“Other standalone `.deb` sources”** stays **Evaluation / not
started** (GitHub-only updater). This decision closes the *first-publisher*
gate with a negative: no provider yet. Expanding tag comparison, suggestions,
or filename hints on the GitHub path remains separate work.
