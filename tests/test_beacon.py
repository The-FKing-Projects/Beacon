import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from beacon import package_provenance


class BeaconProvenanceConfidenceTest(unittest.TestCase):
    def run_with_policy(self, policy_output, installed_output=""):
        def fake_run(args, **kwargs):
            if args[:2] == ["apt-cache", "policy"]:
                return SimpleNamespace(stdout=policy_output, stderr="")

            if args[:3] == ["apt", "list", "--installed"]:
                return SimpleNamespace(stdout=installed_output, stderr="")

            raise AssertionError(f"Unexpected command: {args}")

        return patch("beacon.subprocess.run", side_effect=fake_run)

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
