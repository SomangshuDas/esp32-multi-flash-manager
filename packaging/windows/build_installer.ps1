# build_installer.ps1
# ====================
# Builds ESP32MultiFlashManager.exe with PyInstaller, then wraps it into a
# Setup.exe with Inno Setup. Run from anywhere; paths are resolved relative
# to this script so it works both locally and from CI.
#
# Usage:
#   .\packaging\windows\build_installer.ps1 [-Version 1.2.0] [-SkipPyInstaller]
#
# Requirements:
#   - Python + the project's requirements.txt installed, plus `pyinstaller`
#   - Inno Setup 6 installed, with ISCC.exe on PATH (or at the default
#     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" location)

param(
    [string]$Version = "1.1.0",
    [switch]$SkipPyInstaller
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")

Push-Location $RepoRoot
try {
    if (-not $SkipPyInstaller) {
        Write-Host "==> Building ESP32MultiFlashManager.exe with PyInstaller" -ForegroundColor Cyan
        pyinstaller --noconfirm --windowed --onefile `
            --name ESP32MultiFlashManager `
            --icon resources\icons\app_icon.ico `
            --add-data "resources;resources" `
            --collect-all esptool `
            --collect-all espsecure `
            --collect-all espefuse `
            run.py
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
    }
    else {
        Write-Host "==> Skipping PyInstaller step (using existing dist\ESP32MultiFlashManager.exe)" -ForegroundColor Yellow
    }

    $ExePath = Join-Path $RepoRoot "dist\ESP32MultiFlashManager.exe"
    if (-not (Test-Path $ExePath)) {
        throw "Expected build output not found at $ExePath"
    }

    $Iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if (-not $Iscc) {
        $DefaultIscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        if (Test-Path $DefaultIscc) {
            $IsccPath = $DefaultIscc
        }
        else {
            throw "ISCC.exe (Inno Setup 6 command-line compiler) not found on PATH or at the default install location. Install it from https://jrsoftware.org/isinfo.php"
        }
    }
    else {
        $IsccPath = $Iscc.Source
    }

    Write-Host "==> Compiling installer with Inno Setup (version $Version)" -ForegroundColor Cyan
    & $IsccPath "/DAppVersion=$Version" "packaging\windows\installer.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed" }

    $InstallerPath = Join-Path $RepoRoot "dist\installer\ESP32MultiFlashManagerSetup-$Version.exe"
    if (Test-Path $InstallerPath) {
        Write-Host "==> Installer ready: $InstallerPath" -ForegroundColor Green
    }
    else {
        throw "Installer build completed but expected output not found at $InstallerPath"
    }
}
finally {
    Pop-Location
}
