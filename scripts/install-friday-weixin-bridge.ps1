# 安装 OpenClaw → 星期五 微信桥接插件
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PluginPath = Join-Path $Root "extensions\friday-weixin-bridge"
$ConfigPath = Join-Path $env:USERPROFILE ".openclaw\openclaw.json"

Write-Host "安装 friday-weixin-bridge 插件..."
openclaw plugins install $PluginPath

Write-Host "写入 plugins.allow（Gateway 必须白名单才加载桥接插件）..."
$config = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $config.plugins) { $config | Add-Member -NotePropertyName plugins -NotePropertyValue (@{}) }
$config.plugins.allow = @("openclaw-weixin", "friday-weixin-bridge")
if (-not $config.plugins.entries) { $config.plugins | Add-Member -NotePropertyName entries -NotePropertyValue (@{}) }
if (-not $config.plugins.entries."friday-weixin-bridge") {
    $config.plugins.entries | Add-Member -NotePropertyName "friday-weixin-bridge" -NotePropertyValue (@{ enabled = $true })
} else {
    $config.plugins.entries."friday-weixin-bridge".enabled = $true
}
$config | ConvertTo-Json -Depth 20 | Set-Content $ConfigPath -Encoding UTF8

Copy-Item -Force (Join-Path $PluginPath "index.js") (Join-Path $env:USERPROFILE ".openclaw\extensions\friday-weixin-bridge\index.js")

Write-Host "重启 OpenClaw Gateway..."
openclaw gateway restart --force
Write-Host "完成。请先启动星期五桌面版，再从微信发新消息测试。"
