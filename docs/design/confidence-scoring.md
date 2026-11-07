# Confidence Scoring Design

## Purpose

Beacon should show the evidence behind package source classifications and make
uncertainty visible rather than presenting every result as definitive.

## User-Facing Representation

Package inspection reports:

- A source category
- A numeric score from 0 to 100
- A descriptive confidence label
- A short explanation of the evidence used

Confidence bands:

| Score | Label |
| --- | --- |
| 75-100 | High |
| 40-74 | Medium |
| 0-39 | Low |

Beacon only assigns a source category when it has source or local-install
evidence. Otherwise, the source is `Unknown`.

## Current Evidence Rules

Beacon inspects the exact installed version when a package is installed, or the
candidate version otherwise. Repository URLs for other available versions do
not establish the source of the installed version.

| Evidence | Source | Score |
| --- | --- | --- |
| Selected version has a PPA URL | PPA | 90 |
| Selected version has an official Ubuntu URL | Ubuntu Repository | 90 |
| Selected version has an official Debian URL | Debian Repository | 90 |
| Selected version has another repository URL | Vendor Repository | 90 |
| APT marks the installed package `[installed,local]` with no selected-version repository URL | Local .deb Candidate | 65 |
| Selected installed version appears only in `/var/lib/dpkg/status` | Local .deb Candidate | 55 |
| No repository URL or local-install signal | Unknown | 0 |

If the selected version is listed in more than one repository type, Beacon
reports `Multiple Sources`, caps confidence at 45, and explains the conflicting
source types.

## Limitations

APT metadata can show that a version is available from a repository, but it
does not always prove which mirror or repository supplied the installed
artifact. Local package results are therefore labeled as candidates, not
confirmed local `.deb` installations. The scores are evidence grades, not
statistical probabilities.

## Follow-Up

Homepage, maintainer, upstream repository, and version-match signals are not
included in the current score. They can be added when Beacon has reliable,
tested sources for those signals.

Related issues:

- #8 Design confidence scoring system
- #12 Design package provenance confidence scoring
