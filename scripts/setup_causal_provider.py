#!/usr/bin/env python3
"""Install an already-qualified local causal backend package after explicit confirmation."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from synapse_app import app, causal_profile, telemetry


def install(source, model, destination, profile, machine, *, confirm):
    if confirm is not True:
        raise ValueError("Explicit confirmation is required to install and register the provider.")
    source, model = source.resolve(strict=True), model.resolve(strict=True)
    destination, profile = destination.absolute(), profile.absolute()
    if destination.exists() or profile.exists():
        raise ValueError("The provider destination and profile must not already exist.")
    metadata = app.model_metadata(model)
    with tempfile.TemporaryDirectory(prefix="synapse-causal-check-") as directory:
        candidate = Path(directory) / "candidate.json"
        candidate.write_text(json.dumps({"schema_version": 1, "backend_dir": str(source), "model": str(model)}))
        provider = causal_profile.Installation(candidate)
        if not provider.eligible(model, metadata, machine, causal_profile.MAX_CONTEXT):
            raise ValueError("The model, package, machine or driver does not match the qualified provider.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        profile.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.mkdir(mode=0o700)
        try:
            for name in causal_profile.COMPONENTS:
                shutil.copyfile(source / name, destination / name)
                (destination / name).chmod(0o755)
            candidate.write_text(json.dumps({"schema_version": 1, "backend_dir": str(destination),
                                             "model": str(model)}))
            provider = causal_profile.Installation(candidate)
            if not provider.eligible(model, metadata, machine, causal_profile.MAX_CONTEXT):
                raise ValueError("The installed components did not retain the qualified identities.")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", dir=profile.parent, prefix=".causal-profile-",
                                                 encoding="utf-8", delete=False) as output:
                    temporary = Path(output.name)
                    json.dump(provider.data, output, indent=2)
                    output.flush()
                    os.fsync(output.fileno())
                os.link(temporary, profile)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        except Exception:
            shutil.rmtree(destination)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-bin", type=Path, required=True, help="Local qualified package directory")
    parser.add_argument("--model", type=Path, required=True, help="The exact locally qualified GGUF")
    parser.add_argument("--destination", type=Path, required=True, help="New backend directory")
    parser.add_argument("--profile", type=Path, default=app.user_config_dir() / "causal-profile.json")
    parser.add_argument("--confirm", action="store_true", help="Confirm installation and profile registration")
    args = parser.parse_args()
    if not args.confirm:
        parser.exit(1, "Provider installation requires --confirm.\n")
    try:
        probe = telemetry.NvidiaProbe()
        try:
            gpus = probe.sample()
        finally:
            probe.close()
        machine = {"platform": "Linux" if sys.platform == "linux" else sys.platform, "gpus": gpus}
        install(args.source_bin, args.model, args.destination, args.profile, machine, confirm=args.confirm)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Provider installation failed: {exc}\n")
    print("Qualified provider installed. Restart Synapse to discover it.")


if __name__ == "__main__":
    main()
