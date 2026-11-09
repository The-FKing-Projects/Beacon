# Software Discovery Test Cases

These fixtures reflect APT and dpkg metadata inspected on 2026-11-07, along
with explicit synthetic cases for source and package-state edge conditions.
They exercise package parsing without requiring network access or packages to
be installed in the test environment.

| Package | Observed evidence | Expected result |
| --- | --- | --- |
| `bash` | Installed version listed at `us.archive.ubuntu.com` | Ubuntu Repository, High |
| `steam` | Candidate from `repo.steampowered.com`; an older version is also listed in Ubuntu | Vendor Repository, High |
| `floorp` | Installed version listed at `ppa.floorp.app` | PPA, High |
| `clover-eye` | Installed version only in dpkg status; APT marks it local | Local .deb Candidate, Medium |
| `discord-ptb` | Installed version only in dpkg status; APT marks it local | Local .deb Candidate, Medium |
| `heroic` | dpkg status abbreviation is `rc` | Config Remains |
| `microsoft-edge-stable` | Synthetic policy fixture: installed version at `packages.microsoft.com` | Vendor Repository, High |
| `brave-browser` | Synthetic policy fixture: installed version at `brave-browser-apt-release.s3.brave.com` | Vendor Repository, High |
| `orphan-candidate` | Synthetic installed/local policy fixture; no configured repository origin | Local .deb Candidate, Medium; not proven orphaned |

The `steam` result differs from the original candidate note in issue #9: the
selected candidate is provided by Steam's repository, while an older package
version is available from Ubuntu. Beacon should report the source of the
selected version, not any source listed for another version.

`microsoft-edge-stable` and `brave-browser` had no APT policy records in the
inspected cache, so they are not used as positive source-attribution fixtures.
The new synthetic fixtures verify that their representative vendor hosts are
classified correctly when APT does provide an origin for the installed
version. They do not claim those repositories or versions were present in the
inspected cache; without such evidence, these packages should remain unknown.

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
