param(
    [string]$RepoOwner = "Bxxxboo",
    [string]$RepoName = "Friday-Zero-barrier-DeepSeek-Agent-for-Windows",
    [string]$GitHubToken = $env:GITHUB_TOKEN,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $GitHubToken) {
    throw "Set GITHUB_TOKEN first. Create at https://github.com/settings/tokens (scope: repo)"
}

$VersionLine = Select-String -Path "friday\version.py" -Pattern '__version__ = "(.+)"' | Select-Object -First 1
if (-not $VersionLine) { throw "Cannot read version" }
$Version = $VersionLine.Matches[0].Groups[1].Value
$Tag = "v$Version"
$Repo = "$RepoOwner/$RepoName"

if (-not $SkipBuild) {
    powershell -ExecutionPolicy Bypass -File scripts\make-release.ps1
}

$Zip = Join-Path $PWD "release\Friday-Windows.zip"
if (-not (Test-Path $Zip)) { throw "release/Friday-Windows.zip not found" }

$ReleaseNotes = & (Join-Path $Root "scripts\release-notes.ps1") | Out-String
$ReleaseNotes = $ReleaseNotes.Trim()

$Headers = @{
    Authorization = "Bearer $GitHubToken"
    Accept = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}

$ReleaseId = $null
try {
    $existing = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/tags/$Tag" -Headers $Headers
    $ReleaseId = $existing.id
    Write-Host "GitHub release $Tag exists (id $ReleaseId)" -ForegroundColor Yellow
} catch {
    Write-Host "Creating GitHub release $Tag on $Repo ..." -ForegroundColor Cyan
    $Body = @{
        tag_name = $Tag
        name = "星期五 v$Version"
        body = $ReleaseNotes
    } | ConvertTo-Json
    $Release = Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$Repo/releases" -Headers $Headers -Body $Body -ContentType "application/json; charset=utf-8"
    $ReleaseId = $Release.id
}

Write-Host "Uploading Friday-Windows.zip to GitHub ..." -ForegroundColor Cyan
$UploadHeaders = @{
    Authorization = "Bearer $GitHubToken"
    Accept = "application/vnd.github+json"
    "Content-Type" = "application/zip"
}
$ZipBytes = [System.IO.File]::ReadAllBytes($Zip)
Invoke-RestMethod -Method Post -Uri "https://uploads.github.com/repos/$Repo/releases/$ReleaseId/assets?name=Friday-Windows.zip" -Headers $UploadHeaders -Body $ZipBytes | Out-Null

Write-Host ""
Write-Host "GitHub release done!" -ForegroundColor Green
Write-Host "  https://github.com/$Repo/releases/tag/$Tag"
