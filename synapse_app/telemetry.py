"""Local, bounded monitoring using OS counters and optional NVIDIA NVML."""

from __future__ import annotations

from collections import deque
import ctypes as ct
import ctypes.util
from functools import lru_cache
import logging
import math
import os
from pathlib import Path
import platform
import threading
import time


LOG = logging.getLogger("synapse.monitor")


def number(value: object) -> float | None:
    return float(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def rate(current: float, previous: float, elapsed: float) -> float | None:
    return (current - previous) / elapsed if elapsed > 0 and current >= previous else None


class MemoryStatus(ct.Structure):
    _fields_ = [("length", ct.c_uint32), ("load", ct.c_uint32)] + [
        (name, ct.c_uint64) for name in
        ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]


class ProcessMemory(ct.Structure):
    _fields_ = [("size", ct.c_uint32), ("faults", ct.c_uint32)] + [
        (name, ct.c_size_t) for name in
        ("peak_rss", "rss", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]


class MacUsage(ct.Structure):
    _fields_ = [("uuid", ct.c_uint8 * 16)] + [(name, ct.c_uint64) for name in (
        "user", "system", "idle_wakeups", "interrupt_wakeups", "pageins", "wired", "rss", "footprint",
        "start", "exit", "child_user", "child_system", "child_idle", "child_interrupt", "child_pageins",
        "child_elapsed", "read_bytes", "write_bytes")]


class SystemProbe:
    def __init__(self):
        self.platform = platform.system()
        if self.platform == "Windows":
            self.kernel = ct.WinDLL("kernel32", use_last_error=True)
            self.psapi = ct.WinDLL("psapi", use_last_error=True)
            self.kernel.OpenProcess.argtypes = [ct.c_uint32, ct.c_int, ct.c_uint32]
            self.kernel.OpenProcess.restype = ct.c_void_p
            self.kernel.CloseHandle.argtypes = [ct.c_void_p]
            self.kernel.GetProcessTimes.argtypes = [ct.c_void_p] + [ct.POINTER(ct.c_uint64)] * 4
            self.kernel.GetProcessIoCounters.argtypes = [ct.c_void_p, ct.POINTER(ct.c_uint64 * 6)]
            self.kernel.GetSystemTimes.argtypes = [ct.POINTER(ct.c_uint64)] * 3
            self.kernel.GlobalMemoryStatusEx.argtypes = [ct.POINTER(MemoryStatus)]
            self.psapi.GetProcessMemoryInfo.argtypes = [ct.c_void_p, ct.POINTER(ProcessMemory), ct.c_uint32]
        elif self.platform == "Darwin":
            self.lib = ct.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
            self.proc = ct.CDLL("/usr/lib/libproc.dylib", use_errno=True)
            self.proc.proc_pid_rusage.argtypes = [ct.c_int, ct.c_int, ct.c_void_p]
            self.lib.mach_host_self.restype = ct.c_uint32
            self.lib.host_statistics.argtypes = [ct.c_uint32, ct.c_int, ct.c_void_p, ct.POINTER(ct.c_uint32)]
            self.lib.host_statistics64.argtypes = self.lib.host_statistics.argtypes
            self.lib.host_page_size.argtypes = [ct.c_uint32, ct.POINTER(ct.c_uint64)]
            self.lib.sysctlbyname.argtypes = [ct.c_char_p, ct.c_void_p, ct.POINTER(ct.c_size_t),
                                             ct.c_void_p, ct.c_size_t]

    def memory(self) -> tuple[int, int]:
        sample = self.memory_details()
        return sample["total_bytes"], sample["available_bytes"]

    def memory_details(self) -> dict:
        if self.platform == "Linux":
            values = {parts[0].rstrip(":"): int(parts[1]) * 1024
                      for line in Path("/proc/meminfo").read_text().splitlines()
                      if (parts := line.split()) and parts[0] in
                      ("MemTotal:", "MemAvailable:", "MemFree:", "Cached:", "Buffers:", "Shmem:")}
            total, available, free = values["MemTotal"], values["MemAvailable"], values["MemFree"]
            shared = values["Shmem"]
            cache = values["Cached"] + values["Buffers"] - shared
            basis = "physical_occupied"
        if self.platform == "Windows":
            values = MemoryStatus()
            values.length = ct.sizeof(values)
            if not self.kernel.GlobalMemoryStatusEx(ct.byref(values)):
                raise OSError(ct.get_last_error(), "GlobalMemoryStatusEx failed")
            total, available, free, cache, shared = values.total, values.available, None, None, None
            basis = "os_unavailable"
        if self.platform == "Darwin":
            total = ct.c_uint64()
            size = ct.c_size_t(ct.sizeof(total))
            if self.lib.sysctlbyname(b"hw.memsize", ct.byref(total), ct.byref(size), None, 0):
                raise OSError(ct.get_errno(), "sysctl hw.memsize failed")
            host = self.lib.mach_host_self()
            values, count, pages = (ct.c_uint32 * 64)(), ct.c_uint32(64), ct.c_uint64()
            if self.lib.host_statistics64(host, 4, ct.byref(values), ct.byref(count)) or \
                    self.lib.host_page_size(host, ct.byref(pages)):
                raise OSError("Mach memory counters unavailable")
            total, available, free, cache, shared = total.value, (values[0] + values[2]) * pages.value, values[0] * pages.value, None, None
            basis = "physical_occupied"
        if self.platform not in ("Linux", "Windows", "Darwin"):
            raise OSError(f"Memory monitoring is unsupported on {self.platform}")
        if (total <= 0 or not 0 <= available <= total or
                free is not None and not 0 <= free <= total or
                cache is not None and not 0 <= cache <= total or
                shared is not None and not 0 <= shared <= total):
            raise ValueError("OS memory counters are inconsistent")
        return {"total_bytes": total, "available_bytes": available, "free_bytes": free,
                "occupied_bytes": total - (available if free is None else free),
                "cache_bytes": cache, "shared_system_bytes": shared,
                "pressure_bytes": total - available, "basis": basis}

    def cpu(self) -> tuple[int, int]:
        if self.platform == "Linux":
            values = list(map(int, Path("/proc/stat").read_text().splitlines()[0].split()[1:9]))
            return sum(values), values[3] + values[4]
        if self.platform == "Windows":
            idle, kernel, user = ct.c_uint64(), ct.c_uint64(), ct.c_uint64()
            if not self.kernel.GetSystemTimes(ct.byref(idle), ct.byref(kernel), ct.byref(user)):
                raise OSError(ct.get_last_error(), "GetSystemTimes failed")
            return kernel.value + user.value, idle.value
        if self.platform == "Darwin":
            values, count = (ct.c_uint32 * 4)(), ct.c_uint32(4)
            if self.lib.host_statistics(self.lib.mach_host_self(), 3, ct.byref(values), ct.byref(count)):
                raise OSError("Mach CPU counters unavailable")
            return sum(values), values[2]
        raise OSError(f"CPU monitoring is unsupported on {self.platform}")

    def process(self, pid: int) -> dict:
        if self.platform == "Linux":
            root = Path("/proc") / str(pid)
            fields = (root / "stat").read_text().rsplit(")", 1)[1].split()
            memory = {parts[0].rstrip(":"): int(parts[1]) * 1024
                      for line in (root / "status").read_text().splitlines()
                      if (parts := line.split()) and parts[0] in ("VmRSS:", "RssAnon:", "RssFile:", "RssShmem:")}
            io = dict(line.split(": ", 1) for line in (root / "io").read_text().splitlines())
            return {"cpu_seconds": (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK"),
                    "rss_bytes": memory["VmRSS"], "anonymous_bytes": memory["RssAnon"],
                    "file_backed_bytes": memory["RssFile"], "shared_bytes": memory["RssShmem"],
                    "read_bytes": int(io["read_bytes"])}
        if self.platform == "Windows":
            handle = self.kernel.OpenProcess(0x1000 | 0x10, False, pid)
            if not handle:
                raise OSError(ct.get_last_error(), "OpenProcess failed")
            try:
                created, exited, kernel, user = (ct.c_uint64() for _ in range(4))
                memory, io = ProcessMemory(), (ct.c_uint64 * 6)()
                memory.size = ct.sizeof(memory)
                if not self.kernel.GetProcessTimes(handle, ct.byref(created), ct.byref(exited),
                                                   ct.byref(kernel), ct.byref(user)) or \
                        not self.psapi.GetProcessMemoryInfo(handle, ct.byref(memory), memory.size) or \
                        not self.kernel.GetProcessIoCounters(handle, ct.byref(io)):
                    raise OSError(ct.get_last_error(), "Windows process counters unavailable")
                return {"cpu_seconds": (kernel.value + user.value) / 10_000_000,
                        "rss_bytes": memory.rss, "anonymous_bytes": None, "file_backed_bytes": None, "shared_bytes": None,
                        "read_bytes": io[3]}
            finally:
                self.kernel.CloseHandle(handle)
        if self.platform == "Darwin":
            usage = MacUsage()
            if self.proc.proc_pid_rusage(pid, 2, ct.byref(usage)):
                raise OSError(ct.get_errno(), "proc_pid_rusage failed")
            return {"cpu_seconds": (usage.user + usage.system) / 1_000_000_000,
                    "rss_bytes": usage.rss, "anonymous_bytes": None, "file_backed_bytes": None, "shared_bytes": None,
                    "read_bytes": usage.read_bytes}
        raise OSError(f"Process monitoring is unsupported on {self.platform}")


@lru_cache(maxsize=1)
def system_probe() -> SystemProbe:
    return SystemProbe()


class GpuMemory(ct.Structure):
    _fields_ = [(name, ct.c_uint64) for name in ("total", "free", "used")]


class GpuUtilization(ct.Structure):
    _fields_ = [("gpu", ct.c_uint), ("memory", ct.c_uint)]


class NvidiaProbe:
    def __init__(self):
        system = platform.system()
        if system == "Windows":
            candidates = [Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/nvml.dll",
                          Path(os.environ.get("ProgramFiles", "C:/Program Files")) /
                          "NVIDIA Corporation/NVSMI/nvml.dll"]
            path = next((str(p) for p in candidates if p.is_file()), None)
        else:
            path = ct.util.find_library("nvidia-ml")
            if not path and system == "Linux":
                path = "libnvidia-ml.so.1"
        if not path:
            raise OSError("NVIDIA NVML is unavailable; Metal/AMD GPU counters are not implemented in this release")
        self.lib = ct.CDLL(path)
        self.lib.nvmlInit_v2.restype = ct.c_int
        self.lib.nvmlDeviceGetHandleByIndex_v2.argtypes = [ct.c_uint, ct.POINTER(ct.c_void_p)]
        self.lib.nvmlDeviceGetName.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_uint]
        self.lib.nvmlDeviceGetUtilizationRates.argtypes = [ct.c_void_p, ct.POINTER(GpuUtilization)]
        self.lib.nvmlDeviceGetMemoryInfo.argtypes = [ct.c_void_p, ct.POINTER(GpuMemory)]
        self.lib.nvmlDeviceGetTemperature.argtypes = [ct.c_void_p, ct.c_uint, ct.POINTER(ct.c_uint)]
        self.lib.nvmlDeviceGetPowerUsage.argtypes = [ct.c_void_p, ct.POINTER(ct.c_uint)]
        self.lib.nvmlDeviceGetPcieThroughput.argtypes = [ct.c_void_p, ct.c_uint, ct.POINTER(ct.c_uint)]
        if self.lib.nvmlInit_v2():
            raise OSError("NVIDIA NVML initialization failed; check the graphics driver")
        self.initialized = True

    def sample(self) -> list[dict]:
        count = ct.c_uint()
        if self.lib.nvmlDeviceGetCount_v2(ct.byref(count)):
            raise OSError("NVML device enumeration failed")
        devices = []
        for index in range(count.value):
            handle = ct.c_void_p()
            if self.lib.nvmlDeviceGetHandleByIndex_v2(index, ct.byref(handle)):
                raise OSError(f"NVML cannot access GPU {index}")
            name, utilization, memory = ct.create_string_buffer(96), GpuUtilization(), GpuMemory()
            device = {"index": index, "name": f"GPU {index}", "errors": {}}
            if not self.lib.nvmlDeviceGetName(handle, name, len(name)):
                device["name"] = name.value.decode("utf-8", errors="replace")
            if not self.lib.nvmlDeviceGetUtilizationRates(handle, ct.byref(utilization)):
                device["load_percent"] = utilization.gpu
            else:
                device["load_percent"] = None
                device["errors"]["load_percent"] = "Utilization counter unavailable"
            if not self.lib.nvmlDeviceGetMemoryInfo(handle, ct.byref(memory)):
                device.update(vram_used_bytes=memory.used, vram_total_bytes=memory.total)
            else:
                device.update(vram_used_bytes=None, vram_total_bytes=None)
                device["errors"]["vram_used_bytes"] = "VRAM counter unavailable"
            for key, function, args, scale in (
                    ("temperature_c", "nvmlDeviceGetTemperature", [0], 1),
                    ("power_w", "nvmlDeviceGetPowerUsage", [], 0.001),
                    ("pcie_tx_bytes_s", "nvmlDeviceGetPcieThroughput", [0], 1024),
                    ("pcie_rx_bytes_s", "nvmlDeviceGetPcieThroughput", [1], 1024)):
                value = ct.c_uint()
                code = getattr(self.lib, function)(handle, *args, ct.byref(value))
                device[key] = value.value * scale if code == 0 else None
                if code:
                    device["errors"][key] = f"Driver counter unavailable (NVML {code})"
            devices.append(device)
        return devices

    def close(self) -> None:
        if self.initialized:
            self.lib.nvmlShutdown()
            self.initialized = False


class HardwareMonitor:
    def __init__(self, backend, *, interval: float = 1, capacity: int = 300):
        self.backend = backend
        self.interval = interval
        self.samples: deque[dict] = deque(maxlen=capacity)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.previous_cpu: tuple[int, int] | None = None
        self.previous_disk: tuple[int, float, float] | None = None
        self.gpu: NvidiaProbe | None = None
        self.gpu_initialized = False
        self.gpu_error: str | None = None
        self.sequence = 0

    def collect(self) -> dict:
        now, errors = time.monotonic(), {}
        values = {"cpu_percent": None, "ram_used_bytes": None, "ram_total_bytes": None,
                  "ram_available_bytes": None, "ram_free_bytes": None, "ram_cache_bytes": None,
                  "ram_shared_bytes": None, "ram_pressure_bytes": None, "ram_basis": None, "disk_read_bytes_s": None}
        try:
            probe = system_probe()
            current = probe.cpu()
            if self.previous_cpu:
                total, idle = current[0] - self.previous_cpu[0], current[1] - self.previous_cpu[1]
                if total > 0 and 0 <= idle <= total:
                    values["cpu_percent"] = 100 * (total - idle) / total
            self.previous_cpu = current
            memory = probe.memory_details()
            values.update(ram_used_bytes=memory["occupied_bytes"], ram_total_bytes=memory["total_bytes"],
                          ram_available_bytes=memory["available_bytes"], ram_free_bytes=memory["free_bytes"],
                          ram_cache_bytes=memory["cache_bytes"], ram_pressure_bytes=memory["pressure_bytes"],
                          ram_shared_bytes=memory["shared_system_bytes"],
                          ram_basis=memory["basis"])
        except (OSError, ValueError, KeyError, IndexError) as exc:
            errors["system"] = str(exc)
        if not self.gpu_initialized:
            self.gpu_initialized = True
            try:
                self.gpu = NvidiaProbe()
            except (OSError, AttributeError) as exc:
                self.gpu_error = str(exc)
        devices = []
        if self.gpu:
            try:
                devices = self.gpu.sample()
            except (OSError, AttributeError) as exc:
                errors["gpu"] = str(exc)
        elif self.gpu_error:
            errors["gpu"] = self.gpu_error
        backend = self.backend()
        pid, read = backend.pop("pid", None), backend.pop("read_bytes", None)
        if pid is not None and number(read) is not None:
            if self.previous_disk and self.previous_disk[0] == pid:
                values["disk_read_bytes_s"] = rate(read, self.previous_disk[2], now - self.previous_disk[1])
            self.previous_disk = pid, now, read
        else:
            self.previous_disk = None
        sample = {"sequence": self.sequence + 1, "time_ms": int(time.time() * 1000),
                  "system": values, "gpus": devices, "backend": backend, "errors": errors}
        with self.lock:
            self.sequence += 1
            self.samples.append(sample)
            cutoff = sample["time_ms"] - self.samples.maxlen * self.interval * 1000
            while self.samples and self.samples[0]["time_ms"] < cutoff:
                self.samples.popleft()
        return sample

    def _run(self) -> None:
        try:
            while not self.stop_event.is_set():
                deadline = time.monotonic() + self.interval
                self.collect()
                self.stop_event.wait(max(0, deadline - time.monotonic()))
        finally:
            if self.gpu:
                self.gpu.close()

    def snapshot(self, after: int = 0) -> dict:
        with self.lock:
            if self.thread is None and not self.stop_event.is_set():
                self.thread = threading.Thread(target=self._run, name="synapse-monitor", daemon=True)
                self.thread.start()
            reset = after > self.sequence
            samples = [s for s in self.samples if s["sequence"] > (0 if reset else after)]
            return {"api_version": 1, "interval_ms": int(self.interval * 1000), "capacity": self.samples.maxlen,
                    "platform": platform.system(), "samples": samples, "reset": reset,
                    "disk_scope": "Backend process read I/O; Windows includes cached and non-disk reads.",
                    "gpu_scope": "Device-wide NVIDIA counters, including other apps. Unsupported metrics stay unavailable.",
                    "memory_scope": "Linux/macOS RAM occupancy includes cached pages. Windows uses OS-unavailable RAM. "
                                    "OS-reported availability is a separate estimate, not a free-physical-memory guarantee. "
                                    "Backend RSS overlaps cache and must not be added to it."}

    def close(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
