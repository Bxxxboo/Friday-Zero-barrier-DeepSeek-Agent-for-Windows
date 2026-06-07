$ErrorActionPreference = "Stop"

$ReleaseRoot = $PSScriptRoot
$AppFolder = Join-Path $ReleaseRoot "Friday"
if (-not (Test-Path $AppFolder)) {
    $AppFolder = Join-Path $ReleaseRoot (-join ([char]0x661F, [char]0x671F, [char]0x4E94))
}
$Exe = Get-ChildItem $AppFolder -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $Exe) {
    Write-Host "未找到 星期五.exe，请确认已解压完整安装包。" -ForegroundColor Red
    pause
    exit 1
}

$Icon = Join-Path $Exe.DirectoryName "app.ico"
if (-not (Test-Path $Icon)) {
    $Icon = $Exe.FullName
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutName = -join ([char]0x661F, [char]0x671F, [char]0x4E94) + ".lnk"
$ShortcutPath = Join-Path $Desktop $ShortcutName

$WshShell = New-Object -ComObject WScript.Shell
if (Test-Path $ShortcutPath) {
    Remove-Item $ShortcutPath -Force
}

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Exe.FullName
$Shortcut.WorkingDirectory = $Exe.DirectoryName
$Shortcut.WindowStyle = 1
$Shortcut.IconLocation = "$Icon,0"
$appName = -join ([char]0x661F, [char]0x671F, [char]0x4E94)
$role = -join ([char]0x7535, [char]0x8111, [char]0x7BA1, [char]0x5BB6)
$Shortcut.Description = "$appName - AI $role"
$Shortcut.Save()

Write-Host "已在桌面创建快捷方式：$ShortcutPath" -ForegroundColor Green
Write-Host "目标：$($Exe.FullName)"
pause
