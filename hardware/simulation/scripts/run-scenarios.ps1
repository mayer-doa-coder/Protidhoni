[CmdletBinding()]
param(
    [string[]]$Scenario,
    [string]$BackendUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$simulationRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $simulationRoot ".runtime\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Simulation environment is missing. Run setup.ps1 first."
}
$arguments = @((Join-Path $PSScriptRoot "run_scenarios.py"), "--backend-url", $BackendUrl)
foreach ($item in $Scenario) {
    $arguments += @("--scenario", $item)
}
& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Integrated Phase 5 scenario run failed with exit code $LASTEXITCODE."
}
