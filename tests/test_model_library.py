import hashlib
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from synapse_app.model_library import ModelLibrary


CONTENT = b"GGUF fixture bytes"
MODEL = {"id": "test-model", "name": "Test", "repo": "publisher/repo", "revision": "a" * 40,
         "filename": "test.gguf", "size": len(CONTENT), "sha256": hashlib.sha256(CONTENT).hexdigest(),
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


if __name__ == "__main__":
    unittest.main()
