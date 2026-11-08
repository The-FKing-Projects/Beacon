#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


VERSION_PATTERN = re.compile(r'^VERSION = "([^"]+)"$', re.MULTILINE)
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


def find_tag_for_pr(pr_number):
    result = subprocess.run(
        ["git", "tag", "--list", "v[0-9]*"],
        check=True,
        capture_output=True,
        text=True,
    )
    marker = f"Beacon-PR: #{pr_number}"

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


def prepare_release(title, body, pr_number, version_file):
    existing_tag = find_tag_for_pr(pr_number)
    if existing_tag:
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

    bump = classify_bump(title, body)
    if bump is None:
        write_outputs({"release": "false"})
        return

    path = Path(version_file)
    source = path.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(source)
    if match is None:
        raise ValueError(f"No VERSION assignment found in {version_file}")

    version = bump_version(match.group(1), bump)
    path.write_text(update_version_text(source, version), encoding="utf-8")
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
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--version-file", default="src/beacon.py")
    args = parser.parse_args()

    prepare_release(args.title, args.body, args.pr_number, args.version_file)


if __name__ == "__main__":
    main()
