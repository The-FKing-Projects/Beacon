# Stacked polish + design PR merge checklist

Snapshot of the open GitHub stack on
[The-FKing-Projects/Beacon](https://github.com/The-FKing-Projects/Beacon)
as verified when this note was written. **Docs only** — does not cut a
release or change CLI behavior.

## Verified open stack (bottom → top)

| Order | PR | Branch (head) | Bases on | Kind |
| ---: | --- | --- | --- | --- |
| 1 | [#40](https://github.com/The-FKing-Projects/Beacon/pull/40) | `cursor/reconcile-post-v1-roadmap-6a31` | `main` | Docs |
| 2 | [#41](https://github.com/The-FKing-Projects/Beacon/pull/41) | `cursor/expand-discovery-qualification-cases-6a31` | #40 | Docs |
| 3 | [#43](https://github.com/The-FKing-Projects/Beacon/pull/43) | `cursor/document-version-comparison-rules-6a31` | #41 | Docs |
| 4 | [#44](https://github.com/The-FKing-Projects/Beacon/pull/44) | `cursor/normalize-homepage-url-fragments-6a31` | #43 | Behavior |
| 5 | [#45](https://github.com/The-FKing-Projects/Beacon/pull/45) | `cursor/conservative-version-comparison-6a31` | #44 | Behavior |
| 6 | [#46](https://github.com/The-FKing-Projects/Beacon/pull/46) | `cursor/add-check-all-command-6a31` | #45 | Behavior |
| 7 | [#47](https://github.com/The-FKing-Projects/Beacon/pull/47) | `cursor/flexible-asset-filename-matching-6a31` | #46 | Behavior |
| 8 | [#48](https://github.com/The-FKing-Projects/Beacon/pull/48) | `cursor/vendor-download-design-eval-6a31` | #47 | Docs (design) |
| 9 | [#49](https://github.com/The-FKing-Projects/Beacon/pull/49) | `cursor/github-desktop-tag-comparison-design-6a31` | #48 | Docs (design) |
| 10 | This checklist PR | `cursor/stacked-pr-merge-checklist-6a31` | #49 | Docs |

There is **no #42** in this stack. Re-verify with GitHub before merging if
branches were retargeted.

## Docs-only vs behavior

**Docs / design (no CLI behavior):** #40, #41, #43, #48, #49, and this
checklist PR.

**Behavior (ship together if cutting a release from this stack):**

| PR | Change (one line) |
| --- | --- |
| #44 | Homepage URL fragments (`#readme`) ignored for `--suggest` ranking |
| #45 | `--check` ignores installed upstream `+ds` / `+dfsg` markers |
| #46 | Read-only `beacon --check-all` summary for tracked packages |
| #47 | Broader conservative `.deb` filename “likely” hints (Feishin / Moonfin-style) |

Design PRs #48 / #49 document vendor-download and GitHub Desktop–style tag
comparison **without** enabling those features.

## What can land only after parents

- Merge **strictly bottom → top** (#40 → … → checklist). Each PR’s base is
  the previous head; merging out of order will fight GitHub’s stack bases.
- Behavior PRs **#44–#47** depend on the docs context in #40–#43 only for
  review narrative; mechanically they still sit above those docs PRs and
  should not be squash-merged onto `main` ahead of their parents without
  restacking.
- **#48 / #49** assume filename-matching and earlier polish are already in
  the branch history they document; land them after #47 (or restack if #47
  is dropped).
- Do **not** implement vendor-download or Desktop-style parsers from #48/#49
  in the same merge wave — those notes are evaluation-only.

If a middle PR is closed without merging, restack every child onto the new
parent head (rebase + lease-push bottom-up) before merging further.

## Post-merge smoke notes (no host APT install tests)

After the stack (or any contiguous prefix) reaches `main`, validate with
**local / CI-style** commands only. Do **not** run real third-party
`--install` against the host package database.

From the repo root (same discovery pattern as
[discovery test cases](../research/discovery-test-cases.md) and package CI):

```bash
python3 -m unittest discover -s tests -v
```

Optional narrower checks after behavior merges:

```bash
python3 -m unittest tests.test_tracking -v
python3 -m unittest tests.test_suggestions -v
```

If Beacon’s Debian package is already installed on a throwaway machine,
read-only CLI smoke (no prepare/install):

```bash
beacon --help
beacon --tracked
beacon --check-all
```

CI remains authoritative for the matrix and isolated APT handoff jobs
described under [Compatibility and validation](../../README.md#compatibility-and-validation).
Skip host Bubblewrap APT experiments unless following
[isolated APT suite](isolated-apt-suite.md) / [APT handoff](apt-handoff.md)
isolation rules (opt-in `BEACON_RUN_APT_HOOK_EXPERIMENTS=1` only; never the
host package database).

## Suggested version bump / release notes (draft only)

**Do not cut a release from this note.** If maintainers later ship the
behavior PRs (#44–#47) together on top of the docs stack, a reasonable draft
is:

- **Suggested bump:** patch or minor at maintainer discretion (new
  `--check-all` surface + comparison/heuristic tweaks; no provider expansion).
  Current stable at stack start: **v1.1.2**.
- **Draft release-notes bullets:**
  - Ignore `#fragment` on package homepage URLs when ranking `--suggest`
    matches (e.g. Caprine `#readme`).
  - Compare `--check` upstream versions when the installed side uses Debian
    `+ds` / `+dfsg` repack markers; other unknown shapes stay unknown.
  - Add read-only `beacon --check-all` to summarize tracked packages without
    preparing or installing.
  - Broaden conservative release-asset filename “likely” hints for
    product-`linux`-arch and amd64-only product-`Linux`-version names;
    exact asset selection remains required.
  - Docs: reconciled post-v1 roadmap, Kubuntu qualification notes, version
    comparison operator rules, vendor-download evaluation, and GitHub
    Desktop–style tag-comparison evaluation (no new providers; no Desktop
    tag parser).

Omit #48/#49 from “Features” if the release is code-focused; keep them under
Documentation / Research.

## Related

- [Version comparison](version-comparison.md)
- [Vendor download evaluation](vendor-download.md)
- [GitHub Desktop–style tag comparison](github-desktop-tag-comparison.md)
- [Discovery test cases](../research/discovery-test-cases.md)
