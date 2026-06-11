# Dev shortcut: Friday (test build) -> source run.py --dev. Does not touch installed Friday.lnk.
$ErrorActionPreference = "Stop"

$Root = Split-Path $PSScriptRoot -Parent
$RunPy = Join-Path $Root "run.py"
$Pythonw = Join-Path $Root ".python-env\Scripts\pythonw.exe"
$Python = Join-Path $Root ".python-env\Scripts\python.exe"

if (-not (Test-Path $RunPy)) {
    Write-Host "Missing: $RunPy" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Pythonw)) {
    Write-Host "Run setup.ps1 first to create .python-env in:" -ForegroundColor Red
    Write-Host $Root -ForegroundColor Yellow
    exit 1
}

$CreateIcon = Join-Path $Root "scripts\create_icon.py"
if (Test-Path $CreateIcon) {
    if (Test-Path $Python) {
        & $Python $CreateIcon
    } else {
        python $CreateIcon
    }
}

$IconSrc = Join-Path $Root "assets\friday.ico"
if (-not (Test-Path $IconSrc)) {
    Write-Host "Missing icon: $IconSrc" -ForegroundColor Red
    exit 1
}

$AppDataFriday = Join-Path $env:APPDATA "Friday"
New-Item -ItemType Directory -Force -Path $AppDataFriday | Out-Null
$Icon = Join-Path $AppDataFriday "friday.ico"
Copy-Item -Path $IconSrc -Destination $Icon -Force
(Get-Item $Icon).LastWriteTime = Get-Date

$Desktop = [Environment]::GetFolderPath("Desktop")
$DevShortcutName = -join ([char]0x661F, [char]0x671F, [char]0x4E94, [char]0xFF08, [char]0x6D4B, [char]0x8BD5, [char]0x7248, [char]0xFF09) + ".lnk"
$DevShortcutPath = Join-Path $Desktop $DevShortcutName
$LegacyNames = @(
    (-join ([char]0x661F, [char]0x671F, [char]0x4E94, [char]0x6D4B, [char]0x8BD5, [char]0x7248) + ".lnk"),
    (-join ([char]0x661F, [char]0x671F, [char]0x4E94) + ".lnk")
)

$WshShell = New-Object -ComObject WScript.Shell

foreach ($legacyName in $LegacyNames) {
    $legacyPath = Join-Path $Desktop $legacyName
    if (-not (Test-Path $legacyPath)) { continue }
    $sc = $WshShell.CreateShortcut($legacyPath)
    $targetsSource = ($sc.Arguments -match 'run\.py')
    if ($targetsSource) {
        Remove-Item $legacyPath -Force
        Write-Host "Removed legacy source shortcut: $legacyName" -ForegroundColor Yellow
    }
}

$Shortcut = $WshShell.CreateShortcut($DevShortcutPath)
$Shortcut.TargetPath = $Pythonw
$Shortcut.Arguments = "`"$RunPy`" --dev"
$Shortcut.WorkingDirectory = $Root
$Shortcut.WindowStyle = 7
$Shortcut.IconLocation = "$Icon,0"
$appName = -join ([char]0x661F, [char]0x671F, [char]0x4E94, [char]0xFF08, [char]0x6D4B, [char]0x8BD5, [char]0x7248, [char]0xFF09)
$Shortcut.Description = "$appName dev build - $Root"
$Shortcut.Save()

$ie4u = Join-Path $env:SystemRoot "System32\ie4uinit.exe"
if (Test-Path $ie4u) {
    Start-Process -FilePath $ie4u -ArgumentList "-show" -WindowStyle Hidden
}

Write-Host ""
Write-Host "Created: $DevShortcutPath" -ForegroundColor Green
Write-Host "Title: Friday (dev) | instance port 58766" -ForegroundColor Cyan
Write-Host "Installed Friday shortcut is unchanged." -ForegroundColor DarkGray
Write-Host "Root: $Root"
