import json
from pathlib import Path
import tempfile
import unittest

from synapse_app.tuning import AutoTuner, client_settings


class TuningTests(unittest.TestCase):
    def tuner(self, store):
        return AutoTuner(lambda: None, metadata=lambda path: {}, compatible=lambda metadata: False,
                         layout=lambda metadata: {}, memory=lambda: (16 * 1024**3, 8 * 1024**3),
                         hardware=lambda: {}, cpu_threads=lambda: 8, cpu_count=lambda: 16,
                         runtime_error=RuntimeError, store=store)

    def test_client_limits_match_the_verified_context_with_output_and_headroom(self):
        for context in (512, 8192, 16384, 32768, 65536, 131072, 262144):
            with self.subTest(context=context):
                settings = client_settings(context)
                self.assertGreater(settings["maxInputTokens"], 0)
                self.assertGreater(settings["maxOutputTokens"], 0)
                self.assertEqual(settings["maxInputTokens"] + settings["maxOutputTokens"] +
                                 settings["safetyMarginTokens"], context)
        self.assertEqual(client_settings(262144)["maxInputTokens"], 245760)
        self.assertEqual(client_settings(262144)["maxOutputTokens"], 8192)

    def test_completed_report_survives_a_restart_without_starting_trials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tuning.json"
            path.write_text(json.dumps({"schema_version": 1, "state": "completed", "active": False,
                                        "trials": [], "recommendation": None, "error": None}))
            tuner = self.tuner(path)
            self.assertFalse(tuner.active)
            self.assertEqual(tuner.snapshot()["state"], "completed")
            self.assertIsNone(tuner.worker)

    def test_corrupt_and_oversized_saved_reports_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tuning.json"
            for text in ("{}", "not JSON", "x" * (1024 * 1024 + 1)):
                path.write_text(text)
                with self.assertLogs("synapse.tuning", level="ERROR"):
                    tuner = self.tuner(path)
                self.assertIn("Saved tuning report unavailable", tuner.snapshot()["error"])
                self.assertFalse(tuner.active)

    def test_malformed_recommendations_and_trial_shapes_are_reported(self):
        base = {"schema_version": 1, "state": "completed", "trials": [], "recommendation": None}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tuning.json"
            for changes in ({"trials": [None]}, {"trials": [{"settings": {}, "capacity_passed": True}]},
                            {"recommendation": {"settings": {"context": 32768, "execution_mode": "standard"},
                                                "apps": {"maxInputTokens": 999999}}}):
                path.write_text(json.dumps({**base, **changes}))
                with self.assertLogs("synapse.tuning", level="ERROR"):
                    tuner = self.tuner(path)
                self.assertIn("Saved tuning report unavailable", tuner.snapshot()["error"])


if __name__ == "__main__":
    unittest.main()
