import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from synapse_app import updates


def application(version):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("__main__.py", "")
        archive.writestr("synapse_app/app.py", "")
        archive.writestr("synapse_app/__init__.py", f'__version__ = "{version}"')
    return output.getvalue()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.archive = self.root / "SYNAPSE.pyz"
        self.archive.write_bytes(application("0.1.0rc1"))
        self.receipt = {"schema_version": 1, "app": "SYNAPSE", "mode": "managed", "channel": "release"}
        (self.root / "install.json").write_text(json.dumps(self.receipt))
        self.release = {"tag": "v0.2.0rc1", "version": "0.2.0rc1",
                        "url": "https://github.com/appatalks/synapse/releases/tag/v0.2.0rc1"}

    def tearDown(self):
        self.temp.cleanup()

    def test_version_order_and_invalid_tags(self):
        versions = ["0.1.0a1", "0.1.0b1", "0.1.0rc1", "0.1.0rc2", "0.1.0", "0.2.0rc1", "1.0.0"]
        self.assertEqual(sorted(versions, key=updates.version_key), versions)
        for value in ("../other", "v1", "1.2.3+shell", "1.2.3/other"):
            self.assertIsNone(updates.version_key(value))

    def test_windows_batch_launcher_quotes_paths_and_escapes_expansion(self):
        spec = importlib.util.spec_from_file_location("synapse_installer_test", ROOT / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        command = installer.windows_command([r"C:\a&b\python.exe", r"C:\模型\100% ready!\SYNAPSE.pyz"])
        self.assertEqual(command, '"C:\\a&b\\python.exe" "C:\\模型\\100%% ready!\\SYNAPSE.pyz"')
        for bad in ('bad"quote', "bad\ncommand"):
            with self.assertRaises(ValueError):
                installer.windows_command([bad])

    def test_release_selection_uses_only_versioned_public_releases_with_assets(self):
        assets = [{"name": "SYNAPSE.pyz"}, {"name": "SHA256SUMS"}]
        data = [{"tag_name": "v0.1.0rc1", "assets": assets},
                {"tag_name": "v0.2.0rc1", "assets": assets},
                {"tag_name": "v9.0.0", "assets": assets, "draft": True},
                {"tag_name": "v8.0.0", "assets": []}, {"tag_name": "../bad", "assets": assets}]
        with mock.patch.object(updates, "download", return_value=json.dumps(data).encode()):
            self.assertEqual(updates.latest_release()["version"], "0.2.0rc1")

    def test_no_release_is_not_an_update_or_silent_network_success(self):
        with mock.patch.object(updates, "latest_release", return_value=None):
            manager = updates.UpdateManager("0.1.0rc1", None)
            manager._check()
        self.assertEqual(manager.snapshot()["state"], "no_release")
        with mock.patch.object(updates, "latest_release", side_effect=OSError("network denied")):
            manager._check()
        self.assertEqual(manager.snapshot()["state"], "error")
        self.assertIn("network denied", manager.snapshot()["error"])

    def test_source_installs_are_not_modified_and_downgrades_are_not_offered(self):
        manager = updates.UpdateManager("1.0.0", None)
        with mock.patch.object(updates, "latest_release", return_value=self.release):
            manager._check()
        self.assertEqual(manager.snapshot()["state"], "current")
        manager.release, manager.state = self.release, "available"
        with self.assertRaisesRegex(ValueError, "Source and pip"):
            manager.apply("0.2.0rc1", mock.Mock())

    def test_checksums_and_archive_version_are_required(self):
        body = application("0.2.0rc1")
        digest = hashlib.sha256(body).hexdigest()
        with mock.patch.object(updates, "download", side_effect=[f"{digest}  SYNAPSE.pyz\n".encode(), body]):
            staged = updates.release_archive(self.release, self.root)
        self.assertEqual(updates.validate_archive(staged), "0.2.0rc1")
        staged.unlink()
        for checksum, content, expected in [
            ("0" * 64, body, "checksum"),
            (hashlib.sha256(application("1.0.0")).hexdigest(), application("1.0.0"), "version")]:
            with mock.patch.object(updates, "download", side_effect=[f"{checksum}  SYNAPSE.pyz\n".encode(), content]):
                with self.assertRaisesRegex(ValueError, expected):
                    updates.release_archive(self.release, self.root)
        self.assertFalse(list(self.root.glob(".synapse-update-*")))
        bad = self.root / "bad.pyz"
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("__main__.py", "")
            archive.writestr("synapse_app/app.py", "")
            archive.writestr("synapse_app/__init__.py", "__version__ = !")
        with self.assertRaisesRegex(ValueError, "Invalid application archive"):
            updates.validate_archive(bad)

    def test_atomic_update_retains_old_archive_and_receipt(self):
        old = self.archive.read_bytes()
        staged = self.root / "staged.pyz"
        staged.write_bytes(application("0.2.0rc1"))
        updates.install_archive(staged, self.archive, {**self.receipt, "version": "0.2.0rc1"})
        self.assertEqual(updates.validate_archive(self.archive), "0.2.0rc1")
        self.assertEqual(self.archive.with_suffix(".pyz.previous").read_bytes(), old)
        self.assertEqual(json.loads((self.root / "install.json").read_text())["version"], "0.2.0rc1")

    def test_update_rolls_back_when_receipt_replacement_fails(self):
        staged = self.root / "staged.pyz"
        staged.write_bytes(application("0.2.0rc1"))
        original = os.replace
        def replace(source, target):
            if Path(target).name == "install.json":
                raise PermissionError("receipt denied")
            return original(source, target)
        with mock.patch.object(updates.os, "replace", side_effect=replace):
            with self.assertRaisesRegex(PermissionError, "receipt denied"):
                updates.install_archive(staged, self.archive, self.receipt)
        self.assertEqual(updates.validate_archive(self.archive), "0.1.0rc1")
        self.assertFalse((self.root / ".install.json.part").exists())

    def test_worker_verifies_then_calls_explicit_restart(self):
        manager = updates.UpdateManager("0.1.0rc1", self.archive)
        manager.state, manager.release = "available", self.release
        finished = threading.Event()
        staged = self.root / "staged.pyz"
        staged.write_bytes(application("0.2.0rc1"))
        seen = {}
        def restart(path, receipt):
            seen.update(path=str(path), receipt=receipt)
            finished.set()
        with mock.patch.object(updates, "release_archive", return_value=staged):
            manager.apply("0.2.0rc1", restart)
            self.assertTrue(finished.wait(5))
        self.assertEqual(seen["receipt"]["version"], "0.2.0rc1")
        self.assertEqual(seen["receipt"]["channel"], "release")

    def test_preview_can_migrate_to_a_matching_public_release(self):
        (self.root / "install.json").write_text(json.dumps({**self.receipt, "channel": "preview"}))
        manager = updates.UpdateManager("0.2.0rc1", self.archive)
        with mock.patch.object(updates, "latest_release", return_value=self.release):
            manager._check()
        self.assertEqual(manager.snapshot()["state"], "available")
        with self.assertRaisesRegex(ValueError, "selected release changed"):
            manager.apply("9.0.0", mock.Mock())

    def test_acceleration_artifacts_are_pinned_and_prerequisites_are_not_installed(self):
        spec = importlib.util.spec_from_file_location("synapse_setup_test", ROOT / "scripts/setup_acceleration.py")
        setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup)
        with mock.patch.object(setup, "download", return_value=b"wrong artifact"):
            with self.assertRaisesRegex(ValueError, "checksum"):
                setup.checked_file("https://example.invalid", self.root / "patch", "0" * 64)
        self.assertFalse((self.root / "patch").exists())
        with mock.patch.object(sys, "argv", ["setup", "--prefix", str(self.root / "backend")]), \
                mock.patch.object(sys, "platform", "linux"), \
                mock.patch.object(setup.shutil, "which", return_value=None), \
                mock.patch.object(setup.subprocess, "run") as run:
            with self.assertRaises(SystemExit):
                setup.main()
            run.assert_not_called()
        self.assertFalse((self.root / "backend").exists())

    def test_first_check_is_not_suppressed_early_after_boot_and_can_be_disabled(self):
        manager = updates.UpdateManager("0.1.0rc1", None)
        with mock.patch.object(updates.time, "monotonic", return_value=100), \
                mock.patch.object(updates.threading, "Thread") as thread:
            manager.check()
            thread.assert_called_once()
        disabled = updates.UpdateManager("0.1.0rc1", None, automatic=False)
        with mock.patch.object(updates.threading, "Thread") as thread:
            disabled.check()
            thread.assert_not_called()
            disabled.check(force=True)
            thread.assert_called_once()

    def test_receipt_and_symlink_guards(self):
        self.assertTrue(updates.managed_receipt(self.archive)[0])
        (self.root / "install.json").write_text('{"app":"unrelated"}')
        self.assertIsNone(updates.managed_receipt(self.archive)[0])
        if sys.platform != "win32":
            (self.root / "install.json").unlink()
            (self.root / "install.json").symlink_to(self.archive)
            self.assertIsNone(updates.managed_receipt(self.archive)[0])

    def test_offline_installer_creates_working_launcher_and_leaves_unrelated_files_alone(self):
        package = self.root / "package.pyz"
        # Use the real zipapp builder rather than counting a placeholder ZIP as a working install.
        subprocess.run([sys.executable, str(ROOT / "scripts/build_synapse.py"), "--output", str(self.root / "dist")],
                       check=True, capture_output=True, timeout=20)
        package = self.root / "dist/SYNAPSE.pyz"
        prefix = self.root / "installed"
        command = [sys.executable, str(ROOT / "install.py"), "--local-package", str(package),
                   "--prefix", str(prefix), "--no-accelerated"]
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
        self.assertIn("installed", result.stdout)
        self.assertTrue(updates.managed_receipt(prefix / "SYNAPSE.pyz")[0])
        subprocess.run([sys.executable, str(prefix / "SYNAPSE.pyz"), "--version"], check=True,
                       capture_output=True, timeout=10)
        launcher = prefix / "bin" / ("synapse.cmd" if sys.platform == "win32" else "synapse")
        self.assertIn("SYNAPSE managed launcher", launcher.read_text())
        if sys.platform != "win32":
            result = subprocess.run([str(launcher), "--version"], check=True, capture_output=True, text=True, timeout=10)
            self.assertIn("SYNAPSE", result.stdout)
        else:
            result = subprocess.run(["cmd.exe", "/d", "/c", str(launcher), "--version"],
                                    check=True, capture_output=True, text=True, timeout=10)
            self.assertIn("SYNAPSE", result.stdout)
        subprocess.run(command, check=True, capture_output=True, timeout=20)
        foreign = self.root / "foreign"
        foreign.mkdir()
        (foreign / "important.txt").write_text("preserve")
        result = subprocess.run([sys.executable, str(ROOT / "install.py"), "--local-package", str(package),
                                 "--prefix", str(foreign), "--no-accelerated"],
                                capture_output=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"unrelated files", result.stderr)
        self.assertEqual((foreign / "important.txt").read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
