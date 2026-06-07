# 星期五 — 首次安装（解压后右键「使用 PowerShell 运行」）
# 自动解除锁定、创建桌面快捷方式并启动应用

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$FridayDir = Join-Path $Root "Friday"
$ExeName = [char]0x661F + [char]0x671F + [char]0x4E94 + ".exe"  # 星期五.exe

if (-not (Test-Path $FridayDir)) {
    Write-Host "未找到 Friday 文件夹，请确认已完整解压 zip。" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

Write-Host "正在解除 Friday 文件夹锁定…" -ForegroundColor Cyan
Get-ChildItem -LiteralPath $FridayDir -Recurse -ErrorAction SilentlyContinue |
    Unblock-File -ErrorAction SilentlyContinue

$ShortcutScript = Join-Path $Root ([char]0x521B + [char]0x5EFA + [char]0x684C + [char]0x9762 + [char]0x5FEB + [char]0x6377 + [char]0x65B9 + [char]0x5F0F + ".ps1")
if (Test-Path $ShortcutScript) {
    Write-Host "正在创建桌面快捷方式…" -ForegroundColor Cyan
    try {
        & $ShortcutScript
    } catch {
        Write-Host "快捷方式创建跳过：$_" -ForegroundColor Yellow
    }
}

$Exe = Join-Path $FridayDir $ExeName
if (-not (Test-Path $Exe)) {
    $Exe = Get-ChildItem $FridayDir -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $Exe) {
    Write-Host "未找到 星期五.exe" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

Write-Host ""
Write-Host "首次运行将自动检测并安装 WebView2、VC++ 等运行组件（需联网，约 1～5 分钟）。" -ForegroundColor Green
Write-Host "正在启动星期五…" -ForegroundColor Green
Start-Process -FilePath $Exe -WorkingDirectory (Split-Path $Exe -Parent)
