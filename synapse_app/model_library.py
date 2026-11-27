"""Curated, checksummed model downloads; no model is downloaded automatically."""

import hashlib
import http.client
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import urllib.request
from collections import deque

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
    {"id": "huihui-qwen38-flash-iq3-xxs",
     "name": "Huihui Qwen3.8 Flash-Next Abliterated v2 · IQ3_XXS",
     "repo": "huihui-ai/Huihui-Qwen3.8-Flash-Next-abliterated-v2-GGUF",
     "revision": "cbc7fba13f1939ac3fa42b18d77ccf43847d74ef",
     "filename": "Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf",
     "size": 75966073120,
     "files": (
         {"filename": "Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf",
          "remote_path": "swift-IQ3_XXS/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf",
          "size": 39785790560, "sha256": "e66b543e5b89f039c81e5d74c31d2410de60e3cb84a7b89aec1f2ce11fdd9830"},
         {"filename": "Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00002-of-00002.gguf",
          "remote_path": "swift-IQ3_XXS/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00002-of-00002.gguf",
          "size": 36180282560, "sha256": "d219681902f80f677b200d6bbb30387010de6cea51f6cc14ef90d873a5357a85"},
     ),
     "license": "qwen-community-1.0", "gain": None,
     "evidence": "Not tested with SYNAPSE; compatibility and performance are unverified. Abliterated model with reduced refusal behavior; review the publisher's model card and license."},
    {"id": "huihui-qwen38-flash-iq3-s",
     "name": "Huihui Qwen3.8 Flash-Next Abliterated v2 · IQ3_S",
     "repo": "huihui-ai/Huihui-Qwen3.8-Flash-Next-abliterated-v2-GGUF",
     "revision": "cbc7fba13f1939ac3fa42b18d77ccf43847d74ef",
     "filename": "Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf",
     "size": 83743737120,
     "files": (
         {"filename": "Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf",
          "remote_path": "swift-IQ3_S/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf",
          "size": 44900816736, "sha256": "9cdb79ad99ef066064628f13b67ace8ef077d02d9d3848a53b11d5c3cbe94332"},
         {"filename": "Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf",
          "remote_path": "swift-IQ3_S/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf",
          "size": 38842920384, "sha256": "04e1f010edbeacbce3a8948abf0044e858d73a37fc74a0e58abeeff98cbe4f0f"},
     ),
     "license": "qwen-community-1.0", "gain": None,
     "evidence": "Not tested with SYNAPSE; compatibility and performance are unverified. Abliterated model with reduced refusal behavior; review the publisher's model card and license."},
)


def _model_files(model):
    if "files" in model:
        return model["files"]
    return ({"filename": model["filename"], "size": model["size"], "sha256": model["sha256"]},)


class Cancelled(Exception):
    pass


