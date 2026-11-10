#!/usr/bin/env python3

import argparse
from datetime import datetime, timezone
import json
import os
import re
import subprocess
from pathlib import Path


VERSION_PATTERN = re.compile(r'^VERSION = "([^"]+)"$', re.MULTILINE)
CHANGELOG_VERSION_PATTERN = re.compile(r"^(beacon \()[^)]+(\) .*; urgency=)", re.MULTILINE)
CONVENTIONAL_TITLE_PATTERN = re.compile(
    r"^(?P<type>[a-z]+)(?:\([^)]*\))?(?P<breaking>!)?:\s+\S"
)
BREAKING_FOOTER_PATTERN = re.compile(r"^BREAKING[- ]CHANGE:\s*\S", re.MULTILINE)
VERSION_PATTERN_STRICT = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def classify_bump(title, body):
    match = CONVENTIONAL_TITLE_PATTERN.match(title.strip())
    if match is None:
        return None

    if match.group("breaking") or BREAKING_FOOTER_PATTERN.search(body):
        return "major"

    change_type = match.group("type")
    if change_type == "feat":
        return "minor"
    if change_type in {"fix", "perf"}:
        return "patch"
    return None


def bump_version(version, bump):
    match = VERSION_PATTERN_STRICT.fullmatch(version)
    if match is None:
        raise ValueError(f"Invalid semantic version: {version}")

    major, minor, patch = (int(component) for component in match.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unsupported version bump: {bump}")


def update_version_text(source, version):
    updated, count = VERSION_PATTERN.subn(f'VERSION = "{version}"', source)
    if count != 1:
        raise ValueError("Expected exactly one VERSION assignment in source file")
    return updated


def update_changelog_version_text(source, version, title, pr_number, manual_run_id=None):
    if CHANGELOG_VERSION_PATTERN.search(source) is None:
        raise ValueError("Expected a Beacon Debian changelog entry")
    if "\n" in title or "\r" in title:
        raise ValueError("Release title cannot contain line breaks")
    date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    origin = (
        f"workflow run {manual_run_id}" if manual_run_id is not None
        else f"pull request #{pr_number}"
    )
    entry = (
        f"beacon ({version}-1) unstable; urgency=medium\n\n"
        f"  * Release for {origin}: {title}.\n\n"
        f" -- The FK'ing Projects <FiendKing04@gmail.com>  {date}\n\n"
    )
    return entry + source


def find_tag_for_pr(pr_number):
    return find_tag_for_marker(f"Beacon-PR: #{pr_number}")


def find_tag_for_marker(marker):
    result = subprocess.run(
        ["git", "tag", "--list", "v[0-9]*"],
        check=True,
        capture_output=True,
        text=True,
    )
    for tag in result.stdout.splitlines():
        tag_type = subprocess.run(
            ["git", "cat-file", "-t", f"refs/tags/{tag}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if tag_type != "tag":
            continue

        contents = subprocess.run(
            ["git", "cat-file", "-p", f"refs/tags/{tag}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        message = contents.partition("\n\n")[2]
        if marker in message.splitlines():
            return tag
    return None


def write_outputs(outputs):
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output_file:
            for name, value in outputs.items():
                output_file.write(f"{name}={value}\n")
    else:
        print(json.dumps(outputs))


def prepare_release(title, body, pr_number, version_file, changelog_file=None,
                    manual_run_id=None, manual_bump=None):
    if not title.strip() or "\n" in title or "\r" in title:
        raise ValueError("Release title must be nonempty and contain no line breaks")
    if manual_run_id is not None:
        if (pr_number is not None or not re.fullmatch(r"[1-9][0-9]*", str(manual_run_id))
                or manual_bump not in {"patch", "minor", "major"}):
            raise ValueError("Manual releases require a positive run ID and an explicit version bump")
        existing_tag = find_tag_for_marker(f"Beacon-Manual-Run: {manual_run_id}")
        bump = manual_bump
    else:
        if pr_number is None or pr_number <= 0 or manual_bump is not None:
            raise ValueError("Automated releases require a positive pull request number")
        existing_tag = find_tag_for_pr(pr_number)
        bump = classify_bump(title, body)
    if existing_tag:
        if not VERSION_PATTERN_STRICT.fullmatch(existing_tag[1:]):
            raise ValueError(f"Invalid existing release tag: {existing_tag}")
        write_outputs(
            {
                "release": "true",
                "version": existing_tag[1:],
                "tag": existing_tag,
                "bump": "existing",
                "reused": "true",
            }
        )
        return

    if bump is None:
        write_outputs({"release": "false"})
        return

    path = Path(version_file)
    source = path.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(source)
    if match is None:
        raise ValueError(f"No VERSION assignment found in {version_file}")

    version = bump_version(match.group(1), bump)
    updated_changelog = None
    changelog_path = Path(changelog_file) if changelog_file else None
    if changelog_path is not None:
        changelog = changelog_path.read_text(encoding="utf-8")
        updated_changelog = update_changelog_version_text(
            changelog,
            version,
            title,
            pr_number,
            manual_run_id=manual_run_id,
        )
    path.write_text(update_version_text(source, version), encoding="utf-8")
    if changelog_path and updated_changelog is not None:
        changelog_path.write_text(updated_changelog, encoding="utf-8")
    write_outputs(
        {
            "release": "true",
            "version": version,
            "tag": f"v{version}",
            "bump": bump,
            "reused": "false",
        }
    )


def main():
    parser = argparse.ArgumentParser(description="Prepare an automated Beacon release")
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", default="")
    origin = parser.add_mutually_exclusive_group(required=True)
    origin.add_argument("--pr-number", type=int)
    origin.add_argument("--manual-run-id", type=int)
    parser.add_argument("--bump", choices=("patch", "minor", "major"))
    parser.add_argument("--version-file", default="src/beacon.py")
    parser.add_argument("--changelog-file")
    args = parser.parse_args()

    prepare_release(
        args.title,
        args.body,
        args.pr_number,
        args.version_file,
        args.changelog_file,
        manual_run_id=args.manual_run_id,
        manual_bump=args.bump,
    )


if __name__ == "__main__":
    main()
