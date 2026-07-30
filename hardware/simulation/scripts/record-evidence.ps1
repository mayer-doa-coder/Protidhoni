[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet(
        "direct-delivery",
        "required-multi-hop",
        "duplicate-reception",
        "loss-and-application-resend",
        "relay-outage",
        "hop-limit-exhaustion",
        "recovery"
    )]
    [string]$Scenario,
    [Parameter(Mandatory)]
    [datetime]$StartedAt,
    [Parameter(Mandatory)]
    [datetime]$EndedAt,
    [Parameter(Mandatory)]
    [ValidateSet("delivered", "not-delivered")]
    [string]$Delivery,
    [Parameter(Mandatory)]
    [ValidateRange(0, 1000000)]
    [int]$DuplicateCount,
    [Parameter(Mandatory)]
    [ValidateSet("accepted", "duplicate", "rejected", "incomplete", "not-observed")]
    [string]$ReassemblyOutcome,
    [Parameter(Mandatory)]
    [ValidateSet("accepted", "duplicate", "rejected", "unavailable", "not-reached")]
    [string]$BackendOutcome,
    [ValidateRange(0, 7)]
    [Nullable[int]]$RouteHops,
    [ValidateSet("meshtasticator-console", "daemon-log", "not-available")]
    [string]$RouteSource = "not-available",
    [ValidateRange(0, 86400000)]
    [Nullable[double]]$LatencyMs,
    [ValidateLength(0, 500)]
    [string]$Notes = "",
    [string[]]$Artifact = @()
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$simulationRoot = Split-Path -Parent $PSScriptRoot
$hardwareRoot = Split-Path -Parent $simulationRoot
$runtimePython = Join-Path $simulationRoot ".runtime\.venv\Scripts\python.exe"
$tool = Join-Path $PSScriptRoot "phase5_tools.py"
$generated = Join-Path $hardwareRoot "evidence\generated"

if (-not (Test-Path -LiteralPath $runtimePython)) {
    throw "Simulation environment is missing. Run setup.ps1 first."
}
if ($StartedAt.Kind -eq [DateTimeKind]::Unspecified -or $EndedAt.Kind -eq [DateTimeKind]::Unspecified) {
    throw "StartedAt and EndedAt must include a UTC offset, for example 2026-07-30T10:00:00Z."
}
$startedUtc = $StartedAt.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
$endedUtc = $EndedAt.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
$safeStamp = $EndedAt.ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
$output = Join-Path $generated "$safeStamp-$Scenario.json"

$arguments = @(
    $tool,
    "record",
    "--scenario", $Scenario,
    "--started-at", $startedUtc,
    "--ended-at", $endedUtc,
    "--delivery", $Delivery,
    "--duplicate-count", [string]$DuplicateCount,
    "--route-source", $RouteSource,
    "--reassembly-outcome", $ReassemblyOutcome,
    "--backend-outcome", $BackendOutcome,
    "--notes", $Notes,
    "--output", $output
)
if ($null -ne $RouteHops) {
    $arguments += @("--route-hops", [string]$RouteHops.Value)
}
if ($null -ne $LatencyMs) {
    $arguments += @("--latency-ms", [string]$LatencyMs.Value)
}
foreach ($path in $Artifact) {
    $arguments += @("--artifact", $path)
}

& $runtimePython @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Evidence was rejected; no result was recorded."
}

