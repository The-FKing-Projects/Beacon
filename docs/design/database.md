# Local Tracking Storage Design

## Status and scope

This is the broader proposed MVP design for issue #4. Beacon now implements a
smaller manual GitHub tracking store, but the schema and discovery persistence
described below are not implemented. The current store records a package name
and architecture and one explicitly confirmed GitHub repository name and ID;
it does not record candidate evidence, rejected decisions, or scan snapshots.
The `--untrack` command explicitly removes one confirmed association after
confirmation, including for packages no longer installed. It resolves against
saved records, requires an architecture when ambiguous, and refuses deletion
if the selected repository identity changed during confirmation.

The store keeps the latest successful package observation, proposed upstream
repositories, and explicit user decisions. Package provenance and upstream
identity are separate: an APT repository is not necessarily the software's
upstream project. Scores are evidence grades, not probabilities.

## Storage choice

Use **SQLite**, accessed through Python's standard-library `sqlite3` module.
Transactions, uniqueness constraints, and foreign keys protect decisions when
scans update observations; multiple processes do not need to rewrite an entire
file. JSON is easier to inspect manually but needs additional locking and
atomic-write handling as records grow; YAML also requires an extra dependency.
SQLite is less convenient to edit by hand, so a future CLI should show and
change records without requiring direct SQL.

The per-user default is `$XDG_STATE_HOME/beacon/tracking.sqlite3`, or
`~/.local/state/beacon/tracking.sqlite3` when `XDG_STATE_HOME` is unset or
empty. Follow the XDG rule that configured paths must be absolute; reject an
invalid relative path with a clear error. No system-wide store, credentials,
package contents, or update automation is included in this design.

## Proposed expanded schema

The schema below is a future design, not the current deployed database. The
manual tracking store uses `PRAGMA user_version = 1` with a `tracked_packages`
table. Migrating it to this expanded schema will require a new version and a
backup-preserving migration that retains existing confirmed associations.
The current implementation validates all four version-1 columns, their types,
nullability, and composite primary key, rejects unexpected user schema objects,
checks SQLite integrity, and validates saved package/architecture/repository
identities. An unversioned database containing a view is not an empty store.
Failures close the connection and report the path without resetting existing
data; no migration or automatic repair is performed.
All timestamps are UTC RFC 3339 strings. JSON columns contain UTF-8 JSON text,
validated by Beacon on read and write; they are not SQLite JSON-extension
requirements. `PRAGMA foreign_keys = ON` is required on **every connection**.

```sql
CREATE TABLE software (
    id INTEGER PRIMARY KEY,
    backend TEXT NOT NULL,               -- initially "dpkg"
    scope TEXT NOT NULL,                 -- initially "system"
    package_name TEXT NOT NULL,          -- exact name, without :architecture
    architecture TEXT NOT NULL,          -- dpkg architecture, e.g. amd64 or all
    state TEXT NOT NULL,                 -- installed, config_remains, etc.
    installed_version TEXT,              -- NULL if not installed
    observed_at TEXT NOT NULL,
    UNIQUE (backend, scope, package_name, architecture)
);

CREATE TABLE package_provenance (
    software_id INTEGER PRIMARY KEY REFERENCES software(id) ON DELETE RESTRICT,
    selected_version TEXT,               -- installed version, else APT candidate
    version_kind TEXT NOT NULL,           -- installed, candidate, or unknown
    source TEXT NOT NULL,                 -- Beacon classification, or Unknown
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    evidence_json TEXT NOT NULL,          -- JSON array of evidence strings
    observed_at TEXT NOT NULL
);

CREATE TABLE upstream_candidate (
    id INTEGER PRIMARY KEY,
    software_id INTEGER NOT NULL REFERENCES software(id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,              -- initially "github"
    repository_key TEXT NOT NULL,        -- canonical lower-case owner/name
    repository_url TEXT NOT NULL,
    provider_repository_id TEXT,         -- GitHub ID as text, when known
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    evidence_json TEXT NOT NULL,          -- JSON array of sourced evidence objects
    is_fork INTEGER CHECK (is_fork IN (0, 1) OR is_fork IS NULL),
    is_archived INTEGER CHECK (is_archived IN (0, 1) OR is_archived IS NULL),
    observed_at TEXT NOT NULL,
    UNIQUE (software_id, provider, repository_key),
    UNIQUE (software_id, provider, provider_repository_id)
);

CREATE TABLE upstream_decision (
    candidate_id INTEGER PRIMARY KEY
        REFERENCES upstream_candidate(id) ON DELETE RESTRICT,
    software_id INTEGER NOT NULL REFERENCES software(id) ON DELETE RESTRICT,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    decided_at TEXT NOT NULL,
    FOREIGN KEY (candidate_id, software_id)
        REFERENCES upstream_candidate(id, software_id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX upstream_candidate_identity
    ON upstream_candidate(id, software_id);
CREATE UNIQUE INDEX one_approved_upstream_per_software
    ON upstream_decision(software_id) WHERE decision = 'approved';
```

