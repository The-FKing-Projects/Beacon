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

    def test_rejects_malformed_or_unsupported_versions(self):
        with self.assertRaises(ValueError):
            bump_version("v0.1.2", "patch")
        with self.assertRaises(ValueError):
            bump_version("0.1.2", "hotfix")

    def test_prepares_version_and_tag_outputs_for_a_feature(self):
        with tempfile.TemporaryDirectory() as directory:
            version_file = Path(directory) / "beacon.py"
            version_file.write_text('VERSION = "0.1.2"\n', encoding="utf-8")
            outputs = []

            with (
                patch("scripts.release.find_tag_for_pr", return_value=None),
                patch("scripts.release.write_outputs", side_effect=outputs.append),
            ):
                prepare_release("feat: add discovery", "", 42, version_file)

            self.assertEqual(version_file.read_text(encoding="utf-8"), 'VERSION = "0.2.0"\n')
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


if __name__ == "__main__":
    unittest.main()
