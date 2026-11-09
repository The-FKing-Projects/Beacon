# Software Discovery Test Cases

These fixtures reflect APT and dpkg metadata inspected on 2026-11-07 and a
user-provided Kubuntu 26.04.1 snapshot from 2026-11-08, along with explicit
synthetic cases for source and package-state edge conditions. They exercise
package parsing without requiring network access or packages to be installed
in the test environment.

| Package | Observed evidence | Expected result |
| --- | --- | --- |
| `bash` | Installed version listed at `us.archive.ubuntu.com` | Ubuntu Repository, High |
| `steam` | Candidate from `repo.steampowered.com`; an older version is also listed in Ubuntu | Vendor Repository, High |
| `floorp` | Installed version listed at `ppa.floorp.app` | PPA, High |
| `clover-eye` | Installed version only in dpkg status; APT marks it local | Local .deb Candidate, Medium |
| `discord-ptb` | Installed version only in dpkg status; APT marks it local | Local .deb Candidate, Medium |
| `code-insiders` | Installed version `1.146.0-1794014368` listed at `packages.microsoft.com/repos/code` | Vendor Repository, High |
| `tailscale` | Installed version `1.104.5` listed at `pkgs.tailscale.com` | Vendor Repository, High |
| `beekeeper-studio` | Installed version `6.2.2` listed at `deb.beekeeperstudio.io` | Vendor Repository, High |
| `heroic` | dpkg status abbreviation is `rc` | Config Remains |
| `microsoft-edge-stable` | Not installed; APT cannot locate package in current cache | Unknown, Low |
| `brave-browser` | Not installed; APT cannot locate package in current cache | Unknown, Low |
| `orphan-candidate` | Synthetic installed/local policy fixture; no configured repository origin | Local .deb Candidate, Medium; not proven orphaned |

The `steam` result differs from the original candidate note in issue #9: the
selected candidate is provided by Steam's repository, while an older package
version is available from Ubuntu. Beacon should report the source of the
selected version, not any source listed for another version.

The user-provided snapshot contains three additional real vendor-repository
examples: Code Insiders, Tailscale, and Beekeeper Studio. In each case, the
installed version is present in current APT policy at the listed host.
`tailscale` and `beekeeper-studio` appear as `unknown` in `apt list --installed`
release labels, but their policy output still identifies the installed
version's repository; Beacon's source classification uses that version
origin, not the release label.

`microsoft-edge-stable` and `brave-browser` were not installed and APT could
not locate either package in the current cache. Their explicit tests assert
`Unknown`, not a positive vendor result. Synthetic fixtures separately verify
that representative Microsoft and Brave repository URLs classify as vendor
sources when such origins are actually present; they do not claim those
repositories or versions were observed on the user's system.

The `orphan-candidate` fixture represents an installed version available only
from dpkg status and marked `[installed,local]` by APT. This evidence supports
`Local .deb Candidate`, but does not prove the package is orphaned: the
original repository may have been removed, the package may have been
installed from a local archive, or the source may otherwise be unavailable.
By contrast, `heroic` has dpkg state `rc` and is classified as configuration
remaining, not installed software. A reproducible positive case for an
orphaned package, in the historical sense of an installed package formerly
provided by a now-removed repository, cannot be established from current
APT/dpkg metadata alone.

Run the deterministic fixtures with:

```sh
python3 -m unittest discover -s tests -v
```
