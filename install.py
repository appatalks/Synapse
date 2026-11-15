#!/usr/bin/env python3
"""Install SYNAPSE per-user; never install drivers or download model weights."""

import argparse
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

from synapse_app.updates import download, install_archive, latest_release, release_archive, validate_archive


WINDOWS_BACKEND_RELEASE = "b11669"
WINDOWS_BACKEND_HASHES = {
    ("cpu", "x64"): "37b3efcf962847ca869745fd4ccf7f5e7e8dacfeff9fa3523b4ca8cdc66d632b",
    ("cpu", "arm64"): "9cff39ffed17edcd03a7d876073f74d7b48cd43a1e5eafdd59ee094185ad871b",
    ("vulkan", "x64"): "2c07574e7bde71321cb785282b20cc821e951132149eeceeea32ddebdbf0598e",
    ("vulkan", "arm64"): "963d3b185362cadca3de643409f916a5ce95dd0f7fd8617ba9ee5d8833ac1ef3",
}


WINDOWS_PATH_VALUE = r"""
function Get-SynapseUserPath {
    param([string]$Previous, [string]$Directory)
    $found = @($Previous -split ';' | Where-Object {
        [Environment]::ExpandEnvironmentVariables($_).Trim().TrimEnd('\') -ieq $Directory.TrimEnd('\')
    }).Count -gt 0
    if ($found) { return $Previous }
    if ($Previous) { return $Previous.TrimEnd(';') + ';' + $Directory }
    return $Directory
}
"""

WINDOWS_INTEGRATION = WINDOWS_PATH_VALUE + r"""
$ErrorActionPreference = 'Stop'
$settings = $env:SYNAPSE_INSTALL_SETTINGS | ConvertFrom-Json
if ($settings.shortcuts) {
    $folders = $settings.shortcut_dirs
    if ($null -eq $folders) {
        $folders = @([Environment]::GetFolderPath('DesktopDirectory'),
                     [Environment]::GetFolderPath('Programs'))
    }
    $shell = New-Object -ComObject WScript.Shell
    foreach ($folder in $folders) {
        if (-not $folder) { throw 'Windows did not provide a shortcut folder.' }
        $path = Join-Path $folder 'SYNAPSE.lnk'
        $shortcut = $shell.CreateShortcut($path)
        if ((Test-Path -LiteralPath $path) -and $shortcut.Description -ne 'SYNAPSE managed launcher') {
            throw "Refusing to replace an unrelated shortcut: $path"
        }
    }
    foreach ($folder in $folders) {
        [IO.Directory]::CreateDirectory($folder) | Out-Null
        $shortcut = $shell.CreateShortcut((Join-Path $folder 'SYNAPSE.lnk'))
        $shortcut.TargetPath = $settings.executable
        $shortcut.Arguments = $settings.arguments
        $shortcut.WorkingDirectory = $settings.directory
        $shortcut.Description = 'SYNAPSE managed launcher'
        $shortcut.IconLocation = $settings.icon + ',0'
        $shortcut.Save()
    }
}
if ($settings.add_path) {
    $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment')
    try {
        $previous = $key.GetValue('Path', '', 'DoNotExpandEnvironmentNames')
        $kind = if ($key.GetValueNames() -contains 'Path') { $key.GetValueKind('Path') } else { 'ExpandString' }
        $updated = Get-SynapseUserPath $previous $settings.launcher_dir
        if ($updated -ne $previous) { $key.SetValue('Path', $updated, $kind) }
    } finally { $key.Dispose() }
    if ($updated -ne $previous) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace SynapseInstall {
    public static class EnvironmentChange {
        [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern IntPtr SendMessageTimeoutW(IntPtr window, uint message,
            UIntPtr param, string text, uint flags, uint timeout, out UIntPtr result);
    }
}
'@
        $result = [UIntPtr]::Zero
        [SynapseInstall.EnvironmentChange]::SendMessageTimeoutW([IntPtr]0xffff, 0x1a,
            [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$result) | Out-Null
    }
}
"""


