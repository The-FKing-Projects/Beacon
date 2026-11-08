"""Opt-in real dpkg experiments in a rootless, read-only-host namespace."""

import os
from pathlib import Path
import shutil
import subprocess
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
            "#!/bin/sh\n"
            f"cat > '{self.base}/hook-input'\n"
            f"printf '%s\\n' \"${{APT_HOOK_INFO_FD-unset}}\" > '{self.base}/hook-fd'\n"
            f"cat '{self.root}/var/lib/dpkg/status' > '{self.base}/status-at-hook'\n"
            f"exit \"$(cat '{self.base}/hook-exit')\"\n"
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

    def install(self, exit_code, *extra, archives=None):
        (self.base / "hook-exit").write_text(str(exit_code))
        return subprocess.run(
            ["bwrap", "--unshare-all", "--ro-bind", "/", "/", "--tmpfs", "/tmp",
             "--bind", str(self.base), str(self.base), "--ro-bind", "/proc", "/proc", "--dev", "/dev",
             "--uid", "0", "--gid", "0", "--chdir", str(self.base),
             "--setenv", "APT_CONFIG", str(self.base / "apt.conf"), "--setenv", "LC_ALL", "C",
             "apt-get", *self.options, "-y", "--no-remove", *extra, "install",
             *(str(path) for path in (archives or [self.archive]))],
            text=True, capture_output=True, timeout=60, check=False,
        )

    def test_hook_failure_aborts_before_package_change(self):
        result = self.install(1)
        self.assertNotEqual(result.returncode, 0)
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
        self.assertEqual((self.base / "status-at-hook").read_text(), old_status)
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
        result = self.install(1, "--allow-downgrades")
        self.assertNotEqual(result.returncode, 0)
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
