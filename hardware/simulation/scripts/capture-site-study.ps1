[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$CoverageGeoJson,
    [Parameter(Mandatory)]
    [string]$PointToPointPng,
    [Parameter(Mandatory)]
    [datetime]$RunAt,
    [Parameter(Mandatory)]
    [ValidateLength(1, 500)]
    [string]$Browser,
    [Parameter(Mandatory)]
    [ValidateLength(1, 500)]
    [string]$CoverageSummary,
    [Parameter(Mandatory)]
    [ValidateLength(1, 500)]
    [string]$PointToPointSummary
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$simulationRoot = Split-Path -Parent $PSScriptRoot
$hardwareRoot = Split-Path -Parent $simulationRoot
$python = Join-Path $simulationRoot ".runtime\.venv\Scripts\python.exe"
$tool = Join-Path $PSScriptRoot "phase5_tools.py"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Simulation environment is missing. Run setup.ps1 first."
}
if ($RunAt.Kind -eq [DateTimeKind]::Unspecified) {
    throw "RunAt must include a UTC offset, for example 2026-07-30T10:00:00Z."
}
$runUtc = $RunAt.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
$stamp = $RunAt.ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
$output = Join-Path $hardwareRoot "evidence\generated\site-planner\$stamp"

& $python $tool capture-site-study `
    --coverage $CoverageGeoJson `
    --point-to-point $PointToPointPng `
    --run-at $runUtc `
    --browser $Browser `
    --coverage-summary $CoverageSummary `
    --point-to-point-summary $PointToPointSummary `
    --output-dir $output
if ($LASTEXITCODE -ne 0) {
    throw "Site Planner evidence was rejected; no manifest was recorded."
}
