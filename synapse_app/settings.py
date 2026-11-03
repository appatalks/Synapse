"""Private, restart-safe settings for the last successfully loaded model."""

import json
import logging
import os
from pathlib import Path
import tempfile

from .tuning import LOAD_FIELDS


LOG = logging.getLogger("synapse.settings")
INTEGER_LIMITS = {
    "context": (512, 262144), "cpu_threads": (1, 65536), "batch_threads": (1, 65536),
    "expert_cache_mib": (0, 65536), "fit_target_mib": (128, 65536), "cpu_poll": (0, 100),
    "op_offload_min_batch": (1, 8192), "draft_tokens": (1, 32),
}
CHOICES = {
    "execution_mode": ("auto", "standard", "hybrid"), "placement": ("auto", "cpu"),
    "load_mode": ("auto", "none"), "kv_cache_type": ("f16", "q8_0"),
    "draft_type": ("none", "dflash", "mtp"), "hybrid_variant": ("auto", "classic", "hosted"),
}


def valid_settings(settings: object) -> bool:
    if not isinstance(settings, dict) or set(settings) != set(LOAD_FIELDS):
        return False
    for key in ("model", "draft_model"):
        value = settings[key]
        if key == "draft_model" and value is None:
            continue
        if not isinstance(value, str) or not value.strip() or len(value) > 4096:
            return False
    return (type(settings["host_op_offload"]) is bool and
            all(type(settings[key]) is int and low <= settings[key] <= high
                for key, (low, high) in INTEGER_LIMITS.items()) and
            all(settings[key] in values for key, values in CHOICES.items()))


class ModelSettings:
    def __init__(self, store: Path | None):
        self.store = store
        self.settings: dict | None = None
        self.error: str | None = None
        if store is not None:
            try:
                if store.stat().st_size > 64 * 1024:
                    raise ValueError("Saved model settings exceed 64 KiB.")
                saved = json.loads(store.read_text(encoding="utf-8"))
                if (not isinstance(saved, dict) or saved.get("schema_version") != 1 or
                        not valid_settings(saved.get("settings"))):
                    raise ValueError("Saved model settings have an unsupported format.")
                self.settings = saved["settings"]
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as exc:
                self.error = f"Saved model settings unavailable: {exc}"
                LOG.error("%s", self.error)

    def remember(self, settings: dict) -> None:
        temporary = None
        try:
            if not valid_settings(settings):
                raise ValueError("Refusing to save invalid model settings.")
            if self.store is not None:
                self.store.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with tempfile.NamedTemporaryFile(mode="w", dir=self.store.parent, prefix=".model-settings-",
                                                 encoding="utf-8", delete=False) as output:
                    temporary = Path(output.name)
                    json.dump({"schema_version": 1, "settings": settings}, output, indent=2)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.replace(self.store)
            self.settings = dict(settings)
            self.error = None
        except (OSError, ValueError) as exc:
            self.error = f"Could not save model settings: {exc}"
            LOG.error("%s", self.error)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
