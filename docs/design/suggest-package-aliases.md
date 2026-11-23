# Documented packaging aliases (`--suggest`)

## Status

**Decision recorded (2026-11-15): freeze the v1.3.0 survey alias table.** Keep
`DOCUMENTED_PACKAGE_ALIASES` exactly at the three labeled mappings shipped in
v1.3.0 (`git-delta`→`delta`, `du-dust`→`dust`, `fd-find`→`fd`). Do **not** add
`gh`→`cli` or any other packaging alias without a new dated discovery case,
low-tier-only wiring, and offline tests. Prefer false negatives over invented
associations. Still never auto-track.

Canonical matching research:
[GitHub repository matching](../research/github-repository-matching.md).

Survey evidence:
[discovery test cases — public GitHub `.deb` survey](../research/discovery-test-cases.md#public-github-deb-survey-2026-11-15).

## Frozen table (v1.3.0)

| Installed package name | Extra `in:name` search / low-tier alias | Evidence |
| --- | --- | --- |
| `git-delta` | `delta` | 2026-11-15 survey: Debian package `git-delta`, upstream [`dandavison/delta`](https://github.com/dandavison/delta) |
| `du-dust` | `dust` | 2026-11-15 survey: Debian package `du-dust`, upstream [`bootandy/dust`](https://github.com/bootandy/dust) |
| `fd-find` | `fd` | Earlier discovery / available-package notes: Ubuntu `fd-find` vs upstream [`sharkdp/fd`](https://github.com/sharkdp/fd) |

Code home: `suggestions.DOCUMENTED_PACKAGE_ALIASES` in `src/suggestions.py`.
Offline regressions: `tests/test_suggestions.py`.

### Behavior that stays in scope (unchanged)

- Extra name-search query per documented alias only when it differs from the
  package name after case/`_`/`-` normalization.
- Alias hits rank at the **Low** similar-name tier only.
- Structural hyphen-token similarity (repo name is a full token of the longer
  package, length ≥ 3) remains low-tier; reverse direction stays non-evidence.
- Homepage preference, exact-name conflict warning, tie warning, and
  never-auto-track rules are unchanged.

### Explicit non-additions (still refused)

| Candidate | Why not now |
| --- | --- |
| `gh`→`cli` | Survey notes package name is `gh`, not `cli`; homepage `cli.github.com` is not a direct repository URL. Filename peel for `gh_*_linux_*` already shipped. No dated miss where searching `cli` would have been the safe missing signal without broadening false positives. |
| Reverse aliases (`dust`→`du-dust`, `delta`→`git-delta`, `fd`→`fd-find`) | Correct negatives today; reverse is non-evidence by design. |
| Broad undocumented or display-name aliases | Roadmap item 2 stays Partial; prefer false negatives. |

## Decision (2026-11-15)

**Product stance:** Prefer false negatives. The survey set is enough for the
labeled packaging mismatches; inventing further aliases (including `gh`→`cli`)
without a new dated case would trade silent wrong-repo ranking for little
operator gain. Name search on the installed package name and manual `--track`
remain available.

**Verdict:** Freeze the table. Docs + constant comment only in this decision.
Agents must not expand `DOCUMENTED_PACKAGE_ALIASES` until the unlock below is
met.

### What would unlock a new alias

Dennis (or a follow-up PR he accepts) must supply **all** of:

1. **Dated discovery observation** of an installed (or carefully simulated
   installed) Debian/Ubuntu package whose packaging name differs from the
   upstream GitHub repository name, with the intended `owner/repo` recorded in
   [discovery test cases](../research/discovery-test-cases.md) (or an
   equivalent dated note linked from there).
2. **Low-tier only** — the new mapping may add at most one extra `in:name`
   search and low-tier evidence wording; it must not raise homepage/high tiers,
   auto-track, or override conflict/tie warnings.
3. **Counterexample review** showing the alias does not promote unrelated
   repos that share the short name, and that the reverse direction (if
   relevant) stays non-evidence unless separately justified.
4. **Offline tests** in `tests/test_suggestions.py` covering the new alias
   search, low-tier ranking, and preservation of homepage preference /
   no-save behavior.

Until then, keep the v1.3.0 three-entry table frozen.

## Relationship to roadmap

README / discovery backlog “Better upstream suggestions” remains **Partial**.
Survey packaging aliases are **shipped and frozen** at the v1.3.0 set. Printing
installed package Description/Source in `--suggest` is display-only operator
context and does **not** unlock search or ranking on those fields. Remaining
Partial leftovers (display-name/description search or rank signals,
README/`in:description` search, broad undocumented aliases, calibrated match
scores) still need dated discovery unlocks before any code change; do not invent
aliases or map tiers to probabilities. Match tiers stay discrete evidence labels,
not calibrated scores. See also the README Partial bullet for item 2.
