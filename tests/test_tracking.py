import contextlib
import io
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import tracking
import beacon


class TrackingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"XDG_STATE_HOME": self.temp.name})
        env.start()
        self.addCleanup(env.stop)

    def test_package_matching_and_architecture(self):
        output = "app:amd64\tamd64\tinstalled\t1.2.3\napp:i386\ti386\tinstalled\t1.2.2\n"
        result = SimpleNamespace(stdout=output, stderr="", returncode=0)
        with patch("tracking.subprocess.run", return_value=result):
            with self.assertRaisesRegex(tracking.TrackingError, "architecture"):
                tracking.installed_package("app")
            self.assertEqual(tracking.installed_package("app:amd64"), ("app", "amd64", "1.2.3"))
            with self.assertRaises(tracking.TrackingError):
                tracking.installed_package("app*")
        result.returncode = 1
        with patch("tracking.subprocess.run", return_value=result):
            with self.assertRaises(tracking.TrackingError):
                tracking.installed_package("app:amd64")

    def test_repository_inputs(self):
        self.assertEqual(tracking.repository_name("https://github.com/Owner/Project/"), "Owner/Project")
        for value in ("https://github.com.evil.test/a/b", "http://github.com/a/b",
                      "a/..", "a/repo.git", "a/repo/issues", "https://github.com/a/b?x=1"):
            with self.subTest(value=value), self.assertRaises(tracking.TrackingError):
                tracking.repository_name(value)

    def test_version_comparison_is_conservative(self):
        cases = {
            ("1.2.3", "v1.2.4"): "Newer upstream release available.",
            ("1.2.3", "v1.2.3"): "Versions match.",
            ("1.2.4", "1.2.3"): "Installed version is newer than the latest upstream release.",
            ("1.2.3-1", "v1.2.4"): "Unknown: versions cannot be compared safely.",
            ("1.2.3", "v1.2.4-beta"): "Unknown: versions cannot be compared safely.",
            ("1.2", "v1.2.3"): "Unknown: versions cannot be compared safely.",
        }
        for (installed, tag), expected in cases.items():
            with self.subTest(installed=installed, tag=tag):
                self.assertEqual(tracking.compare_versions(installed, tag), expected)

    def test_track_check_and_preserve_decisions(self):
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.2.3")), \
             patch("tracking.resolve_repository", return_value=("Owner/Project", 123)), \
             patch("builtins.input", return_value="yes"), contextlib.redirect_stdout(io.StringIO()):
            tracking.track("app", "Owner/Project")
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.2.3")), \
             patch("tracking.resolve_repository", return_value=("Owner/Renamed", 123)), \
             patch("tracking.latest_release", return_value=("v1.2.4", "https://github.com/Owner/Renamed/releases/tag/v1.2.4")):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                tracking.check("app")
            self.assertIn("Newer upstream release available.", output.getvalue())
            self.assertIn("Owner/Renamed", output.getvalue())
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.2.3")), \
             patch("tracking.resolve_repository", return_value=("Other/Project", 456)), \
             patch("builtins.input", return_value="no"), contextlib.redirect_stdout(io.StringIO()):
            tracking.track("app", "Other/Project")
        with contextlib.closing(tracking.open_database()) as db:
            self.assertEqual(db.execute("SELECT repository_name, repository_id FROM tracked_packages").fetchone(),
                             ("Owner/Renamed", 123))
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.2.3")), \
             patch("tracking.resolve_repository", return_value=("Owner/Project", 999)):
            with self.assertRaisesRegex(tracking.TrackingError, "identity changed"):
                tracking.check("app")

    def test_failed_checks_do_not_change_association(self):
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.2.3")), \
             patch("tracking.resolve_repository", return_value=("Owner/Project", 123)), \
             patch("builtins.input", return_value="y"), contextlib.redirect_stdout(io.StringIO()):
            tracking.track("app", "Owner/Project")
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.2.3")), \
             patch("tracking.resolve_repository", side_effect=tracking.TrackingError("offline")):
            with self.assertRaisesRegex(tracking.TrackingError, "offline"):
                tracking.check("app")
        with contextlib.closing(tracking.open_database()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tracked_packages").fetchone()[0], 1)

    def test_confirmation_is_required(self):
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.2.3")), \
             patch("tracking.resolve_repository", return_value=("Owner/Project", 123)), \
             patch("builtins.input", side_effect=EOFError), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(tracking.TrackingError, "Confirmation required"):
                tracking.track("app", "Owner/Project")
        with contextlib.closing(tracking.open_database()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tracked_packages").fetchone()[0], 0)

    def test_database_guards(self):
        with patch.dict(os.environ, {"XDG_STATE_HOME": "relative"}):
            with self.assertRaisesRegex(tracking.TrackingError, "absolute"):
                tracking.database_path()
        path = Path(self.temp.name) / "beacon" / "tracking.sqlite3"
        path.parent.mkdir()
        with contextlib.closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE unrelated (id INTEGER)")
        with self.assertRaisesRegex(tracking.TrackingError, "unrecognized"):
            tracking.open_database()
        with contextlib.closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),
                             [("unrelated",)])

    def test_github_errors_are_visible(self):
        error = HTTPError("https://api.github.com", 429, "limited", {}, None)
        with patch("tracking.urlopen", side_effect=error):
            with self.assertRaisesRegex(tracking.TrackingError, "rate limits"):
                tracking.github_get("/repos/a/b")
        with patch("tracking.urlopen", side_effect=URLError("offline")):
            with self.assertRaisesRegex(tracking.TrackingError, "offline"):
                tracking.github_get("/repos/a/b")

    def test_cli_tracking_flow(self):
        package_output = SimpleNamespace(
            stdout="app\tamd64\tinstalled\t1.2.3\n", stderr="", returncode=0
        )
        responses = [
            {"full_name": "Owner/Project", "id": 123},
            {"full_name": "Owner/Project", "id": 123},
            {"tag_name": "v1.2.4", "html_url": "https://github.com/Owner/Project/releases/tag/v1.2.4"},
        ]
        output = io.StringIO()
        with patch("tracking.subprocess.run", return_value=package_output), \
             patch("tracking.github_get", side_effect=responses), \
             patch("builtins.input", return_value="yes"), contextlib.redirect_stdout(output):
            with patch.object(sys, "argv", ["beacon.py", "--track", "app", "Owner/Project"]):
                beacon.main()
            with patch.object(sys, "argv", ["beacon.py", "--tracked"]):
                beacon.main()
            with patch.object(sys, "argv", ["beacon.py", "--check", "app"]):
                beacon.main()
        self.assertIn("Association saved.", output.getvalue())
        self.assertIn("app:amd64  https://github.com/Owner/Project", output.getvalue())
        self.assertIn("Newer upstream release available.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
