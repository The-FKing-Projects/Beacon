# Automated Releases

Beacon's GitHub Actions release workflow publishes a tag and GitHub Release
after a qualifying pull request is merged into `main`. It follows Semantic
Versioning and updates the `VERSION` value in `src/beacon.py` in the same
release commit.

## Pull Request Titles

Use Conventional Commit prefixes for changes that should publish a release:

| Pull request title | Version change |
| --- | --- |
| `feat: add repository matching` | Minor |
| `fix: handle missing package metadata` | Patch |
| `perf: reduce discovery time` | Patch |
| `feat(api)!: change the output format` | Major |

A `BREAKING CHANGE:` footer in the pull request description also requests a
major release. Other title types, including `docs:`, `test:`, `chore:`, and
`refactor:`, do not publish a release unless they declare a breaking change.

The workflow maps each merged commit back to its pull request, increments the
current version, commits the version update, and atomically pushes that commit
and its annotated `vX.Y.Z` tag to `main`. It then creates the matching GitHub
Release. Tags include the originating PR number so a rerun can resume release
publication without incrementing the version twice.

## Manual releases

Direct pushes to `main` do not automatically release. To publish changes
already on `main`, run the **Release** workflow with its `workflow_dispatch`
action, selecting the `main` branch, an explicit `patch`, `minor`, or `major`
bump, and a short, single-line release title. For example:

```sh
gh workflow run release.yml --ref main \
  -f bump=minor -f title="Tracking management and Debian revision comparison"
```

The workflow increments the current application version and Debian changelog
together, pushes the release commit and annotated tag atomically, and builds
and uploads the matching `.deb` using the same steps as PR-triggered releases.
Manual titles describe the release; their prefixes do not determine the bump.
The workflow refuses to release from a branch other than `main`.

Manual tags record `Beacon-Manual-Run: <run-id>` rather than a fabricated PR
number. **Rerun the same Actions run** to resume a failed publication without
another version bump. Dispatching a new run intentionally requests a new
release and increments again. Both manual and PR reruns build from the exact
original release tag, not newer `main` contents. Release executions share one
concurrency group; a concurrent external push can still make the atomic push
fail safely, in which case rerun after reviewing the updated `main`.

## Repository Configuration

The workflow requests only `contents: write` and `pull-requests: read`. In
**Settings → Actions → General → Workflow permissions**, allow workflows to
write repository contents.

Because the workflow pushes a version commit and tag directly to `main`, branch
protection or repository rulesets must allow the GitHub Actions bot to update
`main` and create tags. If that is not allowed, the atomic push fails and
neither the version commit nor tag is published. Configure a narrowly scoped
exception for GitHub Actions rather than disabling branch protection.

For push events, the workflow intentionally skips commits that are not associated with one
merged pull request targeting `main`, and it skips non-release title types.
