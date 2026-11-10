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
            ("1.2.3", "v1.2.4-beta"): "Unknown: versions cannot be compared safely.",
            ("1.2", "v1.2.3"): "Unknown: versions cannot be compared safely.",
            ("1.2.3-1ubuntu1", "v1.2.4"): "Unknown: versions cannot be compared safely.",
            ("1.2.3-1+b1", "v1.2.4"): "Unknown: versions cannot be compared safely.",
            ("1.2.3-1~deb12u1", "v1.2.4"): "Unknown: versions cannot be compared safely.",
            ("1:1.2.3-1", "v1.2.4"): "Unknown: versions cannot be compared safely.",
            ("0:1.2.3-1", "v1.2.4"): "Unknown: versions cannot be compared safely.",
            ("1.2.3~rc1-1", "v1.2.4"): "Unknown: versions cannot be compared safely.",
            ("1.2.3-beta-1", "v1.2.4"): "Unknown: versions cannot be compared safely.",
            ("1.2.3-", "v1.2.4"): "Unknown: versions cannot be compared safely.",
            ("1.2.3-1-2", "v1.2.4"): "Unknown: versions cannot be compared safely.",
            ("1.2.3-1", "v1.2.4-1"): "Unknown: versions cannot be compared safely.",
            ("1.2.3-1", "v1.2.4-beta"): "Unknown: versions cannot be compared safely.",
            ("01.2.3-1", "v1.2.4"): "Unknown: versions cannot be compared safely.",
        }
        for (installed, tag), expected in cases.items():
            with self.subTest(installed=installed, tag=tag):
                self.assertEqual(tracking.compare_versions(installed, tag), expected)

    def test_numeric_debian_revisions_compare_only_upstream(self):
        cases = [
            ("0.8.1-1", "v0.8.2", "Newer upstream release available.", "1"),
            ("1.2.3-99", "v1.2.4", "Newer upstream release available.", "99"),
            ("1.2.9-1", "v1.2.10", "Newer upstream release available.", "1"),
            ("1.2.3-1", "v1.2.3", "Upstream versions match.", "1"),
            ("1.2.3-0", "1.2.3", "Upstream versions match.", "0"),
            ("1.2.3-01", "v1.2.3", "Upstream versions match.", "01"),
            ("1.2.4-1", "v1.2.3",
             "Installed version is newer than the latest upstream release.", "1"),
        ]
        for installed, tag, status, revision in cases:
            with self.subTest(installed=installed, tag=tag):
                self.assertEqual(
                    tracking.compare_versions(installed, tag),
                    f"{status} Comparing upstream versions only; installed Debian revision "
                    f"{revision} is not compared.",
                )

    def test_track_check_and_preserve_decisions(self):
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.2.3")), \
             patch("tracking.resolve_repository", return_value=("Owner/Project", 123)), \
             patch("builtins.input", return_value="yes"), contextlib.redirect_stdout(io.StringIO()):
            tracking.track("app", "Owner/Project")
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.2.3")), \
             patch("tracking.resolve_repository", return_value=("Owner/Renamed", 123)), \
             patch("tracking.latest_release", return_value=("v1.2.4", "https://github.com/Owner/Renamed/releases/tag/v1.2.4", [])):
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

    def save_association(self, architecture="amd64", repository="Owner/Project", identifier=123):
        with contextlib.closing(tracking.open_database()) as db, db:
            db.execute("INSERT INTO tracked_packages VALUES (?, ?, ?, ?)",
                       ("app", architecture, identifier, repository))

    def test_untrack_is_offline_and_independent_of_installed_state(self):
        self.save_association()
        self.save_association("arm64")
        with patch("tracking.installed_package", side_effect=AssertionError("dpkg not needed")), \
             patch("tracking.github_get", side_effect=AssertionError("network not needed")), \
             patch("builtins.input", return_value="YES"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            tracking.untrack("app:amd64")
        self.assertIn("Current association: https://github.com/Owner/Project", output.getvalue())
        self.assertIn("no package will be uninstalled", output.getvalue())
        self.assertIn("Association removed.", output.getvalue())
        with contextlib.closing(tracking.open_database()) as db:
            self.assertEqual(db.execute("SELECT architecture FROM tracked_packages").fetchall(),
                             [("arm64",)])

    def test_untrack_requires_unambiguous_saved_architecture(self):
        self.save_association()
        self.save_association("arm64")
        with patch("builtins.input", side_effect=AssertionError("must not prompt")):
            with self.assertRaisesRegex(tracking.TrackingError, "Multiple tracked architectures"):
                tracking.untrack("app")
            for package in ("missing", "app:i386"):
                with self.subTest(package=package):
                    with self.assertRaisesRegex(tracking.TrackingError, "No confirmed upstream"):
                        tracking.untrack(package)
            for package in ("app*", "app:", "app:amd64:arm64"):
                with self.subTest(package=package):
                    with self.assertRaisesRegex(tracking.TrackingError, "Invalid Debian package name"):
                        tracking.untrack(package)
        with contextlib.closing(tracking.open_database()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tracked_packages").fetchone()[0], 2)

    def test_untrack_decline_and_missing_confirmation_preserve_association(self):
        self.save_association()
        for answer in ("", "no", "invalid"):
            with self.subTest(answer=answer), patch("builtins.input", return_value=answer), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                tracking.untrack("app")
                self.assertIn("Association not removed.", output.getvalue())
        with patch("builtins.input", side_effect=EOFError), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(tracking.TrackingError, "Confirmation required"):
                tracking.untrack("app")
        with contextlib.closing(tracking.open_database()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tracked_packages").fetchone()[0], 1)

    def test_untrack_does_not_remove_concurrently_changed_association(self):
        self.save_association()

        def change_during_confirmation(_):
            with contextlib.closing(tracking.open_database()) as db, db:
                db.execute("UPDATE tracked_packages SET repository_name=?, repository_id=?",
                           ("Other/Project", 456))
            return "yes"

        with patch("builtins.input", side_effect=change_during_confirmation), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(tracking.TrackingError, "changed during confirmation"):
                tracking.untrack("app")
        with contextlib.closing(tracking.open_database()) as db:
            self.assertEqual(db.execute("SELECT repository_name, repository_id FROM tracked_packages").fetchone(),
                             ("Other/Project", 456))

    def test_cli_untrack_and_list(self):
        self.save_association()
        with patch("builtins.input", return_value="y"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            with patch.object(sys, "argv", ["beacon", "--untrack", "app"]):
                beacon.main()
            with patch.object(sys, "argv", ["beacon", "--tracked"]):
                beacon.main()
        self.assertIn("Association removed.", output.getvalue())
        self.assertIn("No confirmed upstream associations.", output.getvalue())

    def test_cli_untrack_errors_and_help(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            beacon.help_menu()
        self.assertIn("--untrack <package>", output.getvalue())
        for args, message in (
            (["--untrack"], "Invalid arguments"),
            (["--untrack", "app", "extra"], "Invalid arguments"),
            (["--untrack", "app"], "No confirmed upstream"),
        ):
            with self.subTest(args=args), patch.object(sys, "argv", ["beacon", *args]), \
                 contextlib.redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as exc:
                    beacon.main()
                self.assertEqual(exc.exception.code, 1)
                self.assertIn(message, error.getvalue())

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

    def test_database_rejects_nonempty_unversioned_schemas_without_changes(self):
        schemas = [
            "CREATE VIEW user_data AS SELECT 42 AS value",
            "CREATE TABLE unrelated (id INTEGER)",
        ]
        for schema in schemas:
            with self.subTest(schema=schema), tempfile.TemporaryDirectory() as state, \
                 patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                path = tracking.database_path()
                path.parent.mkdir()
                with contextlib.closing(sqlite3.connect(path)) as db, db:
                    db.execute(schema)
                before = path.read_bytes()
                with self.assertRaisesRegex(tracking.TrackingError, "unrecognized"):
                    tracking.open_database()
                self.assertEqual(path.read_bytes(), before)

    def test_database_rejects_incompatible_versioned_schemas_without_changes(self):
        cases = [
            ("CREATE TABLE tracked_packages (package_name TEXT)", 1),
            ("""CREATE TABLE tracked_packages (
                package_name TEXT NOT NULL, architecture TEXT NOT NULL,
                repository_id INTEGER NOT NULL, repository_name TEXT NOT NULL
            )""", 1),
            ("""CREATE TABLE tracked_packages (
                package_name TEXT, architecture TEXT,
                repository_id INTEGER, repository_name TEXT,
                PRIMARY KEY (package_name, architecture)
            )""", 1),
            ("CREATE TABLE tracked_packages (package_name TEXT)", 2),
        ]
        for schema, version in cases:
            with self.subTest(schema=schema, version=version), \
                 tempfile.TemporaryDirectory() as state, \
                 patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                path = tracking.database_path()
                path.parent.mkdir()
                with contextlib.closing(sqlite3.connect(path)) as db, db:
                    db.execute(schema)
                    db.execute(f"PRAGMA user_version = {version}")
                before = path.read_bytes()
                with self.assertRaises(tracking.TrackingError) as error:
                    tracking.open_database()
                self.assertIn(str(path), str(error.exception))
                self.assertIn("Beacon has not reset it", str(error.exception))
                self.assertEqual(path.read_bytes(), before)

    def test_database_rejects_invalid_saved_associations_without_changes(self):
        cases = [
            ("app:amd64", "amd64", 123, "Owner/Project"),
            ("app*", "amd64", 123, "Owner/Project"),
            ("app", "amd64\n", 123, "Owner/Project"),
            ("app", "amd64", 0, "Owner/Project"),
            ("app", "amd64", 1.5, "Owner/Project"),
            ("app", "amd64", "not-an-id", "Owner/Project"),
            ("app", "amd64", 123, "https://github.com/Owner/Project"),
            ("app", "amd64", 123, "Owner/Project\n"),
            ("app", "amd64", 123, sqlite3.Binary(b"Owner/Project")),
        ]
        for row in cases:
            with self.subTest(row=row), tempfile.TemporaryDirectory() as state, \
                 patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                with contextlib.closing(tracking.open_database()) as db, db:
                    db.execute("INSERT INTO tracked_packages VALUES (?, ?, ?, ?)", row)
                path = tracking.database_path()
                before = path.read_bytes()
                with self.assertRaises(tracking.TrackingError):
                    tracking.open_database()
                self.assertEqual(path.read_bytes(), before)

    def test_database_rejects_extra_schema_objects_without_changes(self):
        self.save_association()
        with contextlib.closing(tracking.open_database()) as db, db:
            db.execute("CREATE TRIGGER prevent_delete BEFORE DELETE ON tracked_packages "
                       "BEGIN SELECT RAISE(IGNORE); END")
        path = tracking.database_path()
        before = path.read_bytes()
        with self.assertRaisesRegex(tracking.TrackingError, "unrecognized"):
            tracking.open_database()
        self.assertEqual(path.read_bytes(), before)

    def test_corrupt_database_has_actionable_cli_error_and_is_preserved(self):
        path = tracking.database_path()
        path.parent.mkdir()
        original = b"This is not a SQLite database."
        path.write_bytes(original)
        with patch.object(sys, "argv", ["beacon", "--tracked"]), \
             contextlib.redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as result:
                beacon.main()
        self.assertEqual(result.exception.code, 1)
        self.assertIn(str(path), error.getvalue())
        self.assertIn("Preserve the database before attempting recovery", error.getvalue())
        self.assertEqual(path.read_bytes(), original)

    def test_valid_existing_store_opens_without_changes(self):
        self.save_association()
        path = tracking.database_path()
        before = path.read_bytes()
        with contextlib.closing(tracking.open_database()) as db:
            self.assertEqual(db.execute("SELECT * FROM tracked_packages").fetchall(),
                             [("app", "amd64", 123, "Owner/Project")])
        self.assertEqual(path.read_bytes(), before)

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
            stdout="app\tamd64\tinstalled\t1.2.3-1\n", stderr="", returncode=0
        )
        responses = [
            {"full_name": "Owner/Project", "id": 123},
            {"full_name": "Owner/Project", "id": 123},
            {"tag_name": "v1.2.4", "html_url": "https://github.com/Owner/Project/releases/tag/v1.2.4",
             "assets": [{"name": "app_1.2.4_amd64.deb", "browser_download_url":
                         "https://github.com/Owner/Project/releases/download/v1.2.4/app_1.2.4_amd64.deb"}]},
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
        self.assertIn("installed Debian revision 1 is not compared.", output.getvalue())
        self.assertIn("app_1.2.4_amd64.deb: Likely candidate", output.getvalue())

    def test_asset_filename_matching(self):
        cases = [
            ("clovereye_0.1.0_amd64.deb", "clover-eye", "amd64", "Likely candidate"),
            ("clover-eye-1.2.3-x86_64.deb", "clover-eye", "amd64", "Likely candidate"),
            ("app_1.2.3_aarch64.deb", "app", "arm64", "Likely candidate"),
            ("app_1.2.3_all.deb", "app", "amd64", "Likely candidate"),
            ("app_1.2.3_arm64.deb", "app", "amd64", "Not suggested"),
            ("different_1.2.3_amd64.deb", "app", "amd64", "Unverified"),
            ("app_1.2.3.deb", "app", "amd64", "Unverified"),
            ("app_1.2.3_amd64.deb", "app", "riscv64", "Not suggested"),
        ]
        for filename, package, architecture, expected in cases:
            with self.subTest(filename=filename, architecture=architecture):
                self.assertTrue(tracking.asset_match(filename, package, architecture).startswith(expected))

    def test_asset_reporting_no_match_and_multiple_matches(self):
        url = "https://github.com/owner/project/releases/download/v1/"
        cases = [
            ([], "none found"),
            ([("app_1_arm64.deb", url + "arm")], "No likely candidates"),
            ([("app_1_amd64.deb", url + "one"),
              ("app_1_all.deb", url + "two")], "Multiple likely candidates"),
            ([("app.deb", url + "unknown")], "architecture not recognized"),
        ]
        for assets, expected in cases:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                tracking.print_deb_assets(assets, "app", "amd64")
            self.assertIn(expected, output.getvalue())

    def test_release_asset_validation(self):
        release = {"tag_name": "v1", "html_url": "https://github.com/owner/repo/releases/tag/v1"}
        cases = [
            ({}, "missing release assets"),
            ({"assets": None}, "missing release assets"),
            ({"assets": [None]}, "invalid release asset"),
            ({"assets": [{"name": "app.deb", "browser_download_url": "https://evil.test/app.deb"}]},
             "invalid Debian asset URL"),
            ({"assets": [{"name": "app\n.deb", "browser_download_url": "https://github.com/a/b"}]},
             "invalid Debian release asset"),
        ]
        for addition, expected in cases:
            with self.subTest(addition=addition), patch("tracking.github_get", return_value={**release, **addition}):
                with self.assertRaisesRegex(tracking.TrackingError, expected):
                    tracking.latest_release("owner/repo")
        with patch("tracking.github_get", return_value={**release, "assets": [
                {"name": "app.rpm"},
                {"name": "app.deb", "browser_download_url": "https://github.com/owner/repo/releases/download/v1/app.deb"},
        ]}):
            _, _, assets = tracking.latest_release("owner/repo")
            self.assertEqual(len(assets), 1)


if __name__ == "__main__":
    unittest.main()
