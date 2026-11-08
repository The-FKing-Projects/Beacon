"""Read-only APT simulation experiments using an isolated package database."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which("apt-get") and shutil.which("dpkg-deb"), "APT tools required")
class AptSafetyExperiments(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for directory in ("lists/partial", "archives/partial", "empty-parts", "pkg/DEBIAN"):
            (self.root / directory).mkdir(parents=True)
        (self.root / "sources.list").write_text("")
        self.installed = (
            "Package: beacon-example\nStatus: install ok installed\n"
            "Priority: optional\nSection: misc\nInstalled-Size: 1\n"
            "Maintainer: Test <test@example.test>\nArchitecture: amd64\n"
            "Version: 1.0\nDescription: Fixture\n\n"
        )
        self.conflict = (
            "Package: beacon-conflict\nStatus: install ok installed\n"
            "Priority: optional\nSection: misc\nInstalled-Size: 1\n"
            "Maintainer: Test <test@example.test>\nArchitecture: amd64\n"
            "Version: 1.0\nDescription: Fixture\n\n"
        )
        (self.root / "status").write_text(self.installed + self.conflict)
        self.options = [
            "-o", f"Dir::State::status={self.root}/status",
            "-o", f"Dir::State::lists={self.root}/lists",
            "-o", f"Dir::Cache::archives={self.root}/archives",
            "-o", f"Dir::Cache::pkgcache={self.root}/pkgcache.bin",
            "-o", f"Dir::Cache::srcpkgcache={self.root}/srcpkgcache.bin",
            "-o", f"Dir::Etc::sourcelist={self.root}/sources.list",
            "-o", f"Dir::Etc::sourceparts={self.root}/empty-parts",
            "-o", f"Dir::Etc::parts={self.root}/empty-parts",
            "-o", "Dir::Etc::main=/dev/null",
            "-o", "APT::Architecture=amd64",
            "-o", "APT::Architectures::=amd64",
        ]

    def build_deb(self, version, conflicts=""):
        (self.root / "pkg/DEBIAN/control").write_text(
            "Package: beacon-example\n"
            f"Version: {version}\n"
            "Architecture: amd64\n"
            "Maintainer: Test <test@example.test>\n"
            f"{conflicts}"
            "Description: Fixture\n"
        )
        archive = self.root / "candidate.deb"
        subprocess.run(["dpkg-deb", "--build", str(self.root / "pkg"), str(archive)],
                       capture_output=True, check=True)
        return archive

    def simulate(self, archive, *options):
        return subprocess.run(
            ["apt-get", *self.options, "-s", *options, "install", str(archive)],
            text=True, capture_output=True, env={**os.environ, "LC_ALL": "C", "APT_CONFIG": os.devnull},
            timeout=30, check=False,
        )

    def test_removal_guard_applies_to_real_solver_plan(self):
        archive = self.build_deb("2.0", "Conflicts: beacon-conflict\n")
        preview = self.simulate(archive)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("Remv beacon-conflict", preview.stdout)
        guarded = self.simulate(archive, "--no-remove")
        self.assertNotEqual(guarded.returncode, 0)
        self.assertIn("packages need to be removed", guarded.stderr.lower())
        self.assertIn("Version: 1.0", (self.root / "status").read_text())

    def test_no_remove_does_not_block_downgrade(self):
        archive = self.build_deb("0.9")
        result = self.simulate(archive, "--no-remove")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DOWNGRADED", result.stdout)
        self.assertIn("Inst beacon-example [1.0]", result.stdout)

    def test_changed_state_produces_different_plan(self):
        archive = self.build_deb("2.0", "Conflicts: beacon-conflict\n")
        status = self.root / "status"
        status.write_text(self.installed)
        first = self.simulate(archive)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertNotIn("Remv beacon-conflict", first.stdout)
        status.write_text(self.installed + self.conflict)
        second = self.simulate(archive)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Remv beacon-conflict", second.stdout)
        guarded = self.simulate(archive, "--no-remove")
        self.assertNotEqual(guarded.returncode, 0)
        self.assertEqual(status.read_text(), self.installed + self.conflict)
