#!/usr/bin/env python3
"""SYNAPSE: local models, a local API, and live hardware monitoring."""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
from importlib.resources import files
import json
import logging
import os
from pathlib import Path
import re
import secrets
import select
import shutil
import signal
import socket
from socketserver import TCPServer
import struct
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

APP_PACKAGE = __package__ or Path(__file__).resolve().parent.name
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
__version__ = import_module(APP_PACKAGE).__version__
_telemetry = import_module(f"{APP_PACKAGE}.telemetry")
HardwareMonitor, number, rate, system_probe = (
    _telemetry.HardwareMonitor, _telemetry.number, _telemetry.rate, _telemetry.system_probe)
_updates = import_module(f"{APP_PACKAGE}.updates")

LOG = logging.getLogger("synapse")
WEB_ROOT = Path(__file__).with_name("web")
BODY_LIMIT = 1024 * 1024
RESPONSE_LIMIT = 8 * 1024 * 1024
PINNED_LLAMA_COMMIT = "620d2225cc436ab0b001e3200e590e3b286ef9ab"
HYBRID_WARNING = (
    "Experimental tensor-derived MoE dispatch. Measured speedups cover limited tested MoE configurations, not every model. "
    "Strict model diagnostics and an answer check remain failed. About 57 GiB of RAM stays pinned "
    "during the measured 120B direct-DMA profile; other layouts and staged transfers differ. "
    "Direct registration enforces a 64 GiB cap and 24 GiB available-RAM headroom. "
    "Unload releases resources. Speculation is disabled."
)


def available_cpus() -> set[int]:
    if hasattr(os, "sched_getaffinity"):
        return set(os.sched_getaffinity(0))
    return set(range(os.cpu_count() or 1))


def default_cpu_threads() -> int:
    cpus = available_cpus()
    if sys.platform != "linux":
        return min(8, len(cpus))
    try:
        physical = set()
        for cpu in cpus:
            root = Path("/sys/devices/system/cpu") / f"cpu{cpu}" / "topology"
            physical.add(((root / "physical_package_id").read_text().strip(),
                          (root / "core_id").read_text().strip()))
        return max(1, len(physical))
    except OSError as exc:
        LOG.warning("Physical CPU topology unavailable; using affinity-based thread count: %s", exc)
        return max(1, len(cpus) - 2)


def backend_executable(value: str) -> str | None:
    path = Path(value).expanduser()
    if path.suffix.lower() == ".py" and path.is_file():
        return str(path.resolve())
    return shutil.which(value)


class AppError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def browse_models(value: object = None) -> dict:
    if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 4096):
        raise AppError(400, "Enter a local folder path or leave it unspecified to start at Home.")
    try:
        folder = Path.home() if value is None else Path(value).expanduser()
        if not folder.is_absolute():
            raise AppError(400, "Use an absolute local folder path.")
        folder = folder.resolve(strict=True)
        if folder.is_file() and folder.suffix.lower() == ".gguf":
            folder = folder.parent
        if not folder.is_dir():
            raise AppError(400, "Choose a folder or a local GGUF model.")
        entries = []
        scanned, truncated = 0, False
        with os.scandir(folder) as iterator:
            for entry in iterator:
                scanned += 1
                if scanned > 4096:
                    truncated = True
                    break
                if entry.name.startswith("."):
                    continue
                directory = entry.is_dir()
                if directory or entry.name.lower().endswith(".gguf") and entry.is_file():
                    entries.append({"name": entry.name, "path": str(folder / entry.name),
                                    "directory": directory})
        entries.sort(key=lambda entry: (not entry["directory"], entry["name"].casefold(), entry["name"]))
        truncated = truncated or len(entries) > 512
        return {"path": str(folder), "parent": str(folder.parent) if folder.parent != folder else None,
                "home": str(Path.home()), "root": folder.anchor, "entries": entries[:512],
                "truncated": truncated}
    except FileNotFoundError as exc:
        raise AppError(404, "That folder no longer exists. Check the path and try again.") from exc
    except PermissionError as exc:
        raise AppError(403, "SYNAPSE does not have permission to browse that folder.") from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise AppError(400, f"Cannot browse this folder: {exc}") from exc


