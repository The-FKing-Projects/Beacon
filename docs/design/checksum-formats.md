# Checksum formats beyond `SHA256SUMS`

## Status

**Decision recorded (2026-11-15): stay `SHA256SUMS`-only** (plus GitHub API
`sha256` digests already implemented). Do **not** accept per-asset `.sha256`
siblings, `*_checksums.txt`, `MD5SUMS`/`SHA1SUMS`/`SHA512SUMS`, or other
manifest names without a later unlock that names one exact format, exact
filename rule, parser, fixtures, and priority with existing checks. Prefer
false negatives / “integrity not verified” over inventing a second allowlisted
format. Integrity evidence still ≠ publisher authenticity.

Canonical handoff / trust copy:
[APT handoff](apt-handoff.md).

Survey note that raised the question:
[discovery test cases — public GitHub `.deb` survey](../research/discovery-test-cases.md#public-github-deb-survey-2026-11-15)
(`BurntSushi/ripgrep` per-asset `.sha256`).

## Current behavior (reference)

`--inspect` / `--prepare` discover a release checksum asset only when an asset
is named exactly `SHA256SUMS` (`inspection._assets_from_release`). The file is
parsed for a single GNU-style entry whose filename matches the selected `.deb`
exactly (`filename` or `./filename`). Prepared-row URL validation likewise
requires any stored `checksum_asset_url` to name `SHA256SUMS`
(`tracking` prepared-update checks).

Separately, when GitHub’s release API supplies a well-formed `sha256:` digest
for the selected asset, Beacon compares downloaded bytes to that digest and
requires agreement with any exact `SHA256SUMS` entry. Operator-facing copy
states that neither an unsigned checksum nor a GitHub API digest authenticates
the publisher.

## Decision (2026-11-15)

**Product stance:** Prefer reporting missing checksum evidence over accepting
ambiguous sibling formats. The dated survey case that motivated this gate
already has GitHub API digest coverage; expanding the allowlist without a
narrow, fixture-backed format risks silent false confidence and schema churn.

**Verdict:** Docs-only defer. Agents must not add code paths, CLI flags, or
prepared-row statuses for non-`SHA256SUMS` checksum assets until the unlock
below is met.

### Evidence reviewed

| Observation | What Beacon sees today | Why it does not authorize a new format |
| --- | --- | --- |
| [`BurntSushi/ripgrep`](https://github.com/BurntSushi/ripgrep/releases/tag/15.2.0) `15.2.0` ships `ripgrep_15.2.0-1_amd64.deb.sha256` (GNU one-line `hex  filename`), not `SHA256SUMS` | No release `SHA256SUMS`; `--inspect`/`--prepare` report checksum asset missing; API `sha256` digest for the `.deb` still matches downloaded bytes | Integrity for this asset is already covered by the API digest path. Sibling `.sha256` would be redundant for the dated case and would still be unsigned co-release evidence (≠ authenticity). |
| Same release family (e.g. `15.1.0`) uses the same sibling naming | Same | One publisher’s convention is not a format standard. |
| [`cli/cli`](https://github.com/cli/cli/releases/tag/v2.104.0) ships `gh_2.104.0_checksums.txt` (multi-file GNU manifest, versioned name) | Not `SHA256SUMS`; ignored | Different exact filename pattern; accepting `.sha256` would immediately pressure a third name. |
| [`rclone/rclone`](https://github.com/rclone/rclone/releases/tag/v1.76.0) ships `SHA256SUMS` (plus `MD5SUMS` / `SHA1SUMS`) | Exact `SHA256SUMS` already used | Weaker algorithms must stay ignored; already correct. |
| bat / fd / bottom / dust / delta / helix survey assets | Often no checksum asset; API digests when GitHub provides them | Missing `SHA256SUMS` is an accepted “integrity not verified” / digest-only outcome. |

### Why a “narrow” `{deb}.sha256` first step is not clearly safe

| Risk | Detail |
| --- | --- |
| Format ambiguity under one extension | Publisher `.sha256` files may be GNU `hex  name`, hex-only, BSD `SHA256 (name) = hex`, or otherwise. Beacon would have to invent which subset counts without a multi-publisher corpus. |
| Neighbor formats | Survey already shows `*_checksums.txt` and `MD5SUMS`/`SHA1SUMS`. Opening the allowlist for one sibling invites immediate follow-on exceptions. |
| Priority / conflict rules | Need explicit behavior when both `SHA256SUMS` and `{deb}.sha256` exist, when the sibling lacks an exact filename entry, or when sibling and API digest disagree — none of that is specified today. |
| Persistence surface | Prepared updates and URL validation hardcode the checksum asset name `SHA256SUMS`. A second name is schema and revalidation work, not a one-line discovery tweak. |
| Integrity≠authenticity | Any new match must keep “not authenticated” wording. Easy to over-claim if UI starts treating “found `.sha256`” as stronger than today’s explicit SHA256SUMS language. |
| Operator gap is small | For the dated ripgrep case, API digest already supplies the same class of integrity check operators get from an unsigned manifest. |

### Answers used for this call

1. **Is there a dated case where missing non-`SHA256SUMS` checksums caused a
   real integrity gap (no API digest either)?** Not in the 2026-11-15 survey.
   Ripgrep had sibling `.sha256` **and** a matching API digest.
2. **Is one extra format clearly safe with fixtures?** Not yet — extension and
   content conventions vary; only one publisher observed for `.sha256`
   siblings among the surveyed `.deb` releases.
3. **Does staying `SHA256SUMS`-only violate product boundaries?** No. README
   and APT handoff already say only `SHA256SUMS` is checked; other formats are
   not. Prefer false negatives / explicit “not verified.”
4. **Commit type for this decision?** `chore:` docs only — must not cut a
   release.

**Gate result:** Stay `SHA256SUMS`-only (+ existing API digests). No parser,
discovery, or prepared-row changes in this decision.

### What would unlock one documented extra format

Dennis (or a follow-up PR he accepts) must supply **all** of:

1. **Dated observation** of a selected GitHub `.deb` where integrity is
   otherwise missing (no usable GitHub API `sha256` digest **and** no
   `SHA256SUMS`), and where a single alternative checksum asset is the
   practical gap — recorded in
   [discovery test cases](../research/discovery-test-cases.md) (or linked
   from there).
2. **Written exact-filename rule** (for example only
   `{selected-asset-name}.sha256`, no globbing, no alternate extensions) and
   **exact content grammar** (reuse today’s GNU entry parser or a specified
   hex-only form — not both without tests).
3. **Priority rules** with `SHA256SUMS` and with the API digest (require
   agreement when both present; define missing-entry vs mismatch vs ambiguous).
4. **Counterexample review** covering `*_checksums.txt`, `MD5SUMS` /
   `SHA1SUMS` / `SHA512SUMS`, hex-only vs GNU ambiguity, and multiple matching
   checksum assets.
5. **Offline fixtures** for accept and reject paths in inspection/prepare
   tests; operator copy must keep integrity≠authenticity language; prepared
   URL validation updated only for the named allowlisted asset filename.

Until then, keep exact `SHA256SUMS` matching only.

## Relationship to roadmap / Remaining

Checksum formats beyond release `SHA256SUMS` are **decision-deferred** (docs).
This closes the integrity-format gate for the current GitHub-path pass; it does
not authorize product code. Stronger authenticity (independent keys /
signatures) remains a separate open product topic in
[APT handoff](apt-handoff.md).
