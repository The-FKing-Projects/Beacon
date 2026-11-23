"""Read-only GitHub repository suggestions for installed packages."""

import subprocess
from urllib.parse import quote, urlparse

import tracking


# Documented Debian/Ubuntu package → GitHub repository-name aliases from the
# 2026-11-15 discovery survey (docs/research/discovery-test-cases.md). Used only
# for extra name-search queries and low-tier evidence. Frozen at the v1.3.0 set
# (2026-11-15): do not add entries (e.g. gh→cli) without a new dated discovery
# case, low-tier-only wiring, and offline tests — see
# docs/design/suggest-package-aliases.md. Prefer false negatives; never auto-track.
DOCUMENTED_PACKAGE_ALIASES = {
    "git-delta": ("delta",),
    "du-dust": ("dust",),
    "fd-find": ("fd",),
}


def normalize_name(value):
    return value.lower().replace("_", "-")


def documented_aliases(package):
    return DOCUMENTED_PACKAGE_ALIASES.get(normalize_name(package), ())


def _package_field(name, architecture, field, label):
    """Read one dpkg-query field with the same timeout/error hardening as homepage."""
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f", "${" + field + "}", f"{name}:{architecture}"],
            capture_output=True, text=True, timeout=15, check=False,
            env=tracking.command_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise tracking.TrackingError(f"Unable to read package {label}: {exc}") from exc
    if result.returncode:
        raise tracking.TrackingError(
            f"Unable to read package {label}: "
            f"{result.stderr.strip() or 'dpkg-query failed'}"
        )
    value = result.stdout.strip()
    if any(not char.isprintable() for char in value):
        raise tracking.TrackingError(f"Package {label} contains invalid characters.")
    return value


def package_homepage(name, architecture):
    return _package_field(name, architecture, "Homepage", "homepage")


def package_description(name, architecture):
    """Installed package short Description — display-only for --suggest."""
    return _package_field(name, architecture, "Description", "description")


def package_source(name, architecture):
    """Installed package Source — display-only for --suggest."""
    return _package_field(name, architecture, "Source", "source")


def homepage_repository(homepage):
    try:
        parsed = urlparse(homepage)
    except ValueError:
        return None
    # Ignore URL fragments (#readme, etc.) so a repository homepage with a
    # fragment still ranks as a direct match. Query strings and params remain
    # unsupported — they are not normalized here.
    if (parsed.scheme != "https" or parsed.netloc.lower() != "github.com"
            or parsed.query or parsed.params):
        return None
    value = parsed.path.strip("/")
    try:
        return tracking.repository_name(value)
    except tracking.TrackingError:
        return None


def parse_candidate(data):
    if not isinstance(data, dict):
        raise tracking.TrackingError("GitHub returned an invalid repository search result.")
    name = data.get("full_name")
    identifier = data.get("id")
    if not isinstance(name, str):
        raise tracking.TrackingError("GitHub returned an invalid repository name.")
    try:
        tracking.repository_name(name)
    except tracking.TrackingError as exc:
        raise tracking.TrackingError("GitHub returned an invalid repository name.") from exc
    if (not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0
            or not isinstance(data.get("fork"), bool) or not isinstance(data.get("archived"), bool)):
        raise tracking.TrackingError("GitHub returned invalid repository metadata.")
    description = data.get("description")
    if description is not None and not isinstance(description, str):
        raise tracking.TrackingError("GitHub returned an invalid repository description.")
    description = " ".join((description or "").split())
    description = "".join(char for char in description if char.isprintable())[:240]
    return {
        "name": name, "id": identifier, "fork": data["fork"],
        "archived": data["archived"], "description": description,
    }


def name_evidence(package, repository):
    repo_name = repository.split("/", 1)[1]
    pkg = normalize_name(package)
    repo = normalize_name(repo_name)
    if pkg == repo:
        return 2, "package and repository names match (case and -/_ normalized)"
    if pkg.replace("-", "") == repo.replace("-", ""):
        return 1, "package and repository names are similar with separators removed"
    aliases = documented_aliases(pkg)
    if repo in aliases:
        return 1, "documented package/repository name alias from discovery cases"
    # Conservative packaging-style token match: repository name equals a full
    # hyphen-delimited token of the longer package name (e.g. git-delta → delta).
    # Require token length ≥ 3 and never treat the reverse (shorter package /
    # longer repo) as evidence — prefer false negatives.
    pkg_tokens = [token for token in pkg.split("-") if token]
    if len(repo) >= 3 and repo in pkg_tokens and pkg != repo:
        return 1, (
            "package name includes the repository name as a hyphen-delimited token"
        )
    return 0, "returned by GitHub name search; no exact package-name match"


