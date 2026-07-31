# Prepares the two large, gitignored offline assets this app bundles:
#   1. A Qwen2.5-1.5B-Instruct GGUF checkpoint for the on-device chat
#      assistant (src/llm/localAssistant.ts).
#   2. An offline Bangladesh map tile package (assets/maps/bangladesh.mbtiles)
#      for the offline map (src/screens/MapScreen.tsx).
#
# Neither is committed to git (see .gitignore) -- both are large binaries
# that must be regenerated locally before a debug/release build that uses
# the Map or Assistant tabs. Needs internet access and a JDK (for planetiler)
# on first run only; the resulting app needs neither at runtime.
#
# JDK NOTE, read before changing anything JDK-related in this project:
# The Android app itself (Gradle/CMake/native builds, including llama.rn and
# MapLibre) is hard-pinned to JDK 17 by android/build.gradle, which throws a
# build error on any other JDK -- that check is untouched by this script and
# is not affected by anything below. The ONLY JDK 21+ requirement here is
# planetiler.jar, a standalone map-tile-generation CLI tool invoked directly
# via `java -jar` (never through Gradle) purely to produce the
# bangladesh.mbtiles data file -- confirmed necessary by an actual
# UnsupportedClassVersionError running planetiler v0.10.2 under JDK 17. This
# script never sets JAVA_HOME globally or touches the Gradle/app build's JDK.
#
# Usage: powershell -File scripts/prepare-offline-assets.ps1
#   -SkipModel            : skip the ~1GB LLM download
#   -SkipMap              : skip the map tile build (downloads ~1.7GB of
#                            OSM/water-polygon source data on first run,
#                            cached after)
#   -PlanetilerJavaHome   : path to a JDK 21+ install, used ONLY to run
#                           planetiler.jar; auto-detects
#                           "C:\Program Files\Java\jdk-25" if present. Must
#                           NOT be a JDK 17 install -- planetiler cannot run
#                           on it. Has no effect on the Android app build.

param(
    [switch]$SkipModel,
    [switch]$SkipMap,
    [string]$PlanetilerJavaHome = "C:\Program Files\Java\jdk-25"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$modelUrl = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
$modelFileName = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
$planetilerUrl = "https://github.com/onthegomap/planetiler/releases/download/v0.10.2/planetiler.jar"

function Ensure-Dir($path) {
    if (-not (Test-Path $path)) { New-Item -ItemType Directory -Force -Path $path | Out-Null }
}

if (-not $SkipModel) {
    Write-Host "== LLM checkpoint =="
    $modelDestDir = Join-Path $root "assets\models"
    $androidModelDestDir = Join-Path $root "android\app\src\main\assets\models"
    Ensure-Dir $modelDestDir
    Ensure-Dir $androidModelDestDir
    $modelDest = Join-Path $modelDestDir $modelFileName
    if (-not (Test-Path $modelDest)) {
        Write-Host "Downloading $modelFileName (~1GB)..."
        Invoke-WebRequest -Uri $modelUrl -OutFile $modelDest
    } else {
        Write-Host "$modelFileName already present, skipping download."
    }
    Copy-Item $modelDest (Join-Path $androidModelDestDir $modelFileName) -Force
    Write-Host "Copied into android/app/src/main/assets/models/."
}

if (-not $SkipMap) {
    Write-Host "== Offline map tiles =="
    $toolsDir = Join-Path $root "scripts\.tools"
    Ensure-Dir $toolsDir
    $planetilerJar = Join-Path $toolsDir "planetiler.jar"
    if (-not (Test-Path $planetilerJar)) {
        Write-Host "Downloading planetiler.jar..."
        Invoke-WebRequest -Uri $planetilerUrl -OutFile $planetilerJar
    }

    $javaExe = Join-Path $PlanetilerJavaHome "bin\java.exe"
    if (-not (Test-Path $javaExe)) {
        throw "Java 21+ not found at $javaExe. Pass -PlanetilerJavaHome, or install a JDK 21+ (planetiler v0.10.2 requires it; this is only for regenerating the map tiles -- the Android app build stays on JDK 17, unaffected)."
    }

    $mapsDestDir = Join-Path $root "assets\maps"
    $androidMapsDestDir = Join-Path $root "android\app\src\main\assets\maps"
    Ensure-Dir $mapsDestDir
    Ensure-Dir $androidMapsDestDir
    $mbtiles = Join-Path $mapsDestDir "bangladesh.mbtiles"

    if (Test-Path $mbtiles) {
        Write-Host "bangladesh.mbtiles already present, skipping generation. Delete it to rebuild."
    } else {
        Write-Host "Generating bangladesh.mbtiles (roads/places, zoom 0-10; ~15-20 min, downloads ~1.7GB of source data on first run)..."
        Push-Location $toolsDir
        try {
            & $javaExe -Xmx6g -jar $planetilerJar --area=bangladesh --download --maxzoom=10 `
                --output="$mbtiles" --force
        } finally {
            Pop-Location
        }
    }
    Copy-Item $mbtiles (Join-Path $androidMapsDestDir "bangladesh.mbtiles") -Force
    Write-Host "Copied into android/app/src/main/assets/maps/."
}

Write-Host "Done. Run 'npx react-native run-android' (or a release build) to pick up the bundled assets."
