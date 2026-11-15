# Homepage URL normalization (`--suggest`)

## Status

**Decision recorded (2026-11-15): defer further normalize.** Keep today’s
`homepage_repository` behavior: ignore URL `#fragment`s only; continue to
reject query strings, params, and non-exact repository paths such as
`…/releases`. No code change in this decision. Prefer false negatives until a
dated installed-package case shows a clear false miss that a narrow rule can
fix without inventing false positives.

Canonical matching research:
[GitHub repository matching](../research/github-repository-matching.md).

## Decision (2026-11-15)

**Product stance:** Prefer false negatives. Direct-homepage “very high” tier
requires an exact HTTPS `github.com/<owner>/<repo>` URL (optional trailing
slash). Fragments such as `#readme` are already ignored for matching
(shipped; Caprine). Query strings and extra path segments are **not**
normalized.

**Verdict:** Do **not** strip query strings and do **not** treat
`…/releases` (or similar repo subpages) as the repository root for
`--suggest` ranking until a dated package homepage observation justifies a
narrow, fixture-backed rule.

### What already shipped (fragments only)

| Case | Evidence | Outcome |
| --- | --- | --- |
| Caprine Kubuntu homepage `https://github.com/sindresorhus/caprine#readme` | Operator-reported miss of the direct-homepage tier before fragment stripping; name search still found the repo | **Done** — `#fragment` ignored in `suggestions.homepage_repository`; offline tests cover Caprine-style `#readme` without auto-confirm |

That case does **not** authorize query-string or path stripping. The miss was
exactly a fragment on an otherwise exact repository URL.

### Why further normalize stays deferred

| Candidate rule | Why not now |
| --- | --- |
| Strip `?query=…` | Offline tests correctly reject query homepages today. No dated installed package whose APT/dpkg `Homepage` is a GitHub repo URL **with** a query string and that therefore missed the direct-homepage tier is recorded in discovery notes. Query tokens can also encode non-identity state; stripping without a real case risks silent acceptance of odd packaging metadata. |
| Treat `…/releases`, `…/issues`, `…/tree/…`, etc. as repo root | Same gap: no dated installed-package homepage that is a GitHub **subpage** and that caused a false negative. Path peeling is easy to over-generalize (marketing pages under `github.com`, nested paths, `.git` suffixes already refused elsewhere). Prefer keeping `repository_name`’s exact `owner/repo` shape. |

Name search and manual `--track` remain available when homepage metadata is
not an exact repository URL. Missing the direct-homepage tier is acceptable;
auto-confirm remains forbidden either way.

### Answers used for this call

1. **Dated false-negative case for query strings?** None in
   [discovery test cases](../research/discovery-test-cases.md) (Kubuntu /
   lab / survey notes). Caprine was fragment-only.
2. **Dated false-negative case for `/releases` (or similar)?** None observed
   as an installed package `Homepage`. Unit fixtures assert
   `…/releases` → no direct match.
3. **Clear narrow rule without false positives?** Not justified without (1)
   or (2). Fragment stripping was safe because `#…` never changes repository
   identity on GitHub; query and path segments can.
4. **Operator workaround?** `--suggest` still surfaces name-search
   candidates; operators confirm with `--track`. No product emergency.

**Gate result:** Docs-only defer. Agents must not add query/path normalize
code, CLI flags, or broaden `homepage_repository` until the unlock below is
met.

### What would unlock a narrow normalize

Dennis (or a follow-up PR he accepts) must supply **all** of:

1. **Dated observation** of an installed package whose `Homepage` is an HTTPS
   GitHub URL that fails today’s matcher **only** because of a query string
   and/or a specific, listed path suffix (e.g. `/releases`), with the intended
   `owner/repo` otherwise exact.
2. **Written narrow rule** naming exactly which suffixes or query forms are
   stripped (prefer an allowlist of path tails, not open path peeling).
3. **Counterexample review** showing the rule does not promote marketing
   sites, nested non-repo paths, or ambiguous hosts.
4. **Offline fixtures** that accept the dated positive case and retain today’s
   rejects for unrelated shapes; still **no auto-confirm**.

Until then, keep rejecting query strings and non-exact paths.

## Current behavior (reference)

`suggestions.homepage_repository`:

- Accepts `https://github.com/<owner>/<repo>` with optional trailing `/`.
- Ignores URL fragments (`#readme`, `#section`, …).
- Returns no direct match when `query` or `params` are present.
- Relies on `tracking.repository_name` for path shape; extra segments such as
  `/releases` fail that exact `owner/repo` pattern.

Related operator copy in the README: fragments ignored; query strings not
accepted.

## Relationship to roadmap

README / discovery backlog “Homepage URL normalization” stays **Done for
fragments only**; further query/path normalize is **decision-deferred**
(docs), not authorized product work. Expanding `--suggest` aliases is a
separate freeze (see
[documented packaging aliases](suggest-package-aliases.md)); display names
and calibrated scores remain deferred.
