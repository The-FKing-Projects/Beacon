import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import apt_handoff
import tracking


class AptHandoffTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = os.path.join(self.temp.name, "selected.deb")
        with open(self.archive, "wb") as output:
            output.write(b"fixture")
        self.plan = [{
            "package": "example-app",
            "architecture": "amd64",
            "old_architecture": "-",
            "old_version": "-",
            "new_version": "2.0",
            "action": "install",
        }]
        self.manifest = {
            "sha256": "a" * 64,
            "artifact": self.archive,
            "package": "example-app",
            "architecture": "amd64",
            "installed_architecture": "amd64",
            "installed_version": "-",
            "repository": "owner/repo",
            "repository_id": 123,
            "release_tag": "v2.0",
            "asset_name": "example-app_2.0_amd64.deb",
            "asset_url": (
                "https://github.com/owner/repo/releases/download/"
                "v2.0/example-app_2.0_amd64.deb"
            ),
            "version": "2.0",
            "plan": self.plan,
        }
        self.protocol = (
            "VERSION 3\nAPT::Architecture=amd64\n\n"
            "example-app - - none < 2.0 amd64 none "
            f"{self.archive}\n"
            "example-app - - none < 2.0 amd64 none **CONFIGURE**\n"
        )

    def test_any_apt_repository_version_blocks_a_newer_local_candidate(self):
        policy = """\
fixture-app:
  Installed: 2.0
  Candidate: 2.0
  Version table:
 *** 2.0 100
        100 /var/lib/dpkg/status
     1.0 500
        500 https://packages.example.test/debian stable/main amd64 Packages
"""
        with patch.object(
            apt_handoff,
            "_run",
            return_value=SimpleNamespace(stdout=policy, stderr="", returncode=0),
        ):
            with self.assertRaisesRegex(tracking.TrackingError, "APT has repository versions"):
                apt_handoff.assert_not_managed_by_apt("fixture-app", "amd64")

    def test_local_only_candidate_remains_eligible_for_beacon(self):
        policy = """\
topgrade:
  Installed: 17.6.1
  Candidate: 17.6.1
  Version table:
 *** 17.6.1 100
        100 /var/lib/dpkg/status
"""
        with patch.object(
            apt_handoff,
            "_run",
            return_value=SimpleNamespace(stdout=policy, stderr="", returncode=0),
        ):
            result = apt_handoff.assert_not_managed_by_apt("topgrade", "amd64")
        self.assertEqual(result["evidence"], "no configured APT repository versions were found")

    def test_preview_parser_captures_installs_upgrades_and_removals(self):
        output = (
            "Inst example-app (2.0 local-deb [amd64])\n"
            "Inst libexample [1.0] (1.1 stable [amd64])\n"
            "Remv obsolete [3.0]\n"
        )
        with patch.object(
            apt_handoff, "_installed_architectures",
            return_value=[
                ("obsolete", "amd64", "3.0"),
                ("libexample", "amd64", "1.0"),
            ],
        ):
            result = apt_handoff.parse_preview(output)
        self.assertEqual(
            result,
            [
                {
                    "package": "example-app", "architecture": "amd64",
                    "old_architecture": "-",
                    "old_version": "-", "new_version": "2.0", "action": "install",
                },
                {
                    "package": "libexample", "architecture": "amd64",
                    "old_architecture": "amd64",
                    "old_version": "1.0", "new_version": "1.1", "action": "install",
                },
                {
                    "package": "obsolete", "architecture": "amd64",
                    "old_architecture": "amd64",
                    "old_version": "3.0", "new_version": "-", "action": "remove",
                },
            ],
        )

    def test_preview_parser_rejects_unknown_package_action_format(self):
        with self.assertRaisesRegex(tracking.TrackingError, "unrecognized install action"):
            apt_handoff.parse_preview("Inst example-app (2.0)\n")

    def test_preview_parser_rejects_unplanned_package_configuration(self):
        output = "Conf unrelated (1.0)\n"
        with patch.object(
            apt_handoff, "_installed_architectures",
            return_value=[("unrelated", "amd64", "1.0")],
        ):
            with self.assertRaisesRegex(tracking.TrackingError, "outside the package changes"):
                apt_handoff.parse_preview(output)

    def test_hook_accepts_exact_transaction_and_ignores_configure_records(self):
        with patch.object(apt_handoff, "_hash_file"), \
             patch.object(apt_handoff, "_metadata", return_value=[
                 "example-app", "amd64", "2.0",
             ]):
            self.assertTrue(
                apt_handoff.validate_hook_protocol(self.protocol, self.manifest)
            )

    def test_hook_rejects_transaction_plan_drift(self):
        changed = self.protocol.replace("2.0 amd64", "2.1 amd64")
        with patch.object(apt_handoff, "_hash_file"), \
             patch.object(apt_handoff, "_metadata", return_value=[
                 "example-app", "amd64", "2.1",
             ]):
            with self.assertRaisesRegex(tracking.TrackingError, "different package version"):
                apt_handoff.validate_hook_protocol(changed, self.manifest)

    def test_hook_rejects_removals_and_downgrades(self):
        removal = (
            "VERSION 3\n\n"
            "obsolete 3.0 amd64 none > - - none **REMOVE**\n"
            f"example-app - - none < 2.0 amd64 none {self.archive}\n"
        )
        with patch.object(apt_handoff, "_hash_file"), \
             patch.object(apt_handoff, "_metadata", return_value=[
                 "example-app", "amd64", "2.0",
             ]):
            with self.assertRaisesRegex(tracking.TrackingError, "removing"):
                apt_handoff.validate_hook_protocol(removal, self.manifest)

        downgrade = (
            "VERSION 3\n\n"
            "example-app 2.0 amd64 none > 1.0 amd64 none "
            f"{self.archive}\n"
        )
        with self.assertRaisesRegex(tracking.TrackingError, "downgrade"):
            apt_handoff.validate_hook_protocol(downgrade, self.manifest)

    def test_hook_rejects_unsupported_or_malformed_protocol(self):
        for protocol in (
            "VERSION 2\n\n",
            "VERSION 3\n",
            "VERSION 3\n\nmalformed\n",
        ):
            with self.subTest(protocol=protocol), self.assertRaises(tracking.TrackingError):
                apt_handoff.validate_hook_protocol(protocol, self.manifest)

    def test_hook_rejects_configuration_of_unplanned_package(self):
        protocol = (
            "VERSION 3\n\n"
            "unrelated 1.0 amd64 none = 1.0 amd64 none **CONFIGURE**\n"
            f"example-app - - none < 2.0 amd64 none {self.archive}\n"
        )
        with self.assertRaisesRegex(tracking.TrackingError, "outside the reviewed plan"):
            apt_handoff.validate_hook_protocol(protocol, self.manifest)


if __name__ == "__main__":
    unittest.main()
