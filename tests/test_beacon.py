from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from subprocess import TimeoutExpired

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from beacon import (
    DiscoveryError, _source_for_repository_url, auto_installed_count,
    config_remains_count, config_remains_packages, help_menu, installed_count,
    main, package_exists, package_provenance, package_state,
)


class BeaconProvenanceConfidenceTest(unittest.TestCase):
    def test_help_uses_packaged_executable_name(self):
        output = StringIO()
        with redirect_stdout(output):
            help_menu()

        help_text = output.getvalue()
        self.assertIn("◆ Beacon Discovery Engine", help_text)
        self.assertIn("Usage:\n    beacon <package>", help_text)
        self.assertIn("    beacon --scan", help_text)
        self.assertNotIn("beacon.py", help_text)

    def run_with_policy(self, policy_output, installed_output=""):
        def fake_run(args, **kwargs):
            if args[:2] == ["apt-cache", "policy"]:
                return SimpleNamespace(stdout=policy_output, stderr="", returncode=0)

            if args[:3] == ["apt", "list", "--installed"]:
                return SimpleNamespace(stdout=installed_output, stderr="", returncode=0)

            raise AssertionError(f"Unexpected command: {args}")

        return patch("beacon.subprocess.run", side_effect=fake_run)

    def test_repository_host_classification_uses_domain_boundaries(self):
        cases = {
            "https://ppa.floorp.app/amd64": "PPA",
            "https://ppa.launchpadcontent.net/owner/archive/ubuntu": "PPA",
            "https://archive.ubuntu.com/ubuntu": "Ubuntu Repository",
            "https://mirror.debian.org/debian": "Debian Repository",
            "https://packages.example.test/repo": "Vendor Repository",
            "https://notlaunchpad.example.test/repo": "Vendor Repository",
            "https://ubuntu.com.example.test/repo": "Vendor Repository",
            "https://debian.org.example.test/repo": "Vendor Repository",
        }

        for url, expected_source in cases.items():
            with self.subTest(url=url):
                self.assertEqual(_source_for_repository_url(url), expected_source)

    def test_package_command_failures_and_timeouts_are_explicit(self):
        cases = [
            (SimpleNamespace(stdout="", stderr="APT unavailable", returncode=100),
             "APT unavailable"),
            (TimeoutExpired(["apt-cache", "policy", "app"], 15), "timed out"),
            (FileNotFoundError("apt-cache"), "apt-cache"),
        ]
        for result, message in cases:
            mocked = {"side_effect": result} if isinstance(result, BaseException) else {"return_value": result}
            with self.subTest(result=result), patch("beacon.subprocess.run", **mocked):
                with self.assertRaisesRegex(DiscoveryError, message):
                    package_exists("app")

    def test_package_command_timeout_is_bounded(self):
        result = SimpleNamespace(
            stdout="app:\n  Candidate: 1.2.3\n", stderr="", returncode=0,
        )
        with patch("beacon.subprocess.run", return_value=result) as command:
            self.assertTrue(package_exists("app"))
        self.assertEqual(command.call_args.kwargs["timeout"], 15)
        self.assertFalse(command.call_args.kwargs.get("shell", False))

    def test_inventory_uses_argument_lists_and_checked_output(self):
        outputs = {
            ("dpkg", "-l"): (
                "Desired=Unknown/Install/Remove/Purge/Hold\n"
                "||/ Name Version Architecture Description\n"
                "ii  one 1 amd64 installed\n"
                "ii  two 1 all installed\n"
                "rc  old 1 amd64 config-remains\n"
                "un  absent <none> <none> not-installed\n"
            ),
            ("apt-mark", "showauto"): "one\ntwo\n",
        }

        def fake_run(command, **kwargs):
            self.assertIsInstance(command, list)
            self.assertEqual(kwargs["timeout"], 15)
            self.assertNotIn("shell", kwargs)
            return SimpleNamespace(
                stdout=outputs[tuple(command)], stderr="", returncode=0,
            )

        with patch("beacon.subprocess.run", side_effect=fake_run):
            self.assertEqual(installed_count(), 2)
            self.assertEqual(config_remains_count(), 1)
            self.assertEqual(config_remains_packages(), ["old"])
            self.assertEqual(auto_installed_count(), 2)

    def test_dpkg_list_nonzero_for_missing_package_is_not_a_command_failure(self):
        outputs = [
            SimpleNamespace(stdout="", stderr="", returncode=1),
            SimpleNamespace(stdout="missing:\n  Candidate: (none)\n", stderr="", returncode=0),
        ]
        with patch("beacon.subprocess.run", side_effect=outputs):
            self.assertEqual(package_state("missing"), "Unknown")

    def test_scan_reports_package_command_timeout_without_traceback(self):
        with patch.object(sys, "argv", ["beacon", "--scan"]), \
             patch("beacon.subprocess.run",
                   side_effect=TimeoutExpired(["dpkg", "-l"], 15)), \
             redirect_stdout(StringIO()), redirect_stderr(StringIO()) as error:
            with self.assertRaises(SystemExit) as result:
                main()
        self.assertEqual(result.exception.code, 1)
        self.assertIn("Error: Unable to list installed packages", error.getvalue())
        self.assertIn("timed out", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())

    def test_ppa_url_provides_high_confidence_with_evidence(self):
        policy = """\
floorp:
  Installed: 1.0.0
  Candidate: 1.0.0
  Version table:
 *** 1.0.0 500
        500 https://ppa.floorp.app/amd64 ./ Packages
        100 /var/lib/dpkg/status
"""

        with self.run_with_policy(policy):
            provenance = package_provenance("floorp")

        self.assertEqual(provenance["source"], "PPA")
        self.assertEqual(provenance["score"], 90)
        self.assertEqual(provenance["confidence"], "High")
        self.assertIn("https://ppa.floorp.app/amd64", provenance["evidence"][0])

    def test_debian_repository_is_not_classified_as_vendor(self):
        policy = """\
sample:
  Installed: (none)
  Candidate: 1.0
  Version table:
     1.0 500
        500 https://deb.debian.org/debian stable/main amd64 Packages
"""

        with self.run_with_policy(policy):
            provenance = package_provenance("sample")

        self.assertEqual(provenance["source"], "Debian Repository")
        self.assertEqual(provenance["confidence"], "High")

    def test_local_candidate_gets_medium_confidence(self):
        policy = """\
clover-eye:
  Installed: 1.2.3
  Candidate: 1.2.3
  Version table:
 *** 1.2.3 100
        100 /var/lib/dpkg/status
"""
        installed = "clover-eye/now 1.2.3 amd64 [installed,local]\n"

        with self.run_with_policy(policy, installed):
            provenance = package_provenance("clover-eye")

        self.assertEqual(provenance["source"], "Local .deb Candidate")
        self.assertEqual(provenance["score"], 65)
        self.assertEqual(provenance["confidence"], "Medium")
        self.assertIn("APT marks", provenance["evidence"][0])

    def test_uses_installed_version_origin_not_newer_candidate(self):
        policy = """\
clover-eye:
  Installed: 1.0.0
  Candidate: 2.0.0
  Version table:
     2.0.0 500
        500 https://ppa.example.test/stable Packages
 *** 1.0.0 100
        100 /var/lib/dpkg/status
"""
        installed = "clover-eye/now 1.0.0 amd64 [installed,local]\n"

        with self.run_with_policy(policy, installed):
            provenance = package_provenance("clover-eye")

        self.assertEqual(provenance["source"], "Local .deb Candidate")
        self.assertEqual(provenance["confidence"], "Medium")

    def test_conflicting_repository_types_are_capped_at_medium(self):
        policy = """\
sample:
  Installed: 1.0
  Candidate: 1.0
  Version table:
 *** 1.0 500
        500 https://archive.ubuntu.com/ubuntu jammy/main amd64 Packages
        500 https://packages.example.test/debian stable/main amd64 Packages
"""

        with self.run_with_policy(policy):
            provenance = package_provenance("sample")

        self.assertEqual(provenance["source"], "Multiple Sources")
        self.assertEqual(provenance["score"], 45)
        self.assertEqual(provenance["confidence"], "Medium")
        self.assertIn("multiple types", provenance["evidence"][0])

    def test_no_origin_evidence_is_unknown_with_low_confidence(self):
        policy = """\
missing-package:
  Installed: (none)
  Candidate: (none)
  Version table:
"""

        with self.run_with_policy(policy):
            provenance = package_provenance("missing-package")

        self.assertEqual(provenance["source"], "Unknown")
        self.assertEqual(provenance["score"], 0)
        self.assertEqual(provenance["confidence"], "Low")
        self.assertTrue(provenance["evidence"])


if __name__ == "__main__":
    unittest.main()
