"""Read-only discovery of a locally qualified optional Strata provider."""

import hashlib
import json
import os
from pathlib import Path
import re
import sys
from importlib.metadata import PackageNotFoundError, version


class Installation:
    def __init__(self, path: Path | None):
        self.path = path
        self.data = None
        self.error = None
        if path is None or not path.exists():
            return
        try:
            if sys.platform != "linux" or path.stat().st_size > 262144:
                raise ValueError("The qualified Strata profile requires Linux and a bounded configuration.")
            data = json.loads(path.read_text())
            if (not isinstance(data, dict) or set(data) != {
                    "schema_version", "executable", "configuration", "model", "minimum_vram_mib",
                    "maximum_context", "cache_mib", "cache_slots", "build_files", "qualification_sha256"} or
                    type(data["schema_version"]) is not int or data["schema_version"] != 1 or
                    not isinstance(data["qualification_sha256"], str) or
                    not re.fullmatch(r"[a-f0-9]{64}", data["qualification_sha256"])):
                raise ValueError("Unsupported Strata provider profile.")
            for name in ("minimum_vram_mib", "maximum_context", "cache_mib"):
                if type(data[name]) is not int or not 1 <= data[name] <= 65536:
                    raise ValueError("Invalid Strata capacity contract.")
            if not 512 <= data["maximum_context"] <= 16384:
                raise ValueError("Strata context exceeds the qualified scope.")
            if type(data["cache_slots"]) is not int or not 1 <= data["cache_slots"] <= 1048576:
                raise ValueError("Invalid qualified Strata cache residency.")
            if not isinstance(data["build_files"], list) or not 1 <= len(data["build_files"]) <= 1024:
                raise ValueError("Invalid Strata component identity.")
            for entry in [data["model"], *data["build_files"]]:
                if (not isinstance(entry, dict) or set(entry) != {"path", "size", "mtime_ns"} or
                        not isinstance(entry["path"], str) or not Path(entry["path"]).is_absolute() or
                        type(entry["size"]) is not int or entry["size"] < 0 or
                        type(entry["mtime_ns"]) is not int):
                    raise ValueError("Invalid Strata asset identity.")
            if data["model"]["size"] == 0:
                raise ValueError("Strata model cannot be empty.")
            for name in ("executable", "configuration"):
                if not isinstance(data[name], str) or not Path(data[name]).is_absolute():
                    raise ValueError("Strata component paths must be absolute.")
                if data[name] not in {item["path"] for item in data["build_files"]}:
                    raise ValueError("Strata entrypoint/configuration must be bound to the component identity.")
            self.data = data
        except (OSError, ValueError, TypeError) as exc:
            self.error = str(exc)

    @staticmethod
    def _current(entry):
        try:
            info = Path(entry["path"]).stat()
            return info.st_size == entry["size"] and info.st_mtime_ns == entry["mtime_ns"]
        except OSError:
            return False

    def available(self, model=None):
        if self.data is None:
            return False
        if (not all(self._current(item) for item in self.data["build_files"]) or
                not self._current(self.data["model"])):
            self.error = "Strata assets changed since qualification; the provider must be requalified."
            return False
        self.error = None
        if model is not None:
            try:
                return os.path.samefile(model, self.data["model"]["path"])
            except OSError:
                return False
        return True

    def eligible(self, model, hardware, placement, cache):
        return (self.available(model) and placement == "auto" and cache == "f16" and
                str(hardware.get("platform", "")).lower() == "linux" and any(
                    isinstance(gpu, dict) and "nvidia" in str(gpu.get("name", "")).lower() and
                    type(gpu.get("vram_total_bytes")) is int and
                    gpu["vram_total_bytes"] >= self.data["minimum_vram_mib"] * 1024**2
                    for gpu in hardware.get("gpus", [])))

    def identity(self):
        if self.data is None:
            return None
        files = []
        for entry in self.data["build_files"]:
            try:
                info = Path(entry["path"]).stat()
                files.append([entry["path"], info.st_size, info.st_mtime_ns])
            except OSError:
                files.append([entry["path"], None, None])
        dependencies = {}
        for name in ("numpy", "regex", "jinja2"):
            try:
                dependencies[name] = version(name)
            except PackageNotFoundError:
                dependencies[name] = None
        return {"model": dict(self.data["model"]), "python": sys.version, "dependencies": dependencies,
                "profile": hashlib.sha256(json.dumps(self.data, sort_keys=True).encode()).hexdigest(),
                "files": files}
