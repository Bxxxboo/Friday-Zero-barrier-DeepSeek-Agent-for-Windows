$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

. (Join-Path $PSScriptRoot "friday-dist.ps1")

$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "venv not found, run setup.ps1 first" -ForegroundColor Yellow
    exit 1
}

Write-Host "Installing dependencies..."
& $python -m pip install pyinstaller cryptography --quiet

Write-Host "Creating icon..."
& $python scripts/create_icon.py

Write-Host "Building exe (1-3 min)..."
& $python -m PyInstaller friday.spec --noconfirm --clean

$DistApp = Get-FridayDistDir -Root $PWD
$exe = Get-FridayExe -DistDir $DistApp
if (-not $exe) {
    $exe = Get-ChildItem (Join-Path $PWD "dist") -Filter "*.exe" | Select-Object -First 1
}
if ($exe) {
    Copy-Item -Path (Join-Path $PWD "assets\friday.ico") -Destination (Join-Path $exe.DirectoryName "app.ico") -Force
    Write-Host "Done: $($exe.FullName)" -ForegroundColor Green
} else {
    Write-Host "Build failed, see errors above." -ForegroundColor Red
    exit 1
}
