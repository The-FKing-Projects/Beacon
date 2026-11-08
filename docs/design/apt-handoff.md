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
failing hook aborts.

### Isolated real-transaction experiments

The opt-in experiments in `tests/test_apt_hook_experiments.py` run real APT and
dpkg against a temporary dpkg root inside a rootless bubblewrap namespace. The
host filesystem is read-only except the test's temporary directory; package
fixtures have no maintainer scripts or payload, APT configuration and state are
isolated, and the namespace has no network. These are not host installations.
The experiments were run on amd64 using Ubuntu 26.04.1 (APT 3.2.1 / dpkg
1.23.7), Debian 12 container (APT 2.6.2 / dpkg 1.21.23), and Ubuntu 24.04
container (APT 2.8.3 / dpkg 1.22.6).

On each tested version, protocol v3 was delivered; a failing hook aborted a
new install and left the temporary dpkg status unchanged; a successful hook
allowed a real fixture install into the temporary root. The hook saw the old
and new version, architecture, and direction for a fixture upgrade and a
downgrade; rejecting it left the installed version unchanged. In a separate
two-package fixture, the hook received both archive paths before either package
was installed. A `Pre-Depends` fixture showed one hook invocation containing
both the dependency and dependent package actions; rejecting it left both
uninstalled. With `--no-remove` omitted in a fixture only, the hook saw the
solver's `**REMOVE**` action, rejected it, and left the dpkg status unchanged.
The fixture policy hook also rejected both forbidden action types when APT was
invoked without `--no-remove` and, for the downgrade experiment only,
`--allow-downgrades`. Those flags were used **only within the isolated
experiments** to demonstrate hook enforcement; they are not proposed
production options.

A separate two-hook experiment exposed an artifact-integrity limitation: the
first (observer) hook saw the selected version-1.0 local archive; a later
configured hook replaced its path with a version-9.0 archive, and dpkg installed
version 9.0. Thus the transaction list and archive path observed by one hook
do not bind the bytes ultimately read by dpkg if a later hook can mutate that
path. APT hooks run with package-manager privilege; this experiment is not a
defense against a malicious system administrator. It does show that a safe
design must control hook ordering and archive immutability, or revalidate at a
trusted final boundary, and must define which privileged system hooks it
preserves. Never assume a hook runs last merely because Beacon configured one.
Protocol v3 also includes APT's configuration space; a production hook must
parse only required fields and never log the raw protocol, which could contain
private configuration values.

An additional ordering probe used an APT-configured hook to replace the
archive, then appended a digest-checking hook to the `apt-get` command line.
The configured hook ran first; the final verifier saw the changed bytes,
rejected the transaction, and left the temporary dpkg status unchanged. APT's
`apt.conf(5)` documents that command-line options are applied after config
files and that `::` appends an item to a list. This suggests a way to retain
configured hooks while adding a final verifier, rather than clearing or
replacing the hook list. The probe covered one explicit `APT_CONFIG` hook and
one local APT version only. It does not prove ordering across every config
source, invocation path, or supported APT version, nor protect against an
independent privileged process changing the archive after verification.

This is encouraging but **not a proven enforcement solution**. The fixtures
do not establish that the hook always contains the complete transaction in
all solver and architecture cases, that all locks protect all relevant
inputs, or that a failing hook reverses earlier side effects. Downloads and
other hooks can run before it, and hooks can run after it. We have not proved
safe archive ownership and immutability, complete control of hook order while
preserving system integrations, fallback protocols, configuration handling,
dependency resolution, removal and multiarch cases, partial failures, or
behavior on every supported version. The fixture policy parser is test code,
not a production transaction verifier. A parser for simulation output is not
a substitute for enforcement.

To repeat the experiments on an amd64 system with bubblewrap, user namespaces,
APT, dpkg, and Python available:

```sh
BEACON_RUN_APT_HOOK_EXPERIMENTS=1 python3 -m unittest discover -s tests -p test_apt_hook_experiments.py -v
```

They are skipped by default and fail rather than falling back to an
unisolated install if namespace setup fails.

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
