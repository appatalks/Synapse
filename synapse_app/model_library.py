"""Curated, checksummed model downloads; no model is downloaded automatically."""

import hashlib
import http.client
import os
from pathlib import Path
import shutil
import tempfile
import threading
import urllib.request

from .updates import HttpsRedirect


CATALOG = (
    {"id": "qwen3-4b-q4", "name": "Qwen3 4B · Q4_K_M", "repo": "Qwen/Qwen3-4B-GGUF",
     "revision": "bc640142c66e1fdd12af0bd68f40445458f3869b", "filename": "Qwen3-4B-Q4_K_M.gguf",
     "size": 2497280256, "sha256": "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5",
     "license": "Apache-2.0", "gain": None, "evidence": "Standard 16K: narrow arithmetic and code checks passed."},
    {"id": "gpt-oss-20b", "name": "GPT-OSS 20B · MXFP4", "repo": "ggml-org/gpt-oss-20b-GGUF",
     "revision": "15dcfc7e7c608c6161507211ed43c5b590801b4b", "filename": "gpt-oss-20b-MXFP4.gguf",
     "size": 12109566624, "sha256": "27cd6c432c7672cb812a92f611cf3ba7bbc35928262bb1e1253ff4ee6ae35901",
     "license": "Apache-2.0", "gain": None, "evidence": "Standard 16K passed narrow checks; tested hybrid was slower."},
    {"id": "qwen3-coder-30b", "name": "Qwen3 Coder 30B-A3B · Q4_K_M",
     "repo": "unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF", "revision": "b17cb02dd882d5b6ab62fc777ad2995f19668350",
     "filename": "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf", "size": 18556689568,
     "sha256": "fadc3e5f8d42bf7e894a785b05082e47daee4df26680389817e2093056f088ad", "license": "Apache-2.0",
     "gain": 57.1, "evidence": "Measured +57.1% vs Standard at 16K, Ryzen 9950X / RTX 5070 Ti; output hashes differed, full numerical parity untested. Not a guarantee."},
    {"id": "glm-47-flash", "name": "GLM-4.7 Flash · Q4_K_M",
     "repo": "unsloth/GLM-4.7-Flash-GGUF", "revision": "0d32489ecb9db6d2a4fc93bd27ef01519f95474d",
     "filename": "GLM-4.7-Flash-Q4_K_M.gguf", "size": 18312339808,
     "sha256": "29837ed2c0fc5f51981adf8ac8083fcf80743c598381f13e9f06cbad0498b174", "license": "MIT",
     "gain": 34.8, "evidence": "Measured +34.8% vs Standard at 16K, Ryzen 9950X / RTX 5070 Ti; output hashes differed, full numerical parity untested. Not a guarantee."},
    {"id": "qwen38-27b", "name": "Qwen3.8 27B · UD-Q4_K_M", "repo": "unsloth/Qwen3.8-27B-GGUF",
     "revision": "4ca720788d1e01f1bff70c033e0d0028fd02e502", "filename": "Qwen3.8-27B-UD-Q4_K_M.gguf",
     "size": 16464440224, "sha256": "322e194ff79741c7baa497c240f677f54b201b0efab44ca8e50f122b39123482",
     "license": "Apache-2.0", "gain": None, "evidence": "Standard 16K passed narrow checks; acceleration gain not measured."},
)


class Cancelled(Exception):
    pass


class ModelLibrary:
    def __init__(self, default_directory=None, catalog=CATALOG):
        self.default_directory = str(default_directory or Path.home() / "Synapse Models")
        self.catalog = {item["id"]: dict(item) for item in catalog}
        self.lock = threading.Lock()
        self.cancelled = threading.Event()
        self.state = {"state": "idle", "active": False}
        self.worker = None

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def listing(self, directory=None):
        root = Path(directory or self.default_directory).expanduser()
        result = []
        for item in self.catalog.values():
            path = root / item["id"] / item["filename"]
            # A matching size is only a local discovery hint, not an integrity verification.
            try:
                exists = path.is_file() and path.stat().st_size == item["size"]
            except OSError:
                exists = False
            result.append({**item, "path": str(path), "installed": exists})
        return {"directory": str(root), "models": result, "download": self.snapshot()}

    def start(self, model_id, directory, confirm):
        if confirm is not True:
            raise ValueError("Confirm the download size and model license before downloading.")
        if not isinstance(model_id, str) or model_id not in self.catalog:
            raise ValueError("Choose a model from the tested catalog.")
        if not isinstance(directory, str) or not directory.strip() or len(directory) > 4096:
            raise ValueError("Choose a model download directory.")
        root = Path(directory).expanduser()
        if not root.is_absolute():
            raise ValueError("Model download directory must be absolute.")
        with self.lock:
            if self.state["active"]:
                raise RuntimeError("A model download is already running.")
            self.cancelled.clear()
            self.state = {"state": "downloading", "active": True, "model": model_id,
                          "downloaded": 0, "total": self.catalog[model_id]["size"], "error": None}
            self.worker = threading.Thread(target=self._download, args=(self.catalog[model_id], root), daemon=True)
            self.worker.start()
        return self.snapshot()

    def cancel(self):
        self.cancelled.set()
        return self.snapshot()

    def close(self):
        self.cancelled.set()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(timeout=3)

    def _download(self, model, root):
        temporary = None
        try:
            root.mkdir(parents=True, exist_ok=True)
            folder = root / model["id"]
            if folder.is_symlink():
                raise ValueError("The model folder cannot be a symbolic link.")
            folder.mkdir(exist_ok=True)
            target = folder / model["filename"]
            if target.exists() or target.is_symlink():
                raise ValueError("Destination already exists; existing files are never overwritten.")
            if shutil.disk_usage(folder).free < model["size"] + 1024**3:
                raise ValueError("Not enough free disk space for the model plus 1 GiB reserve.")
            url = f"https://huggingface.co/{model['repo']}/resolve/{model['revision']}/{model['filename']}"
            request = urllib.request.Request(url, headers={"User-Agent": "SYNAPSE-model-download",
                                                         "Accept-Encoding": "identity"})
            digest = hashlib.sha256()
            count = 0
            with tempfile.NamedTemporaryFile(dir=folder, prefix=".synapse-download-", suffix=".part",
                                             delete=False) as output:
                temporary = Path(output.name)
                with urllib.request.build_opener(HttpsRedirect()).open(request, timeout=30) as response:
                    while True:
                        if self.cancelled.is_set():
                            raise Cancelled()
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > model["size"]:
                            raise ValueError("Download exceeded the expected model size.")
                        output.write(chunk)
                        digest.update(chunk)
                        with self.lock:
                            self.state["downloaded"] = count
                output.flush()
                os.fsync(output.fileno())
            if self.cancelled.is_set():
                raise Cancelled()
            if count != model["size"] or digest.hexdigest() != model["sha256"]:
                raise ValueError("Download size or SHA-256 did not match the pinned model.")
            os.link(temporary, target)
            with self.lock:
                self.state.update(state="completed", active=False, path=str(target))
        except Cancelled:
            with self.lock:
                self.state.update(state="cancelled", active=False)
        except (OSError, ValueError, http.client.HTTPException) as exc:
            with self.lock:
                self.state.update(state="error", active=False, error=str(exc))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
