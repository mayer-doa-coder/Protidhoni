[CmdletBinding()]
param(
    [switch]$RequireEvidenceArtifacts
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$simulationRoot = Split-Path -Parent $PSScriptRoot
$evidenceRoot = Join-Path (Split-Path -Parent $simulationRoot) "evidence"

& py -3.12 (Join-Path $PSScriptRoot "phase5_tools.py") validate-source
if ($LASTEXITCODE -ne 0) {
    throw "Phase 5 source validation failed."
}

$evidenceFiles = @(Get-ChildItem -LiteralPath (Join-Path $evidenceRoot "generated") -Filter "*.json" -File -ErrorAction SilentlyContinue)
foreach ($file in $evidenceFiles) {
    $arguments = @((Join-Path $PSScriptRoot "phase5_tools.py"), "validate-evidence", $file.FullName)
    if ($RequireEvidenceArtifacts) {
        $arguments += "--require-artifacts"
    }
    & py -3.12 @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Generated evidence validation failed: $($file.FullName)"
    }
}

Write-Host "Validated source and $($evidenceFiles.Count) generated evidence file(s)."

