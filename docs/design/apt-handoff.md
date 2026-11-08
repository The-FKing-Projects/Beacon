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
  rotation, and revocation remain open product decisions; do not assume all
  projects provide signatures.

## Reviewed product decisions

- When independent authenticity verification is unavailable, Beacon may
  proceed only after a clear warning and explicit user approval. An unsigned
  checksum from the same release does not establish authenticity. This
  exception does not override a failed or mismatched verification check.
- Block an APT handoff if the proposed dependency plan removes other installed
  packages, and show the proposed removals. Do not silently proceed even if
  the user approved an earlier plan.
- Block downgrades: an asset older than the installed package must not be
  handed off for installation.

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
   blockers. Block plans that remove installed packages. A simulation is
   advisory, not a guarantee: repositories and installed state can change
   before the real transaction. The implementation must prevent a changed
   real plan from bypassing the removal restriction, not rely on preview
   alone.
4. Require a clear, fresh confirmation of the planned APT action after the
   preview and before requesting elevated privileges. Block removals and
   downgrades; do not silently accept other changes beyond what was shown.
   Decide how to handle APT's own interactive prompts, changing plans, and
   non-interactive sessions before implementation.
5. Explain that installation may execute package maintainer scripts with
   elevated privileges. Report APT failures and partial state accurately;
   never claim an installation succeeded based only on initiating a command.

## Decisions still needed

The acceptable forms of independent authenticity evidence, how to present
approval for missing verification, handling same-version reinstalls and
incomparable versions, privilege escalation UX, and the precise APT invocation
and preview mechanism are not yet decided. The design must be tested on
supported Debian and Ubuntu versions, including interrupted operations and
changed system state.

## APT investigation and release gate

The documented `apt-get --simulate` mode does not lock the package state.
The installed system, repository metadata, and configuration may therefore
change after a preview. An unprivileged simulation may also lack access to
some APT configuration. A preview is informational and is not an approval
token or a guarantee of the eventual transaction.

`apt-get --no-remove` documents that it aborts when its plan includes package
removal. It is an important independent guard for the real APT invocation,
but it does not ensure the remaining actions match the approved preview.
The documented `--allow-downgrades` option controls whether APT prompts in
certain situations; omitting it is not a general no-downgrade guarantee.
Rejecting an older selected `.deb` also does not by itself prove the solver
cannot downgrade another package. Avoid automatic yes and dangerous override
options; account for inherited APT configuration and hooks.

An isolated APT 3.2.1 / dpkg 1.23.7 simulation experiment using temporary
package state and locally built fixture archives found:

- A conflict caused a removal in the preview; `--no-remove` rejected it.
- A downgrade was still present in a successful `--no-remove` simulation.
- Adding a conflicting installed package after a clean preview changed the
  subsequent plan; `--no-remove` rejected that changed removal plan.

These are solver simulations, not real installations or proof for other APT
versions. Repeat the isolated experiments with the command below; they do not
modify the host package database.

```sh
python3 -m unittest discover -s tests -p test_apt_safety_experiments.py -v
```

APT also documents a `DPkg::Pre-Install-Pkgs` hook protocol with package
actions, old/new versions and (in protocol version 3) architectures; a
failing hook aborts. This is a **possible research path**, not a proven
solution. Before relying on it, establish the exact transaction boundary,
locking, complete action and archive identities, protocol/version support,
ordering with other hooks, failure behavior, local-file immutability, and
interactions with APT/dpkg configuration across supported distributions. A
simulation output parser alone is not a substitute for enforcement.

**Release gate:** do not implement an automated APT handoff until a tested
mechanism can bind the approved artifact and complete transaction to the
actual privileged operation, block all removals and downgrades, and abort on
changed or unverifiable plans. Until then, Beacon may inspect and report but
must not claim to enforce an installation plan.

References: [apt-get(8)](https://manpages.debian.org/bookworm/apt/apt-get.8.en.html)
and [apt.conf(5)](https://manpages.debian.org/bookworm/apt/apt.conf.5.en.html).

## Inspection examples

- CloverEye: installed `clover-eye:amd64` 0.1.1; release v0.1.0 asset
  `clovereye_0.1.0_amd64.deb` reported matching package and architecture,
  an older version, and a matching but unauthenticated `SHA256SUMS` entry.
- Caprine: installed `caprine:amd64` 2.61.0; release v2.61.0 asset
  `caprine_2.61.0_amd64.deb` reported matching package, architecture, and
  version. The release had no `SHA256SUMS` asset, so integrity was not
  verified. These observations are snapshots, not claims about future releases.
