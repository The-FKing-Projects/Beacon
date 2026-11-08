# Software Discovery Test Cases

These fixtures reflect APT and dpkg metadata inspected on 2026-11-07. They
exercise package parsing without requiring network access or packages to be
installed in the test environment.

| Package | Observed evidence | Expected result |
| --- | --- | --- |
| `bash` | Installed version listed at `us.archive.ubuntu.com` | Ubuntu Repository, High |
| `steam` | Candidate from `repo.steampowered.com`; an older version is also listed in Ubuntu | Vendor Repository, High |
| `floorp` | Installed version listed at `ppa.floorp.app` | PPA, High |
| `clover-eye` | Installed version only in dpkg status; APT marks it local | Local .deb Candidate, Medium |
| `discord-ptb` | Installed version only in dpkg status; APT marks it local | Local .deb Candidate, Medium |
| `heroic` | dpkg status abbreviation is `rc` | Config Remains |

The `steam` result differs from the original candidate note in issue #9: the
selected candidate is provided by Steam's repository, while an older package
version is available from Ubuntu. Beacon should report the source of the
selected version, not any source listed for another version.

`microsoft-edge-stable` and `brave-browser` had no APT policy records in the
inspected cache, so they are not used as positive source-attribution fixtures.
They should remain unknown unless a configured repository provides evidence.
Orphaned-package examples remain unvalidated.

Run the deterministic fixtures with:

```sh
python3 -m unittest discover -s tests -v
```
