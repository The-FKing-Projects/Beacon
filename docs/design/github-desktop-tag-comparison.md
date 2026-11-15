# GitHub Desktop–style tag comparison (design only)

## Status

**Decision recorded (2026-11-15): keep `--check` / `--check-all` unknown** for
GitHub Desktop–style shapes. No publisher-scoped parser profile is approved.
`--check` continues under today’s narrow `compare_versions` rules (optional
`v` + three numeric components; installed optional `+ds`/`+dfsg` and numeric
Debian revision). Operators who need Debian-direction answers use `--inspect`
on an exact selected `.deb`. This note is documentation only — **no parser
code**.

Canonical current behavior:
[version comparison](version-comparison.md).

## Decision (2026-11-15)

**Product stance:** Prefer false negatives. Unknown is the correct product
answer for `3.7.1-build.50` vs `release-3.4.13-linux1` and for the same
token family globally.

**Verdict:** Stay unknown. Do **not** ship a `shiftkey/desktop` (or other)
publisher-scoped profile in this change, and do **not** expand global
`release-` / `-build` parsing. Rely on `--inspect` / `--prepare` for asset
Debian versions via `dpkg --compare-versions`.

### Why the preferred default wins

The decision gate below is **not** fully met for any concrete publisher:

| Gate item | Status for a hypothetical `shiftkey/desktop` profile |
| --- | --- |
| Concrete publisher scope | Partially sketched only — not approved |
| Bidirectional tag ↔ installed mapping | Incomplete; schemes disagree across packaging channels |
| Counterexamples that never lie | Documented below; they **block** a safe profile today |
| Operator copy / integrity≠authenticity | Unchanged; not a reason to expand `--check` |
| Offline fixtures for positive cases | **Not ready** — only unknown/sentinel fixtures exist |
| No CLI/schema/APT-gate hitchhikers | N/A while staying docs-only |

Because several items are missing or fail, this PR ratifies **docs-only
stay-unknown**. Parser expansion remains blocked until a future review
re-answers the gate with dated samples *and* offline fixtures.

### Dated samples used for this call (2026-11-15)

Fetched from public GitHub APIs / release assets on **2026-11-15** (agent
qualification; not an operator desktop transcript):

| Sample | Evidence |
| --- | --- |
| `shiftkey/desktop` latest stable tag | `release-3.4.13-linux1` (`published_at` `2025-02-09T18:00:21Z`) |
| Same-release amd64 asset | `GitHubDesktop-linux-amd64-3.4.13-linux1.deb` |
| Internal Debian version of that asset | `Package: github-desktop` / `Version: 3.4.13-linux1` / `Architecture: amd64` (`dpkg-deb -f`) |
| Nearby stable tags | `release-3.4.12-linux1` … `release-3.4.9-linux1` (same `release-X.Y.Z-linuxN` shape; several published `2025-02-09`) |
| Channel / prerelease tags in history | e.g. `release-3.4.4-linuxbeta2` (prerelease); `release-3.4.0-linux2` alongside `release-3.4.0-linux1` |
| Bare `release-X.Y.Z` tags also exist | e.g. `release-2.9.10` in tag history — not every historical tag is `-linuxN` |
| Upstream `desktop/desktop` (no Linux `.deb`s in sampled releases) | Tags such as `release-3.6.10` / `release-3.6.9` (2026-10/11); empty `.deb` asset lists on sampled releases — different product channel than shiftkey Linux packaging |

### Counterexamples (why a profile would lie or stay incomplete)

1. **Kubuntu sentinel (scheme mismatch).** Operator-reported installed
   `3.7.1-build.50` vs tracked tag `release-3.4.13-linux1` (undated Kubuntu
   26.04 v1.1.2 summary). Naive strip of both sides yields `3.7.1` vs
   `3.4.13` → false “installed newer.” The installed `-build.50` shape is
   **not** the Debian version shiftkey ships in its `.deb` (`3.4.13-linux1`).
   A tag-only `shiftkey/desktop` strip would still invent a comparison across
   unrelated packaging schemes whenever that installed string is tracked
   against that repository.
2. **Even pure shiftkey pairs stay outside today’s parser.** Installed
   `3.4.13-linux1` vs tag `release-3.4.13-linux1` would require stripping
   `release-` **and** treating `-linuxN` as a comparable revision/channel on
   both sides. That is a new bidirectional rule, not a cosmetic prefix drop.
   Without fixtures proving `dpkg` direction on same-release assets and
   refusing betas / `linux2` vs `linux1` confusion, the gate fails.
3. **`linuxN` is not a no-op.** History includes `…-linux1` and `…-linux2`
   for the same `X.Y.Z`, plus `…-linuxbetaN`. Mapping that ignores the suffix
   can hide channel rebuilds or compare a stable install to a beta tag shape.
4. **Global `release-` / `-build` regex remains rejected.** Other projects use
   those tokens differently; Beacon already guards `release-3.29.0` as unknown
   in offline tests. No global expansion.