def match_tier(rank):
    tiers = {
        3: "Very high: installed package homepage directly identifies this repository",
        2: "High: package and repository names match",
        1: "Low: similar names only",
        0: "Candidate only: search result without independent identity evidence",
    }
    return tiers[rank]


def _merge_search_page(name, data, candidates):
    items = data.get("items")
    count = data.get("total_count")
    incomplete = data.get("incomplete_results")
    if (not isinstance(items, list) or not isinstance(count, int) or isinstance(count, bool)
            or count < 0 or not isinstance(incomplete, bool)):
        raise tracking.TrackingError("GitHub returned invalid search results.")
    for item in items:
        candidate = parse_candidate(item)
        rank, evidence = name_evidence(name, candidate["name"])
        if candidate["id"] in candidates:
            existing = candidates[candidate["id"]]
            if evidence not in existing["evidence"]:
                existing["evidence"].append(evidence)
            if rank > existing["rank"] and existing["rank"] < 3:
                existing["rank"] = rank
        else:
            candidate["rank"] = rank
            candidate["evidence"] = [evidence]
            candidates[candidate["id"]] = candidate
    return items, count, incomplete


def suggest(package):
    name, architecture, _ = tracking.installed_package(package)
    homepage = package_homepage(name, architecture)
    direct = homepage_repository(homepage)
    homepage_candidate_id = None
    candidates = {}
    if direct:
        candidate = parse_candidate(tracking.github_get("/repos/" + quote(direct, safe="/")))
        candidate["evidence"] = [f"installed package homepage: {homepage}"]
        candidate["rank"] = 3
        candidates[candidate["id"]] = candidate
        homepage_candidate_id = candidate["id"]

    search_terms = [name]
    for alias in documented_aliases(name):
        if normalize_name(alias) != normalize_name(name) and alias not in search_terms:
            search_terms.append(alias)

    incomplete = False
    # Accumulate across package + alias queries so the truncation warning
    # describes every search page being presented, not only the largest one.
    total_count = 0
    shown = 0
    for term in search_terms:
        query = quote(f"{term} in:name", safe="")
        data = tracking.github_get(f"/search/repositories?q={query}&per_page=30")
        items, count, page_incomplete = _merge_search_page(name, data, candidates)
        incomplete = incomplete or page_incomplete
        total_count += count
        shown += len(items)

    # Description/Source are operator context only — never search terms, evidence, or ranks.
    description = package_description(name, architecture)
    source = package_source(name, architecture)
    print(f"Package: {name}:{architecture}")
    print(f"Package homepage: {homepage or '(not provided)'}")
    print(f"Package description: {description or '(not provided)'}")
    print(f"Package source: {source or '(not provided)'}")
    if homepage and not direct:
        print("Homepage is not a direct HTTPS GitHub repository URL.")
    print("GitHub search results are suggestions, not proof of upstream identity.")
    if incomplete:
        print("Warning: GitHub reported incomplete search results.")
    if total_count > shown:
        print(f"Warning: showing only the first {shown} of {total_count} search results.")
    if not candidates:
        print("No candidates found; this does not prove that no upstream exists.")
        return
    if homepage_candidate_id is not None and any(
        candidate["id"] != homepage_candidate_id and candidate["rank"] >= 2
        for candidate in candidates.values()
    ):
        print(
            "Warning: an exact package-name match points to a different repository "
            "than the installed package homepage; review both candidates."
        )
    ordered = sorted(candidates.values(), key=lambda c: (-c["rank"], c["name"].lower()))
    strongest_rank = ordered[0]["rank"]
    strongest_matches = [candidate for candidate in ordered
                         if candidate["rank"] == strongest_rank]
    if strongest_rank > 0 and len(strongest_matches) > 1:
        print(
            "Warning: multiple repositories share the strongest match evidence; "
            "no single upstream is identified."
        )
    for candidate in ordered:
        print(f"\n  https://github.com/{candidate['name']}")
        print(f"    Match: {match_tier(candidate['rank'])}")
        print(f"    Evidence: {'; '.join(candidate['evidence'])}")
        print(f"    Fork: {'yes' if candidate['fork'] else 'no'}; "
              f"archived: {'yes' if candidate['archived'] else 'no'}")
        if candidate["description"]:
            print(f"    Description: {candidate['description']}")
    print("\nVerify the project independently before using --track. Nothing was saved.")
