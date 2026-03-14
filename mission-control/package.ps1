# OpenClaw Mission Control — Windows Package Builder (PowerShell)
# Produces: releases/openclaw-mission-control-vX.Y.Z.zip
# Run from the mission-control\ directory.

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$version  = (Get-Content "$scriptDir\VERSION" -Raw).Trim()
$pkgName  = "openclaw-mission-control-v$version"
$staging  = "$env:TEMP\$pkgName"
$outDir   = "$scriptDir\releases"
$zipOut   = "$outDir\$pkgName.zip"

Write-Host ""
Write-Host " Building package: $pkgName"
Write-Host ""

# Clean staging
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory $staging | Out-Null

# Copy launcher files
foreach ($f in @("launch_agents.bat","launch_agents.command","monitor_agents.bat","monitor_agents.command","VERSION")) {
    Copy-Item "$scriptDir\$f" "$staging\$f"
}

# Copy app code (excluding build artifacts)
$excludeDirs = @(".venv","dist","build","__pycache__",".git","releases")
$excludeFiles = @("*.pyc","*.pyo","*.spec")
robocopy $scriptDir "$staging\mission-control" /E `
    /XD $excludeDirs `
    /XF $excludeFiles | Out-Null

# Create releases dir and zip
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory $outDir | Out-Null }
if (Test-Path $zipOut) { Remove-Item $zipOut -Force }
Compress-Archive -Path "$staging\*" -DestinationPath $zipOut -Force

# Cleanup staging
Remove-Item $staging -Recurse -Force

$size = (Get-Item $zipOut).Length
Write-Host " [+] Package created: releases\$pkgName.zip"
Write-Host " Size: $size bytes"
Write-Host ""
