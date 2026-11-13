"""Read-only GitHub repository suggestions for installed packages."""

import re
import subprocess
from urllib.parse import quote, urlparse

import tracking


def package_homepage(name, architecture):
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f", "${Homepage}", f"{name}:{architecture}"],
            capture_output=True, text=True, timeout=15, check=False,
            env=tracking.command_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise tracking.TrackingError(f"Unable to read package homepage: {exc}") from exc
    if result.returncode:
        raise tracking.TrackingError(
            f"Unable to read package homepage: {result.stderr.strip() or 'dpkg-query failed'}"
        )
    homepage = result.stdout.strip()
    if any(not char.isprintable() for char in homepage):
        raise tracking.TrackingError("Package homepage contains invalid characters.")
    return homepage


def homepage_repository(homepage):
    try:
        parsed = urlparse(homepage)
    except ValueError:
        return None
    if (parsed.scheme != "https" or parsed.netloc.lower() != "github.com"
            or parsed.query or parsed.fragment or parsed.params):
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
    normalize = lambda value: value.lower().replace("_", "-")
    if normalize(package) == normalize(repo_name):
        return 2, "package and repository names match (case and -/_ normalized)"
    if normalize(package).replace("-", "") == normalize(repo_name).replace("-", ""):
        return 1, "package and repository names are similar with separators removed"
    return 0, "returned by GitHub name search; no exact package-name match"


def match_tier(rank):
    tiers = {
        3: "Very high: installed package homepage directly identifies this repository",
        2: "High: package and repository names match",
        1: "Low: similar names only",
        0: "Candidate only: search result without independent identity evidence",
    }
    return tiers[rank]


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

    query = quote(f"{name} in:name", safe="")
    data = tracking.github_get(f"/search/repositories?q={query}&per_page=30")
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
            candidates[candidate["id"]]["evidence"].append(evidence)
        else:
            candidate["rank"] = rank
            candidate["evidence"] = [evidence]
            candidates[candidate["id"]] = candidate

    print(f"Package: {name}:{architecture}")
    print(f"Package homepage: {homepage or '(not provided)'}")
    if homepage and not direct:
        print("Homepage is not a direct HTTPS GitHub repository URL.")
    print("GitHub search results are suggestions, not proof of upstream identity.")
    if incomplete:
        print("Warning: GitHub reported incomplete search results.")
    if count > len(items):
        print(f"Warning: showing only the first {len(items)} of {count} search results.")
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
