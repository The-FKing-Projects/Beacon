import contextlib
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import beacon
import inspection
import tracking


class InspectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"XDG_STATE_HOME": self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        with contextlib.closing(tracking.open_database()) as db, db:
            db.execute("INSERT INTO tracked_packages VALUES (?, ?, ?, ?)", ("app", "amd64", 123, "owner/repo"))
        self.release = {
            "tag_name": "v1.2.0",
            "assets": [
                {"name": "app_1.2.0_amd64.deb", "browser_download_url":
                 "https://github.com/owner/repo/releases/download/v1.2.0/app_1.2.0_amd64.deb"},
                {"name": "SHA256SUMS", "browser_download_url":
                 "https://github.com/owner/repo/releases/download/v1.2.0/SHA256SUMS"},
            ],
        }

    def test_selects_exact_release_asset_and_rejects_bad_urls(self):
        with patch("tracking.github_get", return_value=self.release):
            tag, asset, checksum = inspection.selected_assets("owner/repo", "app_1.2.0_amd64.deb")
            self.assertEqual(tag, "v1.2.0")
            self.assertTrue(asset.endswith(".deb"))
            self.assertTrue(checksum.endswith("SHA256SUMS"))
            for name in ("../app.deb", "unknown.deb", "SHA256SUMS"):
                with self.subTest(name=name), self.assertRaises(tracking.TrackingError):
                    inspection.selected_assets("owner/repo", name)
        self.release["assets"][0]["browser_download_url"] = "https://github.com/evil/repo/releases/download/v1.2.0/app_1.2.0_amd64.deb"
        with patch("tracking.github_get", return_value=self.release):
            with self.assertRaisesRegex(tracking.TrackingError, "does not match"):
                inspection.selected_assets("owner/repo", "app_1.2.0_amd64.deb")

    def test_checksum_entries_and_ambiguity(self):
        path = Path(self.temp.name) / "sums"
        digest = "a" * 64
        path.write_text(f"{digest}  ./app.deb\n", encoding="utf-8")
        self.assertEqual(inspection.expected_checksum(path, "app.deb"), digest)
        self.assertIsNone(inspection.expected_checksum(path, "other.deb"))
        path.write_text(f"{digest}  app.deb\n{digest} *app.deb\n", encoding="utf-8")
        with self.assertRaisesRegex(tracking.TrackingError, "Multiple"):
            inspection.expected_checksum(path, "app.deb")

    def test_asset_without_checksum_and_multiple_sums(self):
        self.release["assets"].pop()
        with patch("tracking.github_get", return_value=self.release):
            self.assertIsNone(inspection.selected_assets("owner/repo", "app_1.2.0_amd64.deb")[2])
        checksum = {"name": "SHA256SUMS", "browser_download_url":
                    "https://github.com/owner/repo/releases/download/v1.2.0/SHA256SUMS"}
        self.release["assets"].extend([checksum, checksum])
        with patch("tracking.github_get", return_value=self.release):
            with self.assertRaisesRegex(tracking.TrackingError, "ambiguous"):
                inspection.selected_assets("owner/repo", "app_1.2.0_amd64.deb")

    def test_real_debian_archive_metadata(self):
        root = Path(self.temp.name) / "package"
        (root / "DEBIAN").mkdir(parents=True)
        (root / "DEBIAN" / "control").write_text(
            "Package: app\nVersion: 1.2.3-1\nArchitecture: all\n"
            "Maintainer: Test <test@example.test>\nDescription: Test package\n"
        )
        archive = Path(self.temp.name) / "app.deb"
        subprocess.run(["dpkg-deb", "--build", str(root), str(archive)],
                       capture_output=True, check=True)
        self.assertEqual(inspection.inspect_fields(archive), ["app", "all", "1.2.3-1"])
        archive.write_text("not a deb")
        with self.assertRaisesRegex(tracking.TrackingError, "Unable to inspect"):
            inspection.inspect_fields(archive)

    def test_download_size_and_incomplete_body(self):
        class FakeResponse(io.BytesIO):
            def __init__(self, content, length):
                super().__init__(content)
                self.headers = {"Content-Length": length} if length is not None else {}

        destination = Path(self.temp.name) / "asset"
        for content, length, limit, error in [
                (b"abc", "100", 3, "exceeds"),
                (b"abcd", None, 3, "exceeds"),
                (b"ab", "3", 3, "incomplete"),
                (b"abc", "invalid", 3, "content length")]:
            with self.subTest(error=error), patch("inspection.build_opener") as opener:
                opener.return_value.open.return_value = FakeResponse(content, length)
                with self.assertRaisesRegex(tracking.TrackingError, error):
                    inspection.download("https://github.com/a", destination, limit)
                destination.unlink(missing_ok=True)

    def test_version_comparison_debian_semantics(self):
        self.assertEqual(inspection.version_relation("1.0-1", "1.0-2"), "newer")
        self.assertEqual(inspection.version_relation("1.0", "1.0~rc1"), "older")
        self.assertEqual(inspection.version_relation("1.0", "1.0"), "same")
        with self.assertRaisesRegex(tracking.TrackingError, "Invalid Debian version"):
            inspection.version_relation("1.0", "not-a-version")

    def run_inspection(self, metadata=("app", "amd64", "1.2.0"), bad_checksum=False):
        paths = []
        filename = "app_1.2.0_amd64.deb"
        digest = hashlib.sha256(b"example").hexdigest()

        def fake_download(url, dest, limit):
            paths.append(dest)
            if url.endswith("SHA256SUMS"):
                dest.write_text(f"{'a' * 64 if bad_checksum else digest}  {filename}\n")
                return "unused"
            dest.write_bytes(b"example")
            return digest

        output = io.StringIO()
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.0-1")), \
             patch("tracking.resolve_repository", return_value=("owner/repo", 123)), \
             patch("tracking.github_get", return_value=self.release), \
             patch("inspection.download", side_effect=fake_download), \
             patch("inspection.inspect_fields", return_value=metadata), contextlib.redirect_stdout(output):
            try:
                inspection.inspect("app", filename)
            finally:
                self.assertTrue(all(not path.exists() for path in paths))
        return output.getvalue()

    def test_inspection_reports_match_and_cleans_up(self):
        output = self.run_inspection()
        self.assertIn("matches release SHA256SUMS (not authenticated)", output)
        self.assertIn("asset is newer", output)
        self.assertIn("No package was installed", output)
        self.assertIn("asset is newer", self.run_inspection(metadata=("app", "all", "1.2.0")))

    def test_inspection_rejects_mismatches_and_cleans_up(self):
        for metadata, error in [(("other", "amd64", "1.2"), "name mismatch"),
                                (("app", "arm64", "1.2"), "architecture mismatch")]:
            with self.subTest(metadata=metadata), self.assertRaisesRegex(tracking.TrackingError, error):
                self.run_inspection(metadata)
        with self.assertRaisesRegex(tracking.TrackingError, "checksum mismatch"):
            self.run_inspection(bad_checksum=True)

    def test_rejects_untrusted_redirects(self):
        for url in ("http://github.com/a", "https://github.com.evil/a",
                    "https://user@github.com/a", "https://127.0.0.1/a"):
            with self.subTest(url=url):
                self.assertFalse(inspection.allowed_download_url(url))
                with self.assertRaises(tracking.TrackingError):
                    inspection.SafeRedirect().redirect_request(None, None, 302, "", {}, url)
        self.assertTrue(inspection.allowed_download_url("https://release-assets.githubusercontent.com/file"))

    def test_changed_repository_identity_prevents_download(self):
        with patch("tracking.installed_package", return_value=("app", "amd64", "1.0")), \
             patch("tracking.resolve_repository", return_value=("owner/repo", 999)), \
             patch("inspection.download") as download:
            with self.assertRaisesRegex(tracking.TrackingError, "identity changed"):
                inspection.inspect("app", "app_1.2.0_amd64.deb")
            download.assert_not_called()

    def test_cli_wiring(self):
        with patch.object(sys, "argv", ["beacon.py", "--inspect", "app", "app.deb"]), \
             patch("inspection.inspect") as inspect:
            beacon.main()
        inspect.assert_called_once_with("app", "app.deb")


if __name__ == "__main__":
    unittest.main()