5. **APT ownership overlap.** shiftkey documents APT feeds generated from the
   same releases. When those feeds own `github-desktop`, Beacon must refuse
   takeover — another reason not to paper over `--check` noise with a
   repository profile that operators might treat as update approval.

**Gate result:** Keep these shapes **unknown by default** under
`tracking.compare_versions` until a future, Dennis-reviewed profile supplies
publisher scope, bidirectional mapping, counterexample-safe behavior, operator
copy, and offline fixtures — still separate from any CLI/APT-gate change.
(Unknown is the standing product answer; the reopening path is that gate, not
a permanent ban on ever reconsidering a scoped profile.)

**What would reopen a publisher profile:** complete every Decision gate item
below for one named repository id, with new dated tag/asset/Debian-version
samples that include the installed-side scheme actually used by that
publisher’s `.deb`s, plus offline regressions (including retention of the
Kubuntu sentinel as `Unknown`). Until then, agents must not add parser code.

## Observed patterns (qualification)

### Kubuntu `github-desktop` (operator-reported)

| Side | Observed string | Why today’s parser refuses |
| --- | --- | --- |
| Installed Debian version | `3.7.1-build.50` | After the first `-`, revision `build.50` is not purely numeric |
| Latest stable release tag | `release-3.4.13-linux1` | Not optional `v` + `X.Y.Z`; has `release-` prefix and `-linux1` suffix |

Outcome: `Unknown: versions cannot be compared safely.` That is **correct**
under current rules. The two strings are not even the same packaging scheme:
the installed side looks like an Electron/desktop *build* revision, while the
tag looks like a *channel/platform* release label. Numerically, `3.7.1` vs
`3.4.13` would also be a misleading “installed newer” story if Beacon stripped
tokens naively — the operator may be on a different packaging channel than
the tag Beacon fetched.

### Nearby unknown shapes (same backlog family)

These are not identical to GitHub Desktop, but they fail for related reasons
and must stay in the “prefer unknown” bucket until separately justified:

| Example | Source | Issue |
| --- | --- | --- |
| Installed `3:20240117-1ubuntu0.1` vs tag `20250605` | Lab `iputils-ping` | Epoch, `ubuntu` revision, date-shaped tag |
| Tag `v1.2.4-beta` / `v1.2.4-1` | Fixtures / backlog | Prerelease or Debian-looking tag suffix |
| Installed `1.2.3-1ubuntu1` | Distro revisions | Non-numeric revision text |
| Tag `release-3.29.0` (hypothetical strip of only `release-`) | Regression guard in tests | Prefix alone is not a safe general rule |

`spdx-licenses` (`3.27.0+ds-1` vs `v3.29.0`) is **out of this note’s
implementation scope**: `+ds`/`+dfsg` ignoring is already shipped. Do not
conflate that narrow exception with GitHub Desktop–style tokens.

## Candidate parse strategies (and why each is or isn’t safe)

### A. Strip a fixed `release-` prefix and optional `-linuxN` suffix from tags

**Idea:** Map `release-3.4.13-linux1` → `3.4.13`, then compare as today.

| Pros | Cons / risk |
| --- | --- |
| Matches one observed tag shape | `-linux1` may encode platform/channel, not a no-op cosmetic |
| Simple regex | Other projects use `release-` for prereleases, marketing labels, or non-semver schemes |
| | Without a matching installed-side rule, Kubuntu still stays unknown (`-build.50`) |

**Verdict:** Unsafe as a **global** tag rule. Might be reconsidered only as a
**publisher-specific** mapping with offline fixtures for that repository’s
tag history — still blocked until the installed side is understood.

### B. Treat `-build.N` (or `-buildN`) as an ignorable Debian revision

**Idea:** For installed `3.7.1-build.50`, compare upstream `3.7.1` only
(analogous to ignoring numeric `-1`).

| Pros | Cons / risk |
| --- | --- |
| Mirrors “revision not compared” messaging | `build.50` is often an app build counter, not a Debian revision; ignoring it can hide real differences between builds |
| Would unblock comparison when the tag is plain `v3.7.1` | Against `release-3.4.13-linux1`, stripping both sides could report “installed newer” even when the user cannot or should not “downgrade” via that tag’s assets |
| | Collides with other `-build*` or vendor strings that are not equivalent |

**Verdict:** Not safe as a global revision exception. A build suffix is not
the same class of evidence as a numeric Debian revision or `+ds`/`+dfsg`.

### C. Extract the first `X.Y.Z` substring from either side

**Idea:** Regex-find three numeric components anywhere in the string.

| Pros | Cons / risk |
| --- | --- |
| Maximizes “comparable” rate | High false-positive rate (`v1.2.3-beta.4`, dates, `...-linux1` digit noise, epochs) |
| | Silently discards semantics operators need to see as unknown |

**Verdict:** Rejected. Prefer false negatives.

### D. Publisher-specific profile (e.g. only `shiftkey/desktop` / GitHub Desktop packaging)

**Idea:** When the tracked repository identity matches a documented profile,
apply an explicit bidirectional mapping table (tag pattern ↔ installed
pattern) reviewed against that project’s release history.

