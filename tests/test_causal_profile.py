import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from synapse_app import causal_profile

script = Path(__file__).resolve().parents[1] / "scripts/setup_causal_provider.py"
spec = importlib.util.spec_from_file_location("setup_causal_provider", script)
setup_provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup_provider)


class CausalProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.model = self.root / "arbitrary-name.gguf"
        self.model.write_bytes(b"qualified model")
        self.backend = self.root / "backend"
        self.backend.mkdir()
        self.hashes = {}
        for name in causal_profile.COMPONENTS:
            data = name.encode()
            (self.backend / name).write_bytes(data)
            self.hashes[name] = hashlib.sha256(data).hexdigest()
        self.profile = self.root / "provider.json"
        self.profile.write_text(json.dumps({"schema_version": 1, "backend_dir": str(self.backend),
                                            "model": str(self.model)}))
        self.patches = [
            mock.patch.object(causal_profile, "COMPONENTS", self.hashes),
            mock.patch.object(causal_profile, "MODEL_SHA256", hashlib.sha256(b"qualified model").hexdigest()),
            mock.patch.object(causal_profile, "cpu_model", return_value=causal_profile.CPU_MODEL),
            mock.patch.object(causal_profile, "driver_version", return_value=causal_profile.DRIVER_VERSION),
            mock.patch.object(causal_profile.platform, "machine", return_value="x86_64"),
            mock.patch.object(causal_profile.sys, "platform", "linux"),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.temporary.cleanup)
        self.provider = causal_profile.Installation(self.profile)
        self.machine = {"platform": "Linux", "gpus": [{"name": causal_profile.GPU_MODEL,
                                                       "vram_total_bytes": 16 * 1024**3}]}
        self.metadata = {"general.architecture": causal_profile.ARCHITECTURE}

    def test_only_exact_model_build_machine_and_context_are_eligible(self):
        self.assertTrue(self.provider.eligible(self.model, self.metadata, self.machine, 131072))
        other = self.root / "other.gguf"
        other.write_bytes(b"qualified model")
        self.assertFalse(self.provider.eligible(other, self.metadata, self.machine, 131072))
        self.assertFalse(self.provider.eligible(self.model, {"general.architecture": "other"}, self.machine, 131072))
        self.assertFalse(self.provider.eligible(self.model, self.metadata, self.machine, 131073))
        self.assertFalse(self.provider.eligible(self.model, self.metadata, {**self.machine, "gpus": []}, 131072))
        self.assertFalse(self.provider.eligible(self.model, self.metadata,
                                                {**self.machine, "gpus": self.machine["gpus"] * 2}, 131072))
        with mock.patch.object(causal_profile, "cpu_model", return_value="different"):
            self.assertFalse(self.provider.eligible(self.model, self.metadata, self.machine, 131072))
        with mock.patch.object(causal_profile, "driver_version", return_value="different"):
            self.assertFalse(self.provider.eligible(self.model, self.metadata, self.machine, 131072))

    def test_asset_changes_invalidate_cached_verification(self):
        self.assertTrue(self.provider.available(self.model))
        (self.backend / "libllama.so.0").write_bytes(b"changed")
        self.assertFalse(self.provider.available(self.model))
        self.assertIn("does not match", self.provider.error)

    def test_model_changes_invalidate_cached_verification(self):
        self.assertTrue(self.provider.available(self.model))
        self.model.write_bytes(b"changed")
        self.assertFalse(self.provider.available(self.model))

    def test_native_capability_override_requires_both_exact_binary_hashes(self):
        executable = self.backend / "llama-server"
        library = self.backend / "libllama.so.0"
        known = {"llama-server": hashlib.sha256(executable.read_bytes()).hexdigest(),
                 "libllama.so.0": hashlib.sha256(library.read_bytes()).hexdigest()}
        with mock.patch.object(causal_profile, "UNSUPPORTED_NATIVE", known):
            self.assertTrue(causal_profile.native_cannot_load(executable))
            library.write_bytes(b"changed")
            self.assertFalse(causal_profile.native_cannot_load(executable))

    def test_discovery_does_not_read_model_weights(self):
        with mock.patch.object(causal_profile, "_hash", wraps=causal_profile._hash) as digest:
            self.assertTrue(self.provider.bound_model(self.model))
        self.assertNotIn(self.model, [call.args[0] for call in digest.call_args_list])

    def test_component_symlink_cannot_escape_package(self):
        name = "libllama.so.0"
        external = self.root / "external"
        external.write_bytes(name.encode())
        (self.backend / name).unlink()
        (self.backend / name).symlink_to(external)
        self.assertFalse(self.provider.available())
        self.assertIn("escapes", self.provider.error)

    def test_mapped_libraries_must_all_be_bound(self):
        maps = "\n".join(f"0-1 r-xp 0 00:00 0 {self.backend / name}"
                         for name in self.hashes if name != "llama-server")
        with mock.patch.object(Path, "read_text", return_value=maps):
            self.provider.verify_mappings(123)
        with mock.patch.object(Path, "read_text", return_value=maps.rsplit("\n", 1)[0]):
            with self.assertRaises(ValueError):
                self.provider.verify_mappings(123)

    def test_setup_requires_confirmation_and_preserves_existing_paths(self):
        destination, profile = self.root / "installed", self.root / "installed-profile.json"
        with self.assertRaisesRegex(ValueError, "confirmation"):
            setup_provider.install(self.backend, self.model, destination, profile, self.machine, confirm=False)
        self.assertFalse(destination.exists())
        self.assertFalse(profile.exists())
        destination.mkdir()
        with self.assertRaisesRegex(ValueError, "must not already exist"):
            setup_provider.install(self.backend, self.model, destination, profile, self.machine, confirm=True)

    def test_setup_installs_only_qualified_assets_and_registers_binding(self):
        destination, profile = self.root / "installed", self.root / "config" / "provider.json"
        with mock.patch.object(setup_provider.app, "model_metadata", return_value=self.metadata):
            setup_provider.install(self.backend, self.model, destination, profile, self.machine, confirm=True)
        installed = causal_profile.Installation(profile)
        self.assertTrue(installed.eligible(self.model, self.metadata, self.machine, 131072))
        self.assertEqual(installed.data["backend_dir"], str(destination))
        self.assertTrue(self.backend.exists())

    def test_setup_rejects_unqualified_component_without_writing(self):
        (self.backend / "libllama.so.0").write_bytes(b"bad")
        destination, profile = self.root / "installed", self.root / "config" / "provider.json"
        with mock.patch.object(setup_provider.app, "model_metadata", return_value=self.metadata):
            with self.assertRaisesRegex(ValueError, "does not match"):
                setup_provider.install(self.backend, self.model, destination, profile, self.machine, confirm=True)
        self.assertFalse(destination.exists())
        self.assertFalse(profile.exists())


if __name__ == "__main__":
    unittest.main()
