import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tarfile
import threading
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from synapse_app import updates
from synapse_app import pi_setup


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

    def test_pi_configuration_preserves_settings_and_tracks_explicit_context_refresh(self):
        directory = self.root / "pi"
        directory.mkdir()
        settings_path = directory / "settings.json"
        settings_path.write_text(json.dumps({"defaultProvider": "existing", "terminal": {"showTerminalProgress": True}}))
        auth = directory / "auth.json"
        auth.write_text("private credentials stay untouched")
        pi_setup.configure_pi(directory, context=64512)
        models = json.loads((directory / "models.json").read_text())
        model = models["providers"]["synapse"]["models"][0]
        self.assertEqual(model["contextWindow"], 64512)
        self.assertEqual(model["maxTokens"], 4096)
        settings = json.loads(settings_path.read_text())
        self.assertEqual(settings["defaultProvider"], "existing")
        self.assertTrue(settings["terminal"]["showTerminalProgress"])
        pi_setup.configure_pi(directory, context=4096)
        self.assertEqual(json.loads((directory / "models.json").read_text())["providers"]["synapse"]["models"][0]["contextWindow"], 64512)
        pi_setup.configure_pi(directory, context=4096, refresh=True)
        model = json.loads((directory / "models.json").read_text())["providers"]["synapse"]["models"][0]
        self.assertEqual((model["contextWindow"], model["maxTokens"]), (4096, 512))
        self.assertEqual(auth.read_text(), "private credentials stay untouched")
        pi_setup.configure_pi(directory, context=4096, port=8081, refresh=True)
        self.assertEqual(json.loads((directory / "models.json").read_text())["providers"]["synapse"]["baseUrl"],
                         "http://127.0.0.1:8081/v1")
        before = (directory / "models.json").read_bytes()
        settings_path.write_text('{"compaction": []}')
        with self.assertRaisesRegex(ValueError, "compaction"):
            pi_setup.configure_pi(directory, port=8081)
        self.assertEqual((directory / "models.json").read_bytes(), before)

    def test_pi_context_refresh_command_uses_ready_server_without_running_inference(self):
        requested = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requested.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"app_name": "SYNAPSE", "state": "ready", "context": 64512}).encode())

            def log_message(self, *arguments):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        directory = self.root / "refreshed-pi"
        try:
            result = subprocess.run([sys.executable, "-m", "synapse_app", "--configure-pi", "--port", str(server.server_port)],
                                    cwd=ROOT, env={**os.environ, "PI_CODING_AGENT_DIR": str(directory)},
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("64512-token", result.stdout)
            model = json.loads((directory / "models.json").read_text())["providers"]["synapse"]["models"][0]
            self.assertEqual(model["contextWindow"], 64512)
            self.assertEqual(requested, ["/api/v1/status"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_pi_standalone_assets_cover_all_platforms_and_extract_only_verified_files(self):
        for system in ("win32", "linux", "darwin"):
            for architecture in ("AMD64", "ARM64"):
                with mock.patch.object(sys, "platform", system), \
                        mock.patch.dict(os.environ, {"PROCESSOR_ARCHITEW6432": architecture}):
                    self.assertIn(pi_setup.release_asset(), pi_setup.PI_HASHES)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("pi/pi.exe", b"fixture")
            archive.writestr("pi/resources/help.txt", b"resource")
        body = output.getvalue()
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.dict(os.environ, {"PROCESSOR_ARCHITEW6432": "AMD64"}), \
                mock.patch.dict(pi_setup.PI_HASHES, {"pi-windows-x64.zip": hashlib.sha256(body).hexdigest()}), \
                mock.patch.object(pi_setup, "download", return_value=body), \
                mock.patch.object(pi_setup.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="1.5.2\n", stderr="")):
            executable = Path(pi_setup.install_pi(self.root))
            self.assertEqual(executable.read_bytes(), b"fixture")
            self.assertTrue((executable.parent / "resources/help.txt").is_file())
        before = set(self.root.iterdir())
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.dict(os.environ, {"PROCESSOR_ARCHITEW6432": "AMD64"}), \
                mock.patch.object(pi_setup, "download", return_value=b"wrong"):
            with self.assertRaisesRegex(ValueError, "checksum"):
                pi_setup.install_pi(self.root)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_pi_unix_archive_extraction_and_link_rejection(self):
        def archive_body(link=False):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w:gz") as archive:
                entry = tarfile.TarInfo("pi/pi")
                entry.mode = 0o755
                entry.size = 7
                archive.addfile(entry, io.BytesIO(b"fixture"))
                if link:
                    entry = tarfile.TarInfo("pi/link")
                    entry.type = tarfile.SYMTYPE
                    entry.linkname = "../../outside"
                    archive.addfile(entry)
            return output.getvalue()
        for link in (False, True):
            body = archive_body(link)
            with mock.patch.object(sys, "platform", "linux"), \
                    mock.patch.dict(os.environ, {"PROCESSOR_ARCHITEW6432": "AMD64"}), \
                    mock.patch.dict(pi_setup.PI_HASHES, {"pi-linux-x64.tar.gz": hashlib.sha256(body).hexdigest()}), \
                    mock.patch.object(pi_setup, "download", return_value=body), \
                    mock.patch.object(pi_setup.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="1.5.2\n", stderr="")):
                before = set(self.root.iterdir())
                if link:
                    with self.assertRaisesRegex(ValueError, "Unsafe"):
                        pi_setup.install_pi(self.root)
                    self.assertEqual(set(self.root.iterdir()), before)
                else:
                    self.assertEqual(Path(pi_setup.install_pi(self.root)).read_bytes(), b"fixture")

    def test_optional_pi_offer_declines_by_default_and_reuses_existing_install(self):
        spec = importlib.util.spec_from_file_location("synapse_installer_test", ROOT / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(sys.stdin, "isatty", return_value=True), \
                mock.patch.object(sys.stdout, "isatty", return_value=True), \
                mock.patch("builtins.input", return_value=""):
            self.assertFalse(installer.confirm_pi())
        launcher_dir = self.root / "bin"
        launcher_dir.mkdir()
        executable = self.root / "pi.cmd"
        executable.write_text("@echo fixture")
        with mock.patch.dict(os.environ, {"PI_CODING_AGENT_DIR": str(self.root / "pi-config")}), \
                mock.patch.object(pi_setup, "existing_pi", return_value=str(executable)), \
                mock.patch.object(pi_setup, "install_pi") as install, \
                mock.patch.object(pi_setup, "loaded_context", return_value=64512):
            installer.setup_pi(self.root, launcher_dir, dict(self.receipt))
            install.assert_not_called()
            launcher = launcher_dir / ("synapse-pi.cmd" if sys.platform == "win32" else "synapse-pi")
            self.assertIn("SYNAPSE managed Pi launcher", launcher.read_text())
            self.assertEqual(json.loads((self.root / "install.json").read_text())["pi_executable"], str(executable))
            models = json.loads((self.root / "pi-config/models.json").read_text())
            self.assertEqual(models["providers"]["synapse"]["models"][0]["contextWindow"], 64512)

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

    @unittest.skipUnless(sys.platform == "win32", "Windows shortcuts require WScript.Shell")
    def test_windows_shortcuts_launch_archive_and_preserve_unrelated_shortcuts(self):
        spec = importlib.util.spec_from_file_location("synapse_installer_test", ROOT / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        folders = [self.root / "Desktop with spaces", self.root / "Programs"]
        command = [sys.executable, str(self.archive), "--llama-server", str(self.root / "backend/llama-server.exe")]
        installer.windows_integration(self.root / "bin", command, add_path=False, shortcut_dirs=folders)
        shortcut = folders[0] / "SYNAPSE.lnk"
        environment = {**os.environ, "SYNAPSE_TEST_SHORTCUT": str(shortcut)}
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                                 "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SYNAPSE_TEST_SHORTCUT); "
                                 "@{target=$s.TargetPath; arguments=$s.Arguments; description=$s.Description; icon=$s.IconLocation} | ConvertTo-Json"],
                                env=environment, check=True, capture_output=True, text=True)
        details = json.loads(result.stdout)
        self.assertEqual(Path(details["target"]), Path(sys.executable))
        self.assertEqual(details["arguments"], subprocess.list2cmdline(command[1:]))
        self.assertEqual(details["description"], "SYNAPSE managed launcher")
        icon = self.root / "SYNAPSE.ico"
        self.assertEqual(details["icon"], str(icon) + ",0")
        self.assertEqual(icon.read_bytes(), (ROOT / "synapse_app/web/icon.ico").read_bytes())
        self.assertTrue((folders[1] / "SYNAPSE.lnk").is_file())
        installer.windows_integration(self.root / "bin", command, add_path=False, shortcut_dirs=folders)
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SYNAPSE_TEST_SHORTCUT); "
                        "$s.Description = 'another app'; $s.Save()"], env=environment, check=True)
        before = shortcut.read_bytes()
        with self.assertRaises(subprocess.CalledProcessError):
            installer.windows_integration(self.root / "bin", command, add_path=False, shortcut_dirs=folders)
        self.assertEqual(shortcut.read_bytes(), before)

    @unittest.skipUnless(sys.platform == "win32", "Windows PATH handling requires PowerShell")
    def test_windows_user_path_preserves_variables_and_does_not_duplicate_entries(self):
        spec = importlib.util.spec_from_file_location("synapse_installer_test", ROOT / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        launcher = self.root / "bin"
        command = installer.WINDOWS_PATH_VALUE + "\nGet-SynapseUserPath $env:SYNAPSE_TEST_PATH $env:SYNAPSE_TEST_BIN"
        for previous, expected in [
                ("", str(launcher)),
                (r"%LOCALAPPDATA%\existing;C:\tools", rf"%LOCALAPPDATA%\existing;C:\tools;{launcher}"),
                (str(launcher).upper() + "\\;C:\\tools", str(launcher).upper() + "\\;C:\\tools"),
                (r"%SYNAPSE_TEST_ROOT%\bin", r"%SYNAPSE_TEST_ROOT%\bin")]:
            environment = {**os.environ, "SYNAPSE_TEST_PATH": previous,
                           "SYNAPSE_TEST_BIN": str(launcher), "SYNAPSE_TEST_ROOT": str(self.root)}
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                                    env=environment, check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), expected)

    def test_windows_installer_finds_adjacent_backend_and_prompts_for_missing_backend(self):
        spec = importlib.util.spec_from_file_location("synapse_installer_test", ROOT / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        backend = self.root / "llama-server.exe"
        backend.touch()
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(installer.shutil, "which", return_value=None), \
                mock.patch("builtins.input") as prompt:
            self.assertEqual(installer.select_backend("llama-server", self.archive), str(backend))
            prompt.assert_not_called()
        folder = self.root / "backend with spaces"
        folder.mkdir()
        selected = folder / "llama-server.exe"
        selected.touch()
        backend.unlink()
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(installer.shutil, "which", return_value=None), \
                mock.patch.object(sys.stdin, "isatty", return_value=True), \
            mock.patch.object(sys.stdout, "isatty", return_value=True), \
                mock.patch("builtins.input", side_effect=["n", "ollama.exe", f'"{folder}"']) as prompt:
            self.assertEqual(installer.select_backend("llama-server", self.archive), str(selected))
            self.assertEqual(prompt.call_count, 3)
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(installer.shutil, "which", return_value=None), \
                mock.patch("builtins.input") as prompt:
            self.assertEqual(installer.select_backend("missing", self.archive, interactive=False), "missing")
            prompt.assert_not_called()

    def test_windows_backend_auto_setup_requires_consent_and_returns_verified_path(self):
        spec = importlib.util.spec_from_file_location("synapse_installer_test", ROOT / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(installer.shutil, "which", return_value=None), \
                mock.patch.object(sys.stdin, "isatty", return_value=True), \
                mock.patch.object(sys.stdout, "isatty", return_value=True), \
                mock.patch.object(installer, "install_windows_backend", return_value="verified/llama-server.exe") as setup:
            for answers in (["n", ""], ["", ""]):
                with mock.patch("builtins.input", side_effect=answers):
                    self.assertEqual(installer.select_backend("missing", self.archive), "missing")
                setup.assert_not_called()
            with mock.patch("builtins.input", side_effect=["yes", "invalid", "2"]):
                self.assertEqual(installer.select_backend("missing", self.archive), "verified/llama-server.exe")
            setup.assert_called_once_with(self.root, "vulkan")
            setup.reset_mock()
            with mock.patch("builtins.input", side_effect=["y", ""]):
                installer.select_backend("missing", self.archive)
            setup.assert_called_once_with(self.root, "cpu")
            setup.side_effect = OSError("network denied")
            with mock.patch("builtins.input", side_effect=["y", "1", ""]):
                self.assertEqual(installer.select_backend("missing", self.archive), "missing")

    def test_windows_backend_download_verification_extraction_and_cleanup(self):
        spec = importlib.util.spec_from_file_location("synapse_installer_test", ROOT / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        def backend_zip(extra=None):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("bin/llama-server.exe", b"test executable")
                archive.writestr("bin/ggml.dll", b"matching library")
                if extra:
                    archive.writestr(extra, b"unsafe")
            return output.getvalue()
        body = backend_zip()
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.dict(os.environ, {"PROCESSOR_ARCHITEW6432": "AMD64"}), \
                mock.patch.object(installer, "download", return_value=body) as fetch, \
                mock.patch.dict(installer.WINDOWS_BACKEND_HASHES, {("cpu", "x64"): hashlib.sha256(body).hexdigest()}), \
                mock.patch.object(installer.subprocess, "run", side_effect=[
                    mock.Mock(returncode=0, stdout="", stderr=(
                        "version: 0.7.0-dev (build 11669, commit 620d2225c)\n"
                        "built with Clang 20.1.8 for Windows x86_64\n")),
                    mock.Mock(returncode=0, stdout="--model --host --port", stderr="")]) as run:
            executable = Path(installer.install_windows_backend(self.root, "cpu"))
            self.assertEqual(executable.read_bytes(), b"test executable")
            self.assertEqual((executable.parent / "ggml.dll").read_bytes(), b"matching library")
            self.assertEqual(run.call_args_list[0].args[0], [str(executable), "--version"])
            self.assertIn("/b11669/llama-b11669-bin-win-cpu-x64.zip", fetch.call_args.args[0])
        prefix = self.root / "installed"
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(sys, "argv", ["install.py", "--local-package", str(self.archive),
                                               "--prefix", str(prefix), "--no-accelerated", "--no-pi"]), \
                mock.patch.object(sys.stdin, "isatty", return_value=True), \
                mock.patch.object(sys.stdout, "isatty", return_value=True), \
                mock.patch.object(installer.shutil, "which", return_value=None), \
                mock.patch.object(installer, "install_windows_backend", return_value=str(executable)) as setup, \
                mock.patch("builtins.input", side_effect=["y", "1"]):
            installer.main()
        setup.assert_called_once_with(prefix, "cpu")
        receipt = json.loads((prefix / "install.json").read_text())
        self.assertEqual(receipt["backend_args"], ["--llama-server", str(executable)])
        self.assertIn(installer.windows_command([str(executable)]), (prefix / "bin/synapse.cmd").read_text())
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(installer.shutil, "which", return_value=str(executable)), \
                mock.patch.object(installer, "install_windows_backend") as setup, \
                mock.patch("builtins.input") as prompt:
            self.assertEqual(installer.select_backend(str(executable), self.archive), str(executable))
            prompt.assert_not_called()
            setup.assert_not_called()
        for content, checksum, message, output, returncode in [
            (body, "0" * 64, "checksum", "", 1),
            (backend_zip("../outside.txt"), None, "Unsafe", "", 1),
            (backend_zip("bin/LLAMA-SERVER.exe"), None, "duplicate", "", 1),
            (body, None, "startup checks", "", 1),
            (body, None, "startup checks", "version: 0.7.0-dev (build 11668, commit 620d2225c)", 0),
            (body, None, "startup checks", "version: 116690 (620d222)", 0)]:
            with self.subTest(message=message), \
                    mock.patch.object(sys, "platform", "win32"), \
                    mock.patch.dict(os.environ, {"PROCESSOR_ARCHITEW6432": "AMD64"}), \
                    mock.patch.object(installer, "download", return_value=content), \
                    mock.patch.dict(installer.WINDOWS_BACKEND_HASHES, {
                        ("cpu", "x64"): checksum or hashlib.sha256(content).hexdigest()}), \
                    mock.patch.object(installer.subprocess, "run", return_value=mock.Mock(
                        returncode=returncode, stdout=output, stderr="missing DLL" if returncode else "")):
                before = set(self.root.iterdir())
                with self.assertRaisesRegex(ValueError, message):
                    installer.install_windows_backend(self.root, "cpu")
                self.assertEqual(set(self.root.iterdir()), before)

    @unittest.skipUnless(sys.platform == "win32", "PowerShell bootstrap is Windows-only")
    def test_standalone_powershell_bootstrap_downloads_source_and_forwards_arguments(self):
        source = io.BytesIO()
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("synapse-source/install.py", "import json, sys; print(json.dumps(sys.argv[1:]))")
        body = source.getvalue()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *arguments):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            script = self.root / "install.ps1"
            script.write_text((ROOT / "install.ps1").read_text().replace(
                "https://api.github.com/repos/appatalks/synapse/zipball/main",
                f"http://127.0.0.1:{server.server_port}/source.zip"))
            result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                     str(script), "-Prefix", str(self.root / "custom prefix"),
                                     "-LlamaServer", str(self.root / "backend with spaces/llama-server.exe"),
                                     "-NoPath", "-NoShortcuts", "-NonInteractive", "-WithPi"],
                                    check=True, capture_output=True, text=True, timeout=20)
            arguments = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(arguments, ["--no-accelerated", "--prefix", str(self.root / "custom prefix"),
                                         "--llama-server", str(self.root / "backend with spaces/llama-server.exe"),
                                         "--no-shortcuts", "--no-path", "--non-interactive", "--with-pi"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

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
                   "--prefix", str(prefix), "--no-accelerated", "--no-pi"]
        if sys.platform == "win32":
            command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                       str(ROOT / "install.ps1"), "-LocalPackage", str(package), "-Prefix", str(prefix),
                       "-NonInteractive"]
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
