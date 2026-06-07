# 解除 Windows 对「从互联网下载」文件的锁定，修复 pythonnet / DLL 无法加载
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$FridayDir = Join-Path $Root "Friday"
if (-not (Test-Path $FridayDir)) {
    $FridayDir = $Root
}
Write-Host "正在解除锁定: $FridayDir" -ForegroundColor Yellow
Get-ChildItem -LiteralPath $FridayDir -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
Write-Host "完成。请双击 Friday\星期五.exe 启动。" -ForegroundColor Green
