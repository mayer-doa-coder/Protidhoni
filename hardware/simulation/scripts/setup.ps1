[CmdletBinding()]
param(
    [switch]$SkipImagePull
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$simulationRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $simulationRoot ".runtime"
$checkout = Join-Path $runtimeRoot "Meshtasticator"
$venv = Join-Path $runtimeRoot ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$versionsPath = Join-Path $simulationRoot "versions.json"
$requirementsPath = Join-Path $simulationRoot "requirements-meshtasticator.txt"
$tool = Join-Path $PSScriptRoot "phase5_tools.py"
$protocolRoot = Join-Path (Split-Path -Parent $simulationRoot) "protocol"
$gatewayRoot = Join-Path (Split-Path -Parent $simulationRoot) "gateway"

function Assert-LastExitCode([string]$Activity) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Activity failed with exit code $LASTEXITCODE."
    }
}

foreach ($command in @("git", "docker", "py")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command '$command' was not found on PATH."
    }
}

$versions = Get-Content -LiteralPath $versionsPath -Raw | ConvertFrom-Json
$commit = [string]$versions.meshtasticator.commit
$repository = [string]$versions.meshtasticator.repository
$daemonImage = [string]$versions.meshtastic_daemon.image

& py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12), sys.version"
Assert-LastExitCode "Python 3.12 check"
& docker version --format '{{.Server.Version}}' | Out-Null
Assert-LastExitCode "Docker engine check"

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $checkout ".git"))) {
    if (Test-Path -LiteralPath $checkout) {
        throw "Runtime checkout path exists but is not a Git repository: $checkout"
    }
    & git clone --no-checkout $repository $checkout
    Assert-LastExitCode "Meshtasticator clone"
}

$origin = (& git -C $checkout remote get-url origin).Trim()
Assert-LastExitCode "Meshtasticator origin check"
$normalizedOrigin = ($origin.TrimEnd("/") -replace '\.git$', '')
$normalizedRepository = ($repository.TrimEnd("/") -replace '\.git$', '')
if ($normalizedOrigin -ne $normalizedRepository) {
    throw "Unexpected Meshtasticator origin: $origin"
}

& git -C $checkout fetch --quiet origin $commit
Assert-LastExitCode "Meshtasticator commit fetch"
& git -C $checkout checkout --quiet --detach $commit
Assert-LastExitCode "Meshtasticator checkout"
if ((& git -C $checkout rev-parse HEAD).Trim() -ne $commit) {
    throw "Meshtasticator checkout is not at the frozen commit."
}

$interactivePath = Join-Path $checkout "lib\interactive.py"
$interactive = [IO.File]::ReadAllText($interactivePath)
$originalLine = 'DEVICE_SIM_DOCKER_IMAGE = "meshtastic/meshtasticd"'
$pinnedLine = "DEVICE_SIM_DOCKER_IMAGE = `"$daemonImage`""
if ($interactive.Contains($originalLine)) {
    $interactive = $interactive.Replace($originalLine, $pinnedLine)
    [IO.File]::WriteAllText($interactivePath, $interactive, [Text.UTF8Encoding]::new($false))
} elseif (-not $interactive.Contains($pinnedLine)) {
    throw "Pinned source no longer contains the reviewed daemon image constant."
}
if (-not $interactive.Contains("TCP_PORT_OFFSET = 4404")) {
    throw "Pinned source no longer exposes the reviewed TCP port offset."
}
$configPath = Join-Path $checkout "lib\config.py"
$config = [IO.File]::ReadAllText($configPath)
$originalPreset = 'self.MODEM_PRESET = "LONG_FAST"'
$simulationPreset = 'self.MODEM_PRESET = "SHORT_FAST"'
if ($config.Contains($originalPreset)) {
    $config = $config.Replace($originalPreset, $simulationPreset)
    [IO.File]::WriteAllText($configPath, $config, [Text.UTF8Encoding]::new($false))
} elseif (-not $config.Contains($simulationPreset)) {
    throw "Pinned source no longer contains the reviewed modem preset constant."
}
$changed = @(& git -C $checkout status --short)
if ($changed.Count -ne 2 -or
    -not ($changed -match 'lib/config\.py$') -or
    -not ($changed -match 'lib/interactive\.py$')) {
    throw "Unexpected modifications in generated Meshtasticator checkout: $($changed -join ', ')"
}

if (-not (Test-Path -LiteralPath $python)) {
    & py -3.12 -m venv $venv
    Assert-LastExitCode "Simulation virtual environment creation"
}
& $python -m pip install --disable-pip-version-check --quiet --upgrade pip
Assert-LastExitCode "pip upgrade"
& $python -m pip install --disable-pip-version-check --quiet -r $requirementsPath
Assert-LastExitCode "Pinned simulation dependency install"
& $python -m pip install --disable-pip-version-check --quiet -e "$protocolRoot[dev,sender]" -e "$gatewayRoot[dev]"
Assert-LastExitCode "Integrated protocol and gateway install"
& $python -m pip check
Assert-LastExitCode "Simulation dependency check"
& $python -c "import importlib.metadata as m; assert m.version('meshtastic') == '2.7.11'"
Assert-LastExitCode "Meshtastic Python version check"
& $python -m pip freeze | Set-Content -LiteralPath (Join-Path $runtimeRoot "pip-freeze.txt") -Encoding utf8

if (-not $SkipImagePull) {
    & docker pull $daemonImage
    Assert-LastExitCode "Digest-pinned Meshtastic daemon pull"
}

& $python $tool validate-source
Assert-LastExitCode "Phase 5 source validation"
& $python $tool write-fixture (Join-Path $runtimeRoot "signed-report.json")
Assert-LastExitCode "Golden fixture preparation"

Write-Host "Phase 5 simulator is ready."
Write-Host "Checkout: $checkout"
Write-Host "Python:   $python"
Write-Host "Image:    $daemonImage"
