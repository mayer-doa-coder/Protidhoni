param(
    [string]$Jdk17Path = "",
    [string]$AndroidSdkPath = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Jdk17Path)) {
    $adoptiumRoot = "C:\Program Files\Eclipse Adoptium"
    $jdkCandidate = Get-ChildItem -LiteralPath $adoptiumRoot -Directory -Filter "jdk-17*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $jdkCandidate) {
        throw "JDK 17 was not found under $adoptiumRoot. Install Temurin 17 or pass -Jdk17Path."
    }
    $Jdk17Path = $jdkCandidate.FullName
}

if ([string]::IsNullOrWhiteSpace($AndroidSdkPath)) {
    $AndroidSdkPath = Join-Path $env:LOCALAPPDATA "Android\Sdk"
}

$javaExecutable = Join-Path $Jdk17Path "bin\java.exe"
$adbExecutable = Join-Path $AndroidSdkPath "platform-tools\adb.exe"
if (!(Test-Path -LiteralPath $javaExecutable)) {
    throw "java.exe was not found at $javaExecutable"
}
if (!(Test-Path -LiteralPath $adbExecutable)) {
    throw "adb.exe was not found at $adbExecutable. Install Android SDK Platform-Tools."
}

$env:JAVA_HOME = $Jdk17Path
$env:ANDROID_HOME = $AndroidSdkPath
$env:Path = (Join-Path $Jdk17Path "bin") + ";" +
    (Join-Path $AndroidSdkPath "platform-tools") + ";" + $env:Path

Write-Host "JAVA_HOME=$env:JAVA_HOME"
Write-Host "ANDROID_HOME=$env:ANDROID_HOME"
& $javaExecutable -version
& $adbExecutable version
