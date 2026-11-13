# Software Discovery Outside dpkg

## Purpose

This research evaluates evidence about software installed through Flatpak,
Snap, AppImage files, standalone binaries, and custom installers. It informs
Beacon's classification of standalone `.deb` candidates and documents the
limits of other inventories; it is not a plan to duplicate their package
manager or Topgrade update workflows. It does not propose installing,
removing, or updating software from these sources.

## Findings

| Source | Inventory evidence | Source and version evidence | Main limitation |
| --- | --- | --- | --- |
| Flatpak | `flatpak list` reports installed applications and runtimes. Query both `--system` and `--user`; record installation scope. | The listing can include the application ID, origin remote, and installation. `flatpak info` provides details for an installed reference. | System, user, and any custom installations have distinct scope. An origin remote is evidence of the configured source, not a guarantee of upstream identity or current availability. |
| Snap | `snap list` reports installed snaps and their version, revision, tracking channel, and publisher. | `snap info <name>` provides additional snap metadata, including publisher and channel information. | Snapd must be available. The publisher identifies the Snap Store publisher, not necessarily the software's upstream project. |
| AppImage | Look for AppImage files only in user-selected or explicitly configured directories. Optional desktop integration may leave launcher entries. | The file may contain application metadata, but there is no shared installed-app registry or guaranteed source record. | An AppImage can be stored anywhere and may not be integrated into the desktop at all. A file search cannot prove that a file is still used or identify its upstream. |
| Standalone binaries | A bounded search of configured directories can find executable files. XDG application directories can provide launcher entries. | A desktop entry's `Exec` field identifies a launch command, not the installer or publisher. | There is no common inventory or provenance format. Executables may be scripts, utilities, wrappers, or stale files. |
| Custom installers | Use installer-specific records only when a supported installer exposes a documented inventory interface. | Installer metadata may identify a product or publisher, but formats vary by installer. | There is no general Linux installer registry; filenames and filesystem locations are not reliable proof of installation or origin. |

Flatpak's command reference documents system-wide and per-user installations,
installed-app listing, and app details. Snap's `snap list` and `snap info`
commands provide their own installed-package inventory and metadata. AppImages
are standalone bundles and do not require installation; desktop integration is
optional. The XDG specifications standardize data and desktop-entry locations,
but desktop entries describe launchers and are not an installation database.

## Recommendation

1. Keep APT/dpkg discovery and the standalone local `.deb` updater as Beacon's
   product scope. Beacon addresses packages with no configured repository or
   built-in updater; this complements, rather than replaces, normal package
   management.
2. Do not add Flatpak or Snap inventory/update adapters merely to reproduce
   capabilities already provided by those managers and Topgrade. If a
   concrete classification need arises, consult their documented read-only
   metadata without duplicating their update workflows or flattening their
   application identifiers into dpkg package names.
3. Treat AppImage files and desktop entries as weaker, independent evidence.
   Search only configured directories, and report a discovered file or
   launcher without claiming that it is installed, maintained, or updateable.
4. Defer general standalone-binary and custom-installer detection until Beacon
   defines explicit search roots or supported installer interfaces. Do not
   recursively scan the whole filesystem or infer provenance from filenames.
5. Keep discovery distinct from update operations. Beacon's standalone `.deb`
   workflow uses APT for the reviewed transaction; it does not recreate
   repository, Flatpak, or Snap updates. Any future integration with Topgrade
   should add only the standalone `.deb` gap and preserve Beacon's approval
   safeguards.

If a concrete classification need justifies a read-only adapter, it should
distinguish an unavailable manager, a failed inventory command, and an empty
inventory. A missing command or inaccessible scope is not evidence that no
software of that type is installed. Discovery should not execute binaries or
installers found during inventory.

## References

- [Flatpak Command Reference](https://docs.flatpak.org/en/latest/flatpak-command-reference.html)
- [Snap command reference](https://manpages.ubuntu.com/manpages/noble/man8/snap.8.html)
- [Running AppImages and desktop integration](https://docs.appimage.org/user-guide/run-appimages.html)
- [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir/0.8/)
- [Desktop Entry Specification](https://specifications.freedesktop.org/desktop-entry/latest/)

Research checked 2026-11-07.