def windows_integration(launcher_dir, command, shortcuts=True, add_path=True, shortcut_dirs=None):
    icon = launcher_dir.parent / "SYNAPSE.ico"
    if shortcuts:
        if icon.is_symlink():
            raise ValueError("Refusing a symlinked shortcut icon.")
        shutil.copyfile(Path(__file__).parent / "synapse_app/web/icon.ico", icon)
    settings = {"launcher_dir": str(launcher_dir), "directory": str(launcher_dir.parent),
                "executable": command[0], "arguments": subprocess.list2cmdline(command[1:]),
                "icon": str(icon),
                "shortcuts": shortcuts, "add_path": add_path,
                "shortcut_dirs": [str(folder) for folder in shortcut_dirs] if shortcut_dirs is not None else None}
    environment = {**os.environ, "SYNAPSE_INSTALL_SETTINGS": json.dumps(settings)}
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", WINDOWS_INTEGRATION],
                   env=environment, check=True)


def windows_command(arguments):
    quoted = []
    for argument in arguments:
        value = str(argument)
        if any(character in value for character in ('"', "\r", "\n")):
            raise ValueError("Windows launcher arguments cannot contain quotes or newlines")
        value = value.replace("%", "%%")
        trailing = len(value) - len(value.rstrip("\\"))
        quoted.append('"' + value + "\\" * trailing + '"')
    return " ".join(quoted)


def install_windows_backend(directory, variant):
    machine = os.environ.get("PROCESSOR_ARCHITEW6432", platform.machine()).lower()
    architecture = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    expected = WINDOWS_BACKEND_HASHES.get((variant, architecture))
    if sys.platform != "win32" or expected is None:
        raise ValueError("Automatic backend installation supports only x64/ARM64 Windows CPU or Vulkan builds.")
    name = f"llama-{WINDOWS_BACKEND_RELEASE}-bin-win-{variant}-{architecture}.zip"
    url = f"https://github.com/ggml-org/llama.cpp/releases/download/{WINDOWS_BACKEND_RELEASE}/{name}"
    print(f"Downloading {name} from ggml-org/llama.cpp...", flush=True)
    body = download(url, 128 * 1024 * 1024)
    if hashlib.sha256(body).hexdigest() != expected:
        raise ValueError("llama.cpp backend checksum verification failed. Nothing was installed.")
    if directory.is_symlink():
        raise ValueError("Refusing a symlinked backend installation directory.")
    root = Path(tempfile.mkdtemp(prefix=f"llama-{WINDOWS_BACKEND_RELEASE}-{variant}-", dir=directory))
    installed = False
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            entries = archive.infolist()
            if len(entries) > 512 or sum(entry.file_size for entry in entries) > 512 * 1024 * 1024:
                raise ValueError("Backend archive is unexpectedly large.")
            seen = set()
            for entry in entries:
                relative = entry.filename.replace("\\", "/").rstrip("/")
                parts = relative.split("/")
                destination = root / relative
                if (not relative or any(part in ("", ".", "..") or ":" in part or
                                        part.rstrip(" .") != part or Path(part).is_reserved() for part in parts) or
                        not destination.resolve().is_relative_to(root.resolve()) or
                        stat.S_ISLNK(entry.external_attr >> 16) or relative.casefold() in seen):
                    raise ValueError("Unsafe or duplicate backend archive path.")
                seen.add(relative.casefold())
            for entry in entries:
                destination = root / entry.filename.replace("\\", "/")
                if entry.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry) as source, destination.open("xb") as output:
                        shutil.copyfileobj(source, output)
        servers = list(root.rglob("llama-server.exe"))
        if len(servers) != 1:
            raise ValueError("Backend archive must contain exactly one llama-server.exe.")
        executable = servers[0]
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("LLAMA_", "GGML_", "STRATA_", "VRAMBRIDGE_"))}
        for option in ("--version", "--help"):
            result = subprocess.run([str(executable), option], cwd=executable.parent, env=environment,
                                    capture_output=True, text=True, errors="replace", timeout=30)
            output = result.stdout + result.stderr
            valid = (re.search(r"(?m)^version:\s*(?:11669\b|\S+\s+\(build 11669,\s*commit [0-9a-f]+\))", output)
                     if option == "--version" else
                     all(flag in output for flag in ("--model", "--host", "--port")))
            if result.returncode != 0 or not valid:
                raise ValueError("The downloaded llama-server.exe could not pass its startup checks.\n"
                                 "Check Windows security, required Visual C++ runtime and existing GPU drivers.\n"
                                 + output[-2000:])
        installed = True
        print(f"Verified llama.cpp {WINDOWS_BACKEND_RELEASE} ({variant}) installed at {executable}")
        return str(executable)
    except zipfile.BadZipFile as error:
        raise ValueError("The backend ZIP is invalid or corrupt.") from error
    finally:
        if not installed:
            shutil.rmtree(root)


