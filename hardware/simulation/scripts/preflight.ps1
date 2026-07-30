[CmdletBinding()]
param(
    [ValidateSet("direct", "relay-required", "two-relay-required")]
    [string]$Topology = "relay-required",
    [switch]$RequireIntegration
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$simulationRoot = Split-Path -Parent $PSScriptRoot
$hardwareRoot = Split-Path -Parent $simulationRoot
$runtimeRoot = Join-Path $simulationRoot ".runtime"
$python = Join-Path $runtimeRoot ".venv\Scripts\python.exe"
$tool = Join-Path $PSScriptRoot "phase5_tools.py"
$topologyPath = Join-Path $simulationRoot "topologies\$Topology.json"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Simulation environment is missing. Run .\hardware\simulation\scripts\setup.ps1 first."
}
& docker version --format '{{.Server.Version}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running or its Linux engine is unavailable."
}
& $python $tool validate-topology $topologyPath
if ($LASTEXITCODE -ne 0) {
    throw "Topology validation failed."
}

$existingContainer = & docker ps -a --filter "name=^/Meshtastic$" --format '{{.Names}}'
if ($existingContainer -eq "Meshtastic") {
    throw "Container 'Meshtastic' already exists. Exit its simulator, or run stop-mesh.ps1."
}
$topology = Get-Content -LiteralPath $topologyPath -Raw | ConvertFrom-Json
$ports = 4404..(4403 + $topology.nodes.Count)
foreach ($port in $ports) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($null -ne $listener) {
        throw "TCP port $port is already in use. Stop the conflicting process before simulation."
    }
}

if ($RequireIntegration) {
    foreach ($path in @(
        (Join-Path $hardwareRoot "protocol\src\protidhoni_lora_protocol\sender.py"),
        (Join-Path $hardwareRoot "gateway\src\protidhoni_lora_gateway\cli.py")
    )) {
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Integrated Phase 5 dependency is missing: $path. Merge Person A and B first."
        }
    }
}

Write-Host "Preflight passed for '$Topology' on TCP ports $($ports -join ', ')."

