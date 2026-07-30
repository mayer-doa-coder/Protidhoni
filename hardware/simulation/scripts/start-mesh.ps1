[CmdletBinding()]
param(
    [ValidateSet("direct", "relay-required")]
    [string]$Topology = "relay-required",
    [switch]$SkipSetup
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$simulationRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $simulationRoot ".runtime"
$checkout = Join-Path $runtimeRoot "Meshtasticator"
$python = Join-Path $runtimeRoot ".venv\Scripts\python.exe"
$tool = Join-Path $PSScriptRoot "phase5_tools.py"

if (-not $SkipSetup) {
    & (Join-Path $PSScriptRoot "setup.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Simulator setup failed."
    }
}
& (Join-Path $PSScriptRoot "preflight.ps1") -Topology $Topology
if ($LASTEXITCODE -ne 0) {
    throw "Simulator preflight failed."
}

$sourceTopology = Join-Path $simulationRoot "topologies\$Topology.json"
$runtimeTopology = Join-Path $checkout "out\nodeConfig.yaml"
& $python $tool write-topology-yaml $sourceTopology $runtimeTopology
if ($LASTEXITCODE -ne 0) {
    throw "Runtime topology conversion failed."
}

Write-Host "Starting topology '$Topology'. Keep this terminal open."
Write-Host "Verified node ports: sender=4404, relay=4405, gateway=4406."
Write-Host "Type 'plot' for simulator route data, 'remove 1' for relay outage, or 'exit' to stop."

$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $checkout
    & $python .\interactiveSim.py --from-file --docker --collisions
    if ($LASTEXITCODE -ne 0) {
        throw "Meshtasticator exited with code $LASTEXITCODE."
    }
} finally {
    Set-Location -LiteralPath $previousLocation
}

