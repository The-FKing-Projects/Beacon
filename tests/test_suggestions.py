import contextlib
import io
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import beacon
import suggestions
import tracking


def repo(name, identifier, fork=False, archived=False, description=None):
    return {
        "full_name": name, "id": identifier, "fork": fork,
        "archived": archived, "description": description,
    }


class SuggestionsTest(unittest.TestCase):
    def test_homepage_requires_exact_github_repository(self):
        cases = {
            "https://github.com/Owner/Project": "Owner/Project",
            "https://github.com/Owner/Project/": "Owner/Project",
            "https://github.com.evil.example/Owner/Project": None,
            "https://github.com/Owner/Project/releases": None,
            "https://github.com/Owner/Project?query=1": None,
            "http://github.com/Owner/Project": None,
            "https://[bad": None,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(suggestions.homepage_repository(value), expected)

    def test_package_homepage_reports_failures(self):
        with patch("suggestions.subprocess.run", return_value=SimpleNamespace(
                returncode=1, stderr="broken", stdout="")):
            with self.assertRaisesRegex(tracking.TrackingError, "broken"):
                suggestions.package_homepage("app", "amd64")
        with patch("suggestions.subprocess.run", return_value=SimpleNamespace(
                returncode=0, stderr="", stdout="https://github.com/a/b\nextra")):
            with self.assertRaisesRegex(tracking.TrackingError, "invalid characters"):
                suggestions.package_homepage("app", "amd64")

    def test_suggest_ranks_homepage_and_preserves_alternatives(self):
        direct = repo("Official/App", 1, description="Official project")
        search = {
            "items": [repo("Other/app", 2, fork=True, archived=True),
                      repo("Official/App", 1), repo("Another/app-helper", 3)],
            "total_count": 40, "incomplete_results": True,
        }
        out = io.StringIO()
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.0.0")), \
             patch("suggestions.package_homepage", return_value="https://github.com/Official/App"), \
             patch("tracking.github_get", side_effect=[direct, search]), \
             contextlib.redirect_stdout(out):
            suggestions.suggest("app")
        result = out.getvalue()
        self.assertLess(result.index("https://github.com/Official/App\n"),
                        result.index("https://github.com/Other/app\n"))
        self.assertEqual(result.count("  https://github.com/Official/App\n"), 1)
        self.assertIn("installed package homepage", result)
        self.assertIn("Other/app", result)
        self.assertIn("Fork: yes; archived: yes", result)
        self.assertIn("incomplete search results", result)
        self.assertIn("first 3 of 40", result)
        self.assertIn("Nothing was saved.", result)

    def test_clovereye_similarity_is_not_exact(self):
        rank, evidence = suggestions.name_evidence("clover-eye", "MiguelCarino/CloverEye")
        self.assertEqual(rank, 1)
        self.assertIn("similar", evidence)
        self.assertEqual(suggestions.name_evidence("clover_eye", "owner/clover-eye")[0], 2)

    def test_empty_and_malformed_search(self):
        with patch("tracking.installed_package", return_value=("app", "amd64", "1")), \
             patch("suggestions.package_homepage", return_value=""):
            out = io.StringIO()
            with patch("tracking.github_get", return_value={
                "items": [], "total_count": 0, "incomplete_results": False,
            }), contextlib.redirect_stdout(out):
                suggestions.suggest("app")
            self.assertIn("does not prove", out.getvalue())
            for bad in ({"items": [], "total_count": 0},
                        {"items": [None], "total_count": 1, "incomplete_results": False},
                        {"items": [], "total_count": True, "incomplete_results": False}):
                with patch("tracking.github_get", return_value=bad):
                    with self.assertRaises(tracking.TrackingError):
                        suggestions.suggest("app")

    def test_search_failure_is_reported(self):
        with patch("tracking.installed_package", return_value=("app", "amd64", "1")), \
             patch("suggestions.package_homepage", return_value=""), \
             patch("tracking.github_get", side_effect=tracking.TrackingError("rate limits")):
            with self.assertRaisesRegex(tracking.TrackingError, "rate limits"):
                suggestions.suggest("app")

    def test_cli_wires_suggestions_without_tracking(self):
        search = {"items": [repo("owner/app", 1)], "total_count": 1, "incomplete_results": False}
        out = io.StringIO()
        with patch.object(sys, "argv", ["beacon.py", "--suggest", "app"]), \
             patch("tracking.installed_package", return_value=("app", "amd64", "1")), \
             patch("suggestions.package_homepage", return_value=""), \
             patch("tracking.github_get", return_value=search), \
             patch("tracking.open_database", side_effect=AssertionError("unexpected write")), \
             contextlib.redirect_stdout(out):
            beacon.main()
        self.assertIn("https://github.com/owner/app", out.getvalue())


if __name__ == "__main__":
    unittest.main()