def readable_gguf(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise AppError(400, f"Enter the path to a local GGUF {label.lower()}.")
    try:
        path = Path(value).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != ".gguf":
            raise AppError(400, f"{label} must be an existing, readable .gguf file.")
        with path.open("rb") as source:
            if source.read(4) != b"GGUF":
                raise AppError(400, f"{label} does not have a GGUF header.")
        return path
    except (OSError, ValueError) as exc:
        raise AppError(400, f"Cannot read {label.lower()}: {exc}") from exc


def validate_hybrid_plan(path: Path, layout: dict | None = None) -> int:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Hybrid plan exceeds 1 MiB.")
    selected = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 2:
            raise ValueError("Hybrid plan rows must contain layer and expert integers.")
        layer, expert = map(int, fields)
        layers = layout["block_count"] if layout else 32768
        experts = layout["expert_count"] if layout else 1048576
        if not 0 <= layer < layers or not 0 <= expert < experts or (layer, expert) in selected:
            raise ValueError("Hybrid plan contains an invalid or duplicate expert.")
        selected.add((layer, expert))
    if not selected:
        raise ValueError("A trained plan must contain experts; use the auto plan for causal cold-start admission.")
    return len(selected)


def model_metadata(path: Path) -> dict:
    """Read bounded GGUF metadata without mapping weights or allocating vocabulary arrays."""
    limit = min(path.stat().st_size, 64 * 1024 * 1024)
    result = {}
    scalar = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i",
              6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
    wanted = {"general.architecture", "general.file_type", "general.name", "split.count"}
    dimensions = {"block_count", "embedding_length", "feed_forward_length",
                  "expert_feed_forward_length", "expert_count", "expert_used_count", "context_length"}
    with path.open("rb") as source:
        def read(count):
            if count < 0 or source.tell() + count > limit:
                raise ValueError("GGUF metadata exceeds the file or 64 MiB read limit.")
            data = source.read(count)
            if len(data) != count:
                raise ValueError("GGUF metadata is truncated.")
            return data

        def number(fmt):
            return struct.unpack("<" + fmt, read(struct.calcsize("<" + fmt)))[0]

        def skip(count):
            if count < 0 or source.tell() + count > limit:
                raise ValueError("GGUF metadata exceeds the file or 64 MiB read limit.")
            source.seek(count, 1)

        def string(keep):
            count = number("Q")
            if keep:
                if count > 65536:
                    raise ValueError("GGUF metadata string exceeds 64 KiB.")
                return read(count).decode("utf-8")
            skip(count)
            return None

        def value(kind, keep, depth=0):
            if kind in scalar:
                item = number(scalar[kind])
                return item if keep else None
            if kind == 8:
                return string(keep)
            if kind == 9 and depth < 2:
                element, count = number("I"), number("Q")
                if count > 1000000:
                    raise ValueError("GGUF metadata array exceeds one million entries.")
                if keep:
                    if element not in (4, 5, 10, 11) or count > 32768:
                        raise ValueError("Model dimension arrays must be bounded integer arrays.")
                    return [number(scalar[element]) for _ in range(count)]
                if element in scalar:
                    skip(count * struct.calcsize("<" + scalar[element]))
                else:
                    for _ in range(count):
                        value(element, False, depth + 1)
                return None
            raise ValueError("Unsupported GGUF metadata value type.")

        if read(4) != b"GGUF" or number("I") not in (2, 3):
            raise ValueError("Expected a little-endian GGUF v2/v3 file.")
        number("Q")  # tensor count
        count = number("Q")
        if count > 100000:
            raise ValueError("GGUF metadata has too many keys.")
        seen = set()
        for _ in range(count):
            key = string(True)
            if key in seen:
                raise ValueError("Duplicate GGUF metadata key.")
            seen.add(key)
            keep = key in wanted or key.rsplit(".", 1)[-1] in dimensions
            item = value(number("I"), keep)
            if keep:
                result[key] = item
    if not isinstance(result.get("general.architecture"), str):
        raise ValueError("Select the first GGUF shard with architecture metadata.")
    return result


def moe_layout(metadata: dict) -> dict | None:
    architecture = metadata.get("general.architecture")
    if not isinstance(architecture, str):
        return None
    if metadata.get("general.file_type") is not None and type(metadata["general.file_type"]) is not int:
        return None
    prefix = architecture + "."
    layout = {name: metadata.get(prefix + name) for name in
              ("block_count", "embedding_length", "expert_count", "expert_used_count")}
    layout["expert_feed_forward_length"] = metadata.get(
        prefix + "expert_feed_forward_length", metadata.get(prefix + "feed_forward_length"))
    for name, maximum in (("block_count", 32768), ("embedding_length", 16777216), ("expert_count", 1048576)):
        if type(layout[name]) is not int or not 1 <= layout[name] <= maximum:
            return None
    if layout["expert_count"] < 2:
        return None
    for name, maximum in (("expert_used_count", layout["expert_count"]),
                          ("expert_feed_forward_length", 16777216)):
        values = layout[name] if isinstance(layout[name], list) else [layout[name]]
        if (not values or (isinstance(layout[name], list) and len(values) != layout["block_count"]) or
                any(type(value) is not int or not 1 <= value <= maximum for value in values)):
            return None
    return {"architecture": architecture, "file_type": metadata.get("general.file_type"), **layout}


def supports_hybrid(metadata: dict) -> bool:
    return moe_layout(metadata) is not None


def select_hybrid_policy(metadata: dict, model_bytes: int, *, mode: str, bound_layout: dict | None,
                         generic: bool, automatic_plan: bool, cache_mib: int) -> dict:
    if mode not in ("auto", "hybrid", "standard"):
        raise ValueError("Unknown hybrid selection policy.")
    if mode == "standard":
        return {"hybrid": False, "automatic_plan": False, "reason": "standard"}
    layout = moe_layout(metadata)
    matched = bound_layout is None or layout == bound_layout
    if layout is None or (not matched and not generic):
        return {"hybrid": False, "automatic_plan": False, "reason": "descriptor_or_plan_mismatch"}
    cold_start = automatic_plan or not matched
    if (mode == "auto" and generic and cold_start and metadata.get("split.count", 1) == 1 and
            model_bytes <= cache_mib*1024*1024):
        return {"hybrid": False, "automatic_plan": True, "reason": "native_budget"}
    return {"hybrid": True, "automatic_plan": cold_start, "reason": "hybrid"}


def read_hybrid_profile(path: Path) -> dict:
    if path.stat().st_size > 65536:
        raise ValueError("Hybrid installation profile exceeds 64 KiB.")
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "backend_commit", "executable", "plan", "cuda_plugin"}
    optional = {"model_layout", "context", "cache_mib", "transfer", "decode_pipeline", "async_ids",
                "generic_cache_mib", "generic_transfer"}
    if (not isinstance(data, dict) or not required <= set(data) or set(data) - required - optional or
            type(data["schema_version"]) is not int or data["schema_version"] not in (1, 2) or
            data["backend_commit"] != PINNED_LLAMA_COMMIT or
            type(data.get("decode_pipeline", False)) is not bool or
            type(data.get("async_ids", False)) is not bool or
            (data.get("async_ids", False) and not data.get("decode_pipeline", False)) or
            ("generic_cache_mib" in data and (type(data["generic_cache_mib"]) is not int or
                                             not 1 <= data["generic_cache_mib"] <= 65536)) or
            ("generic_transfer" in data and data["generic_transfer"] not in ("direct", "staged")) or
            any(not isinstance(data[key], str) or not Path(data[key]).is_absolute()
                for key in ("executable", "cuda_plugin")) or not isinstance(data["plan"], str) or
            (data["plan"] != "auto" and not Path(data["plan"]).is_absolute())):
        raise ValueError("Invalid pinned hybrid installation profile.")
    layout = data.get("model_layout")
    if data["schema_version"] == 1:
        # Preserve the old model-bound installation, not an engine-wide architecture allowlist.
        layout = {"architecture": "gpt-oss", "file_type": 38, "block_count": 36,
                  "embedding_length": 2880, "expert_feed_forward_length": 2880,
                  "expert_count": 128, "expert_used_count": 4}
    elif data["plan"] != "auto" and layout is None:
        raise ValueError("A version-2 trained plan requires model_layout; use auto for an untrained causal plan.")
    if layout is not None:
        if not isinstance(layout, dict) or not isinstance(layout.get("architecture"), str):
            raise ValueError("Invalid trained-plan model layout.")
        normalized = moe_layout({"general.architecture": layout["architecture"],
                                 "general.file_type": layout.get("file_type"),
                                 **{layout["architecture"] + "." + key: value for key, value in layout.items()
                                    if key not in ("architecture", "file_type")}})
        if normalized != layout:
            raise ValueError("Invalid trained-plan model layout.")
    return {"hybrid_executable": data["executable"],
            "hybrid_plan": "auto" if data["plan"] == "auto" else Path(data["plan"]),
            "hybrid_cuda_plugin": Path(data["cuda_plugin"]), "hybrid_layout": layout,
            "hybrid_generic": data["schema_version"] == 2,
            "hybrid_context": data.get("context", 16384), "hybrid_cache_mib": data.get("cache_mib", 10240),
            "hybrid_transfer": data.get("transfer", "direct" if data["schema_version"] == 1 else "staged"),
            "hybrid_decode_pipeline": data.get("decode_pipeline", False),
            "hybrid_async_ids": data.get("async_ids", False),
            "hybrid_generic_cache_mib": data.get("generic_cache_mib"),
            "hybrid_generic_transfer": data.get("generic_transfer")}


