import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from beacon import package_confidence, package_source


class BeaconSourceSignalsTest(unittest.TestCase):
    @patch("beacon.subprocess.run")
    def test_detects_ppa_source(self, mock_run):
        def fake_run(args, **kwargs):
            if args[:2] == ["apt-cache", "policy"]:
                return SimpleNamespace(
                    stdout="""
N: /etc/apt/sources.list.d/floorp.sources
N: Candidate: 1.0.0
N: Version table:
N:     1.0.0 500 https://ppa.floorp.app/amd64 ./ Packages
N:     1.0.0 500 https://ppa.floorp.app/amd64 ./ Packages
                    """,
                    stderr="",
                )
            if args[:2] == ["apt-cache", "show"]:
                return SimpleNamespace(
                    stdout="Origin: Ubuntu\nSuite: jammy\n",
                    stderr="",
                )
            if args[:2] == ["apt", "list"]:
                return SimpleNamespace(stdout="", stderr="")
            raise AssertionError(f"Unexpected command: {args}")

        mock_run.side_effect = fake_run

        self.assertEqual(package_source("floorp"), "PPA")
        self.assertEqual(package_confidence("floorp"), "High")

    @patch("beacon.subprocess.run")
    def test_detects_local_candidate_source(self, mock_run):
        def fake_run(args, **kwargs):
            if args[:2] == ["apt-cache", "policy"]:
                return SimpleNamespace(
                    stdout="""
Installed: 1.2.3
    """,
                    stderr="",
                )
            if args[:2] == ["apt-cache", "show"]:
                return SimpleNamespace(stdout="", stderr="")
            if args[:2] == ["apt", "list"]:
                return SimpleNamespace(
                    stdout="clover-eye/now 1.2.3 amd64 [installed,local]\n",
                    stderr="",
                )
            raise AssertionError(f"Unexpected command: {args}")

        mock_run.side_effect = fake_run

        self.assertEqual(package_source("clover-eye"), "Local .deb Candidate")
        self.assertEqual(package_confidence("clover-eye"), "Medium")


if __name__ == "__main__":
    unittest.main()
