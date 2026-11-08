"""Read-only discovery and binding for a separately qualified causal provider."""

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import threading


MODEL_SHA256 = "4d439bb832487fbb91d0a739a5746cf3089bde4137c17050576b24e6dba3539c"
COMPONENTS = {
    "llama-server": "aaf14eb2a6ed697cbd4197126cfe1066cc49fa9971ac29a05db92455a7e94199",
    "libllama-server-impl.so": "1106099e3d8de07a46c2ccaf0e5c529d4283086bbbcc7b4f71761584b0b53863",
    "libllama-common.so.0": "4e31151911c27be3a574be3c12e1a085914fb2b0edea8496074d0bec0f64d2f2",
    "libllama.so.0": "c99600b55f68234b64846d85ba504c25e6cb9a0c3bc0419c12fb19103f40b1ec",
    "libmtmd.so.0": "f8d0ac43e1fa00dae749a2dcb2caeaf7de406f43444310f3f0238f7c7f543f70",
    "libggml.so.0": "749a1e32564cd4a8c59d8e6c63502bd5cc6685366b62535d66db4b1c07da1382",
    "libggml-base.so.0": "23bd5a4a49a34f53b568fdc9128886acfb0f40ead8897e9b1449cb7a9646a409",
    "libggml-cpu.so.0": "6da5034d1923c243519e714ac03783598a96587f4ff2f7995332879bd51e2383",
    "libggml-cuda.so.0": "00a3e5a2c8a996a46122ed410bf78e454716a81a97fb366910688156eff0acda",
}
ARCHITECTURE = "clover_moe"
MAX_CONTEXT = 131072
CPU_MODEL = "AMD Ryzen 9 9950X 16-Core Processor"
GPU_MODEL = "NVIDIA GeForce RTX 5070 Ti"
DRIVER_VERSION = "595.58.03"
UNSUPPORTED_NATIVE = {
    "llama-server": "3ac6495070ae9627825dbe706de3b580fdbedd2fbe079197b2c6c81982dbd0f9",
    "libllama.so.0": "d49cfef496d223e74f7890cdfcb96f59ba226e92acf5ab7194a3ee0c3c99f59d",
}
LIBRARY_PATTERN = re.compile(r"^lib(?:llama(?:-common|-server-impl)?|ggml(?:-base|-cpu|-cuda)?|mtmd)\.so(?:\.|$)")


def _signature(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _hash(path):
    before = _signature(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if _signature(path) != before:
        raise ValueError("A provider asset changed while it was being verified.")
    return before, digest.hexdigest()


def cpu_model():
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("model name"):
            return line.partition(":")[2].strip()
    return None


def driver_version():
    text = Path("/proc/driver/nvidia/version").read_text()
    match = re.search(r"Kernel Module.*?\s(\d+\.\d+(?:\.\d+)?)\s", text)
    return match[1] if match else None


def native_cannot_load(executable):
    if not executable:
        return False
    try:
        server = Path(executable).resolve(strict=True)
        return (server.name == "llama-server" and
                _hash(server)[1] == UNSUPPORTED_NATIVE["llama-server"] and
                _hash(server.parent / "libllama.so.0")[1] == UNSUPPORTED_NATIVE["libllama.so.0"])
    except (OSError, ValueError):
        return False


class Installation:
    def __init__(self, path: Path | None):
        self.data = None
        self.error = None
        self.lock = threading.RLock()
        self.verified = {}
        if path is None or not path.exists():
            return
        try:
            if sys.platform != "linux" or path.stat().st_size > 4096:
                raise ValueError("The qualified causal provider requires Linux and a bounded profile.")
            data = json.loads(path.read_text())
            if (not isinstance(data, dict) or set(data) != {"schema_version", "backend_dir", "model"} or
                    type(data["schema_version"]) is not int or data["schema_version"] != 1 or
                    any(not isinstance(data[key], str) or not Path(data[key]).is_absolute()
                        for key in ("backend_dir", "model"))):
                raise ValueError("Unsupported causal provider profile.")
            self.data = data
        except (OSError, ValueError, TypeError) as exc:
            self.error = str(exc)

    def _checked(self, path, expected):
        signature = _signature(path)
        if self.verified.get(str(path)) != (signature, expected):
            result = _hash(path)
            if result[1] != expected:
                raise ValueError("A provider asset does not match the qualified build or model.")
            self.verified[str(path)] = result

    def available(self, model=None):
        if self.data is None:
            return False
        with self.lock:
            try:
                directory = Path(self.data["backend_dir"]).resolve(strict=True)
                for name, digest in COMPONENTS.items():
                    path = (directory / name).resolve(strict=True)
                    if path.parent != directory:
                        raise ValueError("A provider component escapes its bound directory.")
                    self._checked(path, digest)
                if model is not None:
                    bound = Path(self.data["model"]).resolve(strict=True)
                    if not os.path.samefile(model, bound):
                        return False
                    self._checked(bound, MODEL_SHA256)
                self.error = None
                return True
            except (OSError, ValueError) as exc:
                self.error = str(exc)
                return False

    def eligible(self, model, metadata, machine, context):
        try:
            devices = machine.get("gpus", []) if isinstance(machine, dict) else []
            return (self.available(model) and metadata.get("general.architecture") == ARCHITECTURE and
                    type(context) is int and 512 <= context <= MAX_CONTEXT and
                    sys.platform == "linux" and platform.machine() == "x86_64" and cpu_model() == CPU_MODEL and
                    driver_version() == DRIVER_VERSION and
                    isinstance(machine, dict) and machine.get("platform") == "Linux" and
                    isinstance(devices, list) and len(devices) == 1 and
                    any(device.get("name") == GPU_MODEL and type(device.get("vram_total_bytes")) is int and
                        device["vram_total_bytes"] >= 14 * 1024**3 for device in devices
                        if isinstance(device, dict)))
        except (OSError, TypeError):
            return False

    def bound_model(self, model):
        if not self.available():
            return False
        try:
            return os.path.samefile(model, self.data["model"])
        except OSError:
            return False

    def executable(self):
        return str(Path(self.data["backend_dir"]).resolve() / "llama-server")

    def identity(self):
        if not self.available():
            return None
        return {"model": str(Path(self.data["model"]).resolve()), "model_sha256": MODEL_SHA256,
                "backend_dir": str(Path(self.data["backend_dir"]).resolve()), "components": dict(COMPONENTS),
                "driver": DRIVER_VERSION}

    def verify_mappings(self, pid):
        directory = Path(self.data["backend_dir"]).resolve(strict=True)
        expected = {(directory / name).resolve(strict=True) for name in COMPONENTS if name != "llama-server"}
        observed = set()
        for line in Path(f"/proc/{pid}/maps").read_text().splitlines():
            fields = line.split(maxsplit=5)
            if len(fields) == 6 and fields[5].startswith("/") and LIBRARY_PATTERN.match(Path(fields[5]).name):
                observed.add(Path(fields[5]).resolve(strict=True))
        if observed != expected:
            raise ValueError("The causal backend did not bind every qualified library to its package.")
