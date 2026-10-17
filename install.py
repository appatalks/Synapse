#!/usr/bin/env python3
"""Install SYNAPSE per-user; never install drivers or download model weights."""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

from synapse_app.updates import install_archive, latest_release, release_archive, validate_archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, help="private installation directory (also puts the launcher in PREFIX/bin)")
    parser.add_argument("--local-package", type=Path, help="install an explicitly supplied local SYNAPSE.pyz without a release download")
    parser.add_argument("--llama-server", help="backend path to save in the launcher")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--accelerated", action="store_true", help="set up the experimental Linux/NVIDIA backend")
    choice.add_argument("--no-accelerated", action="store_true", help="do not offer accelerated-backend setup")
    parser.add_argument("--launch", action="store_true", help="open SYNAPSE after installation")
    args = parser.parse_args()
    directory = (args.prefix or Path.home() / ".local/share/synapse").expanduser().absolute()
    launcher_dir = directory / "bin" if args.prefix else Path.home() / ".local/bin"
    target = directory / "SYNAPSE.pyz"
    receipt_file = directory / "install.json"
    if directory.is_symlink() or target.is_symlink() or receipt_file.is_symlink():
        parser.error("Refusing a symlinked installation path.")
    if directory.exists() and any(directory.iterdir()) and not receipt_file.is_file():
        parser.error("The installation directory contains unrelated files; choose a new --prefix.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if hasattr(os, "getuid") and (directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o022):
        parser.error("Use a private, user-owned installation directory.")
    lock = directory / ".install.lock"
    try:
        with lock.open("x") as stream:
            stream.write(str(os.getpid()))
    except FileExistsError:
        parser.error("Another install may be running. Inspect the existing .install.lock before retrying.")
    staged = None
    try:
        release = None if args.local_package else latest_release()
        if args.local_package:
            version = validate_archive(args.local_package)
            descriptor, name = tempfile.mkstemp(prefix=".synapse-local-", dir=directory)
            os.close(descriptor)
            staged = Path(name)
            shutil.copyfile(args.local_package, staged)
            print("Installing the explicitly supplied local preview package.")
        elif release:
            staged = release_archive(release, directory)
            version = release["version"]
            print(f"Verified public release v{version}.")
        else:
            print("No public release is available yet. Installing a clearly labeled main-branch preview.")
            with tempfile.TemporaryDirectory(prefix="synapse-preview-") as build:
                subprocess.run([sys.executable, str(Path(__file__).parent / "scripts/build_synapse.py"),
                                "--output", build], check=True)
                version = validate_archive(Path(build) / "SYNAPSE.pyz")
                descriptor, name = tempfile.mkstemp(prefix=".synapse-preview-", dir=directory)
                os.close(descriptor)
                staged = Path(name)
                shutil.copyfile(Path(build) / "SYNAPSE.pyz", staged)
        receipt = {"schema_version": 1, "app": "SYNAPSE", "mode": "managed",
                   "version": version, "channel": "release" if release else "preview"}
        previous = {}
        if receipt_file.exists():
            previous = json.loads(receipt_file.read_text())
            if previous.get("app") != "SYNAPSE" or previous.get("mode") != "managed":
                raise ValueError("Refusing to replace an unrecognized installation.")
        backend_args = previous.get("backend_args", ["--llama-server", os.environ.get("LLAMA_SERVER", "llama-server")])
        if args.llama_server:
            backend_args = ["--llama-server", args.llama_server]
        accelerated = args.accelerated
        if sys.platform == "linux" and not args.no_accelerated and not accelerated:
            try:
                with open("/dev/tty", "r+") as terminal:
                    terminal.write("Offer experimental Linux/NVIDIA acceleration? Builds native code; no model downloads. [y/N] ")
                    terminal.flush()
                    accelerated = terminal.readline().strip().lower() in ("y", "yes")
            except OSError:
                print("No interactive terminal. For optional Linux/NVIDIA setup, rerun with --accelerated.")
        if accelerated:
            if sys.platform != "linux":
                raise ValueError("Experimental acceleration is Linux/NVIDIA-only. Standard app execution is cross-platform.")
            legacy = Path.home() / ".local/share/vrambridge/hybrid-profile.json"
            if legacy.is_file():
                from synapse_app.app import read_hybrid_profile
                read_hybrid_profile(legacy)
                print("Reusing the existing verified-format research installation profile; no backend rebuild.")
                backend_args += ["--hybrid-profile", str(legacy)]
            else:
                profile = directory / "backend/hybrid-profile.json"
                subprocess.run([sys.executable, str(Path(__file__).parent / "scripts/setup_acceleration.py"),
                                "--prefix", str(directory / "backend")], check=True)
                backend_args += ["--hybrid-profile", str(profile)]
                backend_args[1] = str(json.loads(profile.read_text())["executable"])
        receipt["backend_args"] = backend_args
        launcher_dir.mkdir(parents=True, exist_ok=True)
        launcher = launcher_dir / ("synapse.cmd" if sys.platform == "win32" else "synapse")
        if launcher.is_symlink() or launcher.exists() and "# SYNAPSE managed launcher" not in launcher.read_text():
            raise ValueError("The launcher path belongs to another program; choose a different --prefix.")
        if target.exists():
            install_archive(staged, target, receipt)
        else:
            os.replace(staged, target)
            with receipt_file.open("x") as stream:
                json.dump(receipt, stream, indent=2)
            receipt_file.chmod(0o600)
        command = [sys.executable, str(target), *backend_args]
        if sys.platform == "win32":
            text = "@rem # SYNAPSE managed launcher\n@" + subprocess.list2cmdline(command) + " %*\n"
        else:
            text = "#!/usr/bin/env bash\n# SYNAPSE managed launcher\nexec " + shlex.join(command) + ' "$@"\n'
        launcher_temp = launcher.with_suffix(".part")
        with launcher_temp.open("x") as stream:
            stream.write(text)
        launcher_temp.chmod(0o755)
        os.replace(launcher_temp, launcher)
        print(f"\nSYNAPSE v{version} installed. Run:\n  {launcher}\n")
        if not shutil.which(backend_args[1]) and not accelerated:
            print("A llama-server backend is still required. Supply --llama-server /path/to/llama-server when launching.")
        print("Click the version in the sidebar for release details and verified application updates.")
        lock.unlink(missing_ok=True)
        if args.launch:
            subprocess.run(command, check=True)
    finally:
        lock.unlink(missing_ok=True)
        if staged:
            staged.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"SYNAPSE installation failed: {error}") from error
