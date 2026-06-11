$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

. (Join-Path $PSScriptRoot "friday-dist.ps1")

$DistApp = Get-FridayDistDir -Root $PWD
$Exe = Get-FridayExe -DistDir $DistApp

$VersionLine = Select-String -Path (Join-Path $PWD "friday\version.py") -Pattern '__version__ = "(.+)"' | Select-Object -First 1
$TargetVersion = if ($VersionLine) { $VersionLine.Matches[0].Groups[1].Value } else { "" }

$needsBuild = -not $Exe
if ($Exe -and $TargetVersion) {
    $builtVersion = ($Exe.VersionInfo.ProductVersion -replace '\.0$', '')
    if ($builtVersion -ne $TargetVersion) {
        Write-Host "Dist exe is v$builtVersion, need v$TargetVersion — rebuilding..." -ForegroundColor Yellow
        $needsBuild = $true
    }
}

if ($needsBuild) {
    Write-Host "Building exe..." -ForegroundColor Yellow
    & (Join-Path $PWD "scripts\build.ps1")
    $Exe = Get-FridayExe -DistDir (Get-FridayDistDir -Root $PWD)
    if (-not $Exe) {
        throw "Build failed."
    }
}

if (-not $TargetVersion) {
    $TargetVersion = Get-FridayVersion -Root $PWD
}

$ReleaseRoot = Join-Path $PWD "release"
$GuideName = -join ([char]0x5B89, [char]0x88C5, [char]0x6559, [char]0x7A0B) + ".txt"
$UnblockName = -join ([char]0x89E3, [char]0x9664, [char]0x9501, [char]0x5B9A) + ".ps1"
$SetupName = "Friday-Setup-$TargetVersion.exe"
$ZipName = "Friday-Windows-$TargetVersion.zip"
$UpdateZipName = "Friday-Update-$TargetVersion.zip"

# 先构建安装包，再组装发布 ZIP（内含 Setup.exe，供官网/浏览器下载）
$SetupPath = Join-Path $ReleaseRoot $SetupName
$BuildInstaller = Join-Path $PWD "scripts\build-installer.ps1"
if (Test-Path $BuildInstaller) {
    Write-Host ""
    Write-Host "Building Setup installer..." -ForegroundColor Cyan
    & $BuildInstaller -SkipBuild -Root $PWD
    if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $SetupPath)) {
        $setupMb = [math]::Round((Get-Item $SetupPath).Length / 1MB, 1)
        Write-Host "Done Setup: $SetupPath (${setupMb} MB)" -ForegroundColor Green
    } elseif ($LASTEXITCODE -eq 2) {
        Write-Host "Setup skipped (install Inno Setup 6 to build Friday-Setup-*.exe)" -ForegroundColor Yellow
    } else {
        Write-Host "Setup build failed (exit $LASTEXITCODE)" -ForegroundColor Yellow
    }
}

if (-not (Test-Path -LiteralPath $SetupPath)) {
    throw "Friday-Setup-$TargetVersion.exe not found. Install Inno Setup 6 and rerun make-release.ps1."
}

function New-ReleaseZip {
    param(
        [string]$Stage,
        [string]$ZipPath
    )
    if (Test-Path $Stage) {
        Remove-Item $Stage -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Stage -Force | Out-Null
    return @{
        Stage   = $Stage
        ZipPath = $ZipPath
    }
}

function Write-ReleaseZip {
    param(
        [string]$Stage,
        [string]$ZipPath
    )
    if (Test-Path $ZipPath) {
        Remove-Item $ZipPath -Force
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory($Stage, $ZipPath)
    Remove-Item $Stage -Recurse -Force
    $sizeMb = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
    Write-Host "Done ZIP: $ZipPath (${sizeMb} MB)" -ForegroundColor Green
}

# --- Friday-Windows：解压后运行 Setup 安装程序（官网默认下载）---
$winStage = Join-Path $ReleaseRoot "stage-windows"
New-ReleaseZip -Stage $winStage -ZipPath (Join-Path $ReleaseRoot $ZipName) | Out-Null

@(
    "Friday Windows $TargetVersion"
    "Build: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    "Installer: $SetupName"
) | Set-Content -Path (Join-Path $winStage "VERSION.txt") -Encoding UTF8

Copy-Item (Join-Path $ReleaseRoot $GuideName) $winStage -Force
Copy-Item $SetupPath (Join-Path $winStage $SetupName) -Force
$UnblockScript = Join-Path $ReleaseRoot $UnblockName
if (Test-Path $UnblockScript) {
    Copy-Item $UnblockScript $winStage -Force
}
# 兼容 1.2.x 应用内一键更新（旧版只拉 Friday-Windows.zip，须含 Friday\Friday.exe）
Copy-Item $DistApp (Join-Path $winStage "Friday") -Recurse -Force
Write-Host "Unblocking staged Windows zip files..." -ForegroundColor Cyan
Get-ChildItem -LiteralPath (Join-Path $winStage "Friday") -Recurse -ErrorAction SilentlyContinue |
    Unblock-File -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Packing $ZipName (Setup + portable for legacy updater)..." -ForegroundColor Cyan
Write-ReleaseZip -Stage $winStage -ZipPath (Join-Path $ReleaseRoot $ZipName)

# --- Friday-Update：便携目录，供应用内「一键更新」覆盖安装 ---
$updateStage = Join-Path $ReleaseRoot "stage-update"
New-ReleaseZip -Stage $updateStage -ZipPath (Join-Path $ReleaseRoot $UpdateZipName) | Out-Null

@(
    "Friday Update $TargetVersion"
    "Build: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    "For in-app auto-update only (contains Friday\Friday.exe)."
) | Set-Content -Path (Join-Path $updateStage "VERSION.txt") -Encoding UTF8

Copy-Item $DistApp (Join-Path $updateStage "Friday") -Recurse -Force
Write-Host "Unblocking staged update files..." -ForegroundColor Cyan
Get-ChildItem -LiteralPath (Join-Path $updateStage "Friday") -Recurse -ErrorAction SilentlyContinue |
    Unblock-File -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Packing $UpdateZipName (in-app updater)..." -ForegroundColor Cyan
Write-ReleaseZip -Stage $updateStage -ZipPath (Join-Path $ReleaseRoot $UpdateZipName)

Write-Host ""
Write-Host "Release artifacts ready in $ReleaseRoot" -ForegroundColor Green