`repository_key` is a case-folded GitHub `owner/name` after the API resolves
the canonical repository. `repository_url` keeps the canonical display URL;
the optional provider ID helps recognize GitHub renames. A NULL provider ID
does not identify a repository and must not be used for deduplication.
`upstream_candidate.evidence_json` records each signal's type, observed
value, and source, rather than only a score; fork and archive flags are
nullable when unavailable.

For example, `package_provenance.evidence_json` might be
`["The selected installed version is listed at https://example.test/apt."]`;
an upstream candidate's `evidence_json` might contain
`[{"type":"homepage","value":"https://github.com/example/project","source":"package metadata"}]`.
These examples show the shape of stored evidence, not a claim about a real
package or repository.

No `upstream_decision` row means **unreviewed**, not rejected. A user can
reject several candidates, but can approve at most one for a software record.
Approval is attached to a specific candidate identity, not to a package name
or score. Only an approved match may be used for future upstream tracking;
discovery does not install, remove, or update packages.

`package_provenance.score` and `upstream_candidate.score` are independent.
Their evidence and observation times must not be combined into one score.
`installed_version` is distinct from `selected_version`: an available but
uninstalled package has no installed version.

## Update and failure rules

1. A successful discovery upserts the exact backend/scope/name/architecture
   record and replaces its latest package observation and provenance together
   in one transaction. Backend and scope are part of the identity so future
   managers or user-level installations do not collide with dpkg.
2. Upsert candidates by provider and canonical identity. Match a known GitHub
   repository ID first, so a rename updates the existing candidate rather
   than losing its decision. If identities conflict or cannot be reconciled,
   report the ambiguity and leave existing decisions unchanged.
3. Discovery never changes approval or rejection. Replacing an approval is an
   explicit user action in a transaction: clear the old approval, then approve
   the chosen candidate. Rejection, revocation, and removal must likewise be
   explicit.
4. An incomplete scan, failed command, failed GitHub request, or missing
   scope must not be recorded as an empty successful result. Preserve the last
   successful observations and decisions, and report the failure. A successful
   scan that no longer finds a package or candidate must not automatically
   delete the existing record or approval; mark stale only after defining a
   trustworthy absence signal.
5. Readers see either the old or the complete new transaction. Surface lock,
   disk, permissions, malformed-data, and migration errors; never silently
   replace an existing database or fabricate an empty inventory.

The schema reserves room for future backends but does not define discovery
behavior for Flatpak, Snap, or standalone binaries. Version 1 stores the latest
observation rather than a history; audit history and stale-record handling are
future work.

## Schema versioning and migration

On open, enable foreign keys, read `user_version`, and create the current
manual-tracking version only for a genuinely new, empty database. Reject
unrecognized or newer versions without modifying them.
For a supported older version, back up the existing database with SQLite's
backup API before migration, then apply sequential migrations and update
`user_version` in a transaction. If a backup or migration fails, report the
error and preserve the original database; verify foreign keys and data
invariants before committing. Never overwrite an existing backup silently.

A future migration to another storage engine should read a consistent SQLite
backup, retain stable software/candidate identities and all user decisions,
and verify the converted data before switching the active store. Keep the
backup until the user can confirm the migration.

## Implementation acceptance cases

- Two architectures of the same dpkg package and two backend/scope identities
  remain separate.
- A candidate with no decision remains unreviewed; rejecting it never approves
  a different candidate, and only one approval per software record is allowed.
- A successful rescan updates evidence without erasing an approval; a failed or
  incomplete rescan preserves the previous successful snapshot.
- A GitHub rename with the same provider ID retains its decision; an ambiguous
  identity produces an error instead of silently reassigning it.
- Concurrent writers do not lose updates; interrupted writes and failed
  migrations preserve existing data.
- Unknown schema versions, inaccessible paths, corrupt JSON, and invalid
  scores produce visible errors.

## References

- [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir/0.8/)
- [Python `sqlite3` backup API](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup)
- [SQLite foreign key support](https://www.sqlite.org/foreignkeys.html)
- [SQLite `user_version` pragma](https://www.sqlite.org/pragma.html#pragma_user_version)
- [GitHub repository matching research](../research/github-repository-matching.md)
- [Source classification model](../research/source-classification.md)
