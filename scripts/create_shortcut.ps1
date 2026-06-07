$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DistDir = Join-Path $ProjectRoot "dist"
. (Join-Path $PSScriptRoot "friday-dist.ps1")
$DistApp = Get-FridayDistDir -Root $ProjectRoot
$Exe = Get-FridayExe -DistDir $DistApp
if (-not $Exe) {
    $Exe = Get-ChildItem $DistDir -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
}
$Pythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
$RunScript = Join-Path $ProjectRoot "run.py"
$SourceIcon = Join-Path $ProjectRoot "assets\friday.ico"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutName = -join ([char]0x661F, [char]0x671F, [char]0x4E94) + ".lnk"
$ShortcutPath = Join-Path $Desktop $ShortcutName

# 纯 ASCII 路径；按内容哈希命名，强制绕过 Windows 图标缓存
$AppDataFriday = Join-Path $env:APPDATA "Friday"
$AppDataIcons = Join-Path $AppDataFriday "icons"

if (Test-Path (Join-Path $ProjectRoot ".venv\Scripts\python.exe")) {
    & (Join-Path $ProjectRoot ".venv\Scripts\python.exe") (Join-Path $ProjectRoot "scripts\create_icon.py")
}

if (-not (Test-Path $AppDataFriday)) {
    New-Item -ItemType Directory -Path $AppDataFriday -Force | Out-Null
}
if (-not (Test-Path $AppDataIcons)) {
    New-Item -ItemType Directory -Path $AppDataIcons -Force | Out-Null
}

$iconForShortcut = $null
if (Test-Path $SourceIcon) {
    $iconHash = (Get-FileHash $SourceIcon -Algorithm SHA256).Hash.Substring(0, 8).ToLower()
    $StableIcon = Join-Path $AppDataIcons "$iconHash.ico"
    Copy-Item -Path $SourceIcon -Destination $StableIcon -Force
    $iconForShortcut = $StableIcon

    # 清理旧版缓存图标
    @(
        (Join-Path $AppDataFriday "app.ico"),
        (Join-Path $AppDataFriday "friday.ico")
    ) | Where-Object { Test-Path $_ } | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem $AppDataIcons -Filter "*.ico" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "$iconHash.ico" } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

$WshShell = New-Object -ComObject WScript.Shell

# 删除旧快捷方式，避免 Explorer 沿用旧 IconLocation / Description 缓存
if (Test-Path $ShortcutPath) {
    Remove-Item -Path $ShortcutPath -Force
}

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)

if ($Exe) {
    $Shortcut.TargetPath = $Exe.FullName
    $Shortcut.Arguments = ""
    $Shortcut.WorkingDirectory = $Exe.DirectoryName
    $Mode = "exe"
} elseif (Test-Path $Pythonw) {
    $Shortcut.TargetPath = $Pythonw
    $Shortcut.Arguments = "`"$RunScript`""
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Mode = "dev"
} else {
    throw "dist\*.exe and dev env not found. Run scripts\build.ps1 or setup.ps1 first."
}

$Shortcut.WindowStyle = 1

# Unicode via char codes - avoid PowerShell encoding issues in Description
$appName = -join ([char]0x661F, [char]0x671F, [char]0x4E94)
$role = -join ([char]0x7535, [char]0x8111, [char]0x7BA1, [char]0x5BB6)
$Shortcut.Description = "$appName - AI $role"

if ($iconForShortcut -and (Test-Path $iconForShortcut)) {
    $Shortcut.IconLocation = "$iconForShortcut,0"
} elseif ($Exe) {
    $Shortcut.IconLocation = "$($Exe.FullName),0"
}

$Shortcut.Save()

# Refresh desktop icon cache
try {
    $ie4u = Join-Path $env:WINDIR "System32\ie4uinit.exe"
    if (Test-Path $ie4u) {
        & $ie4u -show | Out-Null
    }
} catch {
    # non-critical
}

if ($Mode -eq "exe") {
    Write-Host "Desktop shortcut created (exe): $ShortcutPath" -ForegroundColor Green
    Write-Host "  Target: $($Exe.FullName)"
    Write-Host "  Icon:   $($Shortcut.IconLocation)"
} else {
    Write-Host "Desktop shortcut created (dev): $ShortcutPath" -ForegroundColor Green
}
