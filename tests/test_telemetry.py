import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest import mock

path = Path(sys.argv.pop(1))
spec = importlib.util.spec_from_file_location("synapse_telemetry_test", path)
telemetry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(telemetry)


class TelemetryTests(unittest.TestCase):
    def test_numeric_guards_and_counter_resets(self):
        for value in (None, True, "12", -1, float("nan"), float("inf")):
            self.assertIsNone(telemetry.number(value))
        self.assertEqual(telemetry.number(0), 0)
        self.assertEqual(telemetry.rate(2048, 1024, 2), 512)
        self.assertIsNone(telemetry.rate(0, 1024, 1))
        self.assertIsNone(telemetry.rate(1, 0, 0))

    def test_linux_counter_units_and_cpu_parse(self):
        with mock.patch.object(telemetry.platform, "system", return_value="Linux"):
            probe = telemetry.SystemProbe()
        files = {"/proc/stat": "cpu 10 0 20 70 5 0 0 0\n",
                 "/proc/meminfo": "MemTotal: 1000 kB\nMemAvailable: 400 kB\n"}
        with mock.patch.object(Path, "read_text", autospec=True, side_effect=lambda p: files[p.as_posix()]):
            self.assertEqual(probe.cpu(), (105, 75))
            self.assertEqual(probe.memory(), (1024000, 409600))

    def test_native_process_and_memory_on_this_platform(self):
        probe = telemetry.SystemProbe()
        result = probe.process(os.getpid())
        self.assertAlmostEqual(result["cpu_seconds"], time.process_time(), delta=0.5)
        self.assertGreater(result["rss_bytes"], 0)
        self.assertGreaterEqual(result["cpu_seconds"], 0)
        self.assertGreaterEqual(result["read_bytes"], 0)
        total, available = probe.memory()
        self.assertGreater(total, 0)
        self.assertGreaterEqual(available, 0)
        self.assertLessEqual(available, total)
        total_cpu, idle = probe.cpu()
        self.assertGreater(total_cpu, 0)
        self.assertLessEqual(idle, total_cpu)

    def test_bounded_history_rates_restart_and_explicit_unavailable_gpu(self):
        probe = mock.Mock()
        probe.cpu.side_effect = [(100, 50), (200, 100), (300, 150)]
        probe.memory.return_value = (8192, 4096)
        backend = mock.Mock(side_effect=[
            {"pid": 10, "read_bytes": 0, "state": "ready"},
            {"pid": 10, "read_bytes": 2 * 1024 ** 2, "state": "ready"},
            {"pid": 11, "read_bytes": 100, "state": "ready"}])
        monitor = telemetry.HardwareMonitor(backend, capacity=2)
        with mock.patch.object(telemetry, "system_probe", return_value=probe), \
                mock.patch.object(telemetry, "NvidiaProbe", side_effect=OSError("No GPU fixture")), \
                mock.patch.object(telemetry.time, "monotonic", side_effect=[1, 2, 3]):
            first, second, third = monitor.collect(), monitor.collect(), monitor.collect()
        self.assertIsNone(first["system"]["cpu_percent"])
        self.assertEqual(second["system"]["cpu_percent"], 50)
        self.assertEqual(second["system"]["disk_read_bytes_s"], 2 * 1024 ** 2)
        self.assertIsNone(third["system"]["disk_read_bytes_s"])
        self.assertIn("No GPU fixture", second["errors"]["gpu"])
        self.assertNotIn("pid", second["backend"])
        self.assertNotIn("read_bytes", second["backend"])
        monitor.stop_event.set()
        data = monitor.snapshot(after=100)
        self.assertTrue(data["reset"])
        self.assertEqual([v["sequence"] for v in data["samples"]], [2, 3])
        self.assertEqual([v["sequence"] for v in monitor.snapshot(after=2)["samples"]], [3])
        self.assertNotIn("prompt", json.dumps(data))

    def test_gpu_partial_failure_does_not_hide_other_counters(self):
        gpu = mock.Mock()
        gpu.sample.return_value = [{"index": 0, "name": "Fixture GPU", "load_percent": 32,
                                   "power_w": None, "errors": {"power_w": "Not supported"}}]
        probe = mock.Mock()
        probe.cpu.return_value = (100, 50)
        probe.memory.return_value = (8192, 4096)
        monitor = telemetry.HardwareMonitor(lambda: {"state": "stopped"})
        with mock.patch.object(telemetry, "system_probe", return_value=probe), \
                mock.patch.object(telemetry, "NvidiaProbe", return_value=gpu):
            sample = monitor.collect()
        self.assertEqual(sample["gpus"][0]["load_percent"], 32)
        self.assertIsNone(sample["gpus"][0]["power_w"])
        self.assertEqual(sample["gpus"][0]["errors"]["power_w"], "Not supported")

    def test_sampling_errors_are_visible(self):
        monitor = telemetry.HardwareMonitor(lambda: {"state": "stopped"})
        with mock.patch.object(telemetry, "system_probe", side_effect=OSError("Denied CPU counters")), \
                mock.patch.object(telemetry, "NvidiaProbe", side_effect=OSError("Missing NVML")):
            sample = monitor.collect()
        self.assertEqual(sample["errors"]["system"], "Denied CPU counters")
        self.assertIsNone(sample["system"]["cpu_percent"])
        self.assertIsNone(sample["system"]["ram_used_bytes"])


if __name__ == "__main__":
    unittest.main()
