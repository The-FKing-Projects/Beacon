import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/publish-aptly.yml"
PUBLISH_SCRIPT = textwrap.dedent(WORKFLOW.read_text().split("        run: |\n", 1)[1])


class AptlyPublicationTest(unittest.TestCase):
    def run_publication(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / "bin"
            tools.mkdir()
            commands = {
                "gh": """
                    printf '%s\\n' "$*" >> "$CALL_LOG"
                    if [ "${FAIL_DOWNLOAD:-0}" = 1 ]; then exit 1; fi
                    while [ "$#" -gt 0 ]; do
                      case "$1" in
                        --pattern) filename="$2"; shift 2 ;;
                        --dir) destination="$2"; shift 2 ;;
                        *) shift ;;
                      esac
                    done
                    touch "$destination/$filename"
                """,
                "dpkg-deb": """
                    case "$3" in
                      Package) echo "${PACKAGE_NAME:-beacon}" ;;
                      Version) echo "${PACKAGE_VERSION:-1.2.3-1}" ;;
                      Architecture) echo "${PACKAGE_ARCHITECTURE:-all}" ;;
                      *) exit 1 ;;
                    esac
                """,
                "aptly": """
                    printf 'aptly %s\\n' "$*" >> "$CALL_LOG"
                    if [ "$1" = "${FAIL_APTLY_COMMAND:-none}" ]; then exit 1; fi
                """,
            }
            for name, body in commands.items():
                executable = tools / name
                executable.write_text(
                    "#!/bin/bash\nset -eu\n" + textwrap.dedent(body), encoding="utf-8"
                )
                executable.chmod(0o755)
            log = root / "calls"
            temporary = root / "tmp"
            temporary.mkdir()
            env = {
                **os.environ,
                "PATH": f"{tools}:{os.environ['PATH']}",
                "HOME": str(root),
                "TMPDIR": str(temporary),
                "TAG": "v1.2.3",
                "GITHUB_REPOSITORY": "The-FKing-Projects/Beacon",
                "EVENT_NAME": "workflow_dispatch",
                "WORKFLOW_REF": "refs/heads/main",
                "CALL_LOG": str(log),
                **overrides,
            }
            result = subprocess.run(
                ["bash", "-c", PUBLISH_SCRIPT],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            calls = log.read_text() if log.exists() else ""
            self.assertEqual(list(temporary.iterdir()), [], result.stderr)
            return result, calls

    def test_publishes_exact_release_asset_with_signing(self):
        result, calls = self.run_publication()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "release download v1.2.3 --repo The-FKing-Projects/Beacon "
            "--pattern beacon_1.2.3-1_all.deb --dir ",
            calls,
        )
        self.assertIn("aptly repo add fkingprojects ", calls)
        self.assertTrue(
            calls.endswith("aptly publish update -batch=true -skip-signing=false stable .\n")
        )

    def test_rejects_invalid_tags_before_download(self):
        for tag in ("main", "v1.2", "v1.2.3-rc1", "--help", "v1.2.3\n"):
            with self.subTest(tag=tag):
                result, calls = self.run_publication(TAG=tag)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Expected a release tag", result.stderr)
                self.assertEqual(calls, "")

    def test_only_dispatch_is_registered_as_a_trigger(self):
        triggers = WORKFLOW.read_text().split("on:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(
            [line.strip() for line in triggers.splitlines() if line.startswith("  ")
             and not line.startswith("   ")],
            ["workflow_dispatch:"],
        )

    def test_targets_existing_organization_runner_labels(self):
        labels = WORKFLOW.read_text().split("    runs-on:\n", 1)[1].split(
            "    timeout-minutes:", 1
        )[0]
        self.assertEqual(
            [line.strip() for line in labels.splitlines()],
            ["- self-hosted", "- Linux", "- X64", "- fkingprojects"],
        )

    def test_rejects_untrusted_events_and_forks_before_download(self):
        contexts = [
            {"EVENT_NAME": event}
            for event in ("pull_request", "pull_request_target", "issue_comment",
                          "push", "workflow_call", "workflow_run")
        ] + [
            {"GITHUB_REPOSITORY": "fork-owner/Beacon"},
            {"WORKFLOW_REF": "refs/heads/untrusted"},
            {"WORKFLOW_REF": "refs/tags/v1.2.3"},
        ]
        for context in contexts:
            with self.subTest(context=context):
                result, calls = self.run_publication(**context)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("requires workflow_dispatch", result.stderr)
                self.assertEqual(calls, "")

    def test_rejects_mismatched_metadata_before_repository_mutation(self):
        for field, value in (
            ("PACKAGE_NAME", "another-package"),
            ("PACKAGE_VERSION", "1.2.4-1"),
            ("PACKAGE_ARCHITECTURE", "amd64"),
        ):
            with self.subTest(field=field):
                result, calls = self.run_publication(**{field: value})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("metadata does not match", result.stderr)
                self.assertNotIn("aptly ", calls)

    def test_download_failure_does_not_mutate_repository(self):
        result, calls = self.run_publication(FAIL_DOWNLOAD="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("aptly ", calls)

    def test_add_failure_stops_before_publication(self):
        result, calls = self.run_publication(FAIL_APTLY_COMMAND="repo")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("aptly repo add ", calls)
        self.assertNotIn("aptly publish ", calls)

    def test_signing_failure_is_reported_without_fallback(self):
        result, calls = self.run_publication(FAIL_APTLY_COMMAND="publish")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.count("aptly publish "), 1)
        self.assertNotIn("-skip-signing=true", calls)


if __name__ == "__main__":
    unittest.main()
