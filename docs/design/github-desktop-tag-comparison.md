# GitHub Desktop–style tag comparison (design only)

## Status

**Design / evaluation only — no parser expansion.** `--check` and
`--check-all` keep today’s narrow `compare_versions` rules (optional `v` +
three numeric components; installed optional `+ds`/`+dfsg` and numeric Debian
revision). This note studies whether Beacon could ever compare shapes like
Kubuntu’s `github-desktop` case without inventing false “update available”
or “current” answers.

Canonical current behavior:
[version comparison](version-comparison.md).

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

**Verdict:** **Recommended default** until D is fully specified and tested.
Unknown is the correct product answer.

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
stays **partial / backlog**. This note is the evaluation artifact for the
GitHub Desktop–shaped subset; implementation waits on the decision gate.
