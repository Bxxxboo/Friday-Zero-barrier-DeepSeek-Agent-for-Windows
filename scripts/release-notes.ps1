param(
    [string]$Version = "",
    [switch]$All
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ChangelogPath = Join-Path $Root "assets\changelog.json"

if (-not $Version) {
    $VersionLine = Select-String -Path (Join-Path $Root "friday\version.py") -Pattern '__version__ = "(.+)"' | Select-Object -First 1
    if (-not $VersionLine) { throw "Cannot read __version__" }
    $Version = $VersionLine.Matches[0].Groups[1].Value
}

if (-not (Test-Path $ChangelogPath)) {
    Write-Output "## Friday $Version`n`nWindows AI desktop butler.`n`nDownload ``Friday-Windows.zip`` from attachments."
    exit 0
}

$data = Get-Content $ChangelogPath -Raw -Encoding UTF8 | ConvertFrom-Json
$entries = @($data.entries)
if (-not $entries.Count) {
    Write-Output "## Friday $Version`n`nWindows AI desktop butler."
    exit 0
}

function Format-Entry($entry) {
    $lines = @("## 星期五 v$($entry.version)")
    if ($entry.date) { $lines += "`n**发布日期：** $($entry.date)" }
    if ($entry.title) { $lines += "`n$($entry.title)" }
    foreach ($sec in @($entry.sections)) {
        if (-not $sec.items -or -not @($sec.items).Count) { continue }
        $lines += "`n### $($sec.label)"
        foreach ($item in @($sec.items)) {
            $lines += "- $item"
        }
    }
    return ($lines -join "`n")
}

if ($All) {
    $parts = @("# 星期五 更新日志")
    foreach ($entry in $entries) {
        $parts += ""
        $parts += (Format-Entry $entry)
    }
    Write-Output ($parts -join "`n")
    exit 0
}

$match = $entries | Where-Object { $_.version -eq $Version } | Select-Object -First 1
if (-not $match) {
    Write-Output @"
## 星期五 v$Version

Windows AI 电脑管家。

### 安装
1. 下载 ``Friday-Windows.zip``
2. 解压后运行 ``星期五.exe``
3. 详见压缩包内 ``安装教程.txt``
"@
    exit 0
}

$body = Format-Entry $match
$body += @"

### 安装
1. 下载 ``Friday-Windows.zip``
2. 解压后运行 ``星期五.exe``
3. 详见压缩包内 ``安装教程.txt``

---
Gitee: https://gitee.com/Bxxxboo/friday/releases
GitHub: https://github.com/Bxxxboo/Friday-Zero-barrier-DeepSeek-Agent-for-Windows/releases
"@
Write-Output $body
