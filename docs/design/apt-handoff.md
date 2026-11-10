# APT handoff safety design

## Status

The bounded APT handoff described here is implemented in the CLI as
`--prepare` and `--install`. The deterministic suite, isolated real APT
transactions, Debian package build, and installed-CLI smoke test have passed
in containers for all five declared Debian/Ubuntu targets.

The trust boundary is explicit: Beacon downloads and prepares packages as the
user, and the privileged helper copies the selected bytes into a root-owned
staging directory before asking APT to install them. Root, the administrator,
and root-run APT hooks are trusted. The implementation protects the staged
artifact and transaction policy from unprivileged changes; it does not protect
against a malicious administrator or promise universal rollback.

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

## Handoff policy

1. `--prepare` downloads only the exact user-selected release asset. It
   verifies package name, exact architecture, version direction, and any
   exact `SHA256SUMS` entry; a mismatched checksum blocks preparation. Missing
   or matching-but-unauthenticated checksum evidence is displayed explicitly.
   The artifact and its source/release identity, digest, metadata, and prior
   installed version are retained in private user storage.
2. `--install` revalidates the confirmed repository ID/name, selected release
   and asset URL, checksum evidence, artifact digest and package metadata,
   APT ownership, and installed package state. It previews the complete APT
   transaction and requires fresh confirmation after showing all package
   changes. Removals, downgrades, ambiguous identities, and changed state are
   blockers.
3. After approval, Beacon invokes a root-owned helper through `sudo`. The
   helper rechecks package and installed-state identity, copies the artifact
   into a root-owned, non-writable staging directory, and runs APT's supported
   local-package workflow with `--no-remove`. A command-line-appended
   protocol-v3 pre-install hook compares the actual action set to the
   approved plan and rejects removals, downgrades, unsupported actions, or a
   changed/missing selected archive. APT errors are reported with the observed
   package state; partial system changes are possible and no rollback is
   promised.
4. The parent verifies the installed package name, architecture, and version
   after APT returns success. The package's maintainer scripts execute with
   root privileges; only install packages whose publisher and contents you
   trust.

The Debian package contains the privileged helper but does not add a
persistent APT hook, install any upstream asset automatically, or change
configured APT repositories. Direct Nala support, Topgrade integration, and
GUI work remain out of scope.

## Accepted limitations

The selected asset and an unsigned checksum published alongside it do not
authenticate a publisher. If independent authenticity evidence is missing,
Beacon warns and requires explicit approval; a failed check always blocks.
Same-version reinstalls require the same fresh approval, and uncomparable
versions are blocked. APT remains responsible for dependency resolution and
installation.

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

An additional ordering probe configured hooks in the `APT_CONFIG` file, an
APT config fragment, and the main config file. The `APT_CONFIG` hook replaced
the archive; all three hooks ran in configuration order, then a digest-checking
hook appended to the `apt-get` command line rejected the changed bytes before
dpkg, leaving the temporary status unchanged. APT's `apt.conf(5)` documents
that command-line options are applied after config files and that `::` appends
an item to a list. This suggests a way to retain hooks from these config
sources while adding a final verifier, rather than clearing or replacing the
hook list. The probe used one local APT version and a controlled configuration;
the same configuration-chain experiment also passed on Debian 12 (APT 2.6.2 /
dpkg 1.21.23) and Ubuntu 24.04 (APT 2.8.3 / dpkg 1.22.6), in addition to the
local Ubuntu environment (APT 3.2.1 / dpkg 1.23.7). This does not prove
ordering across every invocation path or supported APT version, nor protect
against an independent privileged process changing the archive after
verification.

The final hook is not an atomic boundary with dpkg. A deterministic fixture
had the final verifier hash the approved archive successfully, then replace
the archive before returning success. APT proceeded and dpkg installed the
replacement version on all three tested APT versions. This models the
post-verification race directly: a digest check only describes the bytes read
at check time. APT's hook protocol passes archive paths, not an already-open
file descriptor that binds the verified bytes to dpkg's later read. A
concurrent process with permission to modify the archive can create the same
gap, although protecting against a malicious privileged administrator is
outside any ordinary package transaction's trust boundary.

The protocol experiments do not establish atomic binding between the bytes
checked by the final hook and dpkg's later read. The production helper closes
the unprivileged race by copying into root-owned, non-writable staging; the
remaining race requires a privileged actor or hook and is within the accepted
trust boundary. The production hook rejects changed plans at APT's handoff
point, and an isolated real-transaction test exercises the helper itself.
Neither mechanism protects against a malicious administrator or guarantees
rollback after failures.

To repeat the experiments on an amd64 system with bubblewrap, user namespaces,
APT, dpkg, and Python available:

```sh
BEACON_RUN_APT_HOOK_EXPERIMENTS=1 python3 -m unittest discover -s tests -p test_apt_hook_experiments.py -v
```

They are skipped by default and fail rather than falling back to an
unisolated install if namespace setup fails.

**Qualification record:** the deterministic suite, 17 opt-in isolated
real-transaction tests, binary package build, helper packaging check, and
installed-CLI smoke test passed on Debian 12, Debian 13, Ubuntu 22.04,
Ubuntu 24.04, and Ubuntu 26.04 in amd64 Podman containers. The Debian package
workflow runs the same matrix checks and requires the isolated tests; its
results remain the CI release gate. Tests are opt-in for local runs:

```sh
BEACON_RUN_APT_HOOK_EXPERIMENTS=1 python3 -m unittest discover -s tests -p test_apt_hook_experiments.py -v
```

The suite must fail closed if bubblewrap or namespace isolation is unavailable;
it must never fall back to a host installation. The isolated tests use bubblewrap and do not modify the host package
database. They do not prove protection against root, a malicious administrator,
or privileged APT hooks.

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
