$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

. (Join-Path $PSScriptRoot "friday-dist.ps1")

$DistApp = Get-FridayDistDir -Root $PWD
$Exe = Get-FridayExe -DistDir $DistApp

if (-not $Exe) {
    Write-Host "Building exe..." -ForegroundColor Yellow
    & (Join-Path $PWD "scripts\build.ps1")
    $Exe = Get-ChildItem $DistApp -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $Exe) {
        throw "Build failed."
    }
}

$ReleaseRoot = Join-Path $PWD "release"
$GuideName = -join ([char]0x5B89, [char]0x88C5, [char]0x6559, [char]0x7A0B) + ".txt"
$ShortcutName = -join ([char]0x521B, [char]0x5EFA, [char]0x684C, [char]0x9762, [char]0x5FEB, [char]0x6377, [char]0x65B9, [char]0x5F0F) + ".ps1"
$ZipName = "Friday-Windows.zip"

$Stage = Join-Path $ReleaseRoot "stage"
if (Test-Path $Stage) {
    Remove-Item $Stage -Recurse -Force
}
New-Item -ItemType Directory -Path $Stage -Force | Out-Null

Copy-Item (Join-Path $ReleaseRoot $GuideName) $Stage -Force
Copy-Item (Join-Path $ReleaseRoot $ShortcutName) $Stage -Force
$UnblockName = -join ([char]0x89E3, [char]0x9664, [char]0x9501, [char]0x5B9A) + ".ps1"
$UnblockScript = Join-Path $ReleaseRoot $UnblockName
if (Test-Path $UnblockScript) {
    Copy-Item $UnblockScript $Stage -Force
}
Copy-Item $DistApp (Join-Path $Stage "Friday") -Recurse -Force

# 打包阶段解除锁定，减少用户手动 Unblock
Write-Host "Unblocking staged files..." -ForegroundColor Cyan
Get-ChildItem -LiteralPath (Join-Path $Stage "Friday") -Recurse -ErrorAction SilentlyContinue |
    Unblock-File -ErrorAction SilentlyContinue

$FirstInstallName = -join ([char]0x9996, [char]0x6B21, [char]0x5B89, [char]0x88C5) + ".ps1"
$FirstInstallScript = Join-Path $ReleaseRoot $FirstInstallName
if (Test-Path $FirstInstallScript) {
    Copy-Item $FirstInstallScript $Stage -Force
}

$ZipPath = Join-Path $ReleaseRoot $ZipName
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($Stage, $ZipPath)

Remove-Item $Stage -Recurse -Force

$sizeMb = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
Write-Host ""
Write-Host "Done: $ZipPath (${sizeMb} MB)" -ForegroundColor Green
