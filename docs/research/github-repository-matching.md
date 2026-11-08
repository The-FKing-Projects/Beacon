# GitHub Repository Matching Research

## Purpose and scope

This research proposes how Beacon can discover and track a likely upstream
GitHub repository for installed software. Repository matching is separate from
package-source classification: knowing that a package came from an APT source
does not identify its upstream project, and a GitHub match does not establish
how the package was installed.

The goal is to present traceable candidates for review, not to make package
management or installation decisions. Scores below are evidence grades, not
probabilities.

## GitHub search capabilities and limits

The REST endpoint `GET /search/repositories` can search public repository
names, descriptions, topics, and (when requested) README contents. Queries can
use qualifiers such as `in:name`, `in:description`, `in:topics`, `in:readme`,
`user:`, `org:`, and `fork:`. Search results are relevance-ranked by default;
that ordering is useful for candidate discovery but is not evidence that the
first result is the upstream.

Relevant API constraints documented by GitHub:

- Repository searches return at most 1,000 results per query; search considers
  up to 4,000 repositories matching a query's filters.
- A query is limited to 256 characters excluding operators and qualifiers and
  may contain at most five `AND`, `OR`, or `NOT` operators.
- Search results allow at most 100 results per page. The response includes
  `incomplete_results`; do not treat an incomplete response as an exhaustive
  candidate set.
- Unauthenticated REST requests for public data have a primary limit of 60
  requests per hour per originating IP. Authenticated user requests generally
  have a primary limit of 5,000 per hour.
- Search has its own limit: up to 10 requests per minute unauthenticated and
  30 per minute authenticated. Code search is a different endpoint, requires
  authentication, and is limited to 10 requests per minute.
- Secondary limits also apply. Read rate-limit response headers and back off
  on `403` or `429`; do not retry immediately or assume the primary quota is
  the only limit.

Public repository search does not need a user credential for basic discovery.
If Beacon later offers authenticated search, it should use a user-authorized
token or GitHub App with only the permissions needed, keep credentials out of
logs and source, and clearly explain why authentication is requested. Avoid
requiring a token merely to identify public repositories. GitHub's published
limits can change, so implementations should follow the current response
headers and documentation rather than hard-code quotas as guarantees.

## Candidate discovery workflow

1. **Check authoritative local evidence first.** Preserve the package name,
   display name, homepage, description, maintainer, and installed binary names
   as separately sourced input fields. Do not treat package maintainer as
   upstream author by default.
2. **Resolve a package homepage if present.** Accept a direct repository match
   only when the parsed URL points to a verifiable GitHub repository path
   (`github.com/owner/repo`) and the repository can be retrieved. Strip only
   known non-repository suffixes such as a release or file path; never infer a
   repository from arbitrary text containing `github.com`.
3. **Search conservatively when there is no verified direct link.** Start with
   exact package/repository-name queries, then known display-name aliases.
   Search names and descriptions first; use README search only as a broader
   candidate-generation step. Binary names and description terms can expand
   discovery, but are weak evidence on their own.
4. **Deduplicate and inspect candidates.** Use the canonical repository
   identity (`owner/name`, preferably the API repository ID where available)
   and retrieve metadata before ranking. Consider name, description, homepage,
   owner, topics, fork state, archive state, and last-push time. Search result
   score/order and popularity metrics are not identity evidence.
5. **Present evidence and alternatives.** Show the candidate URL, evidence
   that contributed to its tier, whether it is a fork or archived, and any
   conflicting candidates. Do not silently select a candidate if the leading
   candidates tie or credible signals conflict.

Example queries, URL-encoding the query parameter in the actual request:

```text
GET /search/repositories?q=PACKAGE in:name
GET /search/repositories?q=DISPLAY_NAME in:name,description
GET /search/repositories?q=PACKAGE in:readme
```

These queries discover candidates; the package manager's homepage metadata,
repository details, and other independent evidence must still be checked.
Repository search is not a complete global index of every project or package,
and absence of a result is not proof that no upstream exists.

