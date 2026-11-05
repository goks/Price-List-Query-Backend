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

$version = python -c "from app_version import APP_VERSION; print(APP_VERSION)"
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Unable to read a valid application version from app_version.py."
}
$portableName = "Price List Update v$version.exe"
$installerName = "Price List Update v$version-installer.exe"
$portableBuildPath = ".\dist\Price List Update.exe"
$portableReleasePath = Join-Path ".\dist" $portableName

Write-Host "Building PyInstaller executable..."
python -m PyInstaller --noconfirm main.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed to build the portable executable."
}
if (-not (Test-Path $portableBuildPath)) {
    throw "Expected build executable was not created: $portableBuildPath"
}
Copy-Item -LiteralPath $portableBuildPath -Destination $portableReleasePath -Force

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

& $makensisPath "/DAPP_VERSION=$version" installer.nsi
if ($LASTEXITCODE -ne 0) {
    throw "NSIS failed to build the installer."
}
if (-not (Test-Path $installerName)) {
    throw "Expected installer was not created: $installerName"
}

Write-Host "Build complete: $portableName and $installerName"
