import contextlib
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import apt_handoff
import beacon
import inspection
import tracking
import updates


class UpdatesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.dict(os.environ, {
            "XDG_STATE_HOME": str(Path(self.temp.name) / "state"),
            "XDG_DATA_HOME": str(Path(self.temp.name) / "data"),
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        with contextlib.closing(tracking.open_database()) as db, db:
            db.execute(
                "INSERT INTO tracked_packages VALUES (?, ?, ?, ?)",
                ("app", "amd64", 123, "owner/repo"),
            )
        self.filename = "app_2.0_amd64.deb"
        self.asset_url = (
            "https://github.com/owner/repo/releases/download/v2.0/"
            "app_2.0_amd64.deb"
        )
        self.checksum_url = (
            "https://github.com/owner/repo/releases/download/v2.0/SHA256SUMS"
        )
        self.asset_bytes = b"pinned Debian archive fixture"
        self.digest = hashlib.sha256(self.asset_bytes).hexdigest()

    def common_prepare_patches(self, *, bad_checksum=False, relation="newer"):
        checksum = ("0" * 64 if bad_checksum else self.digest)

        def fake_download(url, destination, _limit):
            if url.endswith("SHA256SUMS"):
                destination.write_text(f"{checksum}  {self.filename}\n", encoding="utf-8")
                return hashlib.sha256(destination.read_bytes()).hexdigest()
            destination.write_bytes(self.asset_bytes)
            return self.digest

        return (
            patch("tracking.installed_package", return_value=("app", "amd64", "1.0")),
            patch("tracking.resolve_repository", return_value=("owner/repo", 123)),
            patch("apt_handoff.assert_not_managed_by_apt", return_value={
                "installed": "1.0", "candidate": "(none)",
                "evidence": "no configured APT repository candidate was found",
            }),
            patch("inspection.selected_assets", return_value=(
                "v2.0", self.asset_url, self.checksum_url,
            )),
            patch("inspection.download", side_effect=fake_download),
            patch("inspection.inspect_fields", return_value=["app", "amd64", "2.0"]),
            patch("inspection.version_relation", return_value=relation),
        )

    def prepare_fixture(self):
        patches = self.common_prepare_patches()
        with contextlib.ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            with contextlib.redirect_stdout(io.StringIO()):
                updates.prepare("app", self.filename)
        return updates._prepared_row("app", "amd64")

    def test_prepare_pins_artifact_and_persists_release_evidence(self):
        patches = self.common_prepare_patches()
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            with contextlib.redirect_stdout(output):
                updates.prepare("app", self.filename)

        row = updates._prepared_row("app", "amd64")
        self.assertEqual(row[3:15], (
            "owner/repo", "v2.0", self.filename, self.asset_url, self.checksum_url,
            self.digest, self.digest, "matched-unauthenticated", "app", "amd64",
            "2.0", "1.0",
        ))
        artifact = Path(row[15])
        self.assertTrue(artifact.is_file())
        self.assertEqual(artifact.read_bytes(), self.asset_bytes)
        self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
        self.assertIn("Publisher authenticity is not independently verified.", output.getvalue())

    def test_prepare_rejects_bad_checksum_without_saving_or_leaking_partial_files(self):
        patches = self.common_prepare_patches(bad_checksum=True)
        with contextlib.ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            with self.assertRaisesRegex(tracking.TrackingError, "checksum mismatch"):
                updates.prepare("app", self.filename)

        self.assertIsNone(updates._prepared_row("app", "amd64"))
        self.assertEqual(list(updates._updates_directory().glob(".partial-*")), [])

    def test_interrupted_repreparation_preserves_last_good_artifact(self):
        existing = self.prepare_fixture()
        directory = updates._updates_directory()
        for stage in ("archive", "checksum"):
            for failure in (tracking.TrackingError, KeyboardInterrupt):
                def interrupted_download(url, destination, _limit):
                    is_checksum = url.endswith("SHA256SUMS")
                    destination.write_bytes(b"interrupted download")
                    if is_checksum == (stage == "checksum"):
                        raise failure("download interrupted")
                    destination.write_bytes(self.asset_bytes)
                    return self.digest

                with self.subTest(stage=stage, failure=failure.__name__):
                    (directory / ".partial-previous-interruption").write_bytes(b"stale partial")
                    with contextlib.ExitStack() as stack:
                        for item in self.common_prepare_patches():
                            stack.enter_context(item)
                        stack.enter_context(patch(
                            "inspection.download", side_effect=interrupted_download,
                        ))
                        with contextlib.redirect_stdout(io.StringIO()), \
                             self.assertRaisesRegex(failure, "download interrupted"):
                            updates.prepare("app", self.filename)
                    self.assertEqual(updates._prepared_row("app", "amd64"), existing)
                    self.assertEqual(Path(existing[15]).read_bytes(), self.asset_bytes)
                    self.assertEqual(list(directory.glob(".partial-*")), [])
                    self.assertEqual(list(directory.glob("*.deb")), [Path(existing[15])])

    def test_repreparation_storage_failure_preserves_previous_artifact(self):
        existing = self.prepare_fixture()
        with contextlib.ExitStack() as stack:
            for item in self.common_prepare_patches():
                stack.enter_context(item)
            stack.enter_context(patch("updates.os.fsync", side_effect=OSError("storage failure")))
            with contextlib.redirect_stdout(io.StringIO()), \
                 self.assertRaisesRegex(OSError, "storage failure"):
                updates.prepare("app", self.filename)
        self.assertEqual(updates._prepared_row("app", "amd64"), existing)
        self.assertEqual(Path(existing[15]).read_bytes(), self.asset_bytes)
        directory = updates._updates_directory()
        self.assertEqual(list(directory.glob(".partial-*")), [])
        self.assertEqual(list(directory.glob("*.deb")), [Path(existing[15])])

    def test_prepare_blocks_downgrade_and_existing_apt_ownership(self):
        patches = self.common_prepare_patches(relation="older")
        with contextlib.ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            with self.assertRaisesRegex(tracking.TrackingError, "downgrades are blocked"):
                updates.prepare("app", self.filename)

        with patch("tracking.installed_package", return_value=("app", "amd64", "1.0")), \
             patch("tracking.resolve_repository", return_value=("owner/repo", 123)), \
             patch("apt_handoff.assert_not_managed_by_apt",
                   side_effect=tracking.TrackingError("APT has a repository candidate")):
            with self.assertRaisesRegex(tracking.TrackingError, "repository candidate"):
                updates.prepare("app", self.filename)

    def test_prepare_rejects_architecture_all_for_an_architecture_specific_install(self):
        patches = self.common_prepare_patches()
        with contextlib.ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            stack.enter_context(
                patch("inspection.inspect_fields", return_value=["app", "all", "2.0"]),
            )
            with self.assertRaisesRegex(tracking.TrackingError, "architecture mismatch"):
                updates.prepare("app", self.filename)
        self.assertIsNone(updates._prepared_row("app", "amd64"))
        self.assertEqual(list(updates._updates_directory().glob(".partial-*")), [])

    def test_upstream_fd_asset_cannot_replace_distro_fd_find(self):
        existing = self.prepare_fixture()
        with contextlib.closing(tracking.open_database()) as db, db:
            db.execute(
                "INSERT INTO tracked_packages VALUES (?, ?, ?, ?)",
                ("fd-find", "amd64", 90793418, "sharkdp/fd"),
            )
        patches = self.common_prepare_patches()
        with contextlib.ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            stack.enter_context(patch(
                "tracking.installed_package", return_value=("fd-find", "amd64", "10.3.0-2ubuntu1"),
            ))
            stack.enter_context(patch(
                "tracking.resolve_repository", return_value=("sharkdp/fd", 90793418),
            ))
            stack.enter_context(patch("inspection.selected_assets", return_value=(
                "v10.5.2",
                "https://github.com/sharkdp/fd/releases/download/v10.5.2/fd_10.5.2_amd64.deb",
                None,
            )))
            stack.enter_context(patch(
                "inspection.inspect_fields", return_value=["fd", "amd64", "10.5.2"],
            ))
            with contextlib.redirect_stdout(io.StringIO()), \
                 self.assertRaisesRegex(tracking.TrackingError, "Package name mismatch"):
                updates.prepare("fd-find", "fd_10.5.2_amd64.deb")

        self.assertIsNone(updates._prepared_row("fd-find", "amd64"))
        self.assertEqual(updates._prepared_row("app", "amd64"), existing)
        self.assertEqual(Path(existing[15]).read_bytes(), self.asset_bytes)
        self.assertEqual(list(updates._updates_directory().glob(".partial-*")), [])
        with contextlib.closing(tracking.open_database()) as db:
            self.assertEqual(db.execute(
                "SELECT repository_name, repository_id FROM tracked_packages WHERE package_name=?",
                ("fd-find",),
            ).fetchone(), ("sharkdp/fd", 90793418))

    def test_apt_managed_bat_is_blocked_before_release_selection_or_download(self):
        with contextlib.closing(tracking.open_database()) as db, db:
            db.execute(
                "INSERT INTO tracked_packages VALUES (?, ?, ?, ?)",
                ("bat", "amd64", 130464961, "sharkdp/bat"),
            )
        policy = (
            "bat:\n"
            "  Installed: 0.25.0-5ubuntu1\n"
            "  Candidate: 0.25.0-5ubuntu1\n"
            "  Version table:\n"
            " *** 0.25.0-5ubuntu1 500\n"
            "        500 http://us.archive.ubuntu.com/ubuntu resolute/universe amd64 Packages\n"
            "        100 /var/lib/dpkg/status\n"
        )
        with patch("tracking.installed_package", return_value=("bat", "amd64", "0.25.0-5ubuntu1")), \
             patch("tracking.resolve_repository", return_value=("sharkdp/bat", 130464961)), \
             patch("apt_handoff._run",
                   return_value=SimpleNamespace(stdout=policy, stderr="", returncode=0)), \
             patch("inspection.selected_assets") as select, \
             patch("inspection.download") as download:
            with self.assertRaisesRegex(tracking.TrackingError, "use the configured APT source"):
                updates.prepare("bat", "bat_0.26.1_amd64.deb")
            select.assert_not_called()
            download.assert_not_called()
        self.assertIsNone(updates._prepared_row("bat", "amd64"))
        self.assertEqual(list(updates._updates_directory().glob("*.deb")), [])

    def _install_patches(self, plan=None, answer="yes", final_version="2.0"):
        if plan is None:
            plan = [{
                "package": "app",
                "architecture": "amd64",
                "old_architecture": "amd64",
                "old_version": "1.0",
                "new_version": "2.0",
                "action": "install",
            }]
        patches = [
            patch("tracking.installed_package", side_effect=[
                ("app", "amd64", "1.0"),
                ("app", "amd64", final_version),
            ]),
            patch("tracking.resolve_repository", return_value=("owner/repo", 123)),
            patch("apt_handoff.assert_not_managed_by_apt", return_value={}),
            patch("inspection.selected_release_assets", return_value=(
                "v2.0", self.asset_url, self.checksum_url,
            )),
            patch("updates._download_checksum", return_value=self.digest),
            patch("apt_handoff._hash_file", return_value=self.digest),
            patch("inspection.inspect_fields", return_value=["app", "amd64", "2.0"]),
            patch("inspection.version_relation", return_value="newer"),
            patch("apt_handoff.simulate_install", return_value=(plan, "preview")),
            patch("builtins.input", return_value=answer),
            patch("updates._sudo_install"),
        ]
        return patches

    def test_install_requires_fresh_approval_and_confirms_installed_state(self):
        self.prepare_fixture()
        patches = self._install_patches()
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            mocks = []
            for item in patches:
                mocks.append(stack.enter_context(item))
            with contextlib.redirect_stdout(output):
                updates.install("app")
            mocks[-1].assert_called_once()
            self.assertEqual(
                mocks[-2].call_args.args[0],
                "Install this exact APT transaction? [y/N] ",
            )
        self.assertIn("Installation confirmed: app:amd64 2.0.", output.getvalue())

    def test_declined_install_does_not_escalate(self):
        self.prepare_fixture()
        patches = self._install_patches(answer="no")
        with contextlib.ExitStack() as stack:
            mocks = []
            for item in patches:
                mocks.append(stack.enter_context(item))
            with contextlib.redirect_stdout(io.StringIO()):
                updates.install("app")
            mocks[-1].assert_not_called()

    def test_changed_release_evidence_blocks_install_before_approval(self):
        existing = self.prepare_fixture()
        cases = [
            ("inspection.selected_release_assets",
             ("v2.0", self.asset_url + ".changed", self.checksum_url),
             "asset identity changed"),
            ("inspection.selected_release_assets",
             ("v2.0", self.asset_url, None),
             "asset identity changed"),
            ("updates._download_checksum", "0" * 64, "checksum changed"),
            ("updates._download_checksum", None, "checksum changed"),
        ]
        for target, value, message in cases:
            with self.subTest(target=target, value=value), contextlib.ExitStack() as stack:
                for item in self._install_patches():
                    stack.enter_context(item)
                stack.enter_context(patch(target, return_value=value))
                preview = stack.enter_context(patch("apt_handoff.simulate_install"))
                approve = stack.enter_context(patch("builtins.input"))
                privileged = stack.enter_context(patch("updates._sudo_install"))
                with self.assertRaisesRegex(tracking.TrackingError, message):
                    updates.install("app")
                preview.assert_not_called()
                approve.assert_not_called()
                privileged.assert_not_called()
                self.assertEqual(updates._prepared_row("app", "amd64"), existing)
                self.assertEqual(Path(existing[15]).read_bytes(), self.asset_bytes)

    def test_tampered_prepared_artifact_blocks_install_before_approval(self):
        existing = self.prepare_fixture()
        Path(existing[15]).write_bytes(b"changed after preparation")
        real_hash_file = apt_handoff._hash_file
        with contextlib.ExitStack() as stack:
            for item in self._install_patches():
                stack.enter_context(item)
            stack.enter_context(patch("apt_handoff._hash_file", wraps=real_hash_file))
            preview = stack.enter_context(patch("apt_handoff.simulate_install"))
            approve = stack.enter_context(patch("builtins.input"))
            privileged = stack.enter_context(patch("updates._sudo_install"))
            with self.assertRaisesRegex(tracking.TrackingError, "digest changed"):
                updates.install("app")
            preview.assert_not_called()
            approve.assert_not_called()
            privileged.assert_not_called()
        self.assertEqual(updates._prepared_row("app", "amd64"), existing)
        self.assertEqual(Path(existing[15]).read_bytes(), b"changed after preparation")

    def test_install_blocks_removals_before_confirmation(self):
        self.prepare_fixture()
        plan = [{
            "package": "app",
            "architecture": "amd64",
            "old_architecture": "amd64",
            "old_version": "1.0",
            "new_version": "2.0",
            "action": "install",
        }, {
            "package": "unrelated",
            "architecture": "amd64",
            "old_architecture": "amd64",
            "old_version": "1.0",
            "new_version": "-",
            "action": "remove",
        }]
        patches = self._install_patches(plan=plan)
        with contextlib.ExitStack() as stack:
            mocks = []
            for item in patches:
                mocks.append(stack.enter_context(item))
            with patch("builtins.input", side_effect=AssertionError("must not prompt")), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(tracking.TrackingError, "proposed removing"):
                    updates.install("app")
            mocks[-1].assert_not_called()

    def test_cli_wires_prepare_and_install(self):
        with patch.object(sys, "argv", ["beacon", "--prepare", "app", self.filename]), \
             patch("updates.prepare") as prepare:
            beacon.main()
        prepare.assert_called_once_with("app", self.filename)
        with patch.object(sys, "argv", ["beacon", "--install", "app"]), \
             patch("updates.install") as install:
            beacon.main()
        install.assert_called_once_with("app")


if __name__ == "__main__":
    unittest.main()
