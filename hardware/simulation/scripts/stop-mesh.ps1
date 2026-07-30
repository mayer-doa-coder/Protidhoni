[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$container = & docker ps -a --filter "name=^/Meshtastic$" --format '{{.Names}}'
if ($container -eq "Meshtastic") {
    & docker rm --force Meshtastic | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not remove the generated Meshtastic simulator container."
    }
    Write-Host "Removed generated simulator container 'Meshtastic'."
} else {
    Write-Host "No generated simulator container is present."
}