class ModelLibrary:
    def __init__(self, default_directory=None, catalog=CATALOG, *, search_roots=None, metadata=None,
                 registered_provider=None):
        self.default_directory = str(default_directory or Path.home() / "Synapse Models")
        self.search_roots = list(search_roots or [])
        self.metadata = metadata
        self.registered_provider = registered_provider
        self.catalog = {item["id"]: dict(item) for item in catalog}
        self.lock = threading.Lock()
        self.cancelled = threading.Event()
        self.state = {"state": "idle", "active": False}
        self.worker = None
        self.scan_worker = None
        self.scan_cancelled = threading.Event()
        self.scan_state = {"state": "idle", "active": False, "models": [], "warnings": [], "truncated": False}
        self.scan_key = None

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def discovery(self):
        with self.lock:
            return {**self.scan_state, "models": [dict(item) for item in self.scan_state["models"]],
                    "warnings": list(self.scan_state["warnings"])}

    def listing(self, directory=None, *, recent=()):
        root = Path(directory or self.default_directory).expanduser()
        self.discover(str(root), recent=recent)
        result = []
        for item in self.catalog.values():
            paths = [root / item["id"] / file["filename"] for file in _model_files(item)]
            path = paths[0]
            # A matching size is only a local discovery hint, not an integrity verification.
            try:
                exists = all(file_path.is_file() and file_path.stat().st_size == file["size"]
                             for file_path, file in zip(paths, _model_files(item)))
            except OSError:
                exists = False
            result.append({**item, "path": str(path), "installed": exists})
        return {"directory": str(root), "models": result, "download": self.snapshot(),
                "discovery": self.discovery()}

    def discover(self, directory=None, *, recent=(), force=False):
        root = directory or self.default_directory
        if not isinstance(root, str) or not root.strip() or len(root) > 4096 or not Path(root).expanduser().is_absolute():
            raise ValueError("Model library directory must be an absolute path.")
        roots = list(dict.fromkeys([str(Path(root).expanduser()), *self.search_roots]))
        recent = tuple(path for path in recent if isinstance(path, str) and path and len(path) <= 4096)
        key = (tuple(roots), recent)
        with self.lock:
            if self.scan_state["active"] or (self.scan_key == key and not force):
                return
            self.scan_key = key
            self.scan_cancelled.clear()
            self.scan_state = {"state": "scanning", "active": True, "models": [], "warnings": [],
                               "truncated": False, "roots": roots}
            self.scan_worker = threading.Thread(target=self._scan, args=(roots, recent), daemon=True)
            self.scan_worker.start()

    def _scan(self, roots, recent):
        models, warnings, files_seen, dirs_seen = [], [], set(), set()
        visited_entries = 0
        truncated = False
        allowed = []
        for root in roots:
            try:
                allowed.append(Path(root).expanduser().resolve())
            except (OSError, RuntimeError):
                warnings.append(f"Could not scan: {root}")

        def append(path, *, recent_file=False):
            try:
                resolved = path.resolve(strict=True)
                if not recent_file and not any(resolved == root or root in resolved.parents for root in allowed):
                    return
                match = re.search(r"-(\d{5})-of-(\d{5})\.gguf$", path.name, re.IGNORECASE)
                if match and int(match[1]) != 1:
                    return
                info = path.stat()
                identity = (info.st_dev, info.st_ino)
                if identity in files_seen or not path.is_file():
                    return
                with path.open("rb") as source:
                    if source.read(4) != b"GGUF":
                        return
                files_seen.add(identity)
                missing, size = [], info.st_size
                if match:
                    total = int(match[2])
                    if not 1 <= total <= 128:
                        missing = ["Shard count outside discovery limit"]
                    else:
                        for index in range(1, total + 1):
                            shard = path.with_name(path.name[:match.start(1)] + f"{index:05d}" + path.name[match.end(1):])
                            if not shard.is_file():
                                missing.append(shard.name)
                            elif index != 1:
                                size += shard.stat().st_size
                architecture = None
                if self.metadata is not None:
                    try:
                        architecture = self.metadata(path).get("general.architecture")
                    except (OSError, ValueError, UnicodeError):
                        pass
                if self.registered_provider is not None and self.registered_provider(path):
                    note = "A provider is registered for this file; integrity and runtime verification are required."
                else:
                    note = ("Clover architecture needs a compatible backend; the default installer backend cannot load it."
                            if architecture == "clover_moe" else
                            "Local file discovered; backend compatibility and quality are not verified.")
                models.append({"name": path.name, "path": str(path), "size": size,
                               "architecture": architecture, "missing_shards": missing, "note": note})
                with self.lock:
                    self.scan_state["models"] = list(models)
            except (OSError, RuntimeError):
                return

        for value in recent:
            path = Path(value).expanduser()
            if path.suffix.lower() == ".gguf":
                append(path, recent_file=True)
        queue = deque(allowed)
        while queue and not self.scan_cancelled.is_set():
            directory = queue.popleft()
            try:
                real = directory.resolve(strict=True)
                if not any(real == root or root in real.parents for root in allowed):
                    continue
                info = real.stat()
                identity = (info.st_dev, info.st_ino)
                if identity in dirs_seen:
                    continue
                if len(dirs_seen) >= 5000 or visited_entries >= 30000 or len(models) >= 500:
                    truncated = True
                    break
                dirs_seen.add(identity)
                with os.scandir(real) as entries:
                    for entry in entries:
                        visited_entries += 1
                        if visited_entries > 30000 or len(models) >= 500 or self.scan_cancelled.is_set():
                            truncated = True
                            break
                        if entry.name.startswith("."):
                            continue
                        try:
                            if entry.is_dir(follow_symlinks=True):
                                queue.append(Path(entry.path))
                            elif entry.name.lower().endswith(".gguf"):
                                append(Path(entry.path))
                        except OSError:
                            continue
            except (OSError, RuntimeError):
                if len(warnings) < 10:
                    warnings.append(f"Could not scan: {directory}")
        with self.lock:
            self.scan_state.update(state="cancelled" if self.scan_cancelled.is_set() else "completed",
                                   active=False, models=models, warnings=warnings, truncated=truncated)

    def start(self, model_id, directory, confirm):
        if confirm is not True:
            raise ValueError("Confirm the download size and model license before downloading.")
        if not isinstance(model_id, str) or model_id not in self.catalog:
            raise ValueError("Choose a model from the catalog.")
        if not isinstance(directory, str) or not directory.strip() or len(directory) > 4096:
            raise ValueError("Choose a model download directory.")
        root = Path(directory).expanduser()
        if not root.is_absolute():
            raise ValueError("Model download directory must be absolute.")
        model = self.catalog[model_id]
        total_size = sum(file["size"] for file in _model_files(model))
        with self.lock:
            if self.state["active"]:
                raise RuntimeError("A model download is already running.")
            self.cancelled.clear()
            self.state = {"state": "downloading", "active": True, "model": model_id,
                          "downloaded": 0, "total": total_size, "error": None}
            self.worker = threading.Thread(target=self._download, args=(model, root), daemon=True)
            self.worker.start()
        return self.snapshot()

    def cancel(self):
        self.cancelled.set()
        return self.snapshot()

    def close(self):
        self.cancelled.set()
        self.scan_cancelled.set()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(timeout=3)
        if self.scan_worker and self.scan_worker is not threading.current_thread():
            self.scan_worker.join(timeout=3)

    def _download(self, model, root):
        published = []
        success = False
        try:
            root.mkdir(parents=True, exist_ok=True)
            folder = root / model["id"]
            if folder.is_symlink():
                raise ValueError("The model folder cannot be a symbolic link.")
            folder.mkdir(exist_ok=True)
            files = _model_files(model)
            targets = [folder / file["filename"] for file in files]
            if any(target.exists() or target.is_symlink() for target in targets):
                raise ValueError("Destination already exists; existing files are never overwritten.")
            if shutil.disk_usage(folder).free < model["size"] + 1024**3:
                raise ValueError("Not enough free disk space for the model plus 1 GiB reserve.")
            downloaded = 0
            with tempfile.TemporaryDirectory(prefix=".synapse-download-", dir=folder) as staging:
                staged = []
                for index, (file, target) in enumerate(zip(files, targets)):
                    temporary = Path(staging) / str(index)
                    remote_path = file.get("remote_path", file["filename"])
                    url = f"https://huggingface.co/{model['repo']}/resolve/{model['revision']}/{remote_path}"
                    request = urllib.request.Request(url, headers={"User-Agent": "SYNAPSE-model-download",
                                                                 "Accept-Encoding": "identity"})
                    digest = hashlib.sha256()
                    count = 0
                    with temporary.open("xb") as output:
                        with urllib.request.build_opener(HttpsRedirect()).open(request, timeout=30) as response:
                            while True:
                                if self.cancelled.is_set():
                                    raise Cancelled()
                                chunk = response.read(1024 * 1024)
                                if not chunk:
                                    break
                                count += len(chunk)
                                if count > file["size"]:
                                    raise ValueError("Download exceeded the expected model shard size.")
                                output.write(chunk)
                                digest.update(chunk)
                                with self.lock:
                                    self.state["downloaded"] = downloaded + count
                        output.flush()
                        os.fsync(output.fileno())
                    if count != file["size"] or digest.hexdigest() != file["sha256"]:
                        raise ValueError("Download size or SHA-256 did not match the pinned model shard.")
                    downloaded += count
                    staged.append((temporary, target))
                if self.cancelled.is_set():
                    raise Cancelled()
                for temporary, target in staged:
                    os.link(temporary, target)
                    published.append(target)
            with self.lock:
                self.state.update(state="completed", active=False, path=str(targets[0]))
            success = True
        except Cancelled:
            with self.lock:
                self.state.update(state="cancelled", active=False)
        except (OSError, ValueError, http.client.HTTPException) as exc:
            with self.lock:
                self.state.update(state="error", active=False, error=str(exc))
        finally:
            if not success:
                for target in published:
                    target.unlink(missing_ok=True)
