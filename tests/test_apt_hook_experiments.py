"""Opt-in real dpkg experiments in a rootless, read-only-host namespace."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(
    os.environ.get("BEACON_RUN_APT_HOOK_EXPERIMENTS") == "1"
    and all(shutil.which(tool) for tool in ("bwrap", "apt-get", "dpkg", "dpkg-deb")),
    "Set BEACON_RUN_APT_HOOK_EXPERIMENTS=1 and install bubblewrap/APT to run",
)
class AptHookExperiments(unittest.TestCase):
    def setUp(self):
        arch = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True, check=True)
        if arch.stdout.strip() != "amd64":
            self.skipTest("Fixture requires an amd64 dpkg host")
        self.tmp = tempfile.TemporaryDirectory(prefix="beacon-apt-hook-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "root"
        for directory in (
            "root/var/lib/dpkg/info", "root/var/lib/dpkg/updates",
            "lists/partial", "archives/partial", "empty", "pkg/DEBIAN", "log",
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

    def install(self, exit_code, *extra, archives=None, no_remove=True, additional_hooks=()):
        for path in [self.base / "hook-count", *self.base.glob("hook-input-*"),
                     *self.base.glob("status-at-hook-*")]:
            path.unlink(missing_ok=True)
        (self.base / "hook-exit").write_text(str(exit_code))
        return subprocess.run(
            ["bwrap", "--unshare-all", "--ro-bind", "/", "/", "--tmpfs", "/tmp",
             "--bind", str(self.base), str(self.base), "--ro-bind", "/proc", "/proc", "--dev", "/dev",
             "--uid", "0", "--gid", "0", "--chdir", str(self.base),
             "--setenv", "APT_CONFIG", str(self.base / "apt.conf"), "--setenv", "LC_ALL", "C",
             "apt-get", *self.options, "-y",
              *(arg for hook in additional_hooks for arg in
                ("-o", f"DPkg::Pre-Install-Pkgs::={hook}")),
              *(["--no-remove"] if no_remove else []), *extra, "install",
             *(str(path) for path in (archives or [self.archive]))],
            text=True, capture_output=True, timeout=60, check=False,
        )

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