def select_backend(value, package, interactive=True, directory=None):
    resolved = shutil.which(value)
    if resolved:
        return resolved
    if sys.platform != "win32":
        return value
    if value == "llama-server":
        for search_directory in (package.parent, Path(__file__).parent):
            candidate = search_directory / "llama-server.exe"
            if candidate.is_file():
                return str(candidate.resolve())
    print("SYNAPSE needs llama.cpp's llama-server.exe, not Ollama.")
    if interactive and sys.stdin.isatty() and sys.stdout.isatty():
        destination = directory or package.parent
        print(f"Automatic setup can download verified official llama.cpp {WINDOWS_BACKEND_RELEASE}\n"
              f"into a new private folder under {destination}.\n"
              "No existing backend, drivers, system packages or model weights will be changed.")
        if input("Auto-install llama-server.exe and configure SYNAPSE? [y/N]: ").strip().lower() in ("y", "yes"):
            print("1. CPU (default; no GPU driver required)\n"
                  "2. GPU via Vulkan (requires an existing Vulkan-capable GPU driver)")
            while True:
                variant = input("Choose backend [1/2, Enter for CPU]: ").strip()
                if variant in ("", "1", "2"):
                    break
                print("Please choose 1 or 2.")
            try:
                return install_windows_backend(destination, "vulkan" if variant == "2" else "cpu")
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                print(f"Automatic backend setup failed: {error}\n"
                      "No fallback backend was selected. Choose an existing backend below or set up later.")
        while True:
            selected = input("Path to llama-server.exe (Enter to set up later): ").strip().strip('"')
            if not selected:
                break
            candidate = Path(selected).expanduser()
            if candidate.is_dir():
                candidate = candidate / "llama-server.exe"
            if candidate.name.lower() == "llama-server.exe" and candidate.is_file():
                return str(candidate.resolve())
            print("That location does not contain llama-server.exe. Please try again.")
        print("For manual setup, extract a Windows llama.cpp release from\n"
                    "https://github.com/ggml-org/llama.cpp/releases with all its DLLs beside llama-server.exe.")
    return value


def confirm_pi():
    prompt = ("Optional Pi coding agent: reuse an existing Pi, or download a verified standalone build.\n"
              "This adds a Synapse provider to Pi's user configuration; credentials and existing defaults are preserved.\n"
              "Pi can edit files and run commands with your user permissions; it is not a sandbox.\n"
              "Install/configure Pi for SYNAPSE? [y/N]: ")
    if sys.platform != "win32":
        try:
            with open("/dev/tty", "r+") as terminal:
                terminal.write(prompt)
                terminal.flush()
                return terminal.readline().strip().lower() in ("y", "yes")
        except OSError:
            return False
    if sys.stdin.isatty() and sys.stdout.isatty():
        return input(prompt).strip().lower() in ("y", "yes")
    return False


