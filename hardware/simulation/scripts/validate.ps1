[CmdletBinding()]
param(
    [switch]$RequireEvidenceArtifacts
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$simulationRoot = Split-Path -Parent $PSScriptRoot
$evidenceRoot = Join-Path (Split-Path -Parent $simulationRoot) "evidence"

$runtimePython = Join-Path $simulationRoot ".runtime\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $runtimePython)) {
    throw "Simulation environment is missing. Run setup.ps1 first."
}

& $runtimePython (Join-Path $PSScriptRoot "phase5_tools.py") validate-source
if ($LASTEXITCODE -ne 0) {
    throw "Phase 5 source validation failed."
}

$scenarioEvidenceRoot = Join-Path $evidenceRoot "generated\scenarios"
$evidenceFiles = @(Get-ChildItem -LiteralPath $scenarioEvidenceRoot -Filter "*.json" -File -ErrorAction SilentlyContinue)
foreach ($file in $evidenceFiles) {
    $arguments = @((Join-Path $PSScriptRoot "phase5_tools.py"), "validate-evidence", $file.FullName)
    if ($RequireEvidenceArtifacts) {
        $arguments += "--require-artifacts"
    }
    & $runtimePython @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Generated evidence validation failed: $($file.FullName)"
    }
}

$siteEvidenceRoot = Join-Path $evidenceRoot "generated\site-planner"
$siteManifests = @(Get-ChildItem -LiteralPath $siteEvidenceRoot -Filter "manifest.json" -File -Recurse -ErrorAction SilentlyContinue)
foreach ($manifest in $siteManifests) {
    & $runtimePython (Join-Path $PSScriptRoot "phase5_tools.py") validate-site-evidence $manifest.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "Generated Site Planner evidence validation failed: $($manifest.FullName)"
    }
}

Write-Host "Validated source, $($evidenceFiles.Count) scenario evidence file(s), and $($siteManifests.Count) Site Planner manifest(s)."

