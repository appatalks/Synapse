import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from synapse_app.strata_profile import Installation
from synapse_app.settings import read_context_policy

from synapse_app import profiles
from synapse_app.tuning import AutoTuner, EngineChoices, client_settings, native_cache_banks


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


class ExecutionProfileTests(unittest.TestCase):
    def test_shared_context_policy_is_bounded_and_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context-policy.json"
            self.assertIsNone(read_context_policy(path))
            path.write_text(json.dumps({"schema_version": 1, "default_context": 131072}))
            self.assertEqual(read_context_policy(path), 131072)
            for value in (True, 0, 262145):
                path.write_text(json.dumps({"schema_version": 1, "default_context": value}))
                with self.assertRaises(ValueError):
                    read_context_policy(path)
    def test_strata_binding_and_component_changes_invalidate_eligibility(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model, backend, configuration = (root / name for name in ("model.gguf", "backend.py", "config.json"))
            for path in (model, backend, configuration):
                path.write_bytes(b"bound asset")
            import os
            os.utime(backend, ns=(0, 0))

            def identity(path):
                info = path.stat()
                return {"path": str(path), "size": info.st_size, "mtime_ns": info.st_mtime_ns}

            profile = root / "provider.json"
            profile.write_text(json.dumps({
                "schema_version": 1, "executable": str(backend), "configuration": str(configuration),
                "model": identity(model), "minimum_vram_mib": 14336, "maximum_context": 16384,
                "cache_mib": 6144, "cache_slots": 128, "build_files": [identity(backend), identity(configuration)],
                "qualification_sha256": "0" * 64}))
            with mock.patch("synapse_app.strata_profile.sys.platform", "linux"):
                provider = Installation(profile)
            hardware = {"platform": "Linux", "gpus": [{"name": "NVIDIA fixture", "vram_total_bytes": 16 * 1024**3}]}
            self.assertTrue(provider.eligible(model, hardware, "auto", "f16"))
            self.assertFalse(provider.eligible(model, hardware, "cpu", "f16"))
            self.assertFalse(provider.eligible(model, hardware, "auto", "q8_0"))
            self.assertFalse(provider.eligible(model, {**hardware, "gpus": []}, "auto", "f16"))
            before = provider.identity()
            other = root / "other.gguf"
            other.write_bytes(b"other model")
            base_machine = {"backend": "native"}
            optional_machine = {**base_machine, "strata": before}
            self.assertEqual(EngineChoices.key(other, "f16", base_machine),
                             EngineChoices.key(other, "f16", optional_machine))
            self.assertNotEqual(EngineChoices.key(model, "f16", base_machine),
                                EngineChoices.key(model, "f16", optional_machine))
            configuration.write_bytes(b"changed asset")
            self.assertFalse(provider.available(model))
            self.assertNotEqual(before, provider.identity())

    def test_metadata_capabilities_gate_components_without_model_names(self):
        cpu = {item["id"]: item for item in profiles.assess({})}
        self.assertEqual(cpu["standard-auto"]["eligibility"], "candidate")
        self.assertEqual(cpu["standard-cpu"]["eligibility"], "candidate")
        self.assertEqual(cpu["hybrid-classic"]["eligibility"], "unavailable")
        staged = {item["id"]: item for item in profiles.assess({"moe": True, "hybrid": True, "hosted": True})}
        self.assertEqual(staged["hybrid-classic"]["eligibility"], "candidate")
        self.assertEqual(staged["hybrid-hosted"]["missing_requirements"], ["direct"])
        direct = profiles.assess({"moe": True, "hybrid": True, "hosted": True, "direct": True,
                                 "native_cache": True, "strata": True})
        self.assertTrue(all(item["eligibility"] == "candidate" for item in direct))
        self.assertTrue(all(item["requires_runtime_verification"] for item in direct))

    def test_catalog_rejects_unguarded_engines_and_claimed_qualification(self):
        base = {"schema_version": 1, "profiles": [
            profiles.definition(name) for name in ("standard-auto", "standard-cpu", "hybrid-classic", "hybrid-hosted",
                                                  "standard-native-cache", "strata-mtp")]}
        for field, value in (("requires", []), ("qualification", "qualified"),
                             ("components", ["expert-sharing", "skip-experts"]),
                             ("settings", {"execution_mode": "hybrid", "placement": "auto",
                                           "hybrid_variant": "classic", "environment": {"TAIL_SKIP": "7"}})):
            altered = json.loads(json.dumps(base))
            altered["profiles"][2][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                profiles.validate(altered)
        missing = {**base, "profiles": base["profiles"][:3]}
        with self.assertRaises(ValueError):
            profiles.validate(missing)

    def test_profile_settings_cannot_be_mutated_by_a_trial(self):
        settings = profiles.settings("hybrid-classic")
        settings["hybrid_variant"] = "hosted"
        self.assertEqual(profiles.settings("hybrid-classic")["hybrid_variant"], "classic")

    def test_native_cache_profile_requires_a_positive_measured_budget(self):
        settings = {**profiles.settings("standard-native-cache"), "expert_cache_mib": 4096}
        self.assertEqual(profiles.identify(settings), "standard-native-cache")
        self.assertEqual(profiles.identify({**settings, "expert_cache_mib": 0}), "standard-auto")
        entry = {"settings": settings, "profile_id": "standard-native-cache",
                 "profile_revision": profiles.revision("standard-native-cache")}
        self.assertTrue(profiles.measured_profile_current(entry))
        self.assertFalse(profiles.measured_profile_valid({**entry, "settings": {**settings, "expert_cache_mib": 0}}))

    def test_native_cache_candidates_require_qualified_platform_gpu_and_precision(self):
        hardware = {"platform": "Linux", "gpus": [{"name": "NVIDIA fixture", "vram_total_bytes": 16 * 1024**3}]}
        options = {"supported": True, "compatible": True, "placement": "auto", "kv_cache_type": "f16"}
        self.assertEqual(native_cache_banks(hardware, **options), [15360, 12288, 8192, 4096, 2048, 1024])
        larger = {**hardware, "gpus": [{"name": "NVIDIA fixture", "vram_total_bytes": 24 * 1024**3}]}
        self.assertEqual(native_cache_banks(larger, **options)[0], 23552)
        for changes in ({"supported": False}, {"compatible": False}, {"placement": "cpu"}, {"kv_cache_type": "q8_0"}):
            self.assertEqual(native_cache_banks(hardware, **{**options, **changes}), [])
        for changed in ({**hardware, "platform": "Windows"}, {**hardware, "gpus": []},
                        {**hardware, "gpus": [{"name": "NVIDIA fixture", "vram_total_bytes": 1024**3}]}):
            self.assertEqual(native_cache_banks(changed, **options), [])

    def test_model_bound_choices_reject_stale_or_mismatched_profiles_without_rewriting_store(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.gguf"
            model.write_bytes(b"model identity")
            store = Path(directory) / "choices.json"
            entry = {
                "settings": {**profiles.settings("standard-cpu"), "context": 8192,
                             "cpu_threads": 8, "batch_threads": 16, "expert_cache_mib": 0, "kv_cache_type": "f16"},
                "goal": "balanced", "measured_at": 1.0, "decode_tokens_per_second": 20.0,
                "standard_decode_tokens_per_second": 20.0, "profile_id": "standard-cpu",
                "profile_revision": profiles.revision("standard-cpu"),
            }
            choices = EngineChoices(store)
            machine = {"backend_sha256": "build-one", "ram_gib": 64}
            choices.remember(model, machine, entry)
            saved = store.read_bytes()
            self.assertEqual(EngineChoices(store).lookup(model, "f16", machine), entry)
            self.assertIsNone(choices.lookup(model, "f16", {**machine, "backend_sha256": "build-two"}))
            with mock.patch.object(profiles, "revision", return_value="0" * 64):
                self.assertIsNone(EngineChoices(store).lookup(model, "f16", machine))
            self.assertEqual(store.read_bytes(), saved)
            for changes in ({"profile_id": "hybrid-hosted"}, {"profile_revision": None},
                            {"profile_id": None, "profile_revision": None}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    choices.remember(model, machine, {**entry, **changes})
            legacy = {key: value for key, value in entry.items() if not key.startswith("profile_")}
            choices.remember(model, machine, legacy)
            self.assertEqual(EngineChoices(store).lookup(model, "f16", machine), legacy)

    def test_optional_provider_choices_do_not_rewrite_legacy_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.gguf"
            model.write_bytes(b"model")
            store = Path(directory) / "choices.json"
            machine = {"backend": "same"}
            native = {
                "settings": {**profiles.settings("standard-auto"), "context": 8192, "cpu_threads": 8,
                             "batch_threads": 16, "expert_cache_mib": 0, "kv_cache_type": "f16"},
                "goal": "balanced", "measured_at": 1, "decode_tokens_per_second": 20,
                "standard_decode_tokens_per_second": 20, "profile_id": "standard-auto",
                "profile_revision": profiles.revision("standard-auto")}
            choices = EngineChoices(store)
            choices.remember(model, machine, native)
            before = store.read_bytes()
            provider = {**native, "settings": {**native["settings"], **profiles.settings("strata-mtp")},
                        "measured_at": 2, "decode_tokens_per_second": 30, "profile_id": "strata-mtp",
                        "profile_revision": profiles.revision("strata-mtp")}
            choices.remember(model, machine, provider)
            self.assertEqual(store.read_bytes(), before)
            self.assertEqual(EngineChoices(store).lookup(model, "f16", machine)["profile_id"], "strata-mtp")
            choices.remember(model, machine, {**native, "measured_at": 3})
            self.assertEqual(EngineChoices(store).lookup(model, "f16", machine)["profile_id"], "standard-auto")


if __name__ == "__main__":
    unittest.main()