def setup_pi(directory, launcher_dir, receipt):
    from synapse_app import pi_setup
    executable = pi_setup.existing_pi()
    if executable is None:
        saved = receipt.get("pi_executable")
        if isinstance(saved, str) and Path(saved).is_file():
            executable = saved
    if executable is None:
        executable = pi_setup.install_pi(directory)
    else:
        print("Reusing the existing Pi installation; no replacement or update.")
    context = 4096
    try:
        context = pi_setup.loaded_context()
    except (OSError, ValueError, http.client.HTTPException) as error:
        print(f"Loaded context unavailable: {error}\nUsing conservative 4K Pi defaults.\n"
              "After loading a model, run synapse --configure-pi to refresh these limits.")
    launcher = launcher_dir / ("synapse-pi.cmd" if sys.platform == "win32" else "synapse-pi")
    if launcher.is_symlink() or launcher.exists() and "# SYNAPSE managed Pi launcher" not in launcher.read_text():
        raise ValueError("The synapse-pi launcher belongs to another program; it was not replaced.")
    config = pi_setup.configure_pi(context=context)
    if sys.platform == "win32":
        command = "call " if Path(executable).suffix.lower() in (".cmd", ".bat") else ""
        text = ("@rem # SYNAPSE managed Pi launcher\n@chcp 65001 >nul\n@setlocal DisableDelayedExpansion\n@" +
                command + windows_command([executable]) + " %*\n")
    else:
        text = "#!/usr/bin/env bash\n# SYNAPSE managed Pi launcher\nexec " + shlex.join([executable]) + ' "$@"\n'
    descriptor, name = tempfile.mkstemp(prefix=".synapse-pi-launcher-", dir=launcher_dir)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        staged.chmod(0o755)
        os.replace(staged, launcher)
    finally:
        staged.unlink(missing_ok=True)
    receipt["pi_executable"] = executable
    pi_setup.write_config(directory / "install.json", receipt)
    print(f"Pi configured in {config}. Start with {launcher}\n"
          "In Pi, use /model and select Synapse Local; keep a model loaded in Synapse.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, help="private installation directory (also puts the launcher in PREFIX/bin)")
    parser.add_argument("--local-package", type=Path, help="install an explicitly supplied local SYNAPSE.pyz without a release download")
    parser.add_argument("--llama-server", help="backend path to save in the launcher")
    parser.add_argument("--non-interactive", action="store_true", help="skip interactive backend, acceleration and Pi offers")
    pi_choice = parser.add_mutually_exclusive_group()
    pi_choice.add_argument("--with-pi", action="store_true", help="consent to optional Pi installation and configuration")
    pi_choice.add_argument("--no-pi", action="store_true", help="skip the optional Pi offer")
    parser.add_argument("--windows-integration", action="store_true", help="also register Windows launchers for a custom --prefix")
    parser.add_argument("--no-shortcuts", action="store_true", help="skip Windows Desktop and Start Menu shortcuts")
    parser.add_argument("--no-path", action="store_true", help="do not add the Windows launcher directory to user PATH")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--accelerated", action="store_true", help="set up the experimental Linux/NVIDIA backend")
    choice.add_argument("--no-accelerated", action="store_true", help="do not offer accelerated-backend setup")
    parser.add_argument("--launch", action="store_true", help="open SYNAPSE after installation")
    args = parser.parse_args()
    windows = sys.platform == "win32"
    default_directory = (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Programs/SYNAPSE"
                         if windows else Path.home() / ".local/share/synapse")
    directory = (args.prefix or default_directory).expanduser().absolute()
    launcher_dir = directory / "bin" if args.prefix or windows else Path.home() / ".local/bin"
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
            if isinstance(previous.get("pi_executable"), str):
                receipt["pi_executable"] = previous["pi_executable"]
        backend_args = previous.get("backend_args", ["--llama-server", os.environ.get("LLAMA_SERVER", "llama-server")])
        if args.llama_server:
            backend_args = ["--llama-server", args.llama_server]
        backend_args[1] = select_backend(backend_args[1], args.local_package or target,
                                         interactive=not args.non_interactive, directory=directory)
        accelerated = args.accelerated
        if sys.platform == "linux" and not args.no_accelerated and not accelerated and not args.non_interactive:
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
            text = ("@rem # SYNAPSE managed launcher\n@chcp 65001 >nul\n"
                    "@setlocal DisableDelayedExpansion\n@" + windows_command(command) + " %*\n")
        else:
            text = "#!/usr/bin/env bash\n# SYNAPSE managed launcher\nexec " + shlex.join(command) + ' "$@"\n'
        launcher_temp = launcher.with_suffix(".part")
        with launcher_temp.open("x", encoding="utf-8") as stream:
            stream.write(text)
        launcher_temp.chmod(0o755)
        os.replace(launcher_temp, launcher)
        if windows and (not args.prefix or args.windows_integration):
            windows_integration(launcher_dir, command, shortcuts=not args.no_shortcuts, add_path=not args.no_path)
            if not args.no_shortcuts:
                print("Desktop and Start Menu shortcuts created (SYNAPSE).")
            if not args.no_path:
                print("User PATH registered. Open a new terminal and run: synapse")
        print(f"\nSYNAPSE v{version} installed. Run:\n  {launcher}\n")
        if not shutil.which(backend_args[1]) and not accelerated:
            print("A llama-server backend is still required. Rerun this installer with\n"
                  "--llama-server followed by its path to remember it in your launchers.")
        print("Click the version in the sidebar for release details and verified application updates.")
        if args.with_pi or not args.no_pi and not args.non_interactive and confirm_pi():
            try:
                setup_pi(directory, launcher_dir, receipt)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                print(f"Optional Pi setup failed: {error}\nSYNAPSE remains installed. Rerun with --with-pi to retry.")
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