| Pros | Cons / risk |
| --- | --- |
| Limits blast radius | Requires ongoing qualification when upstream changes tag scheme |
| Can encode channel rules (Linux vs other) | Must not auto-enable from package name alone |
| Fits Beacon’s “confirmed upstream” model | Still must not auto-select assets or weaken APT gates |

**Verdict:** Only strategy that could pass a decision gate — and only after
dated tag/asset samples show the mapping never flips “newer” incorrectly.
Still design-only here.

### E. Do nothing in `--check`; rely on `--inspect`

**Idea:** Keep unknown; operator selects an exact `.deb` and uses
`dpkg --compare-versions` on the asset’s internal Debian version.

| Pros | Cons / risk |
| --- | --- |
| Already implemented and honest | `--check` / `--check-all` stay noisy for that tracked package |
| Avoids false update signals | Does not help operators triage “is there a newer tag?” at a glance |

**Verdict:** **Adopted (2026-11-15).** Recommended default is now the recorded
product decision until D is fully specified, fixture-backed, and approved.
Unknown remains the correct product answer.

## Explicit rule: when Beacon must stay `unknown`

Keep or extend these as hard stops for any future parser work:

1. **Either side fails today’s `VERSION_PATTERN` / revision / `+ds`/`+dfsg`
   rules** and no reviewed, publisher-scoped mapping applies.
2. **Tag and installed schemes disagree** (e.g. `release-…-linux*` tag vs
   `…-build.*` installed) unless a profile defines both sides together.
3. **Stripping tokens would change the comparison outcome** relative to
   leaving the strings opaque, and that outcome is not backed by asset-level
   Debian versions from the same release.
4. **Channel / platform suffixes** (`linux`, `linux1`, beta, canary, PTB)
   appear on only one side or differ between sides.
5. **Epochs, `ubuntu`/`debXuY` revisions, prerelease tags, date tags, and
   arbitrary `+git` / `+other` markers** — out of scope for this note; stay
   unknown under [version comparison](version-comparison.md).
6. **Ambiguity after stripping** (multiple `X.Y.Z` candidates, leading zeros,
   empty components) — stay unknown.

`--check` must never invent “Newer upstream release available.” or
“Versions match.” for these shapes. Operators who need direction use
`--inspect` on an exact asset.

## Decision gate (before any broader tag compare)

Do **not** expand `compare_versions` beyond current `+ds`/`+dfsg` support
until all of the following are written and reviewed:

1. **Concrete publisher scope** (repository id/name list) — no global
   `release-` or `-build` regex.
2. **Bidirectional mapping** for tags *and* installed versions, including
   what is compared vs only displayed.
3. **Counterexamples** from that publisher’s history where a naive strip
   would lie (wrong newer/older/match); show the proposed rule stays
   `unknown` or matches `dpkg` direction on the release’s `.deb`.
4. **Operator copy** that still says ignored tokens are not install approval
   and digests ≠ authenticity.
5. **Offline regressions** listed below, plus retention of every current
   unknown fixture (including `3.7.1-build.50` vs `release-3.4.13-linux1`).
6. **No CLI / schema / APT-gate changes** in the same change set as a parser
   expansion unless separately justified.

If any item is missing, ship documentation and keep `--check` unknown.

## Tests required before code lands

Minimum offline coverage (extend `tests/test_tracking.py` version cases):

| Case | Expected until/unless a gated profile lands |
| --- | --- |
| `3.7.1-build.50` vs `release-3.4.13-linux1` | `Unknown` (keep forever as the Kubuntu sentinel) |
| `3.7.1-build.50` vs `v3.7.1` | `Unknown` without a build-suffix profile |
| `3.7.1` vs `release-3.4.13-linux1` | `Unknown` without a tag-prefix profile |
| `3.7.1` vs `release-3.7.1` | `Unknown` globally; only comparable under an approved profile |
| `3.7.1` vs `v3.7.1-linux1` | `Unknown` |
| Existing `+ds`/`+dfsg`, numeric revision, epoch, `ubuntu`, beta cases | Unchanged |
| Any new positive case for a profile | Assert exact status strings; assert ignored-token messaging; assert unrelated repos still unknown for the same string shapes |

Also required before merge of parser code:

- No change to `--inspect` / `--prepare` Debian comparison path in the same
  patch without its own tests.
- Explicit assertion that filename “likely” hints and version comparison
  remain independent.
- Docs update to [version comparison](version-comparison.md) moving any
  newly supported shape from “unknown” to “comparable” with examples.

## Non-goals

- No CLI behavior changes in this design PR.
- No auto-selection of GitHub Desktop `.deb` assets.
- No treating unknown as an error to retry blindly.
- No vendor-download provider work (see [vendor download](vendor-download.md)).

## Relationship to roadmap

README / discovery backlog item “broader release-tag version comparison”
stays **partial / backlog** for other unsupported forms (epochs, `ubuntu`
revisions, prereleases, date tags). The GitHub Desktop–shaped subset is
**decision-closed**: stay unknown; no parser until a future gate reopening.
This note is that decision artifact.
