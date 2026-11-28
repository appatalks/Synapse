import hashlib
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from synapse_app.model_library import CATALOG, ModelLibrary


CONTENT = b"GGUF fixture bytes"
MODEL = {"id": "test-model", "name": "Test", "repo": "publisher/repo", "revision": "a" * 40,
         "filename": "test.gguf", "size": len(CONTENT), "sha256": hashlib.sha256(CONTENT).hexdigest(),
         "license": "MIT", "gain": None, "evidence": "fixture"}
SHARDED_CONTENT = (b"first shard", b"second shard")
SHARDED_MODEL = {"id": "test-sharded-model", "name": "Sharded test", "repo": "publisher/repo",
                 "revision": "b" * 40,
                 "filename": "weights-00001-of-00002.gguf",
                 "size": sum(map(len, SHARDED_CONTENT)),
                 "files": tuple({"filename": f"weights-0000{index}-of-00002.gguf", "size": len(content),
                                 "remote_path": f"quant/weights-0000{index}-of-00002.gguf",
                                 "sha256": hashlib.sha256(content).hexdigest()}
                                for index, content in enumerate(SHARDED_CONTENT, 1)),
                 "license": "MIT", "gain": None, "evidence": "fixture"}


class ModelLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.library = ModelLibrary(self.root, [MODEL])
        self.addCleanup(self.library.close)

    def wait(self):
        self.library.worker.join(timeout=5)
        self.assertFalse(self.library.worker.is_alive())
        return self.library.snapshot()

    def run_download(self, content=CONTENT):
        opener = mock.Mock()
        opener.open.return_value = io.BytesIO(content)
        with mock.patch("synapse_app.model_library.urllib.request.build_opener", return_value=opener), \
                mock.patch("synapse_app.model_library.shutil.disk_usage") as disk:
            disk.return_value.free = 2 * 1024**3
            self.library.start("test-model", str(self.root), True)
            return self.wait()

    def test_explicit_download_checks_hash_and_never_overwrites(self):
        with self.assertRaises(ValueError):
            self.library.start("test-model", str(self.root), False)
        with self.assertRaises(ValueError):
            self.library.start("unknown", str(self.root), True)
        with self.assertRaises(ValueError):
            self.library.start([], str(self.root), True)
        state = self.run_download()
        self.assertEqual(state["state"], "completed")
        path = Path(state["path"])
        self.assertEqual(path.read_bytes(), CONTENT)
        self.assertTrue(self.library.listing()["models"][0]["installed"])
        self.assertEqual(self.run_download()["state"], "error")
        self.assertEqual(path.read_bytes(), CONTENT)

    def test_hash_failure_never_publishes_and_removes_partial(self):
        state = self.run_download(b"X" * len(CONTENT))
        self.assertEqual(state["state"], "error")
        self.assertIn("SHA-256", state["error"])
        self.assertEqual(list((self.root / "test-model").iterdir()), [])

    def test_sharded_download_verifies_all_files_before_publishing(self):
        library = ModelLibrary(self.root, [SHARDED_MODEL])
        self.addCleanup(library.close)
        openers = [mock.Mock() for _ in SHARDED_CONTENT]
        for opener, content in zip(openers, SHARDED_CONTENT):
            opener.open.return_value = io.BytesIO(content)
        with mock.patch("synapse_app.model_library.urllib.request.build_opener", side_effect=openers), \
                mock.patch("synapse_app.model_library.shutil.disk_usage") as disk:
            disk.return_value.free = 100 * 1024**3
            state = library.start("test-sharded-model", str(self.root), True)
            self.assertEqual(state["total"], SHARDED_MODEL["size"])
            state = self.wait_library(library)
        self.assertEqual(state["state"], "completed")
        for index, opener in enumerate(openers, 1):
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, f"https://huggingface.co/publisher/repo/resolve/{'b' * 40}/"
                             f"quant/weights-0000{index}-of-00002.gguf")
        folder = self.root / "test-sharded-model"
        for file in SHARDED_MODEL["files"]:
            self.assertEqual((folder / file["filename"]).read_bytes(),
                             SHARDED_CONTENT[SHARDED_MODEL["files"].index(file)])
        self.assertTrue(library.listing()["models"][0]["installed"])

    def test_sharded_download_failure_does_not_publish_verified_first_shard(self):
        library = ModelLibrary(self.root, [SHARDED_MODEL])
        self.addCleanup(library.close)
        openers = [mock.Mock(), mock.Mock()]
        openers[0].open.return_value = io.BytesIO(SHARDED_CONTENT[0])
        openers[1].open.return_value = io.BytesIO(b"X" * len(SHARDED_CONTENT[1]))
        with mock.patch("synapse_app.model_library.urllib.request.build_opener", side_effect=openers), \
                mock.patch("synapse_app.model_library.shutil.disk_usage") as disk:
            disk.return_value.free = 100 * 1024**3
            library.start("test-sharded-model", str(self.root), True)
            state = self.wait_library(library)
        self.assertEqual(state["state"], "error")
        self.assertIn("SHA-256", state["error"])
        self.assertEqual(list((self.root / "test-sharded-model").iterdir()), [])
        self.assertFalse(library.listing()["models"][0]["installed"])

    def test_huihui_shards_use_quantization_subdirectories(self):
        for model in CATALOG:
            if not model["id"].startswith("huihui-qwen38-flash-iq3-"):
                continue
            quantization = "IQ3_XXS" if model["id"].endswith("xxs") else "IQ3_S"
            for file in model["files"]:
                self.assertEqual(file["remote_path"], f"swift-{quantization}/{file['filename']}")

    def test_huihui_27b_catalog_entry_is_pinned_and_unverified(self):
        model = next(item for item in CATALOG if item["id"] == "huihui-qwen38-27b-iq3-s")
        self.assertEqual(model["filename"], "Huihui-Qwen3.8-27B-abliterated-GSQ-RCO-IQ3_S.gguf")
        self.assertEqual(model["size"], 11771546208)
        self.assertEqual(len(model["revision"]), 40)
        self.assertEqual(len(model["sha256"]), 64)
        self.assertIn("unverified", model["evidence"])

    def wait_library(self, library):
        library.worker.join(timeout=5)
        self.assertFalse(library.worker.is_alive())
        return library.snapshot()

    def test_cancellation_removes_partial(self):
        started = threading.Event()
        proceed = threading.Event()

        class Blocked(io.BytesIO):
            def read(self, size=-1):
                started.set()
                proceed.wait(3)
                return super().read(size)

        opener = mock.Mock()
        opener.open.return_value = Blocked(CONTENT)
        with mock.patch("synapse_app.model_library.urllib.request.build_opener", return_value=opener), \
                mock.patch("synapse_app.model_library.shutil.disk_usage") as disk:
            disk.return_value.free = 2 * 1024**3
            self.library.start("test-model", str(self.root), True)
            self.assertTrue(started.wait(3))
            self.library.cancel()
            proceed.set()
            self.assertEqual(self.wait()["state"], "cancelled")
        self.assertEqual(list((self.root / "test-model").iterdir()), [])

    def test_unavailable_space_is_reported_without_network(self):
        with mock.patch("synapse_app.model_library.shutil.disk_usage") as disk, \
                mock.patch("synapse_app.model_library.urllib.request.build_opener") as opener:
            disk.return_value.free = 0
            self.library.start("test-model", str(self.root), True)
            self.assertIn("free disk", self.wait()["error"])
            opener.assert_not_called()

    def test_discovers_recent_and_local_models_groups_shards_and_reports_clover(self):
        root = self.root / "models"
        root.mkdir()
        nested = root / "qwen"
        nested.mkdir()
        first = nested / "weights-00001-of-00002.gguf"
        second = nested / "weights-00002-of-00002.gguf"
        first.write_bytes(b"GGUFfirst")
        second.write_bytes(b"GGUFsecond")
        clover = root / "clover.gguf"
        clover.write_bytes(b"GGUFclover")
        recent = self.root / "outside.gguf"
        recent.write_bytes(b"GGUFrecent")
        invalid = root / "invalid.gguf"
        invalid.write_bytes(b"NOPE")
        try:
            (root / "loop").symlink_to(root, target_is_directory=True)
            (root / "duplicate.gguf").symlink_to(clover)
            outside = self.root / "outside-dir"
            outside.mkdir()
            (outside / "not-allowed.gguf").write_bytes(b"GGUFoutside")
            (root / "outside-link").symlink_to(outside, target_is_directory=True)
        except OSError:
            pass

        def metadata(path):
            return {"general.architecture": "clover_moe" if path.name == "clover.gguf" else "qwen4exp"}

        library = ModelLibrary(str(root), [], metadata=metadata)
        self.addCleanup(library.close)
        library.discover(recent=[str(recent), str(clover)])
        library.scan_worker.join(timeout=5)
        state = library.discovery()
        self.assertEqual(state["state"], "completed")
        self.assertEqual(len(state["models"]), 3)
        by_name = {item["name"]: item for item in state["models"]}
        self.assertIn("outside.gguf", by_name)
        self.assertEqual(by_name[first.name]["size"], first.stat().st_size + second.stat().st_size)
        self.assertEqual(by_name[first.name]["missing_shards"], [])
        self.assertIn("compatible backend", by_name[clover.name]["note"])
        self.assertNotIn(second.name, by_name)
        self.assertNotIn("not-allowed.gguf", by_name)

        second.unlink()
        library.discover(recent=[str(recent), str(clover)], force=True)
        library.scan_worker.join(timeout=5)
        first_entry = next(item for item in library.discovery()["models"] if item["name"] == first.name)
        self.assertEqual(first_entry["missing_shards"], [second.name])

    def test_unavailable_roots_are_reported_and_do_not_block_other_models(self):
        folder = self.root / "present"
        folder.mkdir()
        (folder / "test.gguf").write_bytes(b"GGUFdata")
        missing = self.root / "missing"
        library = ModelLibrary(str(folder), [], search_roots=[str(missing)])
        self.addCleanup(library.close)
        library.discover()
        library.scan_worker.join(timeout=5)
        state = library.discovery()
        self.assertEqual(len(state["models"]), 1)
        self.assertTrue(any(str(missing) in warning for warning in state["warnings"]))


if __name__ == "__main__":
    unittest.main()