class Runtime:
    def __init__(self, executable: str, load_timeout: float = 600,
                 backend_kind: str = "llama.cpp", enable_speculation: bool = False,
                 hybrid_plan: Path | str | None = None, hybrid_cuda_plugin: Path | None = None,
                 hybrid_executable: str | None = None, execution_mode: str | None = None,
                 hybrid_layout: dict | None = None, hybrid_generic: bool = False,
                 hybrid_context: int = 16384, hybrid_cache_mib: int = 10240, hybrid_transfer: str = "direct",
                 hybrid_decode_pipeline: bool = False, hybrid_async_ids: bool = False,
                 hybrid_generic_cache_mib: int | None = None, hybrid_generic_transfer: str | None = None):
        if backend_kind not in ("llama.cpp", "ik_llama.cpp"):
            raise ValueError("Unsupported backend kind.")
        if (hybrid_plan is None) != (hybrid_cuda_plugin is None):
            raise ValueError("Hybrid execution requires both a plan and the matching CUDA plugin.")
        self.default_execution_mode = execution_mode or ("hybrid" if hybrid_plan is not None else "standard")
        if self.default_execution_mode not in ("auto", "standard", "hybrid"):
            raise ValueError("Execution mode must be auto, standard, or hybrid.")
        if self.default_execution_mode == "hybrid" and hybrid_plan is None:
            raise ValueError("Hybrid mode requires an installed or explicit plan/plugin profile.")
        self.execution_mode = self.default_execution_mode
        self.hybrid_active = hybrid_plan is not None and self.execution_mode == "hybrid"
        self.selection_reason = ("Hybrid direct DMA explicitly selected." if self.hybrid_active else
                                 "Automatic mode selects a profile from GGUF metadata when a model is loaded."
                                 if self.execution_mode == "auto" and hybrid_plan is not None else
                                 "Standard execution; no compatible hybrid installation selected.")
        if (type(hybrid_context) is not int or not 512 <= hybrid_context <= 65536 or
                type(hybrid_cache_mib) is not int or not 1 <= hybrid_cache_mib <= 65536 or
                hybrid_transfer not in ("direct", "staged") or type(hybrid_generic) is not bool or
                (hybrid_generic_cache_mib is not None and (type(hybrid_generic_cache_mib) is not int or
                                                         not 1 <= hybrid_generic_cache_mib <= 65536)) or
                (hybrid_generic_transfer is not None and hybrid_generic_transfer not in ("direct", "staged")) or
                type(hybrid_decode_pipeline) is not bool or type(hybrid_async_ids) is not bool or
                (hybrid_async_ids and not hybrid_decode_pipeline)):
            raise ValueError("Invalid generic hybrid context, residency budget, or transfer policy.")
        self.hybrid_plan = "auto" if hybrid_plan == "auto" else Path(hybrid_plan).resolve(strict=True) if hybrid_plan is not None else None
        self.hybrid_layout = hybrid_layout
        self.hybrid_generic = hybrid_generic
        self.hybrid_context = hybrid_context
        self.hybrid_cache_mib = hybrid_cache_mib
        self.hybrid_transfer = hybrid_transfer
        self.hybrid_generic_cache_mib = hybrid_cache_mib if hybrid_generic_cache_mib is None else hybrid_generic_cache_mib
        self.hybrid_generic_transfer = (hybrid_transfer if hybrid_plan == "auto" else "staged") if hybrid_generic_transfer is None else hybrid_generic_transfer
        self.hybrid_decode_pipeline = hybrid_decode_pipeline
        self.hybrid_async_ids = hybrid_async_ids
        self.active_hybrid_transfer = self.hybrid_generic_transfer if hybrid_plan == "auto" else hybrid_transfer
        self.required_hybrid_markers = {"hybrid", "context", "coverage", "direct", "registered"} if self.active_hybrid_transfer == "direct" else {"hybrid", "context", "coverage", "staged"}
        self.hybrid_cuda_plugin = hybrid_cuda_plugin.resolve(strict=True) if hybrid_cuda_plugin is not None else None
        self.hybrid_experts = 0
        self.hybrid_plan_sha256 = None
        if self.hybrid_plan is not None:
            if backend_kind != "llama.cpp" or enable_speculation:
                raise ValueError("Hybrid execution requires the patched official backend without speculation.")
            if self.hybrid_plan != "auto":
                self.hybrid_experts = validate_hybrid_plan(self.hybrid_plan, self.hybrid_layout)
                self.hybrid_plan_sha256 = hashlib.sha256(self.hybrid_plan.read_bytes()).hexdigest()
            if not self.hybrid_cuda_plugin.is_file():
                raise ValueError("Hybrid CUDA plugin must be a matching shared-library file.")
            with self.hybrid_cuda_plugin.open("rb") as plugin:
                if not plugin.read(1):
                    raise ValueError("Hybrid CUDA plugin is empty.")
        self.hybrid_markers: set[str] = set()
        self.backend_kind = backend_kind
        self.enable_speculation = enable_speculation
        self.executable = backend_executable(executable)
        self.requested_executable = executable
        self.standard_executable = self.executable
        self.hybrid_executable = backend_executable(hybrid_executable or executable) if hybrid_plan is not None else None
        if hybrid_plan is not None and not self.hybrid_executable:
            raise ValueError("The configured patched hybrid executable was not found.")
        if self.hybrid_active:
            self.executable = self.hybrid_executable
        self.load_timeout = load_timeout
        self.lock = threading.RLock()
        self.chat_lock = threading.Lock()
        self.process: subprocess.Popen[str] | None = None
        self.state = "stopped"
        self.model: str | None = None
        self.error: str | None = None
        self.readiness_error: str | None = None
        self.logs: deque[str] = deque(maxlen=80)
        self.port = 0
        self.key = ""
        self.context = 4096
        self.placement = "auto"
        self.cpu_threads = default_cpu_threads()
        self.batch_threads = self.cpu_threads
        self.load_mode = "auto"
        self.expert_cache_mib = 0
        self.fit_target_mib = 1024
        self.host_op_offload = True
        self.cpu_poll = 50
        self.op_offload_min_batch = 32
        self.draft_model: str | None = None
        self.draft_tokens = 9
        self.resources: dict | None = None
        self.resource_error: str | None = None
        self.cpu_sample: tuple[float, float] | None = None
        self.closed = False
        if self.hybrid_active:
            self.context = self.hybrid_context
            self.cpu_threads = min(8, len(available_cpus()))
            self.batch_threads = min(16, len(available_cpus()))
            self.expert_cache_mib = self.hybrid_generic_cache_mib if self.hybrid_plan == "auto" else self.hybrid_cache_mib
            self.host_op_offload = False
        self.requested_context = self.context
        self.context_warning: str | None = None
        self.generation_serial = 0
        self.generation = {}
        self.slot_sample: tuple[int, float, float] | None = None
        self.monitor = HardwareMonitor(self._monitor_backend)

    def begin_generation(self) -> int:
        with self.lock:
            self.generation_serial += 1
            self.generation = {"active": True, "tokens_per_second": None, "output_tokens": None,
                               "prompt_tokens": None, "error": None}
            self.slot_sample = None
            return self.generation_serial

    def observe_generation(self, serial: int, data: object) -> None:
        if not isinstance(data, dict):
            return
        with self.lock:
            if serial != self.generation_serial:
                return
            timings, usage = data.get("timings", {}), data.get("usage", {})
            if isinstance(timings, dict):
                for source, target in (("predicted_per_second", "tokens_per_second"),
                                       ("predicted_n", "output_tokens"), ("prompt_n", "prompt_tokens")):
                    if source in timings:
                        self.generation[target] = number(timings[source])
                        if self.generation[target] is None:
                            self.generation["error"] = f"Backend timing {source} is invalid"
            if isinstance(usage, dict):
                for source, target in (("completion_tokens", "output_tokens"), ("prompt_tokens", "prompt_tokens")):
                    if source in usage:
                        self.generation[target] = number(usage[source])
                        if self.generation[target] is None:
                            self.generation["error"] = f"Backend usage {source} is invalid"

    def end_generation(self, serial: int) -> None:
        with self.lock:
            if serial == self.generation_serial:
                self.generation["active"] = False
                self.generation["final_pending"] = self.generation.get("tokens_per_second") is not None

    def _monitor_backend(self) -> dict:
        with self.lock:
            process = self.process
            running = process is not None and process.poll() is None
            resources = dict(self.resources or {}) if running else {}
            state, context, port, key = self.state, self.context, self.port, self.key
            generation = dict(self.generation)
            if generation.get("final_pending"):
                self.generation["final_pending"] = False
            serial = self.generation_serial
            resource_error = self.resource_error
        result = {"state": state, "generation_active": generation.get("active", False),
                  "tokens_per_second": generation.get("tokens_per_second")
                  if generation.get("active") or generation.get("final_pending") else 0,
                  "last_tokens_per_second": generation.get("tokens_per_second"),
                  "output_tokens": generation.get("output_tokens"), "context_used": None,
                  "context_total": context if running else None, "context_source": None,
                  "speed_source": "backend_final_timings" if generation.get("final_pending") else
                  "backend_timings" if generation.get("tokens_per_second") is not None else None,
                  "rss_bytes": resources.get("rss_bytes"), "cpu_logical_cores": resources.get("cpu_logical_cores"),
                  "pid": process.pid if running else None, "read_bytes": resources.get("read_bytes"),
                  "errors": {}}
        if resource_error:
            result["errors"]["process"] = resource_error
        if generation.get("error"):
            result["errors"]["generation"] = generation["error"]
        if state == "ready" and running:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
            try:
                connection.request("GET", "/slots", headers={"Authorization": f"Bearer {key}"})
                response = connection.getresponse()
                body = response.read(1024 * 1024 + 1)
                if response.status != 200 or len(body) > 1024 * 1024:
                    raise ValueError(f"Slot counters unavailable (HTTP {response.status})")
                slots = json.loads(body)
                if not isinstance(slots, list) or not slots or not isinstance(slots[0], dict):
                    raise ValueError("Backend did not provide slot counters")
                slot = slots[0]
                result["context_used"] = number(slot.get("n_prompt_tokens"))
                if result["context_used"] is not None:
                    result["context_source"] = "backend_slot"
                decoded = slot.get("next_token", [])
                count = number(decoded[0].get("n_decoded")) if decoded and isinstance(decoded[0], dict) else None
                now = time.monotonic()
                with self.lock:
                    if count is not None and generation.get("active") and serial == self.generation_serial:
                        if result["tokens_per_second"] is None and self.slot_sample and self.slot_sample[0] == serial:
                            result["tokens_per_second"] = rate(count, self.slot_sample[2], now - self.slot_sample[1])
                            result["speed_source"] = "backend_slot_counter"
                        self.slot_sample = serial, now, count
            except (OSError, http.client.HTTPException, ValueError, TypeError) as exc:
                result["errors"]["context"] = str(exc)
            finally:
                connection.close()
        if result["context_used"] is None and running:
            prompt, output = generation.get("prompt_tokens"), generation.get("output_tokens")
            if prompt is not None:
                result["context_used"] = prompt + (output or 0)
                result["context_source"] = "reported_usage"
        with self.lock:
            if process is not self.process:
                return {"state": self.state, "generation_active": False, "errors": {"context": "Model changed during sample"}}
        return result

    def status(self) -> dict:
        with self.lock:
            return {
                "api_version": 1,
                "app_name": "SYNAPSE",
                "app_version": __version__,
                "state": self.state,
                "model": self.model,
                "error": self.error,
                "readiness_error": self.readiness_error,
                "logs": list(self.logs),
                "backend_available": self.executable is not None or self.hybrid_executable is not None,
                "backend": self.executable or self.requested_executable,
                "backend_kind": self.backend_kind,
                "speculation_enabled": self.enable_speculation,
                "execution_mode": self.execution_mode,
                "hybrid_available": self.hybrid_plan is not None,
                "hybrid_plan_sha256": self.hybrid_plan_sha256,
                "hybrid_model_layout": self.hybrid_layout,
                "hybrid_generic": self.hybrid_generic,
                "hybrid_initialization": "auto" if self.hybrid_plan == "auto" else "trained",
                "selection_reason": self.selection_reason,
                "execution_profile": f"experimental-hybrid-{self.active_hybrid_transfer}" if self.hybrid_active else "standard",
                "hybrid_transfer": self.active_hybrid_transfer if self.hybrid_active else None,
                "hybrid_decode_pipeline": self.hybrid_active and self.hybrid_decode_pipeline,
                "hybrid_async_ids": self.hybrid_active and self.hybrid_async_ids,
                "hybrid_async_ids_verified": self.hybrid_active and "async-ids" in self.hybrid_markers,
                "hybrid_overlap_verified": self.hybrid_active and "overlap" in self.hybrid_markers,
                "hybrid_gate_up_verified": self.hybrid_active and "gate-up" in self.hybrid_markers,
                "hybrid_context": self.context if self.hybrid_active else self.hybrid_context,
                "hybrid_context_budget": self.hybrid_context,
                "hybrid_cache_mib": self.hybrid_cache_mib,
                "hybrid_generic_cache_mib": self.hybrid_generic_cache_mib,
                "hybrid_generic_transfer": self.hybrid_generic_transfer,
                "execution_warning": HYBRID_WARNING if self.hybrid_active else None,
                "hybrid_verified": self.hybrid_active and self.required_hybrid_markers <= self.hybrid_markers,
                "fit_enabled": not self.hybrid_active and self.placement == "auto",
                "context": self.context,
                "requested_context": self.requested_context,
                "context_warning": self.context_warning,
                "placement": self.placement,
                "cpu_threads": self.cpu_threads,
                "batch_threads": self.batch_threads,
                "load_mode": self.load_mode,
                "expert_cache_mib": self.expert_cache_mib,
                "fit_target_mib": self.fit_target_mib,
                "host_op_offload": self.host_op_offload,
                "cpu_poll": self.cpu_poll,
                "op_offload_min_batch": self.op_offload_min_batch,
                "draft_model": self.draft_model,
                "draft_tokens": self.draft_tokens,
                "logical_cpus": len(available_cpus()),
                "resources": self.resources,
                "resource_error": self.resource_error,
                "chat_busy": self.chat_lock.locked(),
            }

    def load(self, data: dict) -> None:
        model_value = data.get("model")
        model = readable_gguf(model_value, "Model")
        mode = data.get("execution_mode", self.default_execution_mode)
        if mode not in ("auto", "standard", "hybrid"):
            raise AppError(400, "Execution mode must be auto, standard, or hybrid.")
        hybrid = mode == "hybrid"
        selected_plan = self.hybrid_plan
        transfer = self.hybrid_transfer
        selected_cache_mib = self.hybrid_cache_mib
        selected_experts = 0
        selected_plan_sha256 = None
        context_limit = None
        reason = "Standard execution explicitly selected."
        if mode != "standard" and self.hybrid_plan is not None:
            try:
                metadata = model_metadata(model)
            except (OSError, ValueError) as exc:
                raise AppError(400, f"Cannot select an execution profile: {exc}") from exc
            layout = moe_layout(metadata)
            context_limit = metadata.get(metadata["general.architecture"] + ".context_length")
            if context_limit is not None and (type(context_limit) is not int or context_limit < 512):
                raise AppError(400, "The model context limit is invalid or below the application's 512-token minimum.")
            policy = select_hybrid_policy(metadata, model.stat().st_size, mode=mode,
                                          bound_layout=self.hybrid_layout, generic=self.hybrid_generic,
                                          automatic_plan=self.hybrid_plan == "auto", cache_mib=self.hybrid_cache_mib)
            hybrid = policy["hybrid"]
            if hybrid and policy["automatic_plan"]:
                selected_plan = "auto"
                transfer = self.hybrid_generic_transfer
                selected_cache_mib = self.hybrid_generic_cache_mib
            if policy["reason"] == "native_budget":
                reason = ("MoE weight file fits the configured residency budget; native fitting is preferred "
                          "to avoid hybrid scheduling overhead. This is not a fit or speed guarantee.")
            elif hybrid:
                reason = (f"Tensor-derived {metadata['general.architecture']} MoE descriptor selected; "
                          f"{'bound training plan' if selected_plan != 'auto' else 'causal cold-start plan'}, "
                          f"{transfer} transfers. Runtime operation/coverage validation is required.")
            else:
                reason = (f"{metadata['general.architecture']} is not supported by this installed residency plan "
                          "or has no complete routed-MoE descriptor; standard execution selected, not a hybrid speedup.")
        if mode == "hybrid" and (not hybrid or self.hybrid_plan is None):
            raise AppError(400, "Hybrid mode requires an installed plan policy and a compatible routed-MoE descriptor.")
        if mode == "auto" and self.hybrid_plan is None:
            reason = "No hybrid installation profile found; standard execution selected."
        selected_executable = (self.hybrid_executable if hybrid else
                               self.standard_executable if self.hybrid_plan is not None else self.executable)
        planned_context = min(self.hybrid_context if hybrid else 4096, context_limit) if context_limit else (
            self.hybrid_context if hybrid else 4096)
        context = data.get("context", planned_context)
        placement = data.get("placement", "auto")
        cpu_threads = data.get("cpu_threads", min(8, len(available_cpus())) if hybrid else default_cpu_threads())
        batch_threads = data.get("batch_threads", min(16, len(available_cpus())) if hybrid else cpu_threads)
        load_mode = data.get("load_mode", "auto")
        expert_cache_mib = data.get("expert_cache_mib", selected_cache_mib if hybrid else 0)
        fit_target_mib = data.get("fit_target_mib", 1024)
        host_op_offload = data.get("host_op_offload", not hybrid)
        cpu_poll = data.get("cpu_poll", 50)
        op_offload_min_batch = data.get("op_offload_min_batch", 32)
        draft_value = data.get("draft_model")
        draft_tokens = data.get("draft_tokens", 9)
        if type(context) is not int or not 512 <= context <= 65536:
            raise AppError(400, "Context must be an integer between 512 and 65536.")
        if placement not in ("auto", "cpu"):
            raise AppError(400, "Placement must be 'auto' or 'cpu'.")
        for name, value in (("CPU threads", cpu_threads), ("Batch threads", batch_threads)):
            if type(value) is not int or not 1 <= value <= len(available_cpus()):
                raise AppError(400, f"{name} must be an integer between 1 and {len(available_cpus())}.")
        if load_mode not in ("auto", "none"):
            raise AppError(400, "Load mode must be 'auto' or 'none'.")
        if type(expert_cache_mib) is not int or not 0 <= expert_cache_mib <= 65536:
            raise AppError(400, "Expert cache must be an integer between 0 and 65536 MiB.")
        if hybrid and mode == "hybrid" and selected_plan == "auto":
            if expert_cache_mib == 0:
                raise AppError(400, "A causal hybrid cache must have a positive residency budget.")
            if expert_cache_mib != selected_cache_mib:
                reason += f" Explicit causal residency budget: {expert_cache_mib} MiB; fit is still model-dependent."
            selected_cache_mib = expert_cache_mib
        if expert_cache_mib and placement != "auto":
            raise AppError(400, "The experimental GPU expert cache requires automatic placement.")
        if self.backend_kind == "ik_llama.cpp" and (placement != "auto" or expert_cache_mib):
            raise AppError(400, "The experimental ik_llama.cpp adapter currently supports "
                           "automatic placement without an explicit expert cache.")
        if type(fit_target_mib) is not int or not 128 <= fit_target_mib <= 65536:
            raise AppError(400, "VRAM reserve must be an integer between 128 and 65536 MiB.")
        if type(host_op_offload) is not bool:
            raise AppError(400, "Host operation offload must be a boolean.")
        if type(cpu_poll) is not int or not 0 <= cpu_poll <= 100:
            raise AppError(400, "CPU polling must be an integer between 0 and 100.")
        if type(op_offload_min_batch) is not int or not 1 <= op_offload_min_batch <= 8192:
            raise AppError(400, "Operation offload minimum batch must be an integer between 1 and 8192.")
        if hybrid:
            if (placement != "auto" or context != planned_context or load_mode != "auto" or
                    expert_cache_mib != selected_cache_mib or host_op_offload or draft_value not in (None, "") or
                    fit_target_mib != 1024 or op_offload_min_batch != 32):
                raise AppError(400, "The experimental hybrid profile requires automatic CPU/GPU execution, "
                               f"{planned_context} context, default loading, {selected_cache_mib} MiB residency, host-op offload off, "
                               "1024 MiB reserve placeholder (fitting is off), batch threshold 32, and no draft.")
            try:
                selected_experts = validate_hybrid_plan(selected_plan, layout) if selected_plan != "auto" else 0
                selected_plan_sha256 = hashlib.sha256(selected_plan.read_bytes()).hexdigest() if selected_plan != "auto" else None
            except (OSError, ValueError) as exc:
                raise AppError(400, f"Cannot use hybrid plan: {exc}") from exc
        if self.backend_kind != "llama.cpp" and (
            not host_op_offload or cpu_poll != 50 or op_offload_min_batch != 32
        ):
            raise AppError(400, "Explicit host-operation and polling tuning requires the official llama.cpp backend.")
        if type(draft_tokens) is not int or not 1 <= draft_tokens <= 32:
            raise AppError(400, "Draft tokens must be an integer between 1 and 32.")
        draft = None
        if draft_value not in (None, ""):
            if not self.enable_speculation:
                raise AppError(400, "DFlash is disabled. It requires --experimental-speculation "
                               "and a compatible backend and target-trained draft.")
            if placement != "auto" or expert_cache_mib:
                raise AppError(400, "DFlash requires automatic placement without an explicit expert cache.")
            draft = readable_gguf(draft_value, "Draft model")
            if draft == model:
                raise AppError(400, "The draft must be a separate, target-trained DFlash model.")
        with self.lock:
            if self.closed:
                raise AppError(503, "The application is shutting down.")
            if self.state == "stopping" or (self.process is not None and self.process.poll() is None):
                raise AppError(409, "Unload the current model before loading another.")
            if not selected_executable:
                raise AppError(503, "llama-server was not found. Install llama.cpp and restart "
                               "with --llama-server /path/to/llama-server.")
            if self.chat_lock.locked():
                raise AppError(409, "Wait for the previous chat request to finish.")
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                self.port = reservation.getsockname()[1]
            self.key = secrets.token_hex(32)
            command = [
                selected_executable, "--model", str(model), "--alias", "local-model",
                "--host", "127.0.0.1", "--port", str(self.port),
                "--api-key", self.key, "--ctx-size", str(context), "--parallel", "1",
                "--threads", str(cpu_threads), "--threads-batch", str(batch_threads),
            ]
            if selected_executable.lower().endswith(".py"):
                command.insert(0, sys.executable)
            if self.backend_kind == "llama.cpp":
                command += ["--slots"]
            if hybrid:
                command += ["--n-gpu-layers", "all", "--cpu-moe", "--fit", "off",
                            "--no-repack", "--no-host", "--moe-cache-mib", str(expert_cache_mib)]
            elif self.backend_kind == "ik_llama.cpp":
                command += ["--n-gpu-layers", "999", "--fit", "--fit-margin", str(fit_target_mib)]
                if load_mode == "none":
                    command += ["--no-mmap"]
            elif placement == "auto":
                command += ["--n-gpu-layers", "all" if expert_cache_mib else "auto",
                            "--fit", "on", "--fit-target", str(fit_target_mib)]
                if expert_cache_mib:
                    command += ["--cpu-moe", "--moe-cache-mib", str(expert_cache_mib)]
            else:
                command += ["--n-gpu-layers", "0", "--device", "none"]
            if load_mode != "auto" and self.backend_kind == "llama.cpp":
                command += ["--load-mode", load_mode]
            if self.backend_kind == "llama.cpp":
                command += ["--poll", str(cpu_poll)]
                if not host_op_offload:
                    command += ["--no-op-offload"]
            if draft is not None:
                command += ["--model-draft", str(draft), "--flash-attn", "on"]
                if self.backend_kind == "llama.cpp":
                    command += ["--spec-type", "draft-dflash", "--spec-draft-n-max", str(draft_tokens),
                                "--gpu-layers-draft", "all", "--jinja"]
                else:
                    command += ["--spec-type", f"dflash:n_max={draft_tokens},p_min=0.0",
                                "--gpu-layers-draft", "999"]
            # Do not inherit placement overrides or credentials from a developer's shell.
            environment = {
                key: value for key, value in os.environ.items()
                if not key.startswith(("LLAMA_ARG_", "GGML_CUDA_ENABLE_UNIFIED_MEMORY", "VRAMBRIDGE_HYBRID_"))
                and key not in ("GGML_OP_OFFLOAD_MIN_BATCH", "GGML_CUDA_REGISTER_HOST")
            }
            if hybrid:
                environment.update(
                    GGML_BACKEND_PATH=str(self.hybrid_cuda_plugin),
                    VRAMBRIDGE_HYBRID_PLAN=str(selected_plan),
                    VRAMBRIDGE_HYBRID_ADAPT="1", VRAMBRIDGE_HYBRID_ASYNC="1",
                )
                if transfer == "direct":
                    environment.update(VRAMBRIDGE_HYBRID_DIRECT="1", GGML_CUDA_REGISTER_HOST="1")
                if self.hybrid_decode_pipeline:
                    environment.update(
                        VRAMBRIDGE_HYBRID_STAGE_INPUT="1", VRAMBRIDGE_HYBRID_OVERLAP="1",
                        VRAMBRIDGE_HYBRID_BOUNDARY="gpu", VRAMBRIDGE_HYBRID_FUSE_GATE_UP="1")
                if self.hybrid_async_ids:
                    environment["VRAMBRIDGE_HYBRID_ASYNC_IDS"] = "1"
            if self.backend_kind == "llama.cpp":
                environment["GGML_OP_OFFLOAD_MIN_BATCH"] = str(op_offload_min_batch)
            self.logs.clear()
            self.hybrid_markers.clear()
            self.executable = selected_executable
            self.hybrid_active = hybrid
            self.hybrid_experts = selected_experts
            self.hybrid_plan_sha256 = selected_plan_sha256
            self.active_hybrid_transfer = transfer
            self.required_hybrid_markers = ({"hybrid", "context", "coverage", "direct", "registered"}
                                            if transfer == "direct" else {"hybrid", "context", "coverage", "staged"})
            if hybrid and self.hybrid_decode_pipeline:
                self.required_hybrid_markers.add("pipeline")
            if hybrid and self.hybrid_async_ids:
                self.required_hybrid_markers.add("async-ids")
            self.execution_mode = mode
            self.selection_reason = reason
            self.error = None
            self.readiness_error = None
            self.model = str(model)
            self.context = context
            self.requested_context = context
            self.context_warning = None
            self.placement = placement
            self.cpu_threads = cpu_threads
            self.batch_threads = batch_threads
            self.load_mode = load_mode
            self.expert_cache_mib = expert_cache_mib
            self.fit_target_mib = fit_target_mib
            self.host_op_offload = host_op_offload
            self.cpu_poll = cpu_poll
            self.op_offload_min_batch = op_offload_min_batch
            self.draft_model = str(draft) if draft is not None else None
            self.draft_tokens = draft_tokens
            self.resources = None
            self.resource_error = None
            self.cpu_sample = None
            self.generation_serial += 1
            self.generation = {}
            self.slot_sample = None
            try:
                process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                    env=environment,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                )
            except OSError as exc:
                self.state = "error"
                self.error = f"Could not start llama-server: {exc}"
                LOG.error("%s", self.error)
                raise AppError(503, self.error) from exc
            self.process = process
            self.state = "loading"
            threading.Thread(target=self._read_logs, args=(process, self.key), daemon=True).start()
            threading.Thread(target=self._watch, args=(process,), daemon=True).start()

    def _read_logs(self, process: subprocess.Popen[str], key: str) -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                backend_failed = False
                with self.lock:
                    if self.process is process:
                        self.logs.append(line.rstrip().replace(key, "[redacted]")[:2000])
                        if self.hybrid_active:
                            if f"EXPERIMENTAL HYBRID enabled: {self.hybrid_experts} selected experts; adaptive admissions" in line:
                                self.hybrid_markers.add("hybrid")
                            if "direct asynchronous admissions; immutable registered sources, no staging copies" in line:
                                self.hybrid_markers.add("direct")
                            if "immutable source bytes" in line and "cap 64 GiB, headroom 24 GiB" in line:
                                self.hybrid_markers.add("registered")
                            if "adaptive admissions enabled;" in line and "bounded staging, asynchronous uploads" in line:
                                self.hybrid_markers.add("staged")
                            coverage = re.search(r"tensor-derived hybrid coverage=(\d+)/(\d+) routed layers", line)
                            if coverage and int(coverage[1]) > 0 and coverage[1] == coverage[2]:
                                self.hybrid_markers.add("coverage")
                            if self.hybrid_decode_pipeline:
                                if "VRAMBridge decode pipeline configured: staged input, guarded overlap, GPU boundary, gate/up fusion" in line:
                                    self.hybrid_markers.add("pipeline")
                                if "VRAMBridge guarded expert overlap active" in line:
                                    self.hybrid_markers.add("overlap")
                                if "VRAMBridge resident gate/up projection fusion active" in line:
                                    self.hybrid_markers.add("gate-up")
                            if (self.hybrid_async_ids and "asynchronous GPU ID handoff:" in line and
                                    "per-layer pinned staging; protected reuse" in line):
                                self.hybrid_markers.add("async-ids")
                        reported_context = re.search(r"n_ctx_slot\s*=\s*'?(\d+)", line)
                        if reported_context:
                            actual = int(reported_context[1])
                            if actual != self.requested_context and self.hybrid_active:
                                self.state = "error"
                                self.error = (f"Backend context {actual} does not match planned hybrid context "
                                              f"{self.requested_context}. Check the model limit and installation policy.")
                                LOG.error("%s", self.error)
                                backend_failed = True
                            elif actual > 0:
                                self.context = actual
                                self.context_warning = None
                                if self.hybrid_active:
                                    self.hybrid_markers.add("context")
                                elif actual != self.requested_context:
                                    self.context_warning = (f"Backend adjusted the requested {self.requested_context} context "
                                                            f"to {actual}. The displayed context is the actual slot size.")
                                    LOG.warning("%s", self.context_warning)
                        if self.placement == "auto" and "ggml_cuda_init: failed to initialize CUDA:" in line:
                            self.state = "error"
                            self.error = ("CUDA initialization failed. Automatic GPU placement was stopped "
                                          "instead of silently running CPU-only. Recover the GPU driver "
                                          "or explicitly select CPU-only mode. See backend output.")
                            LOG.error("%s", self.error)
                            backend_failed = True
                if backend_failed:
                    self._terminate(process)
                    return
        finally:
            process.stdout.close()

    def _watch(self, process: subprocess.Popen[str]) -> None:
        deadline = time.monotonic() + self.load_timeout
        while True:
            with self.lock:
                if self.process is not process or self.state in ("stopping", "error"):
                    return
                code = process.poll()
                if code is not None:
                    self.state = "error"
                    self.error = f"llama-server exited with code {code}. See backend output below."
                    LOG.error("%s", self.error)
                    return
                loading = self.state == "loading"
                port, key = self.port, self.key
            self._sample_resources(process)
            if loading:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                try:
                    connection.request("GET", "/v1/models", headers={"Authorization": f"Bearer {key}"})
                    response = connection.getresponse()
                    if response.status == 200:
                        with self.lock:
                            self.readiness_error = None
                            if (self.process is process and self.state == "loading" and
                                    (not self.hybrid_active or
                                     self.required_hybrid_markers <= self.hybrid_markers)):
                                self.state = "ready"
                    else:
                        with self.lock:
                            if self.process is process:
                                self.readiness_error = f"Backend readiness returned HTTP {response.status}"
                except (OSError, http.client.HTTPException) as exc:
                    with self.lock:
                        if self.process is process:
                            self.readiness_error = f"Backend readiness is unavailable: {exc}"
                finally:
                    connection.close()
                with self.lock:
                    if (self.process is process and self.state == "loading"
                            and time.monotonic() >= deadline):
                        self._terminate(process)
                        self.state = "error"
                        missing = ", ".join(sorted(self.required_hybrid_markers - self.hybrid_markers))
                        self.error = ("Experimental hybrid readiness timed out: selected transfers, full routed-layer coverage, "
                                      "adaptive residency, requested pipeline settings and actual context must all be confirmed. "
                                      f"Unconfirmed: {missing or 'backend readiness response'}. "
                                      "Check the patched backend, plan and matching CUDA plugin."
                                      if self.hybrid_active else
                                      "Model loading timed out. See backend output; try a smaller model or CPU mode. "
                                      + (self.readiness_error or ""))
                        LOG.error("%s", self.error)
                        return
            time.sleep(0.2)

    def _sample_resources(self, process: subprocess.Popen[str]) -> None:
        try:
            probe = system_probe()
            resources = probe.process(process.pid)
            cpu_seconds = resources.pop("cpu_seconds")
            _, available = probe.memory()
            now = time.monotonic()
            with self.lock:
                if self.process is not process:
                    return
                cores = None
                if self.cpu_sample is not None:
                    previous_time, previous_cpu = self.cpu_sample
                    if now > previous_time:
                        cores = max(0.0, (cpu_seconds - previous_cpu) / (now - previous_time))
                self.cpu_sample = now, cpu_seconds
                self.resources = {**resources, "cpu_logical_cores": cores,
                                  "system_available_ram_bytes": available}
                self.resource_error = None
        except FileNotFoundError:
            # The exit monitor handles a process that ended during sampling.
            return
        except (OSError, ValueError, IndexError, KeyError, StopIteration) as exc:
            message = f"Process telemetry unavailable: {exc}"
            with self.lock:
                if self.process is process:
                    if self.resource_error != message:
                        LOG.warning("%s", message)
                    self.resource_error = message
                    self.resources = None

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def stop(self, closing: bool = False) -> None:
        with self.lock:
            self.closed = self.closed or closing
            self.state = "stopping"
            process = self.process
        if process is not None:
            self._terminate(process)
        with self.lock:
            if self.process is process:
                self.process = None
                self.state = "stopped"
                self.error = None
                self.readiness_error = None
                self.model = None
                self.resources = None
                self.resource_error = None
                self.cpu_sample = None
                self.hybrid_markers.clear()
                self.generation_serial += 1
                self.generation = {}
                self.slot_sample = None
        if closing:
            self.monitor.close()

    def connection(self) -> tuple[http.client.HTTPConnection, str]:
        with self.lock:
            if self.closed or self.state != "ready" or self.process is None or self.process.poll() is not None:
                raise AppError(503, "No model is ready. Load a model and check its status first.")
            return http.client.HTTPConnection("127.0.0.1", self.port, timeout=120), self.key


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, address: tuple[str, int], runtime: Runtime, *, update_checks: bool = True):
        self.runtime = runtime
        archive = Path(sys.argv[0]).resolve() if sys.argv[0].endswith(".pyz") else None
        self.updates = _updates.UpdateManager(__version__, archive, automatic=update_checks)
        self.restart_requested = False
        super().__init__(address, Handler)

    def install_update(self, staged: Path, receipt: dict) -> None:
        if not self.runtime.chat_lock.acquire(blocking=False):
            raise RuntimeError("A chat started while downloading. Wait for it to finish and retry the update.")
        try:
            with self.runtime.lock:
                if self.runtime.closed or self.runtime.state in ("loading", "stopping"):
                    raise RuntimeError("The model is changing. Wait until it is idle before updating.")
                self.runtime.closed = True
            self.runtime.stop()
            _updates.install_archive(staged, self.updates.archive, receipt)
            self.restart_requested = True
            with self.updates.lock:
                self.updates.state = "restarting"
            threading.Thread(target=self.shutdown, daemon=True).start()
        except (OSError, ValueError, RuntimeError):
            with self.runtime.lock:
                self.runtime.closed = False
            raise
        finally:
            self.runtime.chat_lock.release()

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        # The loopback listener needs no potentially blocking reverse-DNS lookup.
        self.server_name = "localhost"
        self.server_port = self.server_address[1]

    def server_close(self) -> None:
        self.runtime.monitor.close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    server: AppServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        LOG.info("%s %s", self.client_address[0], format % args)

    def _guard(self) -> None:
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            raise AppError(403, "Only the local application host is allowed.")
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{host}" for host in hosts}:
            raise AppError(403, "Cross-origin requests are not allowed.")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise AppError(403, "Cross-site requests are not allowed.")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self._headers(content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; connect-src 'self'; script-src 'self'; "
                         "style-src 'self'; img-src 'self'; frame-ancestors 'none'; "
                         "base-uri 'none'; form-action 'none'")

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data).encode(), "application/json; charset=utf-8")

    def _body(self) -> dict:
        if self.headers.get("Transfer-Encoding"):
            raise AppError(400, "Chunked request bodies are not supported.")
        if self.headers.get_content_type() != "application/json":
            raise AppError(415, "Content-Type must be application/json.")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1:
            raise AppError(411, "Exactly one Content-Length header is required.")
        try:
            length = int(lengths[0])
        except ValueError as exc:
            raise AppError(400, "Invalid Content-Length.") from exc
        if not 0 < length <= BODY_LIMIT:
            raise AppError(413, "Request body must be between 1 byte and 1 MiB.")
        self.connection.settimeout(15)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise AppError(400, "Incomplete request body.")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise AppError(400, "Request body must be valid JSON.") from exc
        if not isinstance(value, dict):
            raise AppError(400, "Request body must be a JSON object.")
        return value

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        try:
            self._guard()
            path = urlsplit(self.path).path
            if method == "GET" and path == "/api/v1/status":
                self._json(200, self.server.runtime.status())
            elif method == "GET" and path == "/api/v1/update":
                self.server.updates.check()
                self._json(200, self.server.updates.snapshot())
            elif method == "POST" and path == "/api/v1/update/check":
                self._body()
                self.server.updates.check(force=True)
                self._json(202, self.server.updates.snapshot())
            elif method == "POST" and path == "/api/v1/update/apply":
                data = self._body()
                if self.server.runtime.chat_lock.locked() or self.server.runtime.state in ("loading", "stopping"):
                    raise AppError(409, "Wait until the model is idle before updating.")
                try:
                    self.server.updates.apply(data.get("version"), self.server.install_update)
                except ValueError as exc:
                    raise AppError(400, str(exc)) from exc
                self._json(202, self.server.updates.snapshot())
            elif method == "GET" and path == "/api/v1/monitor":
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                values = query.get("after", ["0"])
                if set(query) - {"after"} or len(values) != 1 or not values[0].isascii() or not values[0].isdigit():
                    raise AppError(400, "Use a single nonnegative integer monitor cursor.")
                if len(values[0]) > 16:
                    raise AppError(400, "Monitor cursor is too large.")
                self._json(200, self.server.runtime.monitor.snapshot(int(values[0])))
            elif method == "POST" and path == "/api/v1/model/load":
                self.server.runtime.load(self._body())
                self._json(202, self.server.runtime.status())
            elif method == "POST" and path == "/api/v1/models/browse":
                data = self._body()
                if set(data) - {"path"}:
                    raise AppError(400, "Model browsing accepts only a local folder path.")
                self._json(200, browse_models(data.get("path")))
            elif method == "POST" and path == "/api/v1/model/unload":
                self._body()
                self.server.runtime.stop()
                self._json(200, self.server.runtime.status())
            elif path == "/v1/models" and method == "GET":
                self._proxy(method, path, None)
            elif path == "/v1/chat/completions" and method == "POST":
                data = self._body()
                messages = data.get("messages")
                if not isinstance(messages, list) or not messages:
                    raise AppError(400, "messages must be a non-empty array.")
                if "stream" in data and not isinstance(data["stream"], bool):
                    raise AppError(400, "stream must be a boolean.")
                self._proxy(method, path, data)
            elif method == "GET" and path in ("/", "/app.js", "/chat-stream.mjs", "/chat-input.mjs", "/theme.js", "/monitor.mjs", "/navigation.mjs", "/updates.mjs",
                                             "/style.css", "/icon.svg"):
                name, mime = {
                    "/": ("index.html", "text/html; charset=utf-8"),
                    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                    "/chat-stream.mjs": ("chat-stream.mjs", "text/javascript; charset=utf-8"),
                    "/chat-input.mjs": ("chat-input.mjs", "text/javascript; charset=utf-8"),
                    "/theme.js": ("theme.js", "text/javascript; charset=utf-8"),
                    "/monitor.mjs": ("monitor.mjs", "text/javascript; charset=utf-8"),
                    "/navigation.mjs": ("navigation.mjs", "text/javascript; charset=utf-8"),
                    "/updates.mjs": ("updates.mjs", "text/javascript; charset=utf-8"),
                    "/icon.svg": ("icon.svg", "image/svg+xml"),
                    "/style.css": ("style.css", "text/css; charset=utf-8"),
                }[path]
                self._send(200, files(APP_PACKAGE).joinpath("web", name).read_bytes(), mime)
            else:
                raise AppError(404, "Endpoint not found.")
        except AppError as exc:
            self.close_connection = True
            self._json(exc.status, {"error": {"message": str(exc), "type": "vrambridge_error"}})
        except (BrokenPipeError, ConnectionResetError):
            LOG.info("Local client disconnected.")
        except (OSError, http.client.HTTPException) as exc:
            LOG.error("Request failed: %s", exc)
            self.close_connection = True
            self._json(502, {"error": {"message": f"Local service request failed: {exc}",
                                     "type": "vrambridge_error"}})

    def _proxy(self, method: str, path: str, data: dict | None) -> None:
        runtime = self.server.runtime
        chat = path == "/v1/chat/completions"
        if chat and not runtime.chat_lock.acquire(blocking=False):
            raise AppError(409, "Another chat is running. Stop it or wait before sending.")
        connection: http.client.HTTPConnection | None = None
        streaming_started = False
        finished = threading.Event()
        disconnected = threading.Event()
        serial = runtime.begin_generation() if chat else None
        event_lines: list[bytes] = []
        event_bytes = 0

        def observe(payload: bytes) -> None:
            if serial is None or not payload or payload.strip() == b"[DONE]":
                return
            try:
                runtime.observe_generation(serial, json.loads(payload))
            except (ValueError, UnicodeDecodeError) as exc:
                LOG.warning("Backend telemetry event unavailable: %s", exc)
        try:
            connection, key = runtime.connection()
            if data is not None:
                data["model"] = "local-model"
            connection.request(method, path, body=json.dumps(data) if data is not None else None,
                               headers={"Content-Type": "application/json",
                                        "Authorization": f"Bearer {key}"})
            upstream_socket = connection.sock
            assert upstream_socket is not None

            def watch_client() -> None:
                while not finished.wait(0.1):
                    try:
                        readable, _, _ = select.select([self.connection], [], [], 0)
                        if readable and not self.connection.recv(1, socket.MSG_PEEK):
                            disconnected.set()
                            upstream_socket.shutdown(socket.SHUT_RDWR)
                            return
                    except OSError:
                        if not finished.is_set():
                            disconnected.set()
                        return

            if chat:
                threading.Thread(target=watch_client, daemon=True).start()
            response = connection.getresponse()
            streaming = data is not None and data.get("stream") is True and response.status == 200
            if not streaming:
                body = response.read(RESPONSE_LIMIT + 1)
                if len(body) > RESPONSE_LIMIT:
                    raise AppError(502, "Backend response exceeded the 8 MiB limit.")
                if chat and response.status == 200:
                    observe(body)
                self._send(response.status, body, "application/json; charset=utf-8")
                return
            self.send_response(200)
            self._headers("text/event-stream; charset=utf-8")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            streaming_started = True
            while True:
                line = response.readline(1024 * 1024)
                if not line:
                    break
                if line.startswith(b"data:"):
                    event_bytes += len(line)
                    if event_bytes <= 1024 * 1024:
                        event_lines.append(line[5:].strip())
                elif not line.strip():
                    if event_bytes <= 1024 * 1024:
                        observe(b"\n".join(event_lines))
                    else:
                        LOG.warning("Backend telemetry event exceeded the 1 MiB capture limit.")
                    event_lines, event_bytes = [], 0
                self.wfile.write(line)
                self.wfile.flush()
            if not disconnected.is_set():
                LOG.info("Chat stream completed.")
        except (OSError, http.client.HTTPException) as exc:
            if disconnected.is_set():
                LOG.info("Chat cancelled by local client.")
                return
            if not streaming_started:
                raise
            LOG.error("Chat stream interrupted: %s", exc)
            if not isinstance(exc, (BrokenPipeError, ConnectionResetError)):
                event = json.dumps({"error": {"message": "Backend stream interrupted. Check model status."}})
                self.wfile.write(f"data: {event}\n\ndata: [DONE]\n\n".encode())
                self.wfile.flush()
        finally:
            finished.set()
            if connection is not None:
                connection.close()
            if chat:
                runtime.end_generation(serial)
                runtime.chat_lock.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"SYNAPSE {__version__}")
    parser.add_argument("--llama-server", default=os.environ.get("LLAMA_SERVER", "llama-server"),
                        help="llama-server executable or path (also LLAMA_SERVER)")
    parser.add_argument("--backend-kind", choices=("llama.cpp", "ik_llama.cpp"), default="llama.cpp",
                        help="explicit backend flag adapter; ik_llama.cpp is experimental")
    parser.add_argument("--experimental-speculation", action="store_true",
                        help="allow opt-in DFlash draft models; requires a compatible backend")
    parser.add_argument("--experimental-hybrid-plan",
                        help="require experimental routed-MoE execution with a model-specific plan file, or auto for causal cold start")
    parser.add_argument("--hybrid-cuda-plugin", type=Path,
                        help="matching pinned CUDA shared-library file; required with --experimental-hybrid-plan")
    parser.add_argument("--execution-mode", choices=("auto", "standard", "hybrid"), default="auto",
                        help="default model selection policy; auto uses an installed hybrid profile only for matching models")
    parser.add_argument("--hybrid-profile", type=Path,
                        help="optional Linux/CUDA experimental installation JSON; legacy VRAMBridge profiles are supported")
    parser.add_argument("--port", type=int, default=8080, help="local app port; 0 chooses a free port")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    parser.add_argument("--no-update-check", action="store_true", help="disable automatic GitHub release checks")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        profile = {}
        explicit = args.experimental_hybrid_plan is not None or args.hybrid_cuda_plugin is not None
        if explicit:
            profile = {"hybrid_plan": args.experimental_hybrid_plan, "hybrid_cuda_plugin": args.hybrid_cuda_plugin}
        elif args.execution_mode != "standard":
            config = (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "SYNAPSE"
                      if sys.platform == "win32" else Path.home() / "Library/Application Support/SYNAPSE"
                      if sys.platform == "darwin" else
                      Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "synapse")
            legacy = Path.home() / ".local/share/vrambridge/hybrid-profile.json"
            path = args.hybrid_profile or config / "hybrid-profile.json"
            if not path.exists() and args.hybrid_profile is None and sys.platform == "linux" and legacy.exists():
                path = legacy
            if args.hybrid_profile is not None or path.exists():
                profile = read_hybrid_profile(path)
        if profile and sys.platform != "linux":
            raise ValueError("The experimental hybrid engine is Linux/CUDA-only in this release. Use --execution-mode standard.")
        mode = "hybrid" if explicit and args.execution_mode == "auto" else args.execution_mode
        runtime = Runtime(args.llama_server, backend_kind=args.backend_kind,
                          enable_speculation=args.experimental_speculation,
                          execution_mode=mode, **profile)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if runtime.hybrid_plan is not None:
        LOG.warning("%s", HYBRID_WARNING)
    try:
        server = AppServer(("127.0.0.1", args.port), runtime, update_checks=not args.no_update_check)
    except OSError as exc:
        parser.exit(1, f"Cannot start local app: {exc}\n")
    url = f"http://127.0.0.1:{server.server_address[1]}"

    def shutdown(signum: int, frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, shutdown)
    print(f"SYNAPSE: {url}", flush=True)
    if not runtime.executable:
        LOG.warning("llama-server not found. The UI will show backend setup instructions.")
    if not args.no_browser and not webbrowser.open(url):
        LOG.warning("Could not open a browser. Open %s manually.", url)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        runtime.stop(closing=True)
        server.server_close()
    if server.restart_requested:
        os.execv(sys.executable, [sys.executable, *sys.argv, "--port", str(server.server_address[1]), "--no-browser"])


if __name__ == "__main__":
    main()
