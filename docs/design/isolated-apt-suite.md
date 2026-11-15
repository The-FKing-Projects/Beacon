# Isolated APT suite (operator / maintainer guide)

How to run Beacon’s real APT/dpkg handoff experiments safely. This is
documentation for the **v1.1.2-era** packaged helper and the polish stack that
sits on top of it. It does not change suite code.

Design and trust boundary details live in [APT handoff](apt-handoff.md).
Product validation overview:
[Compatibility and validation](../../README.md#compatibility-and-validation).

## What this suite is

| Suite | File | Default | Purpose |
| --- | --- | --- | --- |
| Deterministic regression | `tests/test_*.py` (most modules) | On in CI / local | Offline unit tests; no APT transactions |
| APT solver safety simulations | `tests/test_apt_safety_experiments.py` | On when discovered | Temporary package-state simulations; **not** host installs |
| Isolated real APT handoff | `tests/test_apt_hook_experiments.py` | **Opt-in** | Real `apt-get` / `dpkg` inside rootless Bubblewrap against a **temporary** dpkg root |

The isolated suite exercises protocol-v3 hooks, `--no-remove` behavior, and
the **packaged** privileged helper (`src/apt_handoff.py` / `/usr/lib/beacon/`
when installed). Fixtures are empty local `.deb` packages (no maintainer
scripts/payload of interest). The namespace has **no network**.

## Isolation requirements (never the host package DB)

Before enabling the opt-in suite:

1. **amd64** host with `bwrap`, `apt-get`, `dpkg`, `dpkg-deb`, and Python 3.10+.
2. **User namespaces** usable by Bubblewrap (CI may add a disposable AppArmor
   profile for `/usr/bin/bwrap`; do not copy that onto a personal host without
   review — see the `apt-handoff` job in
   [debian-package.yml](../../.github/workflows/debian-package.yml)).
3. The suite **fails closed** if Bubblewrap or prerequisites are missing; it
   must **never** fall back to installing into the host’s package database.
4. Host filesystem is bound **read-only** except the test temporary directory;
   package state under test is a temporary dpkg root inside the namespace.

Do **not** run these experiments as a substitute for upgrading third-party
packages on a desktop. Operator-reported Kubuntu installs are separate
evidence (see below).

## How to run

### Deterministic CI / local (safe default)

From the repo root — same pattern as
[discovery test cases](../research/discovery-test-cases.md) and package CI:

```sh
python3 -m unittest discover -s tests -v
```

This discovers the APT hook module but **skips** the real-transaction class
unless the opt-in environment variable is set.

Solver simulations (still not host installs):

```sh
python3 -m unittest discover -s tests -p test_apt_safety_experiments.py -v
```

### Opt-in isolated real transactions

Only on a machine that meets the isolation requirements:

```sh
BEACON_RUN_APT_HOOK_EXPERIMENTS=1 python3 -m unittest discover -s tests -p test_apt_hook_experiments.py -v
```

CI runs that command on a **native** Ubuntu 24.04 GitHub-hosted VM (not inside
the nested distro-matrix containers, which disallow Bubblewrap user
namespaces). The isolated step is a required release gate in the Debian
package workflow.

## Packaged helper and the v1.1.2 `/run` `noexec` fix

Production install path:

1. Unprivileged `--prepare` retains the exact selected artifact under user
   data (`$XDG_DATA_HOME/beacon/updates`).
2. `--install` revalidates, previews the APT plan, requires **fresh**
   confirmation, then invokes the packaged helper via
   `sudo -- /usr/bin/python3 /usr/lib/beacon/apt_handoff.py …`
   ([`updates.py`](../../src/updates.py)).
3. The helper stages under `/run/beacon/` (root-owned artifact + manifest) and
   appends a protocol-v3 `DPkg::Pre-Install-Pkgs` hook that runs the
   **packaged** helper — not a generated script copied into `/run`.
4. Staging on `/run` may be mounted `noexec`. v1.1.2 fixed the failure mode
   where a helper/hook path required executing a script from that mount
   (Kubuntu `stopgrade` upgrade; see
   [discovery qualification](../research/discovery-test-cases.md#kubuntu-2604-beacon-v112-operator-reported-summary)).
   Artifact bytes still live under `/run/beacon/`; execution stays on the
   packaged path under `/usr`.

The Debian package ships the helper but does **not** install a persistent APT
hook or take over APT/PPA-managed packages.

## Live discovery vs deterministic CI

| Kind | What it covers | What it does **not** authorize |
| --- | --- | --- |
| Deterministic unittest / package matrix | Parser, tracking, suggestions, digests, CLI smoke in containers | Live GitHub search results; third-party upgrades on a desktop |
| Isolated APT suite (this doc) | Fixture APT/dpkg handoff + helper hooks in Bubblewrap | Publisher authenticity; host installs; non-amd64 |
| Live discovery / Kubuntu notes | Operator workflows, homepage/tag/filename observations | Unattended install; treating digests as authenticity; new providers |

Keep temporary `XDG_*` state for exploratory discovery. Digests and
`SHA256SUMS` matches are integrity evidence only ([APT handoff](apt-handoff.md)).

## Cross-links

- [README — Compatibility and validation](../../README.md#compatibility-and-validation)
- [README — `--install` / helper summary](../../README.md) (Track a GitHub upstream)
- [APT handoff design](apt-handoff.md) (trust, limitations, historical qualification run)
- [Discovery / Kubuntu v1.1.2 summary](../research/discovery-test-cases.md#kubuntu-2604-beacon-v112-operator-reported-summary)
- [Stacked polish merge checklist](stacked-pr-merge-checklist.md) (post-merge smoke; no host APT installs)
- [Vendor download evaluation](vendor-download.md) (no provider in this track)

## Honesty limits

- Passing the isolated suite does not prove protection against root, a
  malicious administrator, or hostile privileged APT hooks.
- It does not replace dated operator qualification for third-party packages.
- This polish stack’s behavior PRs (`--check-all`, `+ds`/`+dfsg`, filename
  likely hints, homepage fragments) do **not** relax APT handoff gates; do not
  re-run the isolated suite against the host to “verify” those changes.
