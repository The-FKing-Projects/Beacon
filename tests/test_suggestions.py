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
        self.assertIn("Match: Very high:", result)
        self.assertIn("Other/app", result)
        self.assertIn("Fork: yes; archived: yes", result)
        self.assertIn("incomplete search results", result)
        self.assertIn("first 3 of 40", result)
        self.assertIn("Nothing was saved.", result)

    def test_homepage_query_timeout_is_bounded_and_reported(self):
        error = suggestions.subprocess.TimeoutExpired("dpkg-query", 15)
        with patch("suggestions.subprocess.run", side_effect=error) as query:
            with self.assertRaisesRegex(tracking.TrackingError, "Unable to read package homepage") as caught:
                suggestions.package_homepage("app", "amd64")
        self.assertIs(caught.exception.__cause__, error)
        self.assertEqual(query.call_args.kwargs["timeout"], 15)

    def test_fd_find_homepage_outweighs_a_synthetic_exact_name_search_match(self):
        direct = repo("sharkdp/fd", 90793418)
        search = {
            "items": [repo("example/fd-find", 1), direct],
            "total_count": 2, "incomplete_results": False,
        }
        out = io.StringIO()
        with patch("tracking.installed_package",
                   return_value=("fd-find", "amd64", "10.3.0-2ubuntu1")), \
             patch("suggestions.package_homepage",
                   return_value="https://github.com/sharkdp/fd"), \
             patch("tracking.github_get", side_effect=[direct, search]), \
             patch("tracking.open_database", side_effect=AssertionError("must not open store")), \
             contextlib.redirect_stdout(out):
            suggestions.suggest("fd-find")

        result = out.getvalue()
        self.assertLess(result.index("https://github.com/sharkdp/fd\n"),
                        result.index("https://github.com/example/fd-find\n"))
        self.assertEqual(result.count("  https://github.com/sharkdp/fd\n"), 1)
        self.assertIn("Match: Very high:", result)
        self.assertIn("Match: High:", result)
        self.assertIn(
            "exact package-name match points to a different repository",
            result,
        )
        self.assertIn("Nothing was saved.", result)

    def test_cli_homepage_timeout_prevents_search_or_database_writes(self):
        with patch.object(sys, "argv", ["beacon", "--suggest", "app"]), \
             patch("tracking.installed_package", return_value=("app", "amd64", "1.2.3")), \
             patch("suggestions.subprocess.run",
                   side_effect=suggestions.subprocess.TimeoutExpired("dpkg-query", 15)), \
             patch("tracking.github_get", side_effect=AssertionError("must not query GitHub")), \
             patch("tracking.open_database", side_effect=AssertionError("must not open store")), \
             contextlib.redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as result:
                beacon.main()
        self.assertEqual(result.exception.code, 1)
        self.assertIn("Unable to read package homepage", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())

    def test_clovereye_similarity_is_not_exact(self):
        rank, evidence = suggestions.name_evidence("clover-eye", "MiguelCarino/CloverEye")
        self.assertEqual(rank, 1)
        self.assertIn("similar", evidence)
        self.assertEqual(suggestions.name_evidence("clover_eye", "owner/clover-eye")[0], 2)

    def test_match_tiers_distinguish_direct_exact_similar_and_search_only(self):
        self.assertIn("homepage directly identifies", suggestions.match_tier(3))
        self.assertIn("names match", suggestions.match_tier(2))
        self.assertIn("similar names only", suggestions.match_tier(1))
        self.assertIn("without independent identity evidence", suggestions.match_tier(0))

    def test_multiple_exact_name_candidates_are_marked_ambiguous(self):
        search = {
            "items": [repo("Publisher/app", 1), repo("Community/app", 2)],
            "total_count": 2,
            "incomplete_results": False,
        }
        out = io.StringIO()
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.0.0")), \
             patch("suggestions.package_homepage", return_value=""), \
             patch("tracking.github_get", return_value=search), \
             contextlib.redirect_stdout(out):
            suggestions.suggest("app")

        result = out.getvalue()
        self.assertIn("multiple repositories share the strongest match evidence", result)
        self.assertIn("no single upstream is identified", result)
        self.assertEqual(result.count("Match: High:"), 2)
        self.assertLess(result.index("https://github.com/Community/app"),
                        result.index("https://github.com/Publisher/app"))

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
        search = {"items": [repo("owner/app-tools", 1)], "total_count": 1, "incomplete_results": False}
        out = io.StringIO()
        with patch.object(sys, "argv", ["beacon.py", "--suggest", "app"]), \
             patch("tracking.installed_package", return_value=("app", "amd64", "1")), \
             patch("suggestions.package_homepage", return_value=""), \
             patch("tracking.github_get", return_value=search), \
             patch("tracking.open_database", side_effect=AssertionError("unexpected write")), \
             contextlib.redirect_stdout(out):
            beacon.main()
        self.assertIn("https://github.com/owner/app-tools", out.getvalue())
        self.assertIn("Candidate only:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
