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

The release workflow requests `contents: write`, `pull-requests: read`, and
`actions: write` (to dispatch APT publication after uploading the package). In
**Settings → Actions → General → Workflow permissions**, allow workflows to
write repository contents.

Because the workflow pushes a version commit and tag directly to `main`, branch
protection or repository rulesets must allow the GitHub Actions bot to update
`main` and create tags. If that is not allowed, the atomic push fails and
neither the version commit nor tag is published. Configure a narrowly scoped
exception for GitHub Actions rather than disabling branch protection.

For push events, the workflow intentionally skips commits that are not associated with one
merged pull request targeting `main`, and it skips non-release title types.

## Self-hosted APT publishing

After uploading a `.deb` to GitHub Releases, both **Release** and **Publish
Debian package** dispatch **Publish to aptly** when the repository Actions variable
`APTLY_PUBLISH_ENABLED` is exactly `true`. GitHub publication remains available
when this variable is unset or `false`. A dispatch failure fails the originating
workflow; publication runs separately and its success or failure appears under
**Publish to aptly**. Neither failure rolls back the GitHub Release.

The server workflow accepts only `workflow_dispatch`, only from `main`, and
only in `The-FKing-Projects/Beacon`. There is no `workflow_call`,
`pull_request`, `pull_request_target`, `issue_comment`, or push trigger on that
workflow. Fork copies are rejected by the repository guard. GitHub-hosted
release jobs dispatch it after the asset is ready, including for automatic
releases originating from a main-branch push. The server job's event is always
`workflow_dispatch`; arbitrary pushes cannot invoke it directly.

The aptly job downloads the exact release asset
`beacon_<version>-1_all.deb`, checks its package name, version, and architecture
without installing it, then runs:

```sh
aptly repo add fkingprojects /temporary/path/to/beacon_<version>-1_all.deb
aptly publish update -batch=true -skip-signing=false stable .
```

This updates the existing root-prefix publication: distribution `stable`,
component `main`, architectures `all, amd64`. Aptly preserves the existing
publication settings. Signing uses the server account's configured default
key, with no passphrase prompt; no private key is exported to GitHub.
Apache and Cloudflare Tunnel continue serving aptly's existing public
directory at <https://repo.fkingprojects.org>. No inbound upload API, SSH access,
or tunnel changes are needed.

### Server setup

1. In the organization's **Settings → Actions → Runners**, register the Linux
   runner `FK04-SERVER` with the custom label `fkingprojects-apt` (in addition
   to the default `self-hosted`, `Linux`, and `X64` labels). Runner labels are
   case-insensitive. Ensure its runner group grants this repository access;
   public repositories may require an explicit group setting.
2. Run its service as `github-runner` with access through the `aptly` group to
   the existing aptly repository and signing key. Ensure its `HOME`, aptly
   configuration, and GPG environment match
   that account's working interactive setup. The account needs write access to
   aptly's database, package pool, and published directory. It does not need
   root access or passwordless sudo.
3. Install `gh`, `dpkg-deb`, `aptly`, and `flock` on the runner and ensure they
   are on the service's `PATH`. `dpkg-deb` comes from `dpkg`; `flock` comes
   from `util-linux`. The runner needs outbound access to GitHub and release
   downloads. The workflow supplies a short-lived, read-only `GH_TOKEN`; do
   not configure a personal token or copy signing keys into Actions secrets.
4. As that account, confirm `aptly repo show fkingprojects` and
   `aptly publish show stable .` identify the intended repository/publication.
   Confirm `aptly publish update -batch=true -skip-signing=false stable .`
   succeeds unattended and Apache still serves the updated signed metadata.
   This command republishes the current repository; it does not add packages.
5. Only after the runner is online and the account is ready, create the
   repository Actions variable `APTLY_PUBLISH_ENABLED` with value `true`.

Use a runner dedicated to trusted release work. A self-hosted runner executes
workflow code with its account's privileges, including access to the signing
key. Never route untrusted pull request jobs to this runner; restrict runner
group access to trusted workflows where your GitHub plan supports it, protect
`main` and workflow changes, and use an isolated host/account where practical.
The publishing job itself does not check out or execute release-tag code and
only runs from `main`, but these safeguards do not replace runner isolation.
The runner label is routing, not an access-control boundary: other workflows
must not target this runner, and runner groups should enforce that restriction
where available. `FK04-SERVER` runs as a systemd service under `github-runner`,
so publication does not depend on an open terminal.

### Retries and coordination

To publish an existing release or retry APT publication without rebuilding or
bumping the version, dispatch **Publish to aptly** from `main`:

```sh
gh workflow run publish-aptly.yml --ref main -f tag=v0.8.0
```

Use the actual existing release tag. The enablement variable also gates this
manual workflow. Alternatively, rerun failed jobs in the **Publish to aptly** run.
An identical package already added to aptly can be republished. The workflow
does not force-replace conflicting package contents or disable signing; a
conflict or signing failure requires investigation, not an unsigned fallback.
To change an already published package, release a new version instead of
overwriting its `.deb`.

Updates take an exclusive lock at
`$HOME/.cache/beacon-aptly-publish.lock` across both aptly commands, waiting up
to ten minutes. All publishing runners must use the same account, home, and
filesystem for this lock to coordinate them. Other server-side automation or
manual repository mutations must take the same lock; do not modify this
repository concurrently outside it. Each job has a fifteen-minute timeout.
Downloads are temporary and removed when the shell exits normally or on error.
