Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".\build")) { New-Item -ItemType Directory -Path ".\build" | Out-Null }
if (-not (Test-Path ".\dist")) { New-Item -ItemType Directory -Path ".\dist" | Out-Null }

Write-Host "Building PyInstaller executable..."
python -m PyInstaller --noconfirm main.spec

Write-Host "Building NSIS installer..."
makensis installer.nsi

Write-Host "Build complete."
