# Install SYNAPSE per-user. Backend downloads require consent; no drivers or models.
[CmdletBinding()]
param(
    [string]$Prefix,
    [string]$LlamaServer,
    [switch]$SwitchBackend,
    [string]$LocalPackage,
    [switch]$NoShortcuts,
    [switch]$NoPath,
    [switch]$NonInteractive,
    [switch]$WithPi,
    [switch]$NoPi,
    [switch]$Launch
)

$ErrorActionPreference = 'Stop'
$pythonArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = 'py'
    $pythonArgs = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = 'python'
} else {
    throw 'SYNAPSE requires Python 3.10+. Install Python from https://www.python.org/downloads/windows/ and rerun this installer.'
}
& $python @pythonArgs -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
if ($LASTEXITCODE -ne 0) {
    throw 'SYNAPSE requires a working Python 3.10+ installation. Check py -3 --version or python --version.'
}

$installerArgs = @('--no-accelerated')
if ($Prefix) { $installerArgs += @('--prefix', $Prefix) }
if ($LlamaServer) { $installerArgs += @('--llama-server', $LlamaServer) }
if ($SwitchBackend) { $installerArgs += '--switch-backend' }
if ($LocalPackage) { $installerArgs += @('--local-package', (Resolve-Path -LiteralPath $LocalPackage).Path) }
if ($NoShortcuts) { $installerArgs += '--no-shortcuts' }
if ($NoPath) { $installerArgs += '--no-path' }
if ($NonInteractive) { $installerArgs += '--non-interactive' }
if ($WithPi) { $installerArgs += '--with-pi' }
if ($NoPi) { $installerArgs += '--no-pi' }
if ($Launch) { $installerArgs += '--launch' }

Write-Host 'Installing SYNAPSE for this user only. No administrator access is needed.'
if (-not $Prefix) {
    if (-not $NoShortcuts) { Write-Host 'Creates SYNAPSE shortcuts on your Desktop and in the Start Menu.' }
    if (-not $NoPath) { Write-Host 'Adds the launcher folder to your user PATH for the synapse command.' }
}
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'install.py')) {
    & $python @pythonArgs (Join-Path $PSScriptRoot 'install.py') @installerArgs
    exit $LASTEXITCODE
}

$bootstrap = @'
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

url = 'https://api.github.com/repos/appatalks/synapse/zipball/main'
request = urllib.request.Request(url, headers={'User-Agent': 'SYNAPSE-installer'})
print('Downloading the SYNAPSE installer from appatalks/synapse...', flush=True)
with urllib.request.urlopen(request, timeout=30) as response:
    body = response.read(16 * 1024 * 1024 + 1)
if len(body) > 16 * 1024 * 1024:
    raise SystemExit('Installer source exceeds its size limit.')
with tempfile.TemporaryDirectory(prefix='synapse-installer-') as directory:
    root = Path(directory).resolve()
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if sum(info.file_size for info in archive.infolist()) > 32 * 1024 * 1024:
            raise SystemExit('Installer source is unexpectedly large.')
        prefixes = {name.split('/', 1)[0] for name in archive.namelist()}
        if len(prefixes) != 1:
            raise SystemExit('Unexpected source archive layout.')
        prefix = prefixes.pop() + '/'
        for name in archive.namelist():
            relative = name.removeprefix(prefix)
            parts = Path(relative).parts
            allowed = relative in ('install.py', 'LICENSE', 'scripts/build_synapse.py',
                                    'scripts/setup_acceleration.py') or (
                len(parts) >= 2 and parts[0] == 'synapse_app' and
                Path(relative).suffix in ('.py', '.mjs', '.js', '.json', '.svg', '.ico', '.html', '.css'))
            if not allowed or name.endswith('/'):
                continue
            destination = root / relative
            if not destination.resolve().is_relative_to(root):
                raise SystemExit('Unsafe installer archive path.')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(name))
    try:
        result = subprocess.run([sys.executable, str(root / 'install.py'), *sys.argv[1:]])
    except KeyboardInterrupt:
        raise SystemExit(130)
    raise SystemExit(result.returncode)
'@
& $python @pythonArgs -c $bootstrap @installerArgs
exit $LASTEXITCODE