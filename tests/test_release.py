import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.release import (
    bump_version,
    classify_bump,
    prepare_release,
    update_changelog_version_text,
    update_version_text,
)


class ReleaseVersioningTest(unittest.TestCase):
    def test_feature_title_requests_minor_release(self):
        self.assertEqual(classify_bump("feat: add discovery", ""), "minor")

    def test_scoped_bug_fix_requests_patch_release(self):
        self.assertEqual(classify_bump("fix(parser): handle empty output", ""), "patch")

    def test_performance_change_requests_patch_release(self):
        self.assertEqual(classify_bump("perf: speed up inventory", ""), "patch")

    def test_breaking_title_requests_major_release(self):
        self.assertEqual(classify_bump("feat(api)!: change output", ""), "major")

    def test_breaking_footer_requests_major_release(self):
        self.assertEqual(
            classify_bump("refactor: replace package result format", "BREAKING CHANGE: update consumers"),
            "major",
        )

    def test_non_release_titles_do_not_bump_version(self):
        for title in (
            "docs: clarify install behavior",
            "test: add discovery fixture",
            "chore: update workflow",
            "feature: add discovery",
        ):
            with self.subTest(title=title):
                self.assertIsNone(classify_bump(title, ""))

    def test_semver_bumps_reset_lower_components(self):
        self.assertEqual(bump_version("0.1.2", "patch"), "0.1.3")
        self.assertEqual(bump_version("0.1.2", "minor"), "0.2.0")
        self.assertEqual(bump_version("0.1.2", "major"), "1.0.0")

    def test_replaces_exactly_one_application_version(self):
        source = 'VERSION = "0.1.2"\nOTHER = "0.1.2"\n'
        self.assertEqual(
            update_version_text(source, "0.2.0"),
            'VERSION = "0.2.0"\nOTHER = "0.1.2"\n',
        )

    def test_updates_debian_changelog_package_version(self):
        source = (
            "beacon (0.7.0-1) unstable; urgency=medium\n\n"
            "  * Initial release.\n\n"
            " -- The FK'ing Projects <FiendKing04@gmail.com>  "
            "Mon, 09 Nov 2026 00:00:00 +0000\n"
        )
        self.assertIn(
            "beacon (0.8.0-1) unstable; urgency=medium\n\n"
            "  * Release for pull request #42: feat: add discovery.",
            update_changelog_version_text(source, "0.8.0", "feat: add discovery", 42),
        )

    def test_rejects_changelog_without_beacon_entry(self):
        with self.assertRaises(ValueError):
            update_changelog_version_text(
                "other (1.0-1) unstable; urgency=medium\n",
                "0.8.0",
                "feat: update",
                42,
            )

    def test_rejects_multiline_release_title_in_changelog(self):
        source = "beacon (0.7.0-1) unstable; urgency=medium\n"
        with self.assertRaises(ValueError):
            update_changelog_version_text(source, "0.8.0", "feat: update\n  * forged", 42)

    def test_rejects_malformed_or_unsupported_versions(self):
        with self.assertRaises(ValueError):
            bump_version("v0.1.2", "patch")
        with self.assertRaises(ValueError):
            bump_version("0.1.2", "hotfix")

    def test_prepares_version_and_tag_outputs_for_a_feature(self):
        with tempfile.TemporaryDirectory() as directory:
            version_file = Path(directory) / "beacon.py"
            version_file.write_text('VERSION = "0.1.2"\n', encoding="utf-8")
            changelog_file = Path(directory) / "changelog"
            changelog_file.write_text(
                "beacon (0.1.2-1) unstable; urgency=medium\n",
                encoding="utf-8",
            )
            outputs = []

            with (
                patch("scripts.release.find_tag_for_pr", return_value=None),
                patch("scripts.release.write_outputs", side_effect=outputs.append),
            ):
                prepare_release(
                    "feat: add discovery",
                    "",
                    42,
                    version_file,
                    changelog_file,
                )

            self.assertEqual(version_file.read_text(encoding="utf-8"), 'VERSION = "0.2.0"\n')
            self.assertEqual(
                changelog_file.read_text(encoding="utf-8").splitlines()[:3],
                [
                    "beacon (0.2.0-1) unstable; urgency=medium",
                    "",
                    "  * Release for pull request #42: feat: add discovery.",
                ],
            )
            self.assertEqual(
                outputs,
                [
                    {
                        "release": "true",
                        "version": "0.2.0",
                        "tag": "v0.2.0",
                        "bump": "minor",
                        "reused": "false",
                    }
                ],
            )

    def test_reuses_tag_for_an_already_processed_pull_request(self):
        with tempfile.TemporaryDirectory() as directory:
            version_file = Path(directory) / "beacon.py"
            version_file.write_text('VERSION = "0.2.0"\n', encoding="utf-8")
            outputs = []

            with (
                patch("scripts.release.find_tag_for_pr", return_value="v0.2.0"),
                patch("scripts.release.write_outputs", side_effect=outputs.append),
            ):
                prepare_release("feat: add discovery", "", 42, version_file)

            self.assertEqual(version_file.read_text(encoding="utf-8"), 'VERSION = "0.2.0"\n')
            self.assertEqual(outputs[0]["reused"], "true")
            self.assertEqual(outputs[0]["tag"], "v0.2.0")

    def test_non_release_pull_request_does_not_change_version(self):
        with tempfile.TemporaryDirectory() as directory:
            version_file = Path(directory) / "beacon.py"
            original_source = 'VERSION = "0.1.2"\n'
            version_file.write_text(original_source, encoding="utf-8")
            outputs = []

            with (
                patch("scripts.release.find_tag_for_pr", return_value=None),
                patch("scripts.release.write_outputs", side_effect=outputs.append),
            ):
                prepare_release("docs: explain release policy", "", 43, version_file)

            self.assertEqual(version_file.read_text(encoding="utf-8"), original_source)
            self.assertEqual(outputs, [{"release": "false"}])

    def test_manual_release_uses_explicit_bump_and_run_identity(self):
        for bump, version in (("patch", "0.8.3"), ("minor", "0.9.0"), ("major", "1.0.0")):
            with self.subTest(bump=bump), tempfile.TemporaryDirectory() as directory:
                version_file = Path(directory) / "beacon.py"
                version_file.write_text('VERSION = "0.8.2"\n', encoding="utf-8")
                changelog_file = Path(directory) / "changelog"
                changelog_file.write_text("beacon (0.8.2-1) unstable; urgency=medium\n",
                                          encoding="utf-8")
                with patch("scripts.release.find_tag_for_marker", return_value=None) as lookup, \
                     patch("scripts.release.write_outputs") as output:
                    prepare_release("Ship tracking management", "", None, version_file,
                                    changelog_file, manual_run_id=1234, manual_bump=bump)
                lookup.assert_called_once_with("Beacon-Manual-Run: 1234")
                self.assertEqual(version_file.read_text(), f'VERSION = "{version}"\n')
                self.assertIn(f"beacon ({version}-1)", changelog_file.read_text())
                self.assertIn("Release for workflow run 1234: Ship tracking management.",
                              changelog_file.read_text())
                self.assertEqual(output.call_args.args[0]["tag"], f"v{version}")
                self.assertEqual(output.call_args.args[0]["reused"], "false")

    def test_manual_rerun_reuses_original_tag_without_changing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "beacon.py"
            original = 'VERSION = "0.10.0"\n'
            path.write_text(original, encoding="utf-8")
            with patch("scripts.release.find_tag_for_marker", return_value="v0.9.0"), \
                 patch("scripts.release.write_outputs") as output:
                prepare_release("Ship tracking management", "", None, path,
                                manual_run_id=1234, manual_bump="minor")
            self.assertEqual(path.read_text(), original)
            self.assertEqual(output.call_args.args[0]["tag"], "v0.9.0")
            self.assertEqual(output.call_args.args[0]["reused"], "true")

    def test_invalid_manual_requests_leave_files_unchanged(self):
        cases = [
            {"manual_run_id": 0, "manual_bump": "minor"},
            {"manual_run_id": 1, "manual_bump": None},
            {"manual_run_id": 1, "manual_bump": "hotfix"},
            {"manual_run_id": None, "manual_bump": "minor"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "beacon.py"
            original = 'VERSION = "0.8.2"\n'
            path.write_text(original, encoding="utf-8")
            for kwargs in cases:
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    prepare_release("Ship changes", "", None, path, **kwargs)
                self.assertEqual(path.read_text(), original)
            for title in ("", "  ", "Ship\nforged", "Ship\rforged"):
                with self.subTest(title=title), self.assertRaises(ValueError):
                    prepare_release(title, "", None, path, manual_run_id=1, manual_bump="minor")
                self.assertEqual(path.read_text(), original)
            with self.assertRaises(ValueError):
                prepare_release("Ship changes", "", 42, path,
                                manual_run_id=1, manual_bump="minor")


if __name__ == "__main__":
    unittest.main()
