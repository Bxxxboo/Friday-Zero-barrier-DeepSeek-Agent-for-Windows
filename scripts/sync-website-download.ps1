# Sync website/download.json from friday/version.py (run after bump / before deploy)
param([string]$Root = "")

$ErrorActionPreference = "Stop"
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }
Set-Location $Root

. (Join-Path $PSScriptRoot "friday-dist.ps1")

$version = Get-FridayVersion -Root $Root
$tag = "v$version"
$giteeHome = "https://gitee.com/Bxxxboo/friday"
$setupName = "Friday-Setup-$version.exe"
$zipName = "Friday-Windows-$version.zip"

$date = (Get-Date -Format "yyyy-MM-dd")
$changelogPath = Join-Path $Root "assets\changelog.json"
if (Test-Path $changelogPath) {
    $entries = (Get-Content $changelogPath -Raw -Encoding UTF8 | ConvertFrom-Json).entries
    if ($entries -and $entries[0].date) { $date = $entries[0].date }
}

$payload = [ordered]@{
    version     = $version
    date        = $date
    tag         = $tag
    gitee_home  = $giteeHome
    releases_page = "$giteeHome/releases"
    download_url = "$giteeHome/releases/download/$tag/$zipName"
    zip_url     = "$giteeHome/releases/download/$tag/$zipName"
    setup_url   = "$giteeHome/releases/download/$tag/$setupName"
    setup_name  = $setupName
    zip_name    = $zipName
}

$outDir = Join-Path $Root "website"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$outFile = Join-Path $outDir "download.json"
$json = $payload | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText($outFile, $json + "`n", [System.Text.UTF8Encoding]::new($false))

$destChangelog = Join-Path $outDir "changelog.json"
Copy-Item -Path $changelogPath -Destination $destChangelog -Force

Write-Host "Synced website/download.json for v$version" -ForegroundColor Green
Write-Host "  $outFile"
