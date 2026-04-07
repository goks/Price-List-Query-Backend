Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".\build")) { New-Item -ItemType Directory -Path ".\build" | Out-Null }
if (-not (Test-Path ".\dist")) { New-Item -ItemType Directory -Path ".\dist" | Out-Null }

$serviceAccountFile = ".\service-account\gokul-agencies-firebase-adminsdk-ti855-702f214fc5.json"
if (-not (Test-Path $serviceAccountFile)) {
    throw "Missing Firebase service account file at $serviceAccountFile. Restore it before building."
}

Write-Host "Building PyInstaller executable..."
python -m PyInstaller --noconfirm main.spec

Write-Host "Building NSIS installer..."
$makensisCandidates = @(
    (Get-Command makensis -ErrorAction SilentlyContinue | ForEach-Object { $_.Source }),
    "C:\Program Files (x86)\NSIS\makensis.exe",
    "C:\Program Files\NSIS\makensis.exe"
) | Where-Object { $_ }

$makensisPath = $makensisCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $makensisPath) {
    throw "Unable to find makensis.exe. Ensure NSIS is installed on the runner."
}

& $makensisPath installer.nsi

Write-Host "Build complete."
