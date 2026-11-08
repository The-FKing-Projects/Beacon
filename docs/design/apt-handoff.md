# Future APT handoff: safety design

## Status

This is a proposal, not an implemented update or installation feature.
`--inspect` deletes its temporary download; it does not retain an artifact
for installation, check dependencies, or authorize an APT operation. An
installation workflow must be designed and reviewed separately.

## Trust and verification

- An approved GitHub repository is a user decision, not proof that its
  releases are authentic or that a `.deb` belongs to the installed package.
  Show the repository identity, release, asset name and URL, and evidence.
- The package name, architecture, and version inside a `.deb` are
  self-declared metadata. Matching them does not establish provenance,
  compatibility, or safety. Fail on mismatches and surface same-version,
  downgrade, and incomparable-version cases rather than silently proceeding.
- The current `SHA256SUMS` check detects a difference from the published
  manifest when an exact entry exists. It does not authenticate either file.
  The manifest and the asset can both be replaced by an attacker with access
  to the release. Report absent, malformed, ambiguous, and mismatched entries
  distinctly; do not describe an unsigned match as a verified publisher.
- A future stronger authenticity check needs an independently trusted key or
  digest and a documented verification method. Key discovery, trust,
  rotation, revocation, and what to do when no signed metadata exists remain
  open product decisions; do not assume all projects provide signatures.

## Proposed handoff requirements

1. Make download and installation separate, explicit user actions. Before
   requesting approval, show the selected source and exact release, asset,
   digest, package metadata, version change, and verification limitations.
   Do not automatically install a suggested asset or bypass a failed check.
2. Keep the approved artifact in a private location and bind approval to its
   bytes, package identity, source, and installed state. Recheck the digest,
   metadata, repository identity, and installed state immediately before
   handoff; reject changed or missing inputs. Define safe ownership,
   permissions, cleanup, and protection against file replacement before
   implementing privileged installation.
3. Use APT's supported local-package workflow for dependency resolution
   instead of executing the `.deb`, running arbitrary installer commands, or
   replacing the package manager. Preview APT's proposed dependency changes,
   removals, and upgrades; treat errors and unresolved dependencies as
   blockers. A simulation is advisory, not a guarantee: repositories and
   installed state can change before the real transaction.
4. Require a clear, fresh confirmation of the planned APT action after the
   preview and before requesting elevated privileges. Do not silently accept
   removals, downgrades, or other changes beyond what was shown. Decide how to
   handle APT's own interactive prompts, changing plans, and non-interactive
   sessions before implementation.
5. Explain that installation may execute package maintainer scripts with
   elevated privileges. Report APT failures and partial state accurately;
   never claim an installation succeeded based only on initiating a command.

## Decisions still needed

The minimum acceptable authenticity evidence, whether and how a user can
explicitly accept missing verification, handling of downgrades and dependency
removals, privilege escalation UX, and the precise APT invocation and preview
mechanism are not yet decided. The design must be tested on supported Debian
and Ubuntu versions, including interrupted operations and changed system state.

## Inspection examples

- CloverEye: installed `clover-eye:amd64` 0.1.1; release v0.1.0 asset
  `clovereye_0.1.0_amd64.deb` reported matching package and architecture,
  an older version, and a matching but unauthenticated `SHA256SUMS` entry.
- Caprine: installed `caprine:amd64` 2.61.0; release v2.61.0 asset
  `caprine_2.61.0_amd64.deb` reported matching package, architecture, and
  version. The release had no `SHA256SUMS` asset, so integrity was not
  verified. These observations are snapshots, not claims about future releases.
