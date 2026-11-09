import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from beacon import package_provenance, package_state


class RealPackageDiscoveryCasesTest(unittest.TestCase):
    def test_bash_is_attributed_to_ubuntu_repository(self):
        policy = """\
bash:
  Installed: 5.3-2ubuntu1
  Candidate: 5.3-2ubuntu1
  Version table:
 *** 5.3-2ubuntu1 500
        500 http://us.archive.ubuntu.com/ubuntu resolute/main amd64 Packages
        100 /var/lib/dpkg/status
"""

        with patch(
            "beacon.subprocess.run",
            return_value=SimpleNamespace(stdout=policy, stderr=""),
        ):
            provenance = package_provenance("bash")

        self.assertEqual(provenance["source"], "Ubuntu Repository")
        self.assertEqual(provenance["confidence"], "High")

    def test_steam_uses_candidate_origin_not_an_older_ubuntu_version(self):
        policy = """\
steam:i386:
  Installed: (none)
  Candidate: 1:1.0.0.87
  Version table:
     1:1.0.0.87 500
        500 http://repo.steampowered.com/steam stable/steam i386 Packages
     1:1.0.0.85~ds-2build1 500
        500 http://us.archive.ubuntu.com/ubuntu resolute/multiverse i386 Packages
"""

        with patch(
            "beacon.subprocess.run",
            return_value=SimpleNamespace(stdout=policy, stderr=""),
        ):
            provenance = package_provenance("steam")

        self.assertEqual(provenance["source"], "Vendor Repository")
        self.assertEqual(provenance["confidence"], "High")
        self.assertIn("repo.steampowered.com", provenance["evidence"][0])

    def test_clover_eye_and_discord_ptb_are_local_candidates(self):
        policies = {
            "clover-eye": """\
clover-eye:
  Installed: 0.1.1
  Candidate: 0.1.1
  Version table:
 *** 0.1.1 100
        100 /var/lib/dpkg/status
""",
            "discord-ptb": """\
discord-ptb:
  Installed: 1.0.196
  Candidate: 1.0.196
  Version table:
 *** 1.0.196 100
        100 /var/lib/dpkg/status
""",
        }
        installed = (
            "clover-eye/now 0.1.1 amd64 [installed,local]\n"
            "discord-ptb/now 1.0.196 amd64 [installed,local]\n"
        )

        def fake_run(args, **kwargs):
            if args[:2] == ["apt-cache", "policy"]:
                return SimpleNamespace(stdout=policies[args[2]], stderr="")

            if args[:3] == ["apt", "list", "--installed"]:
                return SimpleNamespace(stdout=installed, stderr="")

            raise AssertionError(f"Unexpected command: {args}")

        with patch("beacon.subprocess.run", side_effect=fake_run):
            for package in policies:
                with self.subTest(package=package):
                    provenance = package_provenance(package)
                    self.assertEqual(provenance["source"], "Local .deb Candidate")
                    self.assertEqual(provenance["confidence"], "Medium")

    def test_edge_and_brave_vendor_repository_policy_fixtures(self):
        policies = {
            "microsoft-edge-stable": """\
microsoft-edge-stable:
  Installed: 9.9.9-fixture
  Candidate: 9.9.9-fixture
  Version table:
 *** 9.9.9-fixture 500
        500 https://packages.microsoft.com/repos/edge stable/main amd64 Packages
        100 /var/lib/dpkg/status
""",
            "brave-browser": """\
brave-browser:
  Installed: 9.9.9-fixture
  Candidate: 9.9.9-fixture
  Version table:
 *** 9.9.9-fixture 500
        500 https://brave-browser-apt-release.s3.brave.com stable/main amd64 Packages
        100 /var/lib/dpkg/status
""",
        }

        def fake_run(args, **kwargs):
            if args[:2] == ["apt-cache", "policy"]:
                return SimpleNamespace(stdout=policies[args[2]], stderr="")
            raise AssertionError(f"Unexpected command: {args}")

        with patch("beacon.subprocess.run", side_effect=fake_run):
            for package in policies:
                with self.subTest(package=package):
                    provenance = package_provenance(package)

                    self.assertEqual(provenance["source"], "Vendor Repository")
                    self.assertEqual(provenance["confidence"], "High")
                    self.assertIn("https://", provenance["evidence"][0])

    def test_installed_without_current_repository_is_not_proven_orphan(self):
        policy = """\
orphan-candidate:
  Installed: 1.0
  Candidate: 1.0
  Version table:
 *** 1.0 100
        100 /var/lib/dpkg/status
"""
        installed = "orphan-candidate/now 1.0 amd64 [installed,local]\n"

        def fake_run(args, **kwargs):
            if args[:2] == ["dpkg", "-l"]:
                return SimpleNamespace(
                    stdout="ii  orphan-candidate 1.0 amd64 Example package\n",
                    stderr="",
                )
            if args[:2] == ["apt-cache", "policy"]:
                return SimpleNamespace(stdout=policy, stderr="")
            if args[:3] == ["apt", "list", "--installed"]:
                return SimpleNamespace(stdout=installed, stderr="")
            raise AssertionError(f"Unexpected command: {args}")

        with patch("beacon.subprocess.run", side_effect=fake_run):
            state = package_state("orphan-candidate")
            provenance = package_provenance("orphan-candidate")

        self.assertEqual(state, "Installed")
        self.assertEqual(provenance["source"], "Local .deb Candidate")
        self.assertIn("no repository origin", provenance["evidence"][0])

    def test_removed_heroic_is_configuration_remains(self):
        dpkg_output = "rc  heroic         2.22.0   amd64        Game launcher\n"

        with patch(
            "beacon.subprocess.run",
            return_value=SimpleNamespace(stdout=dpkg_output, stderr=""),
        ):
            self.assertEqual(package_state("heroic"), "Config Remains")

    def test_package_name_matching_does_not_match_prefix_or_none_candidate(self):
        def fake_run(args, **kwargs):
            if args[:2] == ["dpkg", "-l"]:
                return SimpleNamespace(stdout="ii  steam-launcher 1.0 amd64\n", stderr="")

            if args[:2] == ["apt-cache", "policy"]:
                return SimpleNamespace(stdout="steam:\n  Candidate: (none)\n", stderr="")

            raise AssertionError(f"Unexpected command: {args}")

        with patch("beacon.subprocess.run", side_effect=fake_run):
            self.assertEqual(package_state("steam"), "Unknown")

    def test_candidate_package_is_available(self):
        def fake_run(args, **kwargs):
            if args[:2] == ["dpkg", "-l"]:
                return SimpleNamespace(stdout="", stderr="")

            if args[:2] == ["apt-cache", "policy"]:
                return SimpleNamespace(
                    stdout="steam:\n  Candidate: 1:1.0.0.87\n",
                    stderr="",
                )

            raise AssertionError(f"Unexpected command: {args}")

        with patch("beacon.subprocess.run", side_effect=fake_run):
            self.assertEqual(package_state("steam"), "Available")


if __name__ == "__main__":
    unittest.main()
