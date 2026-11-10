"""Opt-in real dpkg experiments in a rootless, read-only-host namespace."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(
    os.environ.get("BEACON_RUN_APT_HOOK_EXPERIMENTS") == "1",
    "Set BEACON_RUN_APT_HOOK_EXPERIMENTS=1 to run isolated APT transactions",
)
class AptHookExperiments(unittest.TestCase):
    def setUp(self):
        missing = [
            tool for tool in ("bwrap", "apt-get", "dpkg", "dpkg-deb")
            if not shutil.which(tool)
        ]
        if missing:
            self.fail(f"Isolated APT test prerequisites are missing: {', '.join(missing)}")
        arch = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True, check=True)
        if arch.stdout.strip() != "amd64":
            self.skipTest("Fixture requires an amd64 dpkg host")
        self.repo_root = Path(__file__).resolve().parents[1]
        self.tmp = tempfile.TemporaryDirectory(prefix="beacon-apt-hook-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "root"
        for directory in (
            "root/var/lib/dpkg/info", "root/var/lib/dpkg/updates",
            "lists/partial", "archives/partial", "empty", "config-parts",
            "pkg/DEBIAN", "log",
        ):
            (self.base / directory).mkdir(parents=True)
        (self.root / "var/lib/dpkg/status").write_text("")
        (self.base / "sources.list").write_text("")
        (self.base / "apt.conf").write_text(
            f'Dir::Etc::parts "{self.base}/empty";\nDir::Etc::main "/dev/null";\n'
        )
        (self.base / "pkg/DEBIAN/control").write_text(
            "Package: beacon-hook-fixture\nVersion: 1.0\nArchitecture: amd64\n"
            "Maintainer: Test <test@example.test>\nDescription: APT hook fixture\n"
        )
        self.archive = self.base / "fixture.deb"
        subprocess.run(["dpkg-deb", "--build", str(self.base / "pkg"), str(self.archive)],
                       capture_output=True, check=True)
        self.hook = self.base / "hook"
        self.hook.write_text(
            f"#!{sys.executable}\n"
            "import os\n"
            "from pathlib import Path\n"
            "import sys\n"
            f"base = Path({str(self.base)!r})\n"
            f"status = Path({str(self.root / 'var/lib/dpkg/status')!r})\n"
            "counter = base / 'hook-count'\n"
            "number = int(counter.read_text()) + 1 if counter.exists() else 1\n"
            "counter.write_text(str(number))\n"
            "data = sys.stdin.read()\n"
            "(base / f'hook-input-{number}').write_text(data)\n"
            "(base / 'hook-input').write_text(data)\n"
            "(base / f'status-at-hook-{number}').write_text(status.read_text())\n"
            "(base / 'hook-fd').write_text(os.environ.get('APT_HOOK_INFO_FD', 'unset'))\n"
            "if (base / 'hook-policy').exists():\n"
            "    actions = data.split('\\n\\n', 1)[-1]\n"
            "    for line in actions.splitlines():\n"
            "        fields = line.split()\n"
            "        if len(fields) >= 9 and (fields[8] == '**REMOVE**' or fields[4] == '>'):\n"
            "            sys.exit(77)\n"
            "specific = base / f'hook-exit-{number}'\n"
            "default = base / 'hook-exit'\n"
            "sys.exit(int((specific if specific.exists() else default).read_text()))\n"
        )
        self.hook.chmod(0o755)
        self.options = [
            "-o", f"Dir::State::status={self.root}/var/lib/dpkg/status",
            "-o", f"Dir::State::lists={self.base}/lists",
            "-o", f"Dir::State::extended_states={self.base}/extended_states",
            "-o", f"Dir::Cache::archives={self.base}/archives",
            "-o", f"Dir::Cache::pkgcache={self.base}/pkgcache",
            "-o", f"Dir::Cache::srcpkgcache={self.base}/srcpkgcache",
            "-o", f"Dir::Etc::sourcelist={self.base}/sources.list",
            "-o", f"Dir::Etc::sourceparts={self.base}/empty",
            "-o", f"Dir::Etc::parts={self.base}/empty",
            "-o", "Dir::Etc::main=/dev/null",
            "-o", f"Dir::Log={self.base}/log",
            "-o", "APT::Architecture=amd64",
            "-o", "APT::Architectures::=amd64",
            "-o", "APT::Sandbox::User=root",
            "-o", f"DPkg::Options::=--root={self.root}",
            "-o", f"DPkg::Options::=--log={self.base}/log/dpkg.log",
            "-o", f"DPkg::Pre-Install-Pkgs::={self.hook}",
            "-o", f"DPkg::Tools::options::{self.hook}::Version=3",
        ]

    def install(self, exit_code, *extra, archives=None, no_remove=True, additional_hooks=(),
                use_configured_hook_sources=False):
        for path in [self.base / "hook-count", *self.base.glob("hook-input-*"),
                     *self.base.glob("status-at-hook-*")]:
            path.unlink(missing_ok=True)
        (self.base / "hook-exit").write_text(str(exit_code))
        options = self.options
        if use_configured_hook_sources:
            ignored = (
                "Dir::Etc::parts=",
                "Dir::Etc::main=",
                f"DPkg::Pre-Install-Pkgs::={self.hook}",
                f"DPkg::Tools::options::{self.hook}::Version=",
            )
            options = [
                argument
                for pair in zip(self.options[::2], self.options[1::2])
                if not pair[1].startswith(ignored)
                for argument in pair
            ]
        return subprocess.run(
            ["bwrap", "--unshare-all", "--ro-bind", "/", "/", "--tmpfs", "/tmp",
             "--ro-bind", str(self.repo_root), str(self.repo_root),
             "--bind", str(self.base), str(self.base), "--ro-bind", "/proc", "/proc", "--dev", "/dev",
             "--uid", "0", "--gid", "0", "--chdir", str(self.base),
             "--setenv", "APT_CONFIG", str(self.base / "apt.conf"), "--setenv", "LC_ALL", "C",
             "apt-get", *options, "-y",
              *(arg for hook in additional_hooks for arg in
                ("-o", f"DPkg::Pre-Install-Pkgs::={hook}",
                 "-o", f"DPkg::Tools::options::{hook}::Version=3")),
              *(["--no-remove"] if no_remove else []), *extra, "install",
             *(str(path) for path in (archives or [self.archive]))],
            text=True, capture_output=True, timeout=60, check=False,
        )

    def production_policy_hook(self, version="1.0", old_version="-"):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        import apt_handoff

        self.archive.chmod(0o400)
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        manifest = self.base / "approved-manifest.json"
        manifest.write_text(json.dumps({
            "sha256": digest,
            "artifact": str(self.archive),
            "package": "beacon-hook-fixture",
            "architecture": "amd64",
            "installed_architecture": "amd64",
            "installed_version": old_version,
            "repository": "owner/repo",
            "repository_id": 123,
            "release_tag": f"v{version}",
            "asset_name": f"beacon-hook-fixture_{version}_amd64.deb",
            "asset_url": (
                "https://github.com/owner/repo/releases/download/"
                f"v{version}/beacon-hook-fixture_{version}_amd64.deb"
            ),
            "version": version,
            "plan": [{
                "package": "beacon-hook-fixture",
                "architecture": "amd64",
                "old_architecture": "-" if old_version == "-" else "amd64",
                "old_version": old_version,
                "new_version": version,
                "action": "install",
            }],
        }))
        manifest.chmod(0o400)
        hook = self.base / "beacon-policy-hook"
        hook.write_text(
            "#!/usr/bin/python3\n"
            "import sys\n"
            f"sys.path.insert(0, {str(Path(apt_handoff.__file__).parent)!r})\n"
            "from apt_handoff import hook_main\n"
            f"raise SystemExit(hook_main({str(manifest)!r}))\n"
        )
        hook.chmod(0o500)
        return hook

    def run_production_helper(self, archive, manifest):
        apt_config = self.base / "production-apt"
        apt_config.mkdir()
        (apt_config / "apt.conf.d").mkdir()
        (apt_config / "apt.conf").write_text(
            f'Dir::Etc::parts "{apt_config}/apt.conf.d";\n'
            'Dir::Etc::main "/dev/null";\n'
            f'Dir::Etc::sourcelist "{self.base}/sources.list";\n'
            f'Dir::Etc::sourceparts "{self.base}/empty";\n'
            'Dir::State::status "/var/lib/dpkg/status";\n'
            f'Dir::State::lists "{self.base}/lists";\n'
            f'Dir::State::extended_states "{self.base}/extended_states";\n'
            f'Dir::Cache::archives "{self.base}/archives";\n'
            f'Dir::Cache::pkgcache "{self.base}/pkgcache";\n'
            f'Dir::Cache::srcpkgcache "{self.base}/srcpkgcache";\n'
            f'Dir::Log "{self.base}/log";\n'
            'APT::Architecture "amd64";\n'
            'APT::Architectures { "amd64"; };\n'
            'APT::Sandbox::User "root";\n'
            'APT::Get::Assume-Yes "true";\n'
            f'DPkg::Options {{ "--log={self.base}/log/dpkg.log"; }};\n'
        )
        source_root = Path(__file__).resolve().parents[1] / "src"
        runner = (
            "import json, sys\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, {str(source_root)!r})\n"
            "import apt_handoff\n"
            f"apt_handoff.STAGING_ROOT = Path({str(self.base / 'run/beacon')!r})\n"
            f"apt_handoff.privileged_install({str(archive)!r}, "
            f"json.loads({json.dumps(manifest)!r}))\n"
        )
        return subprocess.run(
            [
                "bwrap", "--unshare-all", "--ro-bind", "/", "/", "--tmpfs", "/tmp",
                "--ro-bind", str(self.repo_root), str(self.repo_root),
                "--bind", str(self.base), str(self.base),
                "--bind", str(apt_config), "/etc/apt",
                "--bind", str(self.root / "var/lib/dpkg"), "/var/lib/dpkg",
                "--bind", str(self.base / "lists"), "/var/lib/apt/lists",
                "--bind", str(self.base / "archives"), "/var/cache/apt/archives",
                "--bind", str(self.base / "log"), "/var/log",
                "--ro-bind", "/proc", "/proc", "--dev", "/dev",
                "--uid", "0", "--gid", "0", "--chdir", str(self.base),
                "--setenv", "LC_ALL", "C", sys.executable, "-c", runner,
            ],
            text=True, capture_output=True, timeout=90, check=False,
        )

    def production_helper_manifest(self, archive):
        source_root = Path(__file__).resolve().parents[1] / "src"
        sys.path.insert(0, str(source_root))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        return {
            "sha256": digest,
            "artifact": str(archive),
            "package": "beacon-hook-fixture",
            "architecture": "amd64",
            "installed_architecture": "amd64",
            "installed_version": "1.0",
            "repository": "owner/repo",
            "repository_id": 123,
            "release_tag": "v2.0",
            "asset_name": "beacon-hook-fixture_2.0_amd64.deb",
            "asset_url": (
                "https://github.com/owner/repo/releases/download/"
                "v2.0/beacon-hook-fixture_2.0_amd64.deb"
            ),
            "version": "2.0",
            "plan": [{
                "package": "beacon-hook-fixture",
                "architecture": "amd64",
                "old_architecture": "amd64",
                "old_version": "1.0",
                "new_version": "2.0",
                "action": "install",
            }],
        }

    def build_upgrade_archive(self, depends=None):
        self.assertEqual(self.install(0).returncode, 0)
        dependency = f"Depends: {depends}\n" if depends else ""
        (self.base / "pkg/DEBIAN/control").write_text(
            "Package: beacon-hook-fixture\nVersion: 2.0\nArchitecture: amd64\n"
            f"{dependency}"
            "Maintainer: Test <test@example.test>\nDescription: APT hook fixture\n"
        )
        archive = self.base / "fixture-v2.deb"
        subprocess.run(["dpkg-deb", "--build", str(self.base / "pkg"), str(archive)],
                       capture_output=True, check=True)
        archive.chmod(0o600)
        return archive

    def test_production_privileged_helper_performs_isolated_upgrade(self):
        archive = self.build_upgrade_archive()
        staging = self.base / "run/beacon"
        staging.mkdir(parents=True, mode=0o700)
        staging.chmod(0o700)
        stale = staging / "transaction-interrupted"
        stale.mkdir(mode=0o700)
        (stale / "selected.deb").write_bytes(b"interrupted fixture")
        result = self.run_production_helper(
            archive, self.production_helper_manifest(archive),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        status = (self.root / "var/lib/dpkg/status").read_text()
        self.assertIn("Version: 2.0", status)
        self.assertFalse(stale.exists())
        self.assertEqual(list((self.base / "run/beacon").glob("transaction-*")), [])

    def test_production_privileged_helper_rejects_plan_drift(self):
        archive = self.build_upgrade_archive()
        manifest = self.production_helper_manifest(archive)
        manifest["plan"].append({
            "package": "unreviewed-dependency",
            "architecture": "amd64",
            "old_architecture": "-",
            "old_version": "-",
            "new_version": "1.0",
            "action": "install",
        })
        result = self.run_production_helper(archive, manifest)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differs from the reviewed plan", result.stderr)
        status = (self.root / "var/lib/dpkg/status").read_text()
        self.assertIn("Version: 1.0", status)
        self.assertNotIn("Version: 2.0", status)

    def test_production_privileged_helper_reports_unresolved_dependency(self):
        archive = self.build_upgrade_archive("beacon-missing-dependency (= 1.0)")
        result = self.run_production_helper(
            archive, self.production_helper_manifest(archive),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("APT installation failed", result.stderr)
        status = (self.root / "var/lib/dpkg/status").read_text()
        self.assertIn("Version: 1.0", status)
        self.assertNotIn("Version: 2.0", status)

    def test_production_privileged_helper_rejects_changed_source_artifact(self):
        archive = self.build_upgrade_archive()
        manifest = self.production_helper_manifest(archive)
        archive.write_bytes(b"changed after review")
        result = self.run_production_helper(archive, manifest)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Pinned package digest changed", result.stderr)
        status = (self.root / "var/lib/dpkg/status").read_text()
        self.assertIn("Version: 1.0", status)
        self.assertNotIn("Version: 2.0", status)

    def test_production_hook_allows_reviewed_real_install(self):
        hook = self.production_policy_hook()
        result = self.install(0, additional_hooks=[hook])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        status = (self.root / "var/lib/dpkg/status").read_text()
        self.assertIn("Version: 1.0", status)

    def test_production_hook_rejects_artifact_changed_after_review(self):
        hook = self.production_policy_hook()
        (self.base / "pkg/DEBIAN/control").write_text(
            "Package: beacon-hook-fixture\nVersion: 2.0\nArchitecture: amd64\n"
            "Maintainer: Test <test@example.test>\nDescription: Changed fixture\n"
        )
        self.archive.unlink()
        subprocess.run(["dpkg-deb", "--build", str(self.base / "pkg"), str(self.archive)],
                       capture_output=True, check=True)
        self.archive.chmod(0o400)
        result = self.install(0, additional_hooks=[hook])
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        status = (self.root / "var/lib/dpkg/status").read_text()
        self.assertNotIn("Package: beacon-hook-fixture", status)

    def test_hook_failure_aborts_before_package_change(self):
        result = self.install(1)
        self.assertNotEqual(
            result.returncode, 0,
            result.stdout + result.stderr + "\nHOOKS:\n"
            + "\n".join(p.read_text() for p in self.base.glob("hook-input-*")),
        )
        self.assertTrue((self.base / "hook-input").exists(), result.stdout + result.stderr)
        hook_data = (self.base / "hook-input").read_text()
        self.assertTrue(hook_data.startswith("VERSION 3\n"), hook_data)
        self.assertIn("beacon-hook-fixture", hook_data)
        self.assertNotIn("beacon-hook-fixture", (self.root / "var/lib/dpkg/status").read_text())

    def test_successful_hook_permits_isolated_real_install(self):
        result = self.install(0)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.base / "hook-input").read_text().startswith("VERSION 3\n"))
        status = (self.root / "var/lib/dpkg/status").read_text()
        self.assertIn("Package: beacon-hook-fixture", status)
        self.assertIn("Status: install ok installed", status)

    def test_hook_sees_upgrade_and_rejects_before_installed_state_changes(self):
        self.assertEqual(self.install(0).returncode, 0)
        old_status = (self.root / "var/lib/dpkg/status").read_text()
        (self.base / "pkg/DEBIAN/control").write_text(
            "Package: beacon-hook-fixture\nVersion: 2.0\nArchitecture: amd64\n"
            "Maintainer: Test <test@example.test>\nDescription: APT hook fixture\n"
        )
        subprocess.run(["dpkg-deb", "--build", str(self.base / "pkg"), str(self.archive)],
                       capture_output=True, check=True)
        result = self.install(1)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("beacon-hook-fixture 1.0 amd64", (self.base / "hook-input").read_text())
        self.assertIn(" < 2.0 amd64", (self.base / "hook-input").read_text())
        self.assertEqual((self.base / "status-at-hook-1").read_text(), old_status)
        self.assertEqual((self.root / "var/lib/dpkg/status").read_text(), old_status)

    def test_hook_sees_downgrade_when_apt_would_allow_it(self):
        self.assertEqual(self.install(0).returncode, 0)
        old_status = (self.root / "var/lib/dpkg/status").read_text()
        (self.base / "pkg/DEBIAN/control").write_text(
            "Package: beacon-hook-fixture\nVersion: 0.9\nArchitecture: amd64\n"
            "Maintainer: Test <test@example.test>\nDescription: APT hook fixture\n"
        )
        subprocess.run(["dpkg-deb", "--build", str(self.base / "pkg"), str(self.archive)],
                       capture_output=True, check=True)
        (self.base / "hook-policy").write_text("reject removals and downgrades")
        result = self.install(0, "--allow-downgrades")
        self.assertNotEqual(result.returncode, 0,
                            result.stdout + result.stderr + "\n"
                            + "\n".join(p.read_text() for p in self.base.glob("hook-input-*")))
        self.assertIn(" > 0.9 amd64", (self.base / "hook-input").read_text())
        self.assertEqual((self.root / "var/lib/dpkg/status").read_text(), old_status)

    def test_hook_sees_both_requested_packages_before_installation(self):
        (self.base / "pkg/DEBIAN/control").write_text(
            "Package: beacon-hook-second\nVersion: 1.0\nArchitecture: amd64\n"
            "Maintainer: Test <test@example.test>\nDescription: APT hook fixture\n"
        )
        second = self.base / "second.deb"
        subprocess.run(["dpkg-deb", "--build", str(self.base / "pkg"), str(second)],
                       capture_output=True, check=True)
        result = self.install(1, archives=[self.archive, second])
        self.assertNotEqual(result.returncode, 0)
        actions = (self.base / "hook-input").read_text().split("\n\n", 1)[1]
        self.assertIn("beacon-hook-fixture ", actions)
        self.assertIn("beacon-hook-second ", actions)
        self.assertIn(str(self.archive), actions)
        self.assertIn(str(second), actions)
        self.assertEqual((self.root / "var/lib/dpkg/status").read_text(), "")

    def test_predepends_actions_are_all_present_before_dpkg(self):
        dependency_dir = self.base / "dependency/DEBIAN"
        dependency_dir.mkdir(parents=True)
        (dependency_dir / "control").write_text(
            "Package: beacon-hook-dependency\nVersion: 1.0\nArchitecture: amd64\n"
            "Maintainer: Test <test@example.test>\nDescription: APT hook dependency\n"
        )
        dependency = self.base / "dependency.deb"
        subprocess.run(["dpkg-deb", "--build", str(self.base / "dependency"), str(dependency)],
                       capture_output=True, check=True)
        (self.base / "pkg/DEBIAN/control").write_text(
            "Package: beacon-hook-fixture\nVersion: 1.0\nArchitecture: amd64\n"
            "Maintainer: Test <test@example.test>\nPre-Depends: beacon-hook-dependency\n"
            "Description: APT hook fixture\n"
        )
        fixture = self.base / "fixture-predepends.deb"
        subprocess.run(["dpkg-deb", "--build", str(self.base / "pkg"), str(fixture)],
                       capture_output=True, check=True)
        result = self.install(1, archives=[dependency, fixture])
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = int((self.base / "hook-count").read_text())
        self.assertEqual(calls, 1, result.stdout + result.stderr)
        first = (self.base / "hook-input-1").read_text()
        self.assertIn("beacon-hook-dependency", first)
        self.assertIn("beacon-hook-fixture", first)
        self.assertIn(str(dependency), first)
        self.assertIn(str(fixture), first)
        status = (self.root / "var/lib/dpkg/status").read_text()
        self.assertNotIn("Package: beacon-hook-dependency", status)
        self.assertNotIn("Package: beacon-hook-fixture", status)

    def test_later_configured_hook_can_replace_archive_after_observer(self):
        replacement_dir = self.base / "replacement/DEBIAN"
        replacement_dir.mkdir(parents=True)
        (replacement_dir / "control").write_text(
            "Package: beacon-hook-fixture\nVersion: 9.0\nArchitecture: amd64\n"
            "Maintainer: Test <test@example.test>\nDescription: Replacement fixture\n"
        )
        replacement = self.base / "replacement.deb"
        subprocess.run(["dpkg-deb", "--build", str(self.base / "replacement"), str(replacement)],
                       capture_output=True, check=True)
        mutator = self.base / "mutator"
        mutator.write_text(
            "#!/bin/sh\n"
            f"cat >/dev/null\ncp '{replacement}' '{self.archive}'\n"
        )
        mutator.chmod(0o755)
        result = self.install(0, additional_hooks=[mutator])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        observed = (self.base / "hook-input").read_text()
        self.assertIn("VERSION 3", observed)
        self.assertIn(" < 1.0 amd64", observed)
        self.assertIn(str(self.archive), observed)
        status = (self.root / "var/lib/dpkg/status").read_text()
        self.assertIn("Version: 9.0", status)
        self.assertNotIn("Version: 1.0", status)

    def test_command_line_verifier_can_reject_archive_changed_by_configured_hook(self):
        approved_digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        replacement_dir = self.base / "replacement/DEBIAN"
        replacement_dir.mkdir(parents=True)
        (replacement_dir / "control").write_text(
            "Package: beacon-hook-fixture\nVersion: 9.0\nArchitecture: amd64\n"
            "Maintainer: Test <test@example.test>\nDescription: Replacement fixture\n"
        )
        replacement = self.base / "replacement.deb"
        subprocess.run(["dpkg-deb", "--build", str(self.base / "replacement"), str(replacement)],
                       capture_output=True, check=True)
        mutator = self.base / "configured-mutator"
        mutator.write_text(
            "#!/bin/sh\n"
            "cat >/dev/null\n"
            f"cp '{replacement}' '{self.archive}'\n"
        )
        mutator.chmod(0o755)
        (self.base / "apt.conf").write_text(
            f'Dir::Etc::parts "{self.base}/empty";\n'
            'Dir::Etc::main "/dev/null";\n'
            f'DPkg::Pre-Install-Pkgs {{ "{mutator}"; }};\n'
            f'DPkg::Tools::options::{mutator}::Version "3";\n'
        )
        verifier = self.base / "final-verifier"
        verifier.write_text(
            f"#!{sys.executable}\n"
            "import hashlib\n"
            "from pathlib import Path\n"
            "import sys\n"
            f"expected = {approved_digest!r}\n"
            f"result = Path({str(self.base / 'final-verifier-result')!r})\n"
            "data = sys.stdin.read()\n"
            "actions = data.split('\\n\\n', 1)[-1]\n"
            "archives = [field for line in actions.splitlines() for field in line.split() "
            "if field.endswith('.deb')]\n"
            "accepted = bool(archives) and all(\n"
            "    hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected\n"
            "    for path in archives\n"
            ")\n"
            "result.write_text('accepted' if accepted else 'rejected')\n"
            "sys.exit(0 if accepted else 78)\n"
        )
        verifier.chmod(0o755)

        result = self.install(0, additional_hooks=[verifier])

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.base / "final-verifier-result").read_text(), "rejected")
        observed = (self.base / "hook-input").read_text()
        self.assertIn(" < 1.0 amd64", observed)
        self.assertIn(str(self.archive), observed)
        self.assertEqual(subprocess.run(
            ["dpkg-deb", "-f", str(self.archive), "Version"],
            capture_output=True, text=True, check=True,
        ).stdout.strip(), "9.0")
        self.assertNotIn(
            "Package: beacon-hook-fixture",
            (self.root / "var/lib/dpkg/status").read_text(),
        )

    def test_archive_can_change_after_final_verifier_checks_digest(self):
        approved_digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        replacement_dir = self.base / "replacement/DEBIAN"
        replacement_dir.mkdir(parents=True)
        (replacement_dir / "control").write_text(
            "Package: beacon-hook-fixture\nVersion: 9.0\nArchitecture: amd64\n"
            "Maintainer: Test <test@example.test>\nDescription: Replacement fixture\n"
        )
        replacement = self.base / "replacement.deb"
        subprocess.run(["dpkg-deb", "--build", str(self.base / "replacement"), str(replacement)],
                       capture_output=True, check=True)
        verifier = self.base / "final-verifier-mutator"
        verifier_result = self.base / "final-verifier-mutator-result"
        verifier.write_text(
            f"#!{sys.executable}\n"
            "import hashlib\n"
            "from pathlib import Path\n"
            "import shutil\n"
            "import sys\n"
            f"expected = {approved_digest!r}\n"
            f"archive = Path({str(self.archive)!r})\n"
            f"replacement = Path({str(replacement)!r})\n"
            f"result = Path({str(verifier_result)!r})\n"
            "data = sys.stdin.read()\n"
            "actions = data.split('\\n\\n', 1)[-1]\n"
            "archives = [field for line in actions.splitlines() for field in line.split() "
            "if field.endswith('.deb')]\n"
            "accepted = bool(archives) and all(\n"
            "    hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected\n"
            "    for path in archives\n"
            ")\n"
            "result.write_text('accepted' if accepted else 'rejected')\n"
            "if not accepted:\n"
            "    sys.exit(78)\n"
            "shutil.copyfile(replacement, archive)\n"
        )
        verifier.chmod(0o755)

        result = self.install(0, additional_hooks=[verifier])

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(verifier_result.read_text(), "accepted")
        installed_status = (self.root / "var/lib/dpkg/status").read_text()
        self.assertIn("Version: 9.0", installed_status)
        self.assertNotIn("Version: 1.0", installed_status)
        self.assertNotEqual(hashlib.sha256(self.archive.read_bytes()).hexdigest(), approved_digest)

    def test_command_line_verifier_runs_after_all_apt_config_sources(self):
        approved_digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        replacement_dir = self.base / "replacement/DEBIAN"
        replacement_dir.mkdir(parents=True)
        (replacement_dir / "control").write_text(
            "Package: beacon-hook-fixture\nVersion: 9.0\nArchitecture: amd64\n"
            "Maintainer: Test <test@example.test>\nDescription: Replacement fixture\n"
        )
        replacement = self.base / "replacement.deb"
        subprocess.run(["dpkg-deb", "--build", str(self.base / "replacement"), str(replacement)],
                       capture_output=True, check=True)
        order = self.base / "configured-hook-order"
        configured_hooks = []
        for name in ("apt-config", "fragment", "main"):
            hook = self.base / f"{name}-hook"
            hook.write_text(
                "#!/bin/sh\n"
                "cat >/dev/null\n"
                f"printf '{name}\\n' >> '{order}'\n"
                + (f"cp '{replacement}' '{self.archive}'\n" if name == "apt-config" else "")
            )
            hook.chmod(0o755)
            configured_hooks.append(hook)

        parts = self.base / "config-parts"
        fragment = parts / "20-beacon-test"
        fragment.write_text(
            f'DPkg::Pre-Install-Pkgs {{ "{configured_hooks[1]}"; }};\n'
            f'DPkg::Tools::options::{configured_hooks[1]}::Version "3";\n'
        )
        main_config = self.base / "main.conf"
        main_config.write_text(
            f'DPkg::Pre-Install-Pkgs {{ "{configured_hooks[2]}"; }};\n'
            f'DPkg::Tools::options::{configured_hooks[2]}::Version "3";\n'
        )
        (self.base / "apt.conf").write_text(
            f'Dir::Etc::parts "{parts}";\n'
            f'Dir::Etc::main "{main_config}";\n'
            f'DPkg::Pre-Install-Pkgs {{ "{configured_hooks[0]}"; }};\n'
            f'DPkg::Tools::options::{configured_hooks[0]}::Version "3";\n'
        )
        verifier = self.base / "chain-verifier"
        verifier_result = self.base / "chain-verifier-result"
        verifier.write_text(
            f"#!{sys.executable}\n"
            "import hashlib\n"
            "from pathlib import Path\n"
            "import sys\n"
            f"expected = {approved_digest!r}\n"
            f"result = Path({str(verifier_result)!r})\n"
            "data = sys.stdin.read()\n"
            "actions = data.split('\\n\\n', 1)[-1]\n"
            "archives = [field for line in actions.splitlines() for field in line.split() "
            "if field.endswith('.deb')]\n"
            "accepted = bool(archives) and all(\n"
            "    hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected\n"
            "    for path in archives\n"
            ")\n"
            "result.write_text('accepted' if accepted else 'rejected')\n"
            "sys.exit(0 if accepted else 78)\n"
        )
        verifier.chmod(0o755)

        result = self.install(
            0, additional_hooks=[verifier], use_configured_hook_sources=True,
        )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(order.read_text().splitlines(), ["apt-config", "fragment", "main"])
        self.assertEqual(verifier_result.read_text(), "rejected")
        self.assertNotIn(
            "Package: beacon-hook-fixture",
            (self.root / "var/lib/dpkg/status").read_text(),
        )

    def test_hook_protocol_includes_solver_removal_action(self):
        conflict = (
            "Package: beacon-hook-conflict\nStatus: install ok installed\n"
            "Priority: optional\nSection: misc\nInstalled-Size: 1\n"
            "Maintainer: Test <test@example.test>\nArchitecture: amd64\n"
            "Version: 1.0\nDescription: Fixture\n\n"
        )
        (self.root / "var/lib/dpkg/status").write_text(conflict)
        (self.base / "pkg/DEBIAN/control").write_text(
            "Package: beacon-hook-fixture\nVersion: 1.0\nArchitecture: amd64\n"
            "Maintainer: Test <test@example.test>\nConflicts: beacon-hook-conflict\n"
            "Description: APT hook fixture\n"
        )
        subprocess.run(["dpkg-deb", "--build", str(self.base / "pkg"), str(self.archive)],
                       capture_output=True, check=True)
        (self.base / "hook-policy").write_text("reject removals and downgrades")
        result = self.install(0, no_remove=False)
        self.assertNotEqual(result.returncode, 0)
        data = (self.base / "hook-input").read_text()
        self.assertIn("beacon-hook-conflict", data)
        self.assertIn("**REMOVE**", data)
        self.assertEqual((self.root / "var/lib/dpkg/status").read_text(), conflict)