## Proposed matching tiers

Use the following issue-proposed score tiers as the maximum score supported by
the strongest evidence. They are not calibrated probabilities and should not be
added together mechanically.

| Score | Evidence | Interpretation |
| --- | --- | --- |
| 100 | Package homepage directly identifies a verified GitHub repository | Very high; retain the exact homepage URL as provenance |
| 90 | Package name exactly matches the repository name | High candidate; verify that the project purpose fits |
| 75 | Independently corroborated maintainer-to-owner relationship | Medium-high; a text match alone is insufficient |
| 50 | Description similarity is the only meaningful match | Medium at best; present as a suggestion, not an automatic match |
| 25 | Several plausible repositories have similar names and no decisive evidence separates them | Low; show alternatives and require user confirmation |

Use a small, explainable normalization for exact-name comparison (case folding
and equivalent separators such as `-` and `_`). Keep the original strings
visible and do not normalize away meaningful words, version suffixes, vendor
names, or architecture. When independent signals corroborate a candidate, show
them as evidence; do not inflate the score unless Beacon has evaluated and
documented a calibrated combination rule.

The 25-point tier describes unresolved ambiguity, not a positive matching
signal. If candidates conflict with a direct homepage link or each other,
report a conflict and withhold a definitive match rather than averaging scores.
Unknown or missing evidence must remain unknown instead of being treated as a
negative match.

## Forks, archives, and repository health

Repository metadata exposes fork and archived indicators. A fork is not
automatically the upstream: follow its parent relationship when available and
prefer a separately supported canonical upstream. Do not exclude a fork
automatically either; a maintained fork may intentionally be the package's
source, so explicit package metadata or user confirmation can override the
default.

An archived repository can still be the correct historical upstream. Keep the
identity match, flag that the repository is archived, and avoid implying that
new releases or active maintenance should be expected. Recent pushes,
stars, forks, and issue counts describe activity or popularity, not project
identity; do not let them outweigh stronger provenance.

## False-positive safeguards and user experience

- Require at least one piece of identity evidence before attaching an
  upstream. A search result alone is only a candidate.
- Treat direct homepage links and exact names as stronger than maintainers,
  binary names, README hits, or description similarity.
- Check repository purpose against package metadata. Generic names and common
  binary names frequently refer to unrelated projects.
- Preserve candidate alternatives and explain why each was ranked. A tie,
  conflicting signals, incomplete search, or failed lookup should lower
  confidence or leave the match unresolved.
- Record the evidence source, observed value, lookup time, canonical repository
  URL/ID, score tier, and any fork/archive flags so a user can audit or correct
  the result.
- Ask for confirmation before persisting a low-confidence association or using
  it for release tracking. Never use a suggested match to install software,
  change package sources, or run repository-provided code.

## Recommendation

Implement a staged, low-request discovery flow: first resolve a verified
homepage link; otherwise run a small number of exact-name/alias searches,
deduplicate candidates, fetch metadata only for the short list, and show
evidence-backed alternatives. Cache results and avoid repeated searches for
unchanged package metadata. Use the 100/90/75/50/25 tiers initially as
conservative display bands, then validate them against a labeled set of true
matches and false positives before enabling automatic associations.

## References

- [REST API endpoints for search](https://docs.github.com/en/rest/search/search?apiVersion=2022-11-28) — search endpoints, result and query limits, rate limits, and incomplete results.
- [Searching for repositories](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories) — repository search fields and qualifiers, including `in:` and fork searches.
- [Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) — primary and secondary limits, response headers, and backoff guidance.
- [Authenticating to the REST API](https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api) — authentication options and credential handling.
- [REST API endpoints for repositories](https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28) — repository metadata fields such as `description`, `homepage`, `fork`, and `archived`.

Research checked against GitHub's published documentation on 2026-11-07.

Related issues:

- #3 Research GitHub repository matching
- #8 Design confidence scoring system
- #12 Design package provenance confidence scoring
